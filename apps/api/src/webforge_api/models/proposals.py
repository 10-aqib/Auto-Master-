from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, str_enum
from webforge_api.models.enums import PreviewStatus, ProposalStatus


class Proposal(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "proposals"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    design_project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_projects.id", ondelete="RESTRICT"), nullable=False
    )
    pdf_storage_key: Mapped[str | None] = mapped_column(String(512))
    proposal_version: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    template_version: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[ProposalStatus] = mapped_column(
        str_enum(ProposalStatus, "proposal_status"),
        default=ProposalStatus.DRAFT,
        server_default=ProposalStatus.DRAFT.value,
        nullable=False,
    )
    generated_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class PreviewDeployment(UUIDPrimaryKey, Base):
    """Only the hash of the preview token is stored, never the raw token."""

    __tablename__ = "preview_deployments"

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("proposals.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    route: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[PreviewStatus] = mapped_column(
        str_enum(PreviewStatus, "preview_status"),
        default=PreviewStatus.ACTIVE,
        server_default=PreviewStatus.ACTIVE.value,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    access_count: Mapped[int] = mapped_column(
        BigInteger, default=0, server_default="0", nullable=False
    )

    __table_args__ = (Index("ix_preview_deployments_status_expires", "status", "expires_at"),)
