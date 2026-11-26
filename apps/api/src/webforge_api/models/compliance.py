from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, str_enum, utcnow
from webforge_api.models.enums import (
    ComplianceDecision,
    PolicyStatus,
    RecipientType,
    SuppressionReason,
    SuppressionScope,
)


class PolicyConfig(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "policy_configs"

    country_code: Mapped[str] = mapped_column(String(2), nullable=False)
    recipient_type: Mapped[RecipientType] = mapped_column(
        str_enum(RecipientType, "policy_recipient_type"), nullable=False
    )
    message_category: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[PolicyStatus] = mapped_column(
        str_enum(PolicyStatus, "policy_status"),
        default=PolicyStatus.DRAFT,
        server_default=PolicyStatus.DRAFT.value,
        nullable=False,
    )
    rules: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default="{}", nullable=False
    )
    reviewer_name: Mapped[str | None] = mapped_column(String(200))
    reviewer_qualification: Mapped[str | None] = mapped_column(String(200))
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    effective_from: Mapped[date | None] = mapped_column(Date)
    effective_to: Mapped[date | None] = mapped_column(Date)
    source_references: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}", nullable=False
    )

    __table_args__ = (
        UniqueConstraint("country_code", "recipient_type", "message_category", "version"),
        # A policy cannot be ACTIVE without a documented qualified legal review.
        CheckConstraint(
            "status <> 'ACTIVE' OR (reviewer_name IS NOT NULL"
            " AND reviewer_qualification IS NOT NULL"
            " AND reviewed_at IS NOT NULL AND effective_from IS NOT NULL"
            " AND cardinality(source_references) > 0)",
            name="active_requires_review",
        ),
        Index(
            "uq_policy_configs_one_active",
            "country_code",
            "recipient_type",
            "message_category",
            unique=True,
            postgresql_where="status = 'ACTIVE'",
        ),
    )


class ComplianceAssessment(UUIDPrimaryKey, Base):
    __tablename__ = "compliance_assessments"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    email_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("email_contacts.id", ondelete="SET NULL"), index=True
    )
    country_code: Mapped[str | None] = mapped_column(String(2))
    recipient_type: Mapped[RecipientType] = mapped_column(
        str_enum(RecipientType, "assessment_recipient_type"), nullable=False
    )
    message_category: Mapped[str] = mapped_column(String(64), nullable=False)
    legal_basis: Mapped[str | None] = mapped_column(String(64))
    legal_basis_evidence: Mapped[str | None] = mapped_column(Text)
    policy_config_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("policy_configs.id", ondelete="RESTRICT")
    )
    policy_version: Mapped[str | None] = mapped_column(String(32))
    provider_policy_version: Mapped[str | None] = mapped_column(String(32))
    decision: Mapped[ComplianceDecision] = mapped_column(
        str_enum(ComplianceDecision, "compliance_decision"), nullable=False
    )
    reason_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}", nullable=False
    )
    reviewer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    assessed_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class ConsentRecord(UUIDPrimaryKey, Base):
    """Only for consent that actually exists and is relevant; never inferred."""

    __tablename__ = "consent_records"

    email_contact_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("email_contacts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    consent_type: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    captured_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    withdrawn_at: Mapped[datetime | None] = mapped_column(UTCDateTime())


class Suppression(UUIDPrimaryKey, Base):
    """Keyed hash only, no FK to contacts: survives prospect/contact deletion by design."""

    __tablename__ = "suppressions"

    email_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[SuppressionScope] = mapped_column(
        str_enum(SuppressionScope, "suppression_scope"),
        default=SuppressionScope.GLOBAL,
        server_default=SuppressionScope.GLOBAL.value,
        nullable=False,
    )
    # Campaign scope key; '' for GLOBAL so the unique constraint covers both scopes.
    scope_ref: Mapped[str] = mapped_column(
        String(64), default="", server_default="", nullable=False
    )
    reason: Mapped[SuppressionReason] = mapped_column(
        str_enum(SuppressionReason, "suppression_reason"), nullable=False
    )
    source_event: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT")
    )

    __table_args__ = (
        UniqueConstraint("email_hash", "scope", "scope_ref"),
        CheckConstraint("(scope = 'GLOBAL') = (scope_ref = '')", name="scope_ref_matches_scope"),
    )
