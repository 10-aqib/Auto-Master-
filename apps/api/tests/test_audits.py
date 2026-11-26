"""Audit rules, storage, the audit job (fake sandbox) and audit API."""

from __future__ import annotations

import base64
import json
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from tests.conftest import Harness
from tests.test_sources_api import _owner
from webforge_api.models import AuditFinding, Job, Prospect, QualificationResult, WebsiteAudit
from webforge_api.models.enums import JobStatus, ProspectState, RunStatus
from webforge_api.security.rate_limit import MemoryRateLimiter
from webforge_api.services.audit_rules import evaluate
from webforge_api.services.audits import BrowserClient
from webforge_api.services.campaigns import QUALIFY
from webforge_api.services.jobs import enqueue
from webforge_api.storage import LocalStorage, S3Storage, StorageError
from webforge_api.worker import Runtime, drain

PNG = base64.b64encode(b"\x89PNG\r\n\x1a\nfake").decode()


def metrics(**over: Any) -> dict[str, Any]:
    m: dict[str, Any] = {
        "url": "https://shop.example.test/", "title": "Shop", "lang": "en", "meta_description": "d",
        "viewport_meta": "width=device-width", "viewport": {"width": 1440, "height": 1000},
        "scroll_width": 1440, "client_width": 1440, "page_height": 2000,
        "headings": [{"level": 1, "text": "H"}, {"level": 2, "text": "S"}], "h1_count": 1, "h1_lines": 1,
        "images_total": 1, "images_broken": [], "images_missing_alt": 0, "same_origin_links": [],
        "external_links": 0, "nav_links": 4, "cta_count": 2, "cta_above_fold": True, "cta_samples": ["Book"],
        "contact_routes": 2, "forms": 0, "small_text_ratio": 0.0, "small_tap_targets": 0, "tap_targets": 6,
        "consent_overlay": False, "word_count": 300,
    }  # fmt: skip
    m |= over
    return m


def result(
    desktop: dict[str, Any] | None = None, mobile: dict[str, Any] | None = None, **over: Any
) -> dict[str, Any]:
    r: dict[str, Any] = {
        "requested_url": "https://shop.example.test/", "browser_version": "1243",
        "desktop": {"status": 200, "final_url": "https://shop.example.test/", "metrics": metrics(**(desktop or {})),
                    "console_errors": [], "load_ms": 900, "screenshot_png_b64": PNG},
        "mobile": {"status": 200, "metrics": metrics(**({"viewport": {"width": 390, "height": 844}, "scroll_width": 390, "client_width": 390} | (mobile or {}))),
                   "screenshot_png_b64": PNG},
        "pages": [], "limits": {}, "timed_out": False,
    }  # fmt: skip
    r |= over
    return r


def test_clean_site_scores_full_marks_except_untested_branding() -> None:
    out = evaluate(result())
    assert out.status == "SUCCEEDED" and out.findings == []
    assert out.categories["branding"] == {"weight": 10, "score": None, "status": "NOT_TESTED"}
    assert out.overall == 100.0 and len(out.strengths) == 6


def test_problem_site_produces_specific_findings() -> None:
    out = evaluate(result(
        desktop={"h1_count": 0, "nav_links": 0, "cta_count": 0, "contact_routes": 0, "images_broken": ["/x.png"], "lang": None},
        mobile={"viewport_meta": None, "scroll_width": 1200, "small_text_ratio": 0.6, "cta_count": 0},
        pages=[{"url": "https://shop.example.test/a", "status": 404}],
    ))  # fmt: skip
    codes = {f.code for f in out.findings}
    assert {"MISSING_H1", "NAVIGATION_MISSING", "NO_CLEAR_CALL_TO_ACTION", "NO_CONTACT_ROUTE", "BROKEN_IMAGES",
            "MOBILE_NO_VIEWPORT_META", "MOBILE_HORIZONTAL_OVERFLOW", "MOBILE_SMALL_TEXT", "BROKEN_INTERNAL_LINKS",
            "MISSING_LANG"} <= codes  # fmt: skip
    overflow = next(f for f in out.findings if f.code == "MOBILE_HORIZONTAL_OVERFLOW")
    assert "1200px" in overflow.description and overflow.viewport.startswith("mobile 390x844")
    assert out.categories["mobile_usability"]["score"] < 50
    assert all(f.reproduction and 0 < f.confidence <= 1 for f in out.findings)


@pytest.mark.parametrize("status", [403, 429, 503])
def test_bot_blocked_is_failed_not_scored(status: int) -> None:
    out = evaluate(result(desktop=None) | {"desktop": {"status": status, "metrics": metrics()}})
    assert (
        out.status == "FAILED"
        and out.categories == {}
        and "refused automated access" in (out.error_summary or "")
    )


def test_unloadable_homepage_fails() -> None:
    out = evaluate({"desktop": {"error": "TimeoutError: x", "metrics": None}, "mobile": {}})
    assert out.status == "FAILED"


def test_missing_mobile_capture_is_not_tested() -> None:
    r = result()
    r["mobile"] = {"error": "x", "metrics": None}
    out = evaluate(r)
    assert out.categories["mobile_usability"]["status"] == "NOT_TESTED"


def test_local_storage_rejects_traversal(tmp_path: Any) -> None:
    s = LocalStorage(str(tmp_path))
    obj = s.put("audits/a1/desktop.png", b"png", "image/png")
    assert s.get("audits/a1/desktop.png") == b"png" and obj.size == 3 and len(obj.sha256) == 64
    for bad in ("../etc/passwd", "/abs", "a/../../b", "UPPER/x", "a//b", "x/"):
        with pytest.raises(StorageError):
            s.put(bad, b"x", "text/plain")
    s.delete("audits/a1/desktop.png")
    assert not s.exists("audits/a1/desktop.png")


def test_s3_storage_with_moto() -> None:
    import boto3
    from moto import mock_aws

    from tests.conftest import make_settings

    with mock_aws():
        boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="wf-test")
        settings = make_settings(storage_backend="s3", s3_bucket="wf-test", s3_region="us-east-1",
                                 s3_access_key="test", s3_secret_key="test")  # fmt: skip
        s = S3Storage(settings)
        s.put("previews/x/index.html", b"<h1>x</h1>", "text/html")
        assert s.get("previews/x/index.html") == b"<h1>x</h1>" and s.exists("previews/x/index.html")
        s.delete("previews/x/index.html")
        assert not s.exists("previews/x/index.html")
        with pytest.raises(StorageError):
            s.get("previews/missing")


class FakeSandbox:
    def __init__(
        self, isolated: bool = True, audit: dict[str, Any] | None = None, status: int = 200
    ) -> None:
        self.isolated = isolated
        self.audit_result = audit or result(mobile={"scroll_width": 900})
        self.status = status
        self.audits = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/selftest":
            return httpx.Response(200, json={"isolated": self.isolated})
        self.audits += 1
        assert json.loads(request.content)["url"].startswith("https://")
        return httpx.Response(self.status, json=self.audit_result)


def _prospect(h: Harness, state: ProspectState = ProspectState.QUALIFYING) -> Prospect:
    with h.db() as db:
        p = Prospect(business_name="Fixture Shop", verified_domain="shop.example.test",
                     website_url="https://shop.example.test/", state=state)  # fmt: skip
        db.add(p)
        db.commit()
        db.expunge(p)
    return p


def _runtime(h: Harness, sandbox: FakeSandbox) -> Runtime:
    return Runtime(h.settings, limiter=MemoryRateLimiter(), clock=h.clock,
                   storage=h.client.app.state.storage,  # type: ignore[attr-defined]
                   browser=BrowserClient("http://browser.test", transport=httpx.MockTransport(sandbox)))  # fmt: skip


def _resume(h: Harness, csrf: dict[str, str]) -> None:
    h.client.put(
        "/api/v1/controls/global_pause", json={"enabled": False, "reason": "tests"}, headers=csrf
    )


def test_audit_job_stores_evidence_and_requalifies(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    p = _prospect(harness)
    sandbox = FakeSandbox()
    rt = _runtime(harness, sandbox)
    try:
        job = harness.client.post(f"/api/v1/prospects/{p.id}/audit", headers=csrf).json()
        assert job["queue"] == "audit"
        drain(rt, ["audit", "qualification"])
        audits = harness.client.get(f"/api/v1/audits?prospect_id={p.id}").json()
        assert len(audits) == 1 and audits[0]["status"] == "SUCCEEDED"
        detail = harness.client.get(f"/api/v1/audits/{audits[0]['id']}").json()
        assert [f["code"] for f in detail["findings"]] == ["MOBILE_HORIZONTAL_OVERFLOW"]
        shot = harness.client.get(f"/api/v1/audits/{audits[0]['id']}/screenshots/mobile")
        assert shot.status_code == 200 and shot.headers["content-type"] == "image/png"
        assert shot.headers["cache-control"] == "private, no-store"
        with harness.db() as db:
            prospect = db.get(Prospect, p.id)
            q = db.scalars(
                select(QualificationResult).where(QualificationResult.prospect_id == p.id)
            ).one()
        assert (
            q.components["mobile_experience"]["score"] == 8.0
        )  # mobile score 60 -> opportunity 20 * 0.4
        assert prospect is not None and prospect.state is not ProspectState.QUALIFYING
    finally:
        rt.close()
    harness.client.cookies.clear()
    assert (
        harness.client.get(f"/api/v1/audits/{audits[0]['id']}/screenshots/mobile").status_code
        == 401
    )


def test_audit_refused_when_isolation_unproven(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    p = _prospect(harness)
    sandbox = FakeSandbox(isolated=False)
    rt = _runtime(harness, sandbox)
    try:
        harness.client.post(f"/api/v1/prospects/{p.id}/audit", headers=csrf)
        drain(rt, ["audit"])
        with harness.db() as db:
            job = db.scalars(select(Job).where(Job.queue == "audit")).one()
            assert job.status is JobStatus.FAILED and job.error_code == "isolation_unproven"
            assert db.scalars(select(WebsiteAudit)).first() is None
        assert sandbox.audits == 0
    finally:
        rt.close()


def test_bot_blocked_audit_goes_to_review(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    p = _prospect(harness, ProspectState.QUALIFIED)
    blocked = {
        "desktop": {"status": 403, "metrics": metrics(), "screenshot_png_b64": PNG},
        "mobile": {},
    }
    rt = _runtime(harness, FakeSandbox(audit=blocked))
    try:
        harness.client.post(f"/api/v1/prospects/{p.id}/audit", headers=csrf)
        drain(rt, ["audit"])
        with harness.db() as db:
            audit = db.scalars(select(WebsiteAudit)).one()
            assert audit.status is RunStatus.FAILED and "refused" in (audit.error_summary or "")
            assert db.scalars(select(AuditFinding)).first() is None
            assert db.get(Prospect, p.id).state is ProspectState.HUMAN_REVIEW  # type: ignore[union-attr]
        drain(rt, ["qualification", "audit"])  # the follow-up re-qualification
        with harness.db() as db:
            q = db.scalars(
                select(QualificationResult).where(QualificationResult.prospect_id == p.id)
            ).one()
            assert q.reason_codes == ["audit_failed"] and q.outcome.value == "MANUAL_REVIEW"
            assert db.get(Prospect, p.id).state is ProspectState.HUMAN_REVIEW  # type: ignore[union-attr]
            assert (
                len(db.scalars(select(Job).where(Job.queue == "audit")).all()) == 1
            )  # no audit loop
    finally:
        rt.close()


def test_sandbox_outage_is_retryable(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    p = _prospect(harness)
    rt = _runtime(harness, FakeSandbox(status=503))
    try:
        harness.client.post(f"/api/v1/prospects/{p.id}/audit", headers=csrf)
        drain(rt, ["audit"])
        with harness.db() as db:
            assert db.scalars(select(Job)).one().status is JobStatus.RETRYING
    finally:
        rt.close()


def test_locked_prospects_are_not_audited(harness: Harness) -> None:
    csrf = _owner(harness)
    p = _prospect(harness, ProspectState.DO_NOT_CONTACT)
    r = harness.client.post(f"/api/v1/prospects/{p.id}/audit", headers=csrf)
    assert r.status_code == 409


def test_qualification_awaiting_audit_queues_an_audit(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    p = _prospect(harness, ProspectState.VERIFIED)
    rt = _runtime(harness, FakeSandbox())
    try:
        with harness.db() as db:
            enqueue(
                db,
                QUALIFY,
                idempotency_key="q1",
                payload={"prospect_id": str(p.id), "campaign_id": None},
                now=harness.clock(),
            )
            db.commit()
        drain(rt, ["qualification", "audit"])
        with harness.db() as db:
            types = [j.job_type for j in db.scalars(select(Job).order_by(Job.created_at))]
        assert (
            types[:2] == ["prospect.qualify", "prospect.audit"]
            and types.count("prospect.qualify") == 2
        )
    finally:
        rt.close()
