from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, str_enum, utcnow
from webforge_api.models.enums import JobStatus, UsageOutcome


class Job(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "jobs"

    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    entity_type: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[JobStatus] = mapped_column(
        str_enum(JobStatus, "job_status"),
        default=JobStatus.QUEUED,
        server_default=JobStatus.QUEUED.value,
        nullable=False,
    )
    queue: Mapped[str] = mapped_column(String(32), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=3, server_default="3", nullable=False
    )
    available_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    heartbeat_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    lease_expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    correlation_id: Mapped[str | None] = mapped_column(String(128), index=True)

    __table_args__ = (
        CheckConstraint("attempts >= 0 AND max_attempts > 0", name="attempts_valid"),
        Index("ix_jobs_status_created_at", "status", "created_at"),
        Index("ix_jobs_queue_status_available", "queue", "status", "available_at"),
    )


class ApiUsage(UUIDPrimaryKey, Base):
    __tablename__ = "api_usage"

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    job_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("jobs.id", ondelete="SET NULL"))
    units: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    output_tokens: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    sku: Mapped[str | None] = mapped_column(String(64))
    outcome: Mapped[UsageOutcome] = mapped_column(
        str_enum(UsageOutcome, "usage_outcome"),
        default=UsageOutcome.SUCCESS,
        server_default=UsageOutcome.SUCCESS.value,
        nullable=False,
    )
    # Cost in thousandths of a minor unit (precise for per-1000 pricing).
    cost_milliminor: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    estimated_cost_minor: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", server_default="USD", nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    provider_request_id: Mapped[str | None] = mapped_column(String(255))

    __table_args__ = (Index("ix_api_usage_provider_occurred_at", "provider", "occurred_at"),)
