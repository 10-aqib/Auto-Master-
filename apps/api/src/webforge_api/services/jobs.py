"""Durable PostgreSQL job queue.

- `enqueue` inserts a job in the CALLER's transaction, so a state change and the job that follows
  from it commit together (transactional outbox without a separate relay).
- Idempotency keys are unique: enqueueing the same logical work twice returns the existing job.
- Workers claim with `FOR UPDATE SKIP LOCKED` and a lease; a crashed worker's job becomes claimable
  again when its lease expires.
- Retryable failures back off exponentially; exhausted retries go to DEAD (dead-letter).
  Non-retryable failures go to FAILED. Both are visible and can be retried manually.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from webforge_api.models import Job
from webforge_api.models.enums import JobStatus
from webforge_api.services.errors import ConflictError, NotFoundError

BACKOFF_BASE_SECONDS = 30
BACKOFF_MAX_SECONDS = 3600
DEFAULT_LEASE_SECONDS = 300
ACTIVE_STATES = (JobStatus.QUEUED, JobStatus.RETRYING, JobStatus.RUNNING)


class JobError(Exception):
    """Raise from a handler to fail a job with a stable code."""

    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class JobCancelled(JobError):  # noqa: N818 - control-flow signal, not an error
    def __init__(self, reason: str) -> None:
        super().__init__("cancelled", reason, retryable=False)


@dataclass(frozen=True)
class JobSpec:
    job_type: str
    queue: str
    max_attempts: int = 3
    schema_version: str = "1"


def enqueue(
    db: Session,
    spec: JobSpec,
    *,
    idempotency_key: str,
    payload: dict[str, Any],
    now: datetime,
    entity_type: str | None = None,
    entity_id: str | uuid.UUID | None = None,
    correlation_id: str | None = None,
    available_at: datetime | None = None,
    created_by_user_id: uuid.UUID | None = None,
) -> tuple[Job, bool]:
    """Add a job to the current transaction. Returns (job, created)."""
    stmt = (
        insert(Job)
        .values(
            job_type=spec.job_type,
            payload_schema_version=spec.schema_version,
            payload=payload,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            queue=spec.queue,
            idempotency_key=idempotency_key[:128],
            max_attempts=spec.max_attempts,
            available_at=available_at or now,
            correlation_id=correlation_id,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
        .returning(Job.id)
    )
    new_id = db.execute(stmt).scalar_one_or_none()
    if new_id is not None:
        job = db.get(Job, new_id)
        assert job is not None  # noqa: S101 - just inserted
        return job, True
    existing = db.scalars(select(Job).where(Job.idempotency_key == idempotency_key[:128])).one()
    return existing, False


def claim(
    db: Session,
    queues: list[str],
    now: datetime,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
) -> Job | None:
    """Claim the next runnable job (commits)."""
    stmt = (
        select(Job)
        .where(
            Job.queue.in_(queues),
            or_(
                (Job.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]))
                & (Job.available_at <= now),
                # Crash recovery: the previous worker's lease ran out.
                (Job.status == JobStatus.RUNNING) & (Job.lease_expires_at < now),
            ),
        )
        .order_by(Job.available_at, Job.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    job = db.scalars(stmt).first()
    if job is None:
        db.commit()
        return None
    job.status = JobStatus.RUNNING
    job.attempts += 1
    job.started_at = now
    job.heartbeat_at = now
    job.lease_expires_at = now + timedelta(seconds=lease_seconds)
    job.error_code = None
    job.error_message = None
    db.commit()
    return job


def complete(db: Session, job: Job, now: datetime, result: dict[str, Any] | None = None) -> None:
    job.status = JobStatus.SUCCEEDED
    job.finished_at = now
    job.lease_expires_at = None
    job.result = result
    db.commit()


def fail(db: Session, job: Job, now: datetime, error: JobError) -> None:
    job.error_code = error.code[:64]
    job.error_message = str(error)[:1000]
    job.lease_expires_at = None
    if isinstance(error, JobCancelled):
        job.status = JobStatus.CANCELLED
        job.finished_at = now
    elif error.retryable and job.attempts < job.max_attempts:
        delay = min(BACKOFF_BASE_SECONDS * 2 ** (job.attempts - 1), BACKOFF_MAX_SECONDS)
        job.status = JobStatus.RETRYING
        job.available_at = now + timedelta(seconds=delay)
    elif error.retryable:
        job.status = JobStatus.DEAD  # retries exhausted: dead-letter
        job.finished_at = now
    else:
        job.status = JobStatus.FAILED
        job.finished_at = now
    db.commit()


def manual_retry(
    db: Session, job_id: uuid.UUID, now: datetime, *, non_idempotent: frozenset[str]
) -> Job:
    job = db.get(Job, job_id, with_for_update=True)
    if job is None:
        raise NotFoundError("not_found", "Job not found.")
    if job.status not in (JobStatus.FAILED, JobStatus.DEAD, JobStatus.CANCELLED):
        raise ConflictError("not_retryable", "Only failed, dead or cancelled jobs can be retried.")
    if job.job_type in non_idempotent:
        raise ConflictError(
            "reconcile_first", "This job type is not idempotent; reconcile with the provider first."
        )
    job.status = JobStatus.QUEUED
    job.available_at = now
    job.max_attempts = job.attempts + 1  # one more attempt per manual retry
    job.finished_at = None
    db.commit()
    return job


def cancel(db: Session, job_id: uuid.UUID, now: datetime) -> Job:
    job = db.get(Job, job_id, with_for_update=True)
    if job is None:
        raise NotFoundError("not_found", "Job not found.")
    if job.status not in (JobStatus.QUEUED, JobStatus.RETRYING):
        raise ConflictError("not_cancellable", "Only queued or retrying jobs can be cancelled.")
    job.status = JobStatus.CANCELLED
    job.finished_at = now
    job.error_code = "cancelled"
    job.error_message = "Cancelled by a user."
    db.commit()
    return job


Handler = Callable[[Any, Job], dict[str, Any] | None]
