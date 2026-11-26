from __future__ import annotations

import uuid
from datetime import datetime

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
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, str_enum, utcnow
from webforge_api.models.enums import ContactVerificationState, ProspectState, RecipientType


class Prospect(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "prospects"

    business_name: Mapped[str] = mapped_column(String(300), nullable=False)
    # Not globally unique: branches of one business may share a site.
    verified_domain: Mapped[str | None] = mapped_column(String(253))
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
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source_record_id: Mapped[str | None] = mapped_column(String(255))
    fact_field: Mapped[str] = mapped_column(String(64), nullable=False)
    safe_value: Mapped[str | None] = mapped_column(Text)
    value_hash: Mapped[str | None] = mapped_column(String(64))
    retrieved_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    observed_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    terms_version: Mapped[str | None] = mapped_column(String(64))
    is_independent: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    evidence_note: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (
        CheckConstraint("safe_value IS NOT NULL OR value_hash IS NOT NULL", name="value_present"),
    )


class ExternalPlaceIdentifier(UUIDPrimaryKey, Base):
    """Provider Place ID only. Confirm current policy before adding any field."""

    __tablename__ = "external_place_identifiers"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    place_id: Mapped[str] = mapped_column(String(255), nullable=False)
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
