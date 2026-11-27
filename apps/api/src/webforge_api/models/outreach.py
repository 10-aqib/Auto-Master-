from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from webforge_api.db.base import Base, Timestamps, UTCDateTime, UUIDPrimaryKey, str_enum
from webforge_api.models.enums import EventProcessingState, MessageStatus


class OutreachMessage(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "outreach_messages"

    prospect_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("prospects.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    email_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("email_contacts.id", ondelete="SET NULL")
    )
    proposal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("proposals.id", ondelete="RESTRICT")
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="RESTRICT")
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(255))
    message_category: Mapped[str] = mapped_column(String(64), nullable=False)
    subject_version: Mapped[str | None] = mapped_column(String(32))
    body_version: Mapped[str | None] = mapped_column(String(32))
    body_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    body_storage_key: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[MessageStatus] = mapped_column(
        str_enum(MessageStatus, "message_status"),
        default=MessageStatus.DRAFT,
        server_default=MessageStatus.DRAFT.value,
        nullable=False,
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0", nullable=False
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    accepted_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    sent_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    last_event_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    compliance_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("compliance_assessments.id", ondelete="RESTRICT")
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(64))
    # Phase 09
    subject: Mapped[str | None] = mapped_column(Text)
    recipient_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    unsubscribe_token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    preview_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("preview_deployments.id", ondelete="SET NULL")
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    cancelled_reason: Mapped[str | None] = mapped_column(String(64))

    __table_args__ = (
        UniqueConstraint("provider", "provider_message_id"),
        Index("ix_outreach_messages_status_created_at", "status", "created_at"),
    )


class EmailEvent(UUIDPrimaryKey, Base):
    __tablename__ = "email_events"

    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_event_id: Mapped[str] = mapped_column(String(255), nullable=False)
    outreach_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outreach_messages.id", ondelete="RESTRICT"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    event_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    processing_state: Mapped[EventProcessingState] = mapped_column(
        str_enum(EventProcessingState, "event_processing_state"),
        default=EventProcessingState.RECEIVED,
        server_default=EventProcessingState.RECEIVED.value,
        nullable=False,
    )

    __table_args__ = (UniqueConstraint("provider", "provider_event_id"),)


class Reply(UUIDPrimaryKey, Base):
    __tablename__ = "replies"

    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("prospects.id", ondelete="RESTRICT"), index=True
    )
    email_contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("email_contacts.id", ondelete="SET NULL")
    )
    outreach_message_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("outreach_messages.id", ondelete="RESTRICT")
    )
    provider_thread_id: Mapped[str | None] = mapped_column(String(255))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    classification: Mapped[str | None] = mapped_column(String(32))
    summary: Mapped[str | None] = mapped_column(Text)
    body_storage_key: Mapped[str | None] = mapped_column(String(512))
    needs_human_review: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    handled_at: Mapped[datetime | None] = mapped_column(UTCDateTime())
    # Phase 09
    provider: Mapped[str | None] = mapped_column(String(32))
    provider_event_id: Mapped[str | None] = mapped_column(String(255))
    from_hash: Mapped[str | None] = mapped_column(String(64))
    body_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary)
    subject: Mapped[str | None] = mapped_column(Text)
    handled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    __table_args__ = (UniqueConstraint("provider", "provider_event_id"),)
