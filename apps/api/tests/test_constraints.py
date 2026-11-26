"""Database constraints, foreign-key behaviour, append-only log and UTC handling."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, StatementError

from tests.conftest import Harness
from webforge_api.models import (
    ActivityLog,
    EmailContact,
    EmailEvent,
    Job,
    PolicyConfig,
    Prospect,
    Suppression,
    User,
    WebsiteAudit,
)
from webforge_api.models.enums import PolicyStatus, RecipientType, Role, SuppressionReason


def _expect_integrity(harness: Harness, *objs: object) -> None:
    with harness.db() as db:
        db.add_all(objs)
        with pytest.raises(IntegrityError):
            db.commit()


def test_single_owner_enforced(harness: Harness) -> None:
    harness.create_user(Role.OWNER)
    with pytest.raises(IntegrityError):
        harness.create_user(Role.OWNER)


def test_email_must_be_normalised(harness: Harness) -> None:
    _expect_integrity(
        harness,
        User(email="Mixed@Case.test", display_name="x", role=Role.REVIEWER, password_hash="h"),
    )


def test_unique_suppression_per_scope(harness: Harness) -> None:
    h = "a" * 64
    with harness.db() as db:
        db.add(Suppression(email_hash=h, reason=SuppressionReason.UNSUBSCRIBE))
        db.commit()
    _expect_integrity(harness, Suppression(email_hash=h, reason=SuppressionReason.COMPLAINT))


def test_suppression_scope_ref_consistency(harness: Harness) -> None:
    _expect_integrity(
        harness,
        Suppression(email_hash="b" * 64, reason=SuppressionReason.MANUAL, scope_ref="camp-1"),
    )


def test_unique_provider_event_and_job_idempotency(harness: Harness) -> None:
    now = datetime.now(UTC)
    ev = {"provider": "mock", "provider_event_id": "evt-1", "event_type": "delivered",
          "event_at": now, "received_at": now, "payload_sha256": "c" * 64}  # fmt: skip
    with harness.db() as db:
        db.add(EmailEvent(**ev))
        db.commit()
    _expect_integrity(harness, EmailEvent(**ev))

    job = {"job_type": "t", "payload_schema_version": "1", "queue": "q", "idempotency_key": "k1"}
    with harness.db() as db:
        db.add(Job(**job))
        db.commit()
    _expect_integrity(harness, Job(**job))


def test_policy_cannot_be_active_without_legal_review(harness: Harness) -> None:
    base = {"country_code": "GB", "recipient_type": RecipientType.CORPORATE,
            "message_category": "b2b_intro", "version": "1"}  # fmt: skip
    _expect_integrity(harness, PolicyConfig(**base, status=PolicyStatus.ACTIVE))
    with harness.db() as db:
        db.add(
            PolicyConfig(
                **base,
                status=PolicyStatus.ACTIVE,
                reviewer_name="Qualified Reviewer",
                reviewer_qualification="Solicitor (test fixture)",
                reviewed_at=datetime.now(UTC),
                effective_from=datetime.now(UTC).date(),
                source_references=["https://example.test/law"],
            )
        )
        db.commit()


def test_invalid_enum_and_country_rejected(harness: Harness) -> None:
    with harness.db() as db, pytest.raises((DBAPIError, StatementError, LookupError)):
        db.execute(text("INSERT INTO prospects (business_name, state) VALUES ('x', 'NOT_A_STATE')"))
    _expect_integrity(harness, Prospect(business_name="x", country_code="pk"))


def test_prospect_with_audit_history_cannot_be_deleted(harness: Harness) -> None:
    with harness.db() as db:
        p = Prospect(business_name="Fixture Bakery")
        db.add(p)
        db.flush()
        db.add(WebsiteAudit(prospect_id=p.id, url="https://bakery.example.test", audit_version="1"))
        db.commit()
        db.delete(p)
        with pytest.raises(IntegrityError):
            db.commit()


def test_contact_survives_as_orphan_when_prospect_link_cleared(harness: Harness) -> None:
    with harness.db() as db:
        p = Prospect(business_name="Fixture Plumber")
        db.add(p)
        db.flush()
        c = EmailContact(
            prospect_id=p.id,
            email_encrypted=harness.crypto.encrypt_str("info@plumber.test", context="c"),
            email_hash=harness.crypto.email_hash("info@plumber.test"),
        )
        db.add(c)
        db.commit()
        db.execute(text("DELETE FROM prospects WHERE id = :id"), {"id": p.id})
        db.commit()
        db.refresh(c)
        assert c.prospect_id is None


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE activity_logs SET action = 'tampered'",
        "DELETE FROM activity_logs",
        "TRUNCATE activity_logs",
    ],
)
def test_activity_log_is_append_only(harness: Harness, sql: str) -> None:
    with harness.db() as db:
        db.add(ActivityLog(actor_type="system", action="test.event"))
        db.commit()
        with pytest.raises(DBAPIError, match="append-only"):
            db.execute(text(sql))
            db.commit()


def test_naive_datetimes_rejected_and_utc_returned(harness: Harness) -> None:
    with harness.db() as db:
        db.add(Job(job_type="t", payload_schema_version="1", queue="q", idempotency_key="naive",
                   available_at=datetime(2026, 1, 1, 12, 0)))  # fmt: skip
        with pytest.raises(StatementError, match="naive datetime"):
            db.commit()

    karachi = timezone(timedelta(hours=5))
    with harness.db() as db:
        job = Job(job_type="t", payload_schema_version="1", queue="q", idempotency_key="tz",
                  available_at=datetime(2026, 1, 1, 17, 0, tzinfo=karachi))  # fmt: skip
        db.add(job)
        db.commit()
        job_id = job.id
    with harness.db() as db:
        stored = db.get(Job, job_id)
        assert stored is not None
        assert stored.available_at == datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        assert stored.available_at.utcoffset() == timedelta(0)
        assert db.scalar(text("SHOW timezone")) == "UTC"


def test_uuid_primary_keys_generated(harness: Harness) -> None:
    user, _ = harness.create_user(Role.REVIEWER)
    assert isinstance(user.id, uuid.UUID)
    with harness.db() as db:
        new_id = db.scalar(
            text("INSERT INTO campaigns (name, created_by_user_id) VALUES ('c', :u) RETURNING id"),
            {"u": user.id},
        )
        assert isinstance(new_id, uuid.UUID)
        assert db.scalar(select(User.id).where(User.id == user.id)) == user.id
