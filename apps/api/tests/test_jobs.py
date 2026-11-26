"""Durable job queue: idempotency, leases, retries, dead-letter, deferral and concurrency."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import select

from tests.conftest import Harness
from webforge_api.models import Job
from webforge_api.models.enums import JobStatus
from webforge_api.services import jobs as q
from webforge_api.services.job_handlers import JobDeferred
from webforge_api.worker import Runtime, drain, run_once

SPEC = q.JobSpec("test.echo", "testq", max_attempts=2)


def _enqueue(h: Harness, key: str = "k1") -> Job:
    with h.db() as db:
        job, _created = q.enqueue(db, SPEC, idempotency_key=key, payload={"n": 1}, now=h.clock())
        db.commit()
        db.expunge(job)
    return job


def test_enqueue_is_idempotent(harness: Harness) -> None:
    a = _enqueue(harness)
    with harness.db() as db:
        b, created = q.enqueue(
            db, SPEC, idempotency_key="k1", payload={"n": 2}, now=harness.clock()
        )
        db.commit()
        assert not created and b.id == a.id and b.payload == {"n": 1}
        assert len(db.scalars(select(Job)).all()) == 1


def test_enqueue_rolls_back_with_caller_transaction(harness: Harness) -> None:
    with harness.db() as db:
        q.enqueue(db, SPEC, idempotency_key="lost", payload={}, now=harness.clock())
        db.rollback()  # the business change failed: the job must not exist either
        assert db.scalars(select(Job)).first() is None


def test_retry_backoff_then_dead_letter(harness: Harness) -> None:
    _enqueue(harness)
    now = harness.clock()
    with harness.db() as db:
        job = q.claim(db, ["testq"], now)
        assert job is not None and job.attempts == 1 and job.status is JobStatus.RUNNING
        q.fail(db, job, now, q.JobError("flaky", "x", retryable=True))
        assert job.status.value == "RETRYING" and job.available_at == now + timedelta(seconds=30)
        assert q.claim(db, ["testq"], now) is None  # not yet due
        later = now + timedelta(seconds=31)
        job = q.claim(db, ["testq"], later)
        assert job is not None and job.attempts == 2
        q.fail(db, job, later, q.JobError("flaky", "x", retryable=True))
        assert job.status.value == "DEAD"


def test_non_retryable_fails_and_manual_retry(harness: Harness) -> None:
    _enqueue(harness)
    now = harness.clock()
    with harness.db() as db:
        job = q.claim(db, ["testq"], now)
        assert job is not None
        q.fail(db, job, now, q.JobError("bad_input", "x"))
        assert job.status is JobStatus.FAILED
        retried = q.manual_retry(db, job.id, now, non_idempotent=frozenset())
        assert retried.status is JobStatus.QUEUED and retried.max_attempts == 2


def test_non_idempotent_jobs_need_reconciliation(harness: Harness) -> None:
    import pytest

    from webforge_api.services.errors import ConflictError

    with harness.db() as db:
        job, _ = q.enqueue(
            db,
            q.JobSpec("outreach.send", "outreach"),
            idempotency_key="s1",
            payload={},
            now=harness.clock(),
        )
        job.status = JobStatus.FAILED
        db.commit()
        with pytest.raises(ConflictError, match="reconcile"):
            q.manual_retry(db, job.id, harness.clock(), non_idempotent=frozenset({"outreach.send"}))


def test_expired_lease_is_reclaimed(harness: Harness) -> None:
    _enqueue(harness)
    now = harness.clock()
    with harness.db() as db:
        first = q.claim(db, ["testq"], now, lease_seconds=60)
        assert first is not None
        assert q.claim(db, ["testq"], now + timedelta(seconds=30)) is None  # lease still held
        again = q.claim(db, ["testq"], now + timedelta(seconds=61))  # worker crashed
        assert again is not None and again.id == first.id and again.attempts == 2


def test_skip_locked_gives_concurrent_workers_different_jobs(harness: Harness) -> None:
    _enqueue(harness, "a")
    _enqueue(harness, "b")
    now = harness.clock()
    s1, s2 = harness.db(), harness.db()
    try:
        from sqlalchemy import select as sel

        row1 = s1.scalars(
            sel(Job).where(Job.queue == "testq").with_for_update(skip_locked=True).limit(1)
        ).first()
        j2 = q.claim(s2, ["testq"], now)
        assert row1 is not None and j2 is not None and row1.id != j2.id
    finally:
        s1.rollback()
        s1.close()
        s2.close()


def test_cancel_only_pending(harness: Harness) -> None:
    job = _enqueue(harness)
    with harness.db() as db:
        assert q.cancel(db, job.id, harness.clock()).status is JobStatus.CANCELLED


def _runtime(h: Harness, handlers: dict[str, Any]) -> Runtime:
    from webforge_api.security.rate_limit import MemoryRateLimiter

    return Runtime(h.settings, limiter=MemoryRateLimiter(), clock=h.clock, handlers=handlers)


def test_worker_runs_defers_and_crash_handling(harness: Harness) -> None:
    calls: list[str] = []

    def ok(_ctx: Any, job: Job) -> dict[str, Any]:
        calls.append(job.idempotency_key)
        return {"done": True}

    def paused(_ctx: Any, _job: Job) -> None:
        raise JobDeferred("system paused", 120)

    def boom(_ctx: Any, _job: Job) -> None:
        raise RuntimeError("secret detail password=hunter2")

    rt = _runtime(harness, {"t.ok": ok, "t.paused": paused, "t.boom": boom})
    try:
        with harness.db() as db:
            for t in ("t.ok", "t.paused", "t.boom"):
                q.enqueue(db, q.JobSpec(t, "w"), idempotency_key=t, payload={}, now=harness.clock())
            db.commit()
        assert drain(rt, ["w"]) == 3
        with harness.db() as db:
            jobs = {j.job_type: j for j in db.scalars(select(Job))}
        assert jobs["t.ok"].status is JobStatus.SUCCEEDED and jobs["t.ok"].result == {"done": True}
        assert jobs["t.paused"].status is JobStatus.QUEUED and jobs["t.paused"].attempts == 0
        assert jobs["t.paused"].available_at == harness.clock() + timedelta(seconds=120)
        assert (
            jobs["t.boom"].status is JobStatus.RETRYING
            and jobs["t.boom"].error_code == "internal_error"
        )
        assert "hunter2" not in (jobs["t.boom"].error_message or "")
        assert run_once(rt, ["w"]) is None
    finally:
        rt.close()
