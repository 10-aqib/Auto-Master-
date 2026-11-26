"""Source terms/permission registry, domain verification evidence and transient cache."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, str_enum
from webforge_api.models.enums import DomainVerificationStatus, SourceStatus, SourceType


class SourceRegistration(UUIDPrimaryKey, Timestamps, Base):
    """One row per connector. Connectors without a recorded terms review stay disabled."""

    __tablename__ = "source_registrations"

    key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(
        str_enum(SourceType, "source_type"), nullable=False
    )
    status: Mapped[SourceStatus] = mapped_column(
        str_enum(SourceStatus, "source_status"),
        default=SourceStatus.DISABLED,
        server_default=SourceStatus.DISABLED.value,
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    # Fields that may be persisted from this source (everything else is transient).
    persistable_fields: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}", nullable=False
    )
    # field -> maximum cache seconds (absent = must not be cached at all).
    cache_rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    attribution_required: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    attribution_text: Mapped[str | None] = mapped_column(String(120))
    policy_urls: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}", nullable=False
    )
    terms_url: Mapped[str | None] = mapped_column(String(2048))
    terms_version: Mapped[str | None] = mapped_column(String(64))
    terms_reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    review_notes: Mapped[str | None] = mapped_column(Text)
    status_changed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    status_changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    status_reason: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        CheckConstraint(
            "status <> 'ENABLED' OR source_type = 'MOCK' OR (terms_url IS NOT NULL"
            " AND terms_version IS NOT NULL AND terms_reviewed_at IS NOT NULL"
            " AND reviewed_by_user_id IS NOT NULL)",
            name="enabled_requires_terms_review",
        ),
    )


class DomainVerification(UUIDPrimaryKey, Base):
    """Evidence that a website belongs to a business. Never derived from guessing."""

    __tablename__ = "domain_verifications"

    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    place_identifier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("external_place_identifiers.id", ondelete="SET NULL"), index=True
    )
    candidate_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    final_url: Mapped[str | None] = mapped_column(String(2048))
    domain: Mapped[str | None] = mapped_column(String(253), index=True)
    # Where the candidate URL came from, e.g. "google_places:websiteUri (transient)" or "owner".
    candidate_origin: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[DomainVerificationStatus] = mapped_column(
        str_enum(DomainVerificationStatus, "domain_verification_status"), nullable=False
    )
    method: Mapped[str] = mapped_column(String(64), nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}", nullable=False
    )
    confidence: Mapped[float | None] = mapped_column(Numeric(4, 3))
    evidence: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    checked_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    checked_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"
        ),
    )


class TransientSourceValue(UUIDPrimaryKey, Base):
    """Short-lived cache of third-party values, only where the source registry permits it."""

    __tablename__ = "transient_source_values"

    source_key: Mapped[str] = mapped_column(
        ForeignKey("source_registrations.key", ondelete="CASCADE"), nullable=False
    )
    external_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    value_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)

    __table_args__ = (
        UniqueConstraint("source_key", "external_ref", "field"),
        CheckConstraint("expires_at > fetched_at", name="expiry_after_fetch"),
        Index("ix_transient_source_values_expires_at", "expires_at"),
    )
