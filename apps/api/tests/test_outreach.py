"""Phase 09: compliance engine, mock provider, suppression, webhooks, replies and pause controls (mock only)."""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from typing import Any

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import Harness
from tests.test_proposals import make_proposal, preview_client, ready_concept
from webforge_api.config import AppEnv
from webforge_api.models import (
    AuditFinding,
    Job,
    OutreachMessage,
    PolicyConfig,
    Prospect,
    Suppression,
    WebsiteAudit,
)
from webforge_api.models.enums import JobStatus, ProspectState, Severity
from webforge_api.security.rate_limit import MemoryRateLimiter
from webforge_api.services import compliance
from webforge_api.services.email.provider import (
    MockEmailProvider,
    build_provider,
    sign,
    signed_request,
)
from webforge_api.services.email.templates import Draft, check
from webforge_api.services.outreach import classify
from webforge_api.worker import Runtime, drain

WEBHOOK = "whsec-test-events-0123456789"
INBOUND = "whsec-test-inbound-0123456789"
EMAIL_SETTINGS: dict[str, Any] = {
    "mfa_required_for_owner": True, "email_from_address": "sender@sender.example.test", "email_reply_to": "sender@sender.example.test",
    "email_daily_max": 5, "email_hourly_max": 3, "email_physical_address": "1 Test Street, Testville",
    "email_webhook_secret": SecretStr(WEBHOOK), "email_inbound_signing_secret": SecretStr(INBOUND),
}  # fmt: skip
RULES = {"permitted": True, "legal_bases": ["legitimate_interest"], "consent_required": False,
         "disclosures": ["sender_identity", "physical_address", "unsubscribe", "concept_notice"],
         "unsubscribe": "link + one-click", "retention_days": 365, "next_review": "2099-01-01", "personal_data_reviewed": True}  # fmt: skip
BASIS = {
    "legal_basis": "legitimate_interest",
    "legal_basis_evidence": "Counsel memo REF-TEST: corporate role address, one message, opt-out.",
}


@pytest.fixture(autouse=True)
def _reset_mock() -> None:
    MockEmailProvider.accepted.clear()


@pytest.fixture
def h(harness_factory: Any) -> Harness:
    harness: Harness = harness_factory(**EMAIL_SETTINGS)
    return harness


def activate_policy(
    h: Harness, csrf: dict[str, str], rules: dict[str, Any] | None = None, country: str = "US"
) -> dict[str, Any]:
    body = {"country_code": country, "recipient_type": "CORPORATE", "message_category": "commercial_initial", "version": "2027.1",
            "rules": rules or RULES, "source_references": ["https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business"]}  # fmt: skip
    r = h.client.post("/api/v1/compliance/policies", json=body, headers=csrf)
    assert r.status_code == 200, r.text
    act = h.client.post(f"/api/v1/compliance/policies/{r.json()['id']}/activate", headers=csrf,
                        json={"reviewer_name": "Test Counsel", "reviewer_qualification": "Fixture reviewer (tests only)",
                              "reviewed_on": "2026-11-01", "effective_from": "2026-11-01"})  # fmt: skip
    assert act.status_code == 200, act.text
    policy: dict[str, Any] = act.json()
    return policy


def setup(
    h: Harness, *, policy: bool = True, email: str = "info@bakery.example.test"
) -> tuple[dict[str, str], Prospect, dict[str, Any], dict[str, Any]]:
    csrf, p, design_id = ready_concept(h)
    r = h.client.put(
        "/api/v1/controls/email_pause",
        json={"enabled": False, "reason": "tests use the mock provider"},
        headers=csrf,
    )
    assert r.status_code == 200, r.text
    proposal = make_proposal(h, csrf, design_id)
    with h.db() as db:
        audit = db.scalars(select(WebsiteAudit).where(WebsiteAudit.prospect_id == p.id)).one()
        db.add(AuditFinding(audit_id=audit.id, category="mobile_usability", severity=Severity.HIGH, code="MOBILE_HORIZONTAL_OVERFLOW",
                            description="The home page scrolls sideways on a 390px phone screen. Content is cut off.",
                            viewport="mobile", observed_at=h.clock()))  # fmt: skip
        db.commit()
    contact = h.client.post(f"/api/v1/prospects/{p.id}/contacts", headers=csrf,
                            json={"email": email, "recipient_type": "CORPORATE", "country_code": "US",
                                  "source_url": "https://bakery.example.test/contact", "verification_method": "published_on_official_website"})  # fmt: skip
    assert contact.status_code == 200, contact.text
    if policy:
        activate_policy(h, csrf)
    return csrf, p, contact.json(), proposal


def draft(
    h: Harness,
    csrf: dict[str, str],
    p: Prospect,
    contact: dict[str, Any],
    proposal: dict[str, Any],
    **extra: Any,
) -> dict[str, Any]:
    r = h.client.post(
        f"/api/v1/prospects/{p.id}/outreach",
        headers=csrf,
        json={"contact_id": contact["id"], "proposal_id": proposal["id"], **BASIS, **extra},
    )
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def runtime(h: Harness, provider: MockEmailProvider) -> Runtime:
    storage = h.client.app.state.storage  # type: ignore[attr-defined]
    return Runtime(
        h.settings, limiter=MemoryRateLimiter(), clock=h.clock, storage=storage, email=provider
    )


def run_outreach(h: Harness, provider: MockEmailProvider) -> None:
    rt = runtime(h, provider)
    try:
        drain(rt, ["outreach"])
    finally:
        rt.close()


def message(h: Harness, mid: str) -> dict[str, Any]:
    """Read from the database: tests advance the clock past the staff session lifetime."""
    with h.db() as db:
        m = db.get(OutreachMessage, mid)
        assert m is not None
        return {
            "id": str(m.id),
            "status": m.status.value,
            "provider_message_id": m.provider_message_id,
            "subject": m.subject,
        }


def prospect_state(h: Harness, pid: Any) -> ProspectState:
    with h.db() as db:
        p = db.get(Prospect, pid)
        assert p is not None
        return p.state


def post_signed(
    h: Harness, path: str, payload: dict[str, Any], secret: str, ts: int | None = None
) -> Any:
    raw = json.dumps(payload).encode()
    headers = {
        "webforge-signature": sign(secret, raw, ts or int(time.time())),
        "content-type": "application/json",
    }
    return h.client.post(path, content=raw, headers=headers)


def sent(
    h: Harness, provider: MockEmailProvider | None = None
) -> tuple[dict[str, str], Prospect, dict[str, Any], MockEmailProvider]:
    csrf, p, contact, proposal = setup(h)
    m = draft(h, csrf, p, contact, proposal)
    assert h.client.post(f"/api/v1/outreach/{m['id']}/approve", headers=csrf).status_code == 200
    provider = provider or MockEmailProvider()
    run_outreach(h, provider)
    return csrf, p, message(h, m["id"]), provider


# ----------------------------------------------------------------------------- eligibility


def test_no_reviewed_policy_holds(h: Harness) -> None:
    csrf, p, contact, proposal = setup(h, policy=False)
    m = draft(h, csrf, p, contact, proposal)
    a = m["assessment"]
    assert (
        m["status"] == "DRAFT"
        and a["decision"] == "HOLD"
        and "no_reviewed_policy" in a["reason_codes"]
    )
    assert sorted({c["n"] for c in a["checks"]}) == list(range(1, 18))
    assert prospect_state(h, p.id) is ProspectState.POLICY_HOLD
    assert (
        h.client.post(f"/api/v1/outreach/{m['id']}/approve", headers=csrf).json()["code"]
        == "not_pending_review"
    )


def test_public_address_is_not_consent_and_consent_policies_hold(h: Harness) -> None:
    csrf, p, contact, proposal = setup(h, policy=False)
    activate_policy(h, csrf, {**RULES, "legal_bases": ["consent"], "consent_required": True})
    m = draft(
        h,
        csrf,
        p,
        contact,
        proposal,
        legal_basis="consent",
        legal_basis_evidence="Address is published on their website.",
    )
    assert (
        m["assessment"]["decision"] == "HOLD"
        and "consent_missing" in m["assessment"]["reason_codes"]
    )


def test_eligible_draft_is_truthful_and_owner_approval_schedules(h: Harness) -> None:
    csrf, p, contact, proposal = setup(h)
    m = draft(h, csrf, p, contact, proposal)
    assert m["status"] == "PENDING_REVIEW" and m["assessment"]["decision"] == "ELIGIBLE", m[
        "assessment"
    ]
    body = m["body"]
    for expected in ("Muhammad Aqib", "independent redesign concept", "not affiliated with", "1 Test Street, Testville",
                     "The home page scrolls sideways", "{{PREVIEW_URL}}", "{{UNSUBSCRIBE_URL}}"):  # fmt: skip
        assert expected in body, expected
    assert not m["subject"].lower().startswith(("re:", "fwd"))
    assert (
        h.client.post(
            f"/api/v1/prospects/{p.id}/outreach",
            headers=csrf,
            json={"contact_id": contact["id"], "proposal_id": proposal["id"], **BASIS},
        ).json()["code"]
        == "one_message_only"
    )
    approved = h.client.post(f"/api/v1/outreach/{m['id']}/approve", headers=csrf).json()
    assert approved["status"] == "SCHEDULED" and prospect_state(h, p.id) is ProspectState.SCHEDULED


def test_contacts_must_come_from_official_source(h: Harness) -> None:
    csrf, p, _, _ = setup(h, policy=False)
    base = {
        "email": "guess@bakery.example.test",
        "recipient_type": "CORPORATE",
        "country_code": "US",
        "source_url": "https://bakery.example.test/",
    }
    assert (
        h.client.post(
            f"/api/v1/prospects/{p.id}/contacts",
            headers=csrf,
            json={**base, "verification_method": "guessed_pattern"},
        ).json()["code"]
        == "unverifiable_source"
    )
    other = {
        **base,
        "source_url": "https://directory.example.test/bakery",
        "verification_method": "published_on_official_website",
    }
    assert (
        h.client.post(f"/api/v1/prospects/{p.id}/contacts", headers=csrf, json=other).json()["code"]
        == "source_not_official"
    )


def test_zero_budget_and_production_mock_fail_closed(harness_factory: Any) -> None:
    h = harness_factory(**{**EMAIL_SETTINGS, "email_daily_max": 0})
    csrf, p, contact, proposal = setup(h)
    m = draft(h, csrf, p, contact, proposal)
    assert m["status"] == "DRAFT" and "rate_or_budget_exceeded" in m["assessment"]["reason_codes"]
    with h.db() as db:
        msg = db.get(OutreachMessage, m["id"])
        assert msg is not None
        prod = h.settings.model_copy(update={"app_env": AppEnv.PRODUCTION, "email_daily_max": 5})
        a = compliance.assess(db, prod, h.crypto, message=msg, draft=Draft(msg.subject or "", "x"), legal_basis="legitimate_interest",
                              legal_basis_evidence="e", now=h.clock(), provider_name="mock", provider_is_mock=True)  # fmt: skip
        assert {"provider_not_approved", "sender_domain_unverified"} <= set(a.reasons)


# ----------------------------------------------------------------------------- sending


def test_send_creates_preview_unsubscribe_and_is_idempotent(h: Harness) -> None:
    _csrf, p, m, provider = sent(h)
    assert m["status"] == "ACCEPTED" and m["provider_message_id"].startswith("mock-")
    assert prospect_state(h, p.id) is ProspectState.SENT
    ((email, key),) = provider.sent
    assert email.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert email.to == "info@bakery.example.test" and "{{" not in email.text
    preview_url = next(line for line in email.text.splitlines() if "/p/" in line).strip()
    token = preview_url.rstrip("/").rsplit("/", 1)[-1]
    assert preview_client(h).get(f"/p/{token}/home").status_code == 200
    # Re-sending with the same idempotency key returns the same message id; nothing is duplicated.
    again = provider.send(email, key)
    assert again.provider_message_id == m["provider_message_id"] and len(provider.sent) == 1


def test_transient_failure_retries_once_and_ambiguous_send_reconciles(h: Harness) -> None:
    provider = MockEmailProvider(script=["failed", "ambiguous"])
    _csrf, p, m, _ = sent(h, provider)
    assert m["status"] == "SCHEDULED" or m["status"] == "AMBIGUOUS"
    h.clock.advance(minutes=10)
    run_outreach(h, provider)  # retry -> ambiguous (accepted remotely, response lost)
    assert message(h, m["id"])["status"] == "AMBIGUOUS"
    h.clock.advance(minutes=5)
    run_outreach(h, provider)  # reconcile asks the provider instead of resending
    final = message(h, m["id"])
    assert (
        final["status"] == "ACCEPTED" and final["provider_message_id"] and len(provider.sent) == 1
    )
    assert prospect_state(h, p.id) is ProspectState.SENT


def test_pause_controls_hold_queued_mail(h: Harness) -> None:
    csrf, p, contact, proposal = setup(h)
    m = draft(h, csrf, p, contact, proposal)
    h.client.post(f"/api/v1/outreach/{m['id']}/approve", headers=csrf)
    for key in ("country_pause:US", "provider_pause:mock"):  # scoped keys are accepted by the API
        r = h.client.put(
            f"/api/v1/controls/{key}",
            json={"enabled": False, "reason": "create scoped switch"},
            headers=csrf,
        )
        assert r.status_code == 200, r.text
    assert (
        h.client.put(
            "/api/v1/controls/country_pause:usa",
            json={"enabled": True, "reason": "bad key"},
            headers=csrf,
        ).status_code
        == 404
    )
    provider = MockEmailProvider()

    def set_switch(key: str, enabled: bool) -> None:
        with h.db() as db:
            db.execute(
                text("UPDATE system_controls SET enabled = :e WHERE key = :k"),
                {"e": enabled, "k": key},
            )
            db.commit()

    for key in ("email_pause", "country_pause:US", "provider_pause:mock"):
        set_switch(key, True)
        run_outreach(h, provider)
        assert message(h, m["id"])["status"] == "SCHEDULED" and provider.sent == [], key
        with h.db() as db:
            job = db.scalars(select(Job).where(Job.job_type == "email.send")).one()
            assert job.status is JobStatus.QUEUED and job.error_code == "deferred"
        set_switch(key, False)
        h.clock.advance(minutes=6)
    run_outreach(h, provider)
    assert message(h, m["id"])["status"] == "ACCEPTED" and len(provider.sent) == 1


def test_suppression_before_send_cancels_queued_mail(h: Harness) -> None:
    csrf, p, contact, proposal = setup(h)
    m = draft(h, csrf, p, contact, proposal)
    h.client.post(f"/api/v1/outreach/{m['id']}/approve", headers=csrf)
    r = h.client.post(
        "/api/v1/compliance/suppressions", json={"email": "INFO@bakery.example.test "}, headers=csrf
    )
    assert r.json() == {"cancelled_messages": 1}
    provider = MockEmailProvider()
    run_outreach(h, provider)
    assert message(h, m["id"])["status"] == "CANCELLED" and provider.sent == []
    assert h.client.delete("/api/v1/compliance/suppressions").status_code in (
        404,
        405,
    )  # no way to remove


# ----------------------------------------------------------------------------- unsubscribe, webhooks, replies


def test_one_click_unsubscribe_suppresses_globally(h: Harness) -> None:
    _csrf, p, _, provider = sent(h)
    url = (
        next(line for line in provider.sent[0][0].text.splitlines() if "/u/" in line)
        .split(": ", 1)[1]
        .strip()
    )
    path = url.split("://", 1)[1].split("/", 1)[1]
    page = h.client.get("/" + path)
    assert (
        page.status_code == 200
        and 'method="post"' in page.text
        and "frame-ancestors 'none'" in page.headers["content-security-policy"]
    )
    with h.db() as db:
        assert db.scalars(select(Suppression)).all() == []  # GET changes nothing
    done = h.client.post("/" + path, data={"List-Unsubscribe": "One-Click"})
    assert done.status_code == 200 and "unsubscribed" in done.text
    with h.db() as db:
        (s,) = db.scalars(select(Suppression)).all()
        assert s.scope.value == "GLOBAL" and s.reason.value == "UNSUBSCRIBE"
        prospect = db.get(Prospect, p.id)
        assert (
            prospect is not None
            and prospect.do_not_contact
            and prospect.state is ProspectState.UNSUBSCRIBED
        )
    assert h.client.post("/u/" + "x" * 43).status_code == 404
    # The same address on another prospect is now ineligible.
    assert compliance.is_suppressed(h.db(), h.crypto.email_hash("info@bakery.example.test"))


def test_webhooks_verify_signature_dedupe_and_reject_replays(h: Harness) -> None:
    _csrf, p, m, _ = sent(h)
    event = {
        "events": [
            {
                "id": "evt-1",
                "type": "delivered",
                "message_id": m["provider_message_id"],
                "at": "2026-11-26T12:00:00+00:00",
            }
        ]
    }
    assert post_signed(h, "/webhooks/email/mock/events", event, WEBHOOK).json() == {
        "processed": 1,
        "duplicates": 0,
        "ignored": 0,
    }
    assert post_signed(h, "/webhooks/email/mock/events", event, WEBHOOK).json()["duplicates"] == 1
    assert (
        message(h, m["id"])["status"] == "DELIVERED"
        and prospect_state(h, p.id) is ProspectState.DELIVERED
    )
    assert post_signed(h, "/webhooks/email/mock/events", event, "wrong-secret").status_code == 403
    assert (
        post_signed(
            h, "/webhooks/email/mock/events", event, WEBHOOK, ts=int(time.time()) - 3600
        ).status_code
        == 403
    )
    assert h.client.post("/webhooks/email/mock/events", content=b"{}").status_code == 403
    assert post_signed(h, "/webhooks/email/resend/events", event, WEBHOOK).status_code == 404


@pytest.mark.parametrize(("kind", "status", "state", "reason"), [
    ("hard_bounce", "BOUNCED", ProspectState.BOUNCED, "HARD_BOUNCE"),
    ("complaint", "COMPLAINED", ProspectState.UNSUBSCRIBED, "COMPLAINT"),
])  # fmt: skip
def test_bounce_and_complaint_suppress(
    h: Harness, kind: str, status: str, state: ProspectState, reason: str
) -> None:
    csrf, p, m, _ = sent(h)
    r = h.client.post(f"/api/v1/outreach/{m['id']}/simulate", json={"kind": kind}, headers=csrf)
    assert r.status_code == 200 and r.json()["processed"] == 1
    assert message(h, m["id"])["status"] == status and prospect_state(h, p.id) is state
    with h.db() as db:
        assert db.scalars(select(Suppression.reason)).one().value == reason


def test_soft_bounce_does_not_suppress(h: Harness) -> None:
    _csrf, _, m, _ = sent(h)
    event = {
        "events": [
            {
                "id": "evt-soft",
                "type": "bounced",
                "bounce_type": "soft",
                "message_id": m["provider_message_id"],
            }
        ]
    }
    assert post_signed(h, "/webhooks/email/mock/events", event, WEBHOOK).json()["ignored"] == 1
    with h.db() as db:
        assert db.scalars(select(Suppression)).all() == []


def test_replies_are_classified_and_opt_out_wins(h: Harness) -> None:
    csrf, p, m, _ = sent(h)
    base = {
        "from": "info@bakery.example.test",
        "subject": "Re: concept",
        "in_reply_to": m["provider_message_id"],
        "headers": {},
    }
    r = post_signed(
        h,
        "/webhooks/email/mock/inbound",
        {**base, "id": "in-1", "text": "Looks nice. How much would this cost?"},
        INBOUND,
    )
    assert r.json() == {"accepted": True, "duplicate": False}
    assert (
        post_signed(
            h, "/webhooks/email/mock/inbound", {**base, "id": "in-1", "text": "dup"}, INBOUND
        ).json()["duplicate"]
        is True
    )
    assert prospect_state(h, p.id) is ProspectState.INTERESTED
    post_signed(
        h,
        "/webhooks/email/mock/inbound",
        {
            **base,
            "id": "in-2",
            "text": "I'm out of office",
            "headers": {"Auto-Submitted": "auto-replied"},
        },
        INBOUND,
    )
    post_signed(
        h,
        "/webhooks/email/mock/inbound",
        {**base, "id": "in-3", "text": "Interesting, but please remove me from your list."},
        INBOUND,
    )
    replies = {r["classification"]: r for r in h.client.get("/api/v1/replies").json()}
    assert replies["INTERESTED"]["needs_human_review"] is True
    assert replies["AUTO_REPLY"]["needs_human_review"] is False
    assert replies["OPT_OUT"]["needs_human_review"] is False
    with h.db() as db:
        assert db.scalars(select(Suppression.reason)).one().value == "UNSUBSCRIBE"
        body = db.execute(text("SELECT body_encrypted FROM replies LIMIT 1")).scalar_one()
        assert b"How much" not in body  # stored encrypted
    open_items = h.client.get("/api/v1/replies?open_only=true").json()
    assert [r["classification"] for r in open_items] == ["INTERESTED"]
    handled = h.client.post(f"/api/v1/replies/{open_items[0]['id']}/handled", headers=csrf).json()
    assert handled["handled_at"]


@pytest.mark.parametrize(("subject", "body", "label"), [
    ("Re: x", "Please unsubscribe me, although I'm interested", "OPT_OUT"),
    ("Re: x", "STOP", "OPT_OUT"),
    ("Automatic reply", "I am away until Monday", "AUTO_REPLY"),
    ("Re: x", "No thanks, we're all set.", "NOT_INTERESTED"),
    ("Re: x", "Sounds good, let's talk next week", "INTERESTED"),
    ("Re: x", "This looks good. Can we talk next week?", "INTERESTED"),
    ("Re: x", "Who are you?", "QUESTION"),
    ("Re: x", "ok", "UNCERTAIN"),
    ("Re: x", "Thanks\n> To opt out of any further messages: link", "UNCERTAIN"),
])  # fmt: skip
def test_classifier(subject: str, body: str, label: str) -> None:
    assert classify(subject, body, False)[0] == label


@pytest.mark.parametrize(("subject", "text_", "code"), [
    ("Re: your website", "Muhammad Aqib independent redesign concept not affiliated with {{PREVIEW_URL}} {{UNSUBSCRIBE_URL}} 1 March 2026", "content_fake_reply_prefix"),
    ("Concept", "URGENT: Muhammad Aqib independent redesign concept not affiliated with {{PREVIEW_URL}} {{UNSUBSCRIBE_URL}} 1 March 2026", "content_false_urgency"),
    ("Concept", "As discussed, Muhammad Aqib independent redesign concept not affiliated with {{PREVIEW_URL}} {{UNSUBSCRIBE_URL}} 1 March 2026", "content_fake_familiarity"),
    ("Concept", "Guaranteed results. Muhammad Aqib independent redesign concept not affiliated with {{PREVIEW_URL}} {{UNSUBSCRIBE_URL}} 1 March 2026", "content_unsupported_claim"),
    ("Concept", "Muhammad Aqib {{PREVIEW_URL}} 1 March 2026", "content_unsubscribe_missing"),
])  # fmt: skip
def test_content_checks(subject: str, text_: str, code: str) -> None:
    assert code in check(
        Draft(subject, text_),
        from_name="Muhammad Aqib",
        physical_address_required=False,
        physical_address="",
    )


# ----------------------------------------------------------------------------- policy registry and provider


def test_policy_registry_rules(h: Harness) -> None:
    csrf = _owner_csrf(h)
    first = activate_policy(h, csrf)
    body = {"country_code": "US", "recipient_type": "CORPORATE", "message_category": "commercial_initial", "version": "2027.2",
            "rules": RULES, "source_references": ["https://www.ftc.gov/"]}  # fmt: skip
    new = h.client.post("/api/v1/compliance/policies", json=body, headers=csrf).json()
    h.client.post(f"/api/v1/compliance/policies/{new['id']}/activate", headers=csrf,
                  json={"reviewer_name": "Test Counsel", "reviewer_qualification": "Fixture", "reviewed_on": "2026-11-20", "effective_from": "2026-11-20"})  # fmt: skip
    statuses = {
        p["version"]: p["status"] for p in h.client.get("/api/v1/compliance/policies").json()
    }
    assert statuses == {"2027.1": "RETIRED", "2027.2": "ACTIVE"} and first["status"] == "ACTIVE"
    bad = {**body, "version": "x", "rules": {"permitted": True}}
    assert (
        h.client.post("/api/v1/compliance/policies", json=bad, headers=csrf).json()["code"]
        == "invalid_rules"
    )
    with h.db() as db, pytest.raises(IntegrityError):
        db.execute(text("INSERT INTO policy_configs (id, country_code, recipient_type, message_category, version, status, rules, source_references, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), 'FR', 'CORPORATE', 'commercial_initial', 'v', 'ACTIVE', '{}', '{}', now(), now())"))  # fmt: skip
        db.commit()


def test_policy_activation_is_owner_only(h: Harness) -> None:
    from webforge_api.models.enums import Role

    csrf = _owner_csrf(h)
    body = {"country_code": "GB", "recipient_type": "CORPORATE", "message_category": "commercial_initial", "version": "1",
            "rules": RULES, "source_references": ["https://ico.org.uk/"]}  # fmt: skip
    pid = h.client.post("/api/v1/compliance/policies", json=body, headers=csrf).json()["id"]
    h.client.cookies.clear()
    admin, secret = h.create_user(Role.ADMIN, mfa=True)
    acsrf = {"X-CSRF-Token": h.login_active(admin, secret)}
    r = h.client.post(f"/api/v1/compliance/policies/{pid}/activate", headers=acsrf,
                      json={"reviewer_name": "x x x", "reviewer_qualification": "y y y", "reviewed_on": "2026-11-01", "effective_from": "2026-11-01"})  # fmt: skip
    assert r.status_code == 403


def test_seeded_policy_drafts_are_inactive(h: Harness) -> None:
    with h.db() as db:
        assert compliance.seed_policy_drafts(db, date(2026, 11, 26)) == 4
        assert compliance.seed_policy_drafts(db, date(2026, 11, 26)) == 0
        rows = db.scalars(select(PolicyConfig)).all()
        assert all(r.status.value == "DRAFT" and r.rules["permitted"] is False for r in rows)


def test_only_mock_provider_exists_and_live_sending_is_rejected() -> None:
    from tests.conftest import make_settings

    with pytest.raises(ValueError, match="live providers are not enabled"):
        build_provider("resend", 300)
    with pytest.raises(ValueError, match="EMAIL_SENDING_ENABLED"):
        make_settings(email_sending_enabled=True)
    raw, headers = signed_request("s", {"a": 1})
    assert MockEmailProvider().verify_webhook(headers, raw, "s", time.time())
    assert not MockEmailProvider().verify_webhook(headers, raw + b" ", "s", time.time())
    assert not MockEmailProvider().verify_webhook(
        headers, raw, "s", time.time() + timedelta(minutes=10).total_seconds()
    )


def _owner_csrf(h: Harness) -> dict[str, str]:
    from tests.test_audits import _resume
    from tests.test_sources_api import _owner

    csrf = _owner(h)
    _resume(h, csrf)
    return csrf
