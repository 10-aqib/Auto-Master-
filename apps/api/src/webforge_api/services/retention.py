"""Retention and deletion interfaces.

Suppression records are deliberately independent of contacts and prospects (keyed email hash,
no foreign key), so deleting personal data never removes the record that prevents re-contact.
Activity logs are append-only and are not deleted by these interfaces.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import delete, exists, or_, select
from sqlalchemy.orm import Session

from webforge_api.models import (
    ComplianceAssessment,
    DesignProject,
    EmailContact,
    OutreachMessage,
    Proposal,
    Prospect,
    Reply,
    UserSession,
    WebsiteAudit,
)
from webforge_api.security.crypto import Crypto
from webforge_api.services import activity
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import ConflictError, NotFoundError


@dataclass(frozen=True)
class RetentionRule:
    data_type: str
    default_days: int | None  # None = retained until a documented review decides otherwise
    note: str


# Defaults pending counsel review (see docs/compliance/retention.md).
RETENTION_RULES: tuple[RetentionRule, ...] = (
    RetentionRule("user_sessions", 30, "Revoked/expired sessions purged after 30 days."),
    RetentionRule("activity_logs", None, "Append-only; archival policy decided in Phase 11."),
    RetentionRule("suppressions", None, "Kept while needed to prevent re-contact."),
    RetentionRule("email_contacts", None, "Deleted on request or when the prospect is erased."),
    RetentionRule("artifacts", 90, "ARTIFACT_RETENTION_DAYS (Phase 04+)."),
    RetentionRule("previews", 30, "PREVIEW_RETENTION_DAYS (Phase 08)."),
)


def purge_expired_sessions(db: Session, *, now: datetime, keep_days: int = 30) -> int:
    cutoff = now - timedelta(days=keep_days)
    result = db.execute(
        delete(UserSession).where(
            or_(
                UserSession.revoked_at < cutoff,
                UserSession.absolute_expires_at < cutoff,
                UserSession.refresh_expires_at < cutoff,
            )
        )
    )
    db.commit()
    return int(getattr(result, "rowcount", 0) or 0)


def delete_email_contact(
    db: Session,
    crypto: Crypto,
    *,
    contact_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    meta: RequestMeta | None = None,
) -> None:
    """Delete a contact and its consent records. Suppressions are untouched."""
    contact = db.get(EmailContact, contact_id)
    if contact is None:
        raise NotFoundError("not_found", "Contact not found.")
    db.delete(contact)
    activity.record(
        db,
        crypto,
        action="retention.contact_deleted",
        actor_user_id=actor_user_id,
        meta=meta,
        entity_type="email_contact",
        entity_id=contact_id,
        system=actor_user_id is None,
    )
    db.commit()


_HISTORY_TABLES = (
    WebsiteAudit,
    DesignProject,
    Proposal,
    ComplianceAssessment,
    OutreachMessage,
    Reply,
)


def erase_prospect(
    db: Session,
    crypto: Crypto,
    *,
    prospect_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    meta: RequestMeta | None = None,
) -> None:
    """Erase a prospect with its sources, identifiers, links and contacts.

    Refused while audit/design/proposal/compliance/outreach/reply history exists, so evidence
    is never silently lost; that history must be handled through its own retention path.
    """
    prospect = db.get(Prospect, prospect_id)
    if prospect is None:
        raise NotFoundError("not_found", "Prospect not found.")
    for model in _HISTORY_TABLES:
        if db.scalar(select(exists().where(model.prospect_id == prospect_id))):
            raise ConflictError(
                "retention_blocked",
                f"Prospect has {model.__tablename__} history; erase that history first.",
            )
    db.execute(delete(EmailContact).where(EmailContact.prospect_id == prospect_id))
    db.delete(prospect)
    activity.record(
        db,
        crypto,
        action="retention.prospect_erased",
        actor_user_id=actor_user_id,
        meta=meta,
        entity_type="prospect",
        entity_id=prospect_id,
        system=actor_user_id is None,
    )
    db.commit()
