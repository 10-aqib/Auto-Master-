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
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, str_enum, utcnow
from webforge_api.models.enums import (
    ContactVerificationState,
    PlaceIdStatus,
    ProspectState,
    ProvenanceSource,
    QualificationOutcome,
    RecipientType,
)


class Prospect(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "prospects"

    business_name: Mapped[str] = mapped_column(String(300), nullable=False)
    # Not globally unique: branches of one business may share a site.
    verified_domain: Mapped[str | None] = mapped_column(String(253))
    # Location-specific path on the shared site ("" = the main site). Domain + branch_key
    # identifies a prospect; different branch keys stay separate prospects.
    branch_key: Mapped[str] = mapped_column(
        String(255), default="", server_default="", nullable=False
    )
    do_not_contact: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    website_url: Mapped[str | None] = mapped_column(String(2048))
    industry: Mapped[str | None] = mapped_column(String(120))
    business_type: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120))
    timezone: Mapped[str | None] = mapped_column(String(64))
    state: Mapped[ProspectState] = mapped_column(
        str_enum(ProspectState, "prospect_state"),
        default=ProspectState.DISCOVERED,
        server_default=ProspectState.DISCOVERED.value,
        nullable=False,
    )
    state_changed_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    qualification_score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    qualification_band: Mapped[str | None] = mapped_column(String(16))
    owner_notes: Mapped[str | None] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (
        CheckConstraint("country_code IS NULL OR country_code ~ '^[A-Z]{2}$'", name="country_iso"),
        CheckConstraint(
            "qualification_score IS NULL"
            " OR (qualification_score >= 0 AND qualification_score <= 100)",
            name="score_range",
        ),
        Index("ix_prospects_verified_domain", "verified_domain"),
        Index("ix_prospects_domain_branch", "verified_domain", "branch_key"),
        Index("ix_prospects_state_created_at", "state", "created_at"),
        Index("ix_prospects_country_state", "country_code", "state"),
    )


class ProspectCampaign(UUIDPrimaryKey, Base):
    __tablename__ = "prospect_campaigns"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    added_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("prospect_id", "campaign_id"),)


class ProspectSource(UUIDPrimaryKey, Base):
    """Field-level provenance. Never store restricted Google Maps Content here."""

    __tablename__ = "prospect_sources"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Restricted to independent sources: Maps content can never back a stored fact.
    source_type: Mapped[ProvenanceSource] = mapped_column(
        str_enum(ProvenanceSource, "provenance_source"), nullable=False
    )
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_key: Mapped[str | None] = mapped_column(
        ForeignKey("source_registrations.key", ondelete="RESTRICT")
    )
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_record_id: Mapped[str | None] = mapped_column(String(255))
    fact_field: Mapped[str] = mapped_column(String(64), nullable=False)
    safe_value: Mapped[str | None] = mapped_column(Text)
    value_hash: Mapped[str | None] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    terms_version: Mapped[str | None] = mapped_column(String(64))
    confidence: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    verification_method: Mapped[str] = mapped_column(String(64), nullable=False)
    is_independent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    evidence_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("safe_value IS NOT NULL OR value_hash IS NOT NULL", name="value_present"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
    )


class ExternalPlaceIdentifier(UUIDPrimaryKey, Base):
    """Provider Place ID only (Google permits storing Place IDs indefinitely).

    Confirm current policy before adding any field. No names, addresses, phones, ratings,
    reviews, photos or website URLs from Maps are ever stored here.
    """

    __tablename__ = "external_place_identifiers"

    # Null while the place is only a candidate (not yet independently verified).
    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    place_id: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[PlaceIdStatus] = mapped_column(
        str_enum(PlaceIdStatus, "place_id_status"),
        default=PlaceIdStatus.ACTIVE,
        server_default=PlaceIdStatus.ACTIVE.value,
        nullable=False,
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(UTCDateTime())

    __table_args__ = (UniqueConstraint("provider", "place_id"),)


class EmailContact(UUIDPrimaryKey, Timestamps, Base):
    """Encrypted contact address. Inferred consent is never stored here."""

    __tablename__ = "email_contacts"

    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prospects.id", ondelete="SET NULL"), index=True
    )
    email_encrypted: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    email_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(200))
    recipient_type: Mapped[RecipientType] = mapped_column(
        str_enum(RecipientType, "recipient_type"),
        default=RecipientType.UNKNOWN,
        server_default=RecipientType.UNKNOWN.value,
        nullable=False,
    )
    role_function: Mapped[str | None] = mapped_column(String(120))
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_retrieved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    country_code: Mapped[str | None] = mapped_column(String(2))
    verification_state: Mapped[ContactVerificationState] = mapped_column(
        str_enum(ContactVerificationState, "contact_verification_state"),
        default=ContactVerificationState.UNVERIFIED,
        server_default=ContactVerificationState.UNVERIFIED.value,
        nullable=False,
    )
    verification_method: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (UniqueConstraint("prospect_id", "email_hash"),)


class QualificationResult(UUIDPrimaryKey, Base):
    """One evidence-based scoring run. Unknown components stay null and do not score."""

    __tablename__ = "qualification_results"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL")
    )
    rubric_version: Mapped[str] = mapped_column(String(16), nullable=False)
    outcome: Mapped[QualificationOutcome] = mapped_column(
        str_enum(QualificationOutcome, "qualification_outcome"), nullable=False
    )
    score: Mapped[float | None] = mapped_column(Numeric(5, 2))
    evidence_coverage: Mapped[float] = mapped_column(Numeric(4, 3), nullable=False)
    components: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    reason_codes: Mapped[list[str]] = mapped_column(
        ARRAY(String(64)), default=list, server_default="{}", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )


class ProspectMerge(UUIDPrimaryKey, Base):
    """Merge history: the merged prospect is kept (state MERGED) and pointed at the survivor."""

    __tablename__ = "prospect_merges"

    from_prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    into_prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    merged_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    merged_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("from_prospect_id <> into_prospect_id", name="distinct_prospects"),
    )
