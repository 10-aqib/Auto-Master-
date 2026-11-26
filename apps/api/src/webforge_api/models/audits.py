from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, str_enum
from webforge_api.models.enums import RunStatus, Severity


class WebsiteAudit(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "website_audits"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "audit_status"),
        default=RunStatus.PENDING,
        server_default=RunStatus.PENDING.value,
        nullable=False,
    )
    audit_version: Mapped[str] = mapped_column(String(32), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    desktop_screenshot_key: Mapped[str | None] = mapped_column(String(512))
    mobile_screenshot_key: Mapped[str | None] = mapped_column(String(512))
    performance_source: Mapped[str | None] = mapped_column(String(64))
    scores: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    browser_version: Mapped[str | None] = mapped_column(String(64))
    error_summary: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_website_audits_status_created_at", "status", "created_at"),)


class AuditFinding(UUIDPrimaryKey, Base):
    __tablename__ = "audit_findings"

    audit_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("website_audits.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "severity"), nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_url: Mapped[str | None] = mapped_column(String(2048))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    screenshot_key: Mapped[str | None] = mapped_column(String(512))
    viewport: Mapped[str | None] = mapped_column(String(32))
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    reproduction_steps: Mapped[str | None] = mapped_column(Text)
