"""Retention/deletion interfaces never remove suppression records."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from tests.conftest import Harness
from webforge_api.models import (
    ActivityLog,
    ConsentRecord,
    EmailContact,
    Prospect,
    ProspectSource,
    Suppression,
    UserSession,
    WebsiteAudit,
)
from webforge_api.models.enums import ProvenanceSource, Role, SuppressionReason
from webforge_api.services.errors import ConflictError
from webforge_api.services.retention import (
    delete_email_contact,
    erase_prospect,
    purge_expired_sessions,
)


def _prospect_with_contact(harness: Harness, email: str) -> tuple[Prospect, EmailContact]:
    with harness.db() as db:
        p = Prospect(business_name="Fixture Dental Clinic")
        db.add(p)
        db.flush()
        db.add(ProspectSource(prospect_id=p.id, source_type=ProvenanceSource.OFFICIAL_WEBSITE,
                              source_name="fixture", fact_field="business_name",
                              safe_value="Fixture Dental Clinic", retrieved_at=datetime.now(UTC),
                              confidence=0.9, verification_method="test"))  # fmt: skip
        c = EmailContact(
            prospect_id=p.id,
            email_encrypted=harness.crypto.encrypt_str(email, context="email_contacts.email"),
            email_hash=harness.crypto.email_hash(email),
        )
        db.add(c)
        db.flush()
        db.add(ConsentRecord(email_contact_id=c.id, consent_type="explicit", scope="newsletter",
                             source="fixture form", evidence="fixture",
                             captured_at=datetime.now(UTC)))  # fmt: skip
        db.add(Suppression(email_hash=c.email_hash, reason=SuppressionReason.UNSUBSCRIBE))
        db.commit()
        db.expunge_all()
    return p, c


def test_deleting_contact_keeps_suppression(harness: Harness) -> None:
    _, contact = _prospect_with_contact(harness, "frontdesk@dental.test")
    with harness.db() as db:
        delete_email_contact(db, harness.crypto, contact_id=contact.id, actor_user_id=None)
        assert db.get(EmailContact, contact.id) is None
        assert db.scalar(select(func.count()).select_from(ConsentRecord)) == 0
        assert (
            db.scalar(select(Suppression).where(Suppression.email_hash == contact.email_hash))
            is not None
        )
        assert db.scalar(
            select(ActivityLog).where(ActivityLog.action == "retention.contact_deleted")
        )


def test_erasing_prospect_removes_personal_data_but_not_suppression(harness: Harness) -> None:
    prospect, contact = _prospect_with_contact(harness, "owner@dental.test")
    with harness.db() as db:
        erase_prospect(db, harness.crypto, prospect_id=prospect.id, actor_user_id=None)
        assert db.get(Prospect, prospect.id) is None
        assert db.scalar(select(func.count()).select_from(EmailContact)) == 0
        assert db.scalar(select(func.count()).select_from(ProspectSource)) == 0
        assert db.scalar(select(func.count()).select_from(Suppression)) == 1
    # The suppression still matches the same address if it is rediscovered later.
    assert harness.crypto.email_hash("OWNER@dental.test") == contact.email_hash


def test_erasing_prospect_with_history_is_blocked(harness: Harness) -> None:
    prospect, _ = _prospect_with_contact(harness, "x@dental.test")
    with harness.db() as db:
        db.add(
            WebsiteAudit(prospect_id=prospect.id, url="https://d.example.test", audit_version="1")
        )
        db.commit()
        with pytest.raises(ConflictError) as info:
            erase_prospect(db, harness.crypto, prospect_id=prospect.id, actor_user_id=None)
        assert info.value.code == "retention_blocked"


def test_purge_expired_sessions(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    now = datetime.now(UTC)
    with harness.db() as db:
        for i, revoked in enumerate([now - timedelta(days=40), None]):
            db.add(UserSession(user_id=user.id, refresh_token_hash=f"{i}" * 64,
                               refresh_expires_at=now + timedelta(days=1),
                               absolute_expires_at=now + timedelta(days=10), revoked_at=revoked))  # fmt: skip
        db.commit()
        assert purge_expired_sessions(db, now=now) == 1
        assert db.scalar(select(func.count()).select_from(UserSession)) == 1
