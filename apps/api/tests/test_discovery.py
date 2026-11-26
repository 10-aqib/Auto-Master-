"""Phase 03 end to end: campaigns, discovery jobs, verification, dedupe, qualification."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select

from tests.conftest import Harness
from tests.fixtures_http import FakeSite, fake_site
from tests.test_sources_api import API_KEY, PRICES, _enable, _owner
from tests.test_website_verifier import policy_for
from webforge_api.models import (
    ExternalPlaceIdentifier,
    Job,
    Prospect,
    ProspectCampaign,
    ProspectMerge,
    QualificationResult,
)
from webforge_api.models.enums import JobStatus, ProspectState
from webforge_api.security.rate_limit import MemoryRateLimiter
from webforge_api.worker import Runtime, drain

QUEUES = ["discovery", "verification", "qualification"]


def page(name: str, schema_type: str = "Bakery") -> str:
    return (
        f'<html><head><title>{name}</title><script type="application/ld+json">'
        f'{{"@type":"{schema_type}","name":"{name}"}}</script></head><body>Hello</body></html>'
    )


class Google:
    """Fake Places API: each place has a Maps name and a website URL."""

    def __init__(self, places: list[tuple[str, str, str]]) -> None:
        self.places = places  # (place_id, display_name, website_uri)
        self.calls = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if request.url.path.endswith(":searchText"):
            size = json.loads(request.content)["pageSize"]
            return httpx.Response(200, json={"places": [
                {"id": pid, "displayName": {"text": name}} for pid, name, _ in self.places[:size]
            ]})  # fmt: skip
        pid = request.url.path.rsplit("/", 1)[-1]
        for p, name, site in self.places:
            if p == pid:
                return httpx.Response(
                    200, json={"id": p, "displayName": {"text": name}, "websiteUri": site}
                )
        return httpx.Response(404, json={})


@pytest.fixture
def site() -> Iterator[FakeSite]:
    with fake_site() as s:
        s.page("/", page("Lahore Fixture Bakery"))
        s.page("/locations/karachi", page("Lahore Fixture Bakery"))
        s.page("/en/", page("Lahore Fixture Bakery"))
        yield s


def _setup(
    harness_factory: Any, site: FakeSite, places: list[tuple[str, str, str]], **settings: Any
) -> tuple[Harness, Google, Runtime, dict[str, str]]:
    google = Google(places)
    base: dict[str, Any] = {
        "google_places_api_enabled": True, "google_maps_api_key": API_KEY,
        "google_places_daily_budget_minor": 1000, "google_places_daily_request_cap": 100,
        "google_places_max_requests_per_campaign": 50,
        "google_places_sku_prices_minor_per_1000": json.dumps(PRICES),
    }  # fmt: skip
    base |= settings
    h = harness_factory(
        app_kwargs={
            "places_transport": httpx.MockTransport(google),
            "fetch_policy": policy_for(site),
        },
        **base,
    )
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    _enable(h, csrf, "official_website")
    rt = Runtime(h.settings, limiter=MemoryRateLimiter(), connectors=h.client.app.state.connectors,
                 fetch_policy=policy_for(site), clock=h.clock)  # fmt: skip
    return h, google, rt, csrf


def _campaign(h: Harness, csrf: dict[str, str], **overrides: Any) -> str:
    body: dict[str, Any] = {
        "name": "Lahore bakeries", "target_countries": ["PK"], "industries": ["bakery"],
        "queries": ["bakeries in Lahore"], "source_key": "google_places", "region_code": "PK",
        "candidate_cap": 10, "daily_budget_minor": 100, "monthly_budget_minor": 1000,
    }  # fmt: skip
    body |= overrides
    r = h.client.post("/api/v1/campaigns", json=body, headers=csrf)
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _resume(h: Harness, csrf: dict[str, str]) -> None:
    r = h.client.put(
        "/api/v1/controls/global_pause", json={"enabled": False, "reason": "testing"}, headers=csrf
    )
    assert r.status_code == 200 and r.json()["effective"] is False, r.text


def _activate(h: Harness, csrf: dict[str, str], cid: str) -> None:
    r = h.client.post(f"/api/v1/campaigns/{cid}/activate", json={"reason": "go"}, headers=csrf)
    assert r.status_code == 200, r.text


def test_campaign_validation_and_rbac(harness: Harness) -> None:
    csrf = _owner(harness)
    bad = harness.client.post("/api/v1/campaigns", json={
        "name": "Xy", "target_countries": ["pak"], "industries": ["unicorns"], "queries": ["a b c", "A B C"],
        "source_key": "google_places", "region_code": "IN", "candidate_cap": 5,
        "daily_budget_minor": 0, "monthly_budget_minor": 0}, headers=csrf)  # fmt: skip
    assert bad.status_code == 422
    assert set(bad.json()["field_errors"]) == {
        "industries",
        "target_countries",
        "region_code",
        "queries",
    }
    cid = _campaign(harness, csrf, source_key="mock_places", daily_budget_minor=0)
    r = harness.client.post(
        f"/api/v1/campaigns/{cid}/activate", json={"reason": "go"}, headers=csrf
    )
    assert r.status_code == 409 and r.json()["code"] == "not_ready"
    detail = harness.client.get(f"/api/v1/campaigns/{cid}").json()
    failing = {c["code"] for c in detail["readiness"] if not c["ok"]}
    assert failing == {"source", "verification"}

    from tests.test_rbac import _login_as
    from webforge_api.models.enums import Role

    other = harness.client
    reviewer_csrf = {"X-CSRF-Token": _login_as(harness, Role.REVIEWER)}
    assert other.get("/api/v1/campaigns").status_code == 200
    assert other.post("/api/v1/campaigns", json={}, headers=reviewer_csrf).status_code in (403, 422)
    assert (
        other.post(f"/api/v1/campaigns/{cid}/pause", json={}, headers=reviewer_csrf).status_code
        == 403
    )


def test_full_discovery_flow_with_dedupe_and_branches(harness_factory: Any, site: FakeSite) -> None:
    base = f"http://bakery.example.test:{site.port}"
    places = [
        ("ChIJplaceA000000001", "Lahore Fixture Bakery", f"{base}/"),
        (
            "ChIJplaceB000000002",
            "Lahore Fixture Bakery Gulberg",
            f"{base}/en/",
        ),  # same site (language path)
        (
            "ChIJplaceC000000003",
            "Lahore Fixture Bakery Karachi",
            f"{base}/locations/karachi",
        ),  # branch
        ("ChIJplaceD000000004", "No Website Cafe", ""),
    ]
    h, _google, rt, csrf = _setup(harness_factory, site, places)
    try:
        cid = _campaign(h, csrf)
        _activate(h, csrf, cid)
        blocked = h.client.post(f"/api/v1/campaigns/{cid}/discover", headers=csrf)
        assert blocked.json()["code"] == "system_paused"  # seeded paused (fail closed)
        _resume(h, csrf)
        jobs = h.client.post(f"/api/v1/campaigns/{cid}/discover", headers=csrf).json()
        again = h.client.post(f"/api/v1/campaigns/{cid}/discover", headers=csrf).json()
        assert [j["id"] for j in jobs] == [j["id"] for j in again]  # idempotent per day
        assert drain(rt, QUEUES) == 1 + 4 + 2  # search, 4 verifications, 2 qualifications

        with h.db() as db:
            prospects = db.scalars(select(Prospect).order_by(Prospect.branch_key)).all()
            assert [(p.verified_domain, p.branch_key) for p in prospects] == [
                ("bakery.example.test", ""), ("bakery.example.test", "/locations/karachi"),
            ]  # fmt: skip
            assert all(p.business_name == "Lahore Fixture Bakery" for p in prospects)
            assert all(p.industry == "bakery" for p in prospects)
            linked = db.scalars(
                select(ExternalPlaceIdentifier).where(
                    ExternalPlaceIdentifier.prospect_id == prospects[0].id
                )
            ).all()
            assert len(linked) == 2  # place A and B dedupe to the same prospect
            assert db.scalar(select(func.count()).select_from(ProspectCampaign)) == 2
            result = db.scalars(
                select(QualificationResult).where(
                    QualificationResult.prospect_id == prospects[0].id
                )
            ).one()
            comps = result.components
            assert comps["business_fit"]["score"] == 15 and comps["website_presence"]["score"] == 10
            assert comps["mobile_experience"]["score"] is None  # unknown stays unknown
            assert result.outcome.value == "INVESTIGATE" and result.reason_codes == [
                "awaiting_audit_evidence"
            ]
            assert float(result.evidence_coverage) == 0.35
            assert prospects[0].state is ProspectState.QUALIFYING
            dump = " ".join(
                json.dumps(r.components) for r in db.scalars(select(QualificationResult))
            )
            assert "Gulberg" not in dump and "No Website Cafe" not in dump
        detail = h.client.get(f"/api/v1/campaigns/{cid}").json()
        assert detail["stats"]["prospects"] == 2 and detail["stats"]["candidates"] == 4
        p = h.client.get(f"/api/v1/prospects/{prospects[0].id}").json()
        assert {f["fact_field"] for f in p["facts"]} >= {
            "business_name",
            "industry",
            "verified_domain",
        }
        assert len(p["place_ids"]) == 2
    finally:
        rt.close()


def test_candidate_cap_limits_and_stops_search(harness_factory: Any, site: FakeSite) -> None:
    places = [(f"ChIJcap{i:012d}", f"Place {i}", "") for i in range(5)]
    h, _google, rt, csrf = _setup(harness_factory, site, places)
    try:
        cid = _campaign(h, csrf, candidate_cap=2, queries=["bakeries in Lahore", "cakes in Lahore"])
        _activate(h, csrf, cid)
        _resume(h, csrf)
        h.client.post(f"/api/v1/campaigns/{cid}/discover", headers=csrf)
        drain(rt, QUEUES)
        with h.db() as db:
            assert db.scalar(select(func.count()).select_from(ExternalPlaceIdentifier)) == 2
            statuses = {
                j.payload.get("query"): j.status
                for j in db.scalars(select(Job).where(Job.job_type == "discovery.search"))
            }
        assert JobStatus.CANCELLED in statuses.values()  # second query hit the cap
    finally:
        rt.close()


def test_policy_failure_blocks_ingestion(harness_factory: Any, site: FakeSite) -> None:
    places = [
        ("ChIJpolicy00000001", "Lahore Fixture Bakery", f"http://bakery.example.test:{site.port}/")
    ]
    h, _google, rt, csrf = _setup(harness_factory, site, places)
    try:
        cid = _campaign(h, csrf)
        _activate(h, csrf, cid)
        _resume(h, csrf)
        h.client.post(f"/api/v1/campaigns/{cid}/discover", headers=csrf)
        h.client.post(
            "/api/v1/sources/official_website/disable",
            json={"reason": "policy changed"},
            headers=csrf,
        )
        drain(rt, QUEUES)
        with h.db() as db:
            assert db.scalar(select(func.count()).select_from(Prospect)) == 0
            verify = db.scalars(select(Job).where(Job.job_type == "discovery.verify")).one()
            assert verify.status is JobStatus.FAILED and verify.error_code == "source_disabled"
    finally:
        rt.close()


def test_campaign_pause_defers_and_archive_cancels(harness_factory: Any, site: FakeSite) -> None:
    places = [
        ("ChIJpause000000001", "Lahore Fixture Bakery", f"http://bakery.example.test:{site.port}/")
    ]
    h, google, rt, csrf = _setup(harness_factory, site, places)
    try:
        cid = _campaign(h, csrf)
        _activate(h, csrf, cid)
        _resume(h, csrf)
        h.client.post(f"/api/v1/campaigns/{cid}/discover", headers=csrf)
        h.client.post(f"/api/v1/campaigns/{cid}/pause", json={"reason": "hold"}, headers=csrf)
        drain(rt, QUEUES)
        assert google.calls == 0
        with h.db() as db:
            job = db.scalars(select(Job)).one()
            assert job.status is JobStatus.QUEUED and job.attempts == 0
        h.client.post(f"/api/v1/campaigns/{cid}/archive", json={"reason": "done"}, headers=csrf)
        with h.db() as db:
            assert db.scalars(select(Job)).one().status is JobStatus.CANCELLED
    finally:
        rt.close()


def test_global_pause_defers_work_and_only_owner_resumes(
    harness_factory: Any, site: FakeSite
) -> None:
    from tests.test_rbac import _login_as
    from webforge_api.models.enums import Role

    places = [
        ("ChIJgp000000000001", "Lahore Fixture Bakery", f"http://bakery.example.test:{site.port}/")
    ]
    h, google, rt, csrf = _setup(harness_factory, site, places)
    try:
        cid = _campaign(h, csrf)
        _activate(h, csrf, cid)
        _resume(h, csrf)
        h.client.post(f"/api/v1/campaigns/{cid}/discover", headers=csrf)
        r = h.client.put(
            "/api/v1/controls/global_pause",
            json={"enabled": True, "reason": "incident"},
            headers=csrf,
        )
        assert r.json()["effective"] is True
        drain(rt, QUEUES)
        assert google.calls == 0
        admin_csrf = {"X-CSRF-Token": _login_as(h, Role.ADMIN)}
        r = h.client.put(
            "/api/v1/controls/global_pause",
            json={"enabled": False, "reason": "x y z"},
            headers=admin_csrf,
        )
        assert r.status_code == 403
    finally:
        rt.close()


def test_do_not_contact_persists_across_campaigns(harness_factory: Any, site: FakeSite) -> None:
    places = [
        ("ChIJdnc0000000001", "Lahore Fixture Bakery", f"http://bakery.example.test:{site.port}/")
    ]
    h, _google, rt, csrf = _setup(harness_factory, site, places)
    try:
        _resume(h, csrf)
        a = _campaign(h, csrf, name="Campaign A")
        _activate(h, csrf, a)
        h.client.post(f"/api/v1/campaigns/{a}/discover", headers=csrf)
        drain(rt, QUEUES)
        pid = h.client.get("/api/v1/prospects").json()["items"][0]["id"]
        r = h.client.post(
            f"/api/v1/prospects/{pid}/review",
            json={"decision": "do_not_contact", "reason": "asked us not to"},
            headers=csrf,
        )
        assert r.json()["state"] == "DO_NOT_CONTACT"

        b = _campaign(h, csrf, name="Campaign B", queries=["cakes in Lahore"])
        _activate(h, csrf, b)
        h.client.post(f"/api/v1/campaigns/{b}/discover", headers=csrf)
        h.clock.advance(seconds=1)
        drain(rt, QUEUES)
        with h.db() as db:
            prospect = db.get(Prospect, pid)
            assert (
                prospect is not None
                and prospect.state is ProspectState.DO_NOT_CONTACT
                and prospect.do_not_contact
            )
            assert db.scalar(select(func.count()).select_from(Prospect)) == 1
            outcomes = [
                q.reason_codes
                for q in db.scalars(
                    select(QualificationResult).order_by(QualificationResult.created_at)
                )
            ]
        assert outcomes[-1] == ["do_not_contact"]
        # Reviewers cannot reopen; admins cannot lift do-not-contact; the owner can.
        from fastapi.testclient import TestClient

        from tests.test_rbac import _login_as
        from webforge_api.models.enums import Role

        admin = TestClient(h.client.app)
        h2 = Harness(h.settings, admin, h.clock, h.limiter, h.engine, h.sessions, h.crypto)
        admin_csrf = {"X-CSRF-Token": _login_as(h2, Role.ADMIN)}
        r = admin.post(
            f"/api/v1/prospects/{pid}/review",
            json={"decision": "reopen", "reason": "try again"},
            headers=admin_csrf,
        )
        assert r.status_code == 403
        r = h.client.post(
            f"/api/v1/prospects/{pid}/review",
            json={"decision": "reopen", "reason": "they asked back"},
            headers=csrf,
        )
        assert r.json()["state"] == "VERIFIED"
    finally:
        rt.close()


def test_manual_merge_keeps_history_and_redirects_rediscovery(
    harness_factory: Any, site: FakeSite
) -> None:
    base = f"http://bakery.example.test:{site.port}"
    places = [("ChIJm0000000000001", "Lahore Fixture Bakery", f"{base}/"),
              ("ChIJm0000000000002", "Lahore Fixture Bakery", f"{base}/locations/karachi")]  # fmt: skip
    h, _google, rt, csrf = _setup(harness_factory, site, places)
    try:
        _resume(h, csrf)
        cid = _campaign(h, csrf)
        _activate(h, csrf, cid)
        h.client.post(f"/api/v1/campaigns/{cid}/discover", headers=csrf)
        drain(rt, QUEUES)
        items = sorted(
            h.client.get("/api/v1/prospects").json()["items"], key=lambda p: p["branch_key"]
        )
        main, branch = items[0]["id"], items[1]["id"]
        r = h.client.post(
            "/api/v1/prospects/merge",
            json={
                "from_prospect_id": branch,
                "into_prospect_id": main,
                "reason": "same shop, owner confirmed",
            },
            headers=csrf,
        )
        assert r.status_code == 200, r.text
        with h.db() as db:
            merged = db.get(Prospect, branch)
            assert merged is not None and merged.state is ProspectState.MERGED
            m = db.scalars(select(ProspectMerge)).one()
            assert m.snapshot["branch_key"] == "/locations/karachi"
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(ExternalPlaceIdentifier)
                    .where(ExternalPlaceIdentifier.prospect_id == main)
                )
                == 2
            )
        assert all(
            p["state"] != "MERGED" for p in h.client.get("/api/v1/prospects").json()["items"]
        )
        again = h.client.post(
            "/api/v1/prospects/merge",
            json={"from_prospect_id": branch, "into_prospect_id": main, "reason": "again again"},
            headers=csrf,
        )
        assert again.json()["code"] == "already_merged"
    finally:
        rt.close()


def test_jobs_api_lists_and_retries(harness: Harness) -> None:
    csrf = _owner(harness)
    from webforge_api.services import jobs as q

    with harness.db() as db:
        job, _ = q.enqueue(
            db, q.JobSpec("x", "y"), idempotency_key="z", payload={}, now=harness.clock()
        )
        job.status = JobStatus.DEAD
        db.commit()
        jid = str(job.id)
    page = harness.client.get("/api/v1/jobs?status=DEAD").json()
    assert page["total"] == 1 and page["counts"]["DEAD"] == 1
    assert (
        harness.client.post(f"/api/v1/jobs/{jid}/retry", headers=csrf).json()["status"] == "QUEUED"
    )
    assert (
        harness.client.post(f"/api/v1/jobs/{jid}/cancel", headers=csrf).json()["status"]
        == "CANCELLED"
    )
