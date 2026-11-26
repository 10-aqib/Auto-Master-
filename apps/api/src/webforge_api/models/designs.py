from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, str_enum
from webforge_api.models.enums import RunStatus


class DesignProject(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "design_projects"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    audit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("website_audits.id", ondelete="SET NULL")
    )
    status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "design_status"),
        default=RunStatus.PENDING,
        server_default=RunStatus.PENDING.value,
        nullable=False,
    )
    brief: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    brief_schema_version: Mapped[str | None] = mapped_column(String(32))
    design_tokens: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    page_plan: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    model: Mapped[str | None] = mapped_column(String(100))
    prompt_version: Mapped[str | None] = mapped_column(String(32))
    renderer_version: Mapped[str | None] = mapped_column(String(32))
    current_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )


class DesignPage(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "design_pages"

    design_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_projects.id", ondelete="CASCADE"), nullable=False
    )
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    page_type: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    render_status: Mapped[RunStatus] = mapped_column(
        str_enum(RunStatus, "render_status"),
        default=RunStatus.PENDING,
        server_default=RunStatus.PENDING.value,
        nullable=False,
    )
    screenshot_key: Mapped[str | None] = mapped_column(String(512))
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    __table_args__ = (UniqueConstraint("design_project_id", "slug", "version"),)


class Asset(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "assets"

    storage_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    asset_type: Mapped[str] = mapped_column(String(32), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    provider: Mapped[str | None] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    license_id: Mapped[str | None] = mapped_column(String(64))
    license_url: Mapped[str | None] = mapped_column(String(2048))
    attribution_required: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False
    )
    attribution_text: Mapped[str | None] = mapped_column(Text)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class DesignBrief(UUIDPrimaryKey, Base):
    """One generated brief version. Regeneration adds a version; older versions are kept."""

    __tablename__ = "design_briefs"

    design_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # DRAFT -> APPROVED | REJECTED; NEEDS_REVIEW when validation failed after repairs.
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    brief: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    raw_output_sha256: Mapped[str | None] = mapped_column(String(64))
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    facts_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    validation_issues: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    input_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    output_tokens: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    cost_milliminor: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    __table_args__ = (
        UniqueConstraint("design_project_id", "version"),
        CheckConstraint(
            "status IN ('DRAFT', 'APPROVED', 'REJECTED', 'NEEDS_REVIEW')", name="brief_status"
        ),
    )


class DesignRender(UUIDPrimaryKey, Base):
    """One deterministic render of an approved brief into six static pages."""

    __tablename__ = "design_renders"

    design_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    brief_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_briefs.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    renderer_version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        default=False, server_default=text("false"), nullable=False
    )
    variant: Mapped[str] = mapped_column(String(32), nullable=False)
    manifest: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    scan_issues: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    __table_args__ = (
        UniqueConstraint("design_project_id", "version"),
        CheckConstraint(
            "status IN ('RENDERED','APPROVED','REJECTED','FAILED')", name="design_render_status"
        ),
        Index(
            "uq_design_renders_one_active",
            "design_project_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )


class DesignValidation(UUIDPrimaryKey, Base):
    """Offline browser validation of one render: report, evidence and screenshots."""

    __tablename__ = "design_validations"

    render_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_renders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    validator_version: Mapped[str] = mapped_column(String(32), nullable=False)
    browser_version: Mapped[str | None] = mapped_column(String(64))
    site_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    report: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    screenshots: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('READY','NEEDS_REVISION')", name="design_validation_status"),
    )
