"""Phase 02 through the API: registry, Places search, ID-only persistence, budgets, verification."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from sqlalchemy import func, select, text

from tests.conftest import Harness
from tests.fixtures_http import FakeSite, fake_site
from tests.test_website_verifier import JSONLD, policy_for
from webforge_api.models import (
    ActivityLog,
    ApiUsage,
    Campaign,
    DomainVerification,
    ExternalPlaceIdentifier,
    Prospect,
    ProspectSource,
)
from webforge_api.models.enums import PlaceIdStatus, Role, UsageOutcome

API_KEY = "AIzaTESTKEY-not-real-0123456789abcdef"
GOOGLE_NAME = "Lahore Fixture Bakery (Pvt) Ltd"  # Maps content: must never be persisted
GOOGLE_ADDRESS = "77 Maps Only Road, Lahore"
PLACE_ID = "ChIJFixturePlace000000001"
PRICES = {
    "TEXT_SEARCH_PRO": 3200,
    "PLACE_DETAILS_ENTERPRISE": 2500,
    "PLACE_DETAILS_IDS_ONLY": 0,
}


class FakeGoogle:
    """httpx transport impersonating places.googleapis.com."""

    def __init__(self, site_port: int | None = None) -> None:
        self.site_port = site_port
        self.calls: list[httpx.Request] = []
        self.details_status = 200
        self.search_status = 200

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        assert request.headers["X-Goog-Api-Key"] == API_KEY
        assert "*" not in request.headers["X-Goog-FieldMask"]
        if request.url.path.endswith(":searchText"):
            if self.search_status != 200:
                return httpx.Response(self.search_status, json={"error": {}})
            return httpx.Response(
                200,
                json={"places": [{
                    "id": PLACE_ID,
                    "displayName": {"text": GOOGLE_NAME},
                    "formattedAddress": GOOGLE_ADDRESS,
                    "businessStatus": "OPERATIONAL",
                    "googleMapsUri": "https://maps.google.com/?cid=777",
                }]},
            )  # fmt: skip
        if self.details_status != 200:
            return httpx.Response(self.details_status, json={"error": {"status": "NOT_FOUND"}})
        body: dict[str, Any] = {"id": PLACE_ID, "displayName": {"text": GOOGLE_NAME}}
        if self.site_port:
            body["websiteUri"] = f"http://bakery.example.test:{self.site_port}/"
        return httpx.Response(200, json=body)


@pytest.fixture
def site() -> Iterator[FakeSite]:
    with fake_site() as s:
        s.page("/", f"<html><head><title>Home</title>{JSONLD}</head><body>Bread</body></html>")
        yield s


def _google_harness(
    harness_factory: Any, site: FakeSite | None, **overrides: Any
) -> tuple[Harness, FakeGoogle]:
    google = FakeGoogle(site.port if site else None)
    settings: dict[str, Any] = {
        "google_places_api_enabled": True,
        "google_maps_api_key": API_KEY,
        "google_places_daily_budget_minor": 1000,
        "google_places_daily_request_cap": 50,
        "google_places_max_requests_per_campaign": 5,
        "google_places_sku_prices_minor_per_1000": json.dumps(PRICES),
    }
    settings |= overrides
    app_kwargs: dict[str, Any] = {"places_transport": httpx.MockTransport(google)}
    if site:
        app_kwargs["fetch_policy"] = policy_for(site)
    return harness_factory(app_kwargs=app_kwargs, **settings), google


def _owner(h: Harness) -> dict[str, str]:
    owner, secret = h.create_user(Role.OWNER, mfa=True)
    return {"X-CSRF-Token": h.login_active(owner, secret)}


def _enable(h: Harness, csrf: dict[str, str], key: str, review: bool = True) -> None:
    if review:
        r = h.client.post(
            f"/api/v1/sources/{key}/review",
            json={"terms_url": "https://example.test/terms", "terms_version": "2026-11-26",
                  "review_notes": "Reviewed policies page, storage rules and attribution."},
            headers=csrf,
        )  # fmt: skip
        assert r.status_code == 200, r.text
    r = h.client.post(f"/api/v1/sources/{key}/enable", json={"reason": "test"}, headers=csrf)
    assert r.status_code == 200, r.text


def _search(
    h: Harness, csrf: dict[str, str], source: str = "google_places", **kw: Any
) -> httpx.Response:
    response: httpx.Response = h.client.post(
        "/api/v1/places/search",
        json={"source_key": source, "text_query": "bakeries in Lahore", "region_code": "PK", **kw},
        headers=csrf,
    )
    return response


def _all_rows_text(h: Harness) -> str:
    """Every row of every application table as JSON text."""
    with h.db() as db:
        tables = db.scalars(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename <> 'alembic_version'"
            )
        ).all()
        return "\n".join(
            str(db.scalar(text(f"SELECT coalesce(json_agg(t)::text, '') FROM \"{t}\" t")))
            for t in tables
        )


# ---------------------------------------------------------------------- registry


def test_all_sources_disabled_by_default(harness: Harness) -> None:
    csrf = _owner(harness)
    rows = harness.client.get("/api/v1/sources").json()
    assert {r["key"]: r["status"] for r in rows} == {
        "google_places": "DISABLED", "mock_places": "DISABLED", "official_website": "DISABLED",
    }  # fmt: skip
    assert all(not r["usable"] and r["blockers"] for r in rows)
    places = next(r for r in rows if r["key"] == "google_places")
    assert places["persistable_fields"] == ["place_id"]
    assert places["attribution_text"] == "Google Maps"
    r = _search(harness, csrf, "mock_places")
    assert r.status_code == 409
    assert r.json()["code"] == "source_disabled"


def test_enable_requires_terms_review_and_owner(harness: Harness) -> None:
    csrf = _owner(harness)
    r = harness.client.post(
        "/api/v1/sources/official_website/enable", json={"reason": "going live"}, headers=csrf
    )
    assert r.status_code == 409
    assert r.json()["code"] == "terms_review_required"

    admin, secret = harness.create_user(Role.ADMIN, mfa=True)
    from fastapi.testclient import TestClient

    other = TestClient(harness.client.app)
    body = other.post(
        "/api/v1/auth/login", json={"email": admin.email, "password": "Correct-Horse-Battery-9"}
    ).json()
    import pyotp

    body = other.post(
        "/api/v1/auth/mfa/verify",
        json={"code": pyotp.TOTP(secret or "").at(harness.clock())},
        headers={"X-CSRF-Token": body["csrf_token"]},
    ).json()
    admin_csrf = {"X-CSRF-Token": body["csrf_token"]}
    review = {"terms_url": "https://example.test/terms", "terms_version": "v1",
              "review_notes": "Admin attempting a review should be refused."}  # fmt: skip
    assert (
        other.post(
            "/api/v1/sources/official_website/review", json=review, headers=admin_csrf
        ).status_code
        == 403
    )
    _enable(harness, csrf, "official_website")
    # Admins may always disable (fail-safe direction).
    r = other.post(
        "/api/v1/sources/official_website/disable", json={"reason": "pause"}, headers=admin_csrf
    )
    assert r.json()["status"] == "DISABLED"
    with harness.db() as db:
        actions = set(
            db.scalars(select(ActivityLog.action).where(ActivityLog.entity_type == "source"))
        )
    assert {"source.terms_reviewed", "source.enabled", "source.disabled"} <= actions


@pytest.mark.parametrize("role", [Role.REVIEWER, Role.READ_ONLY])
def test_lower_roles_cannot_use_sources(harness: Harness, role: Role) -> None:
    user, _ = harness.create_user(role)
    csrf = {"X-CSRF-Token": harness.login_active(user, None)}
    assert harness.client.get("/api/v1/sources").status_code == 403
    assert _search(harness, csrf, "mock_places").status_code == 403


def test_review_requires_https_terms_url(harness: Harness) -> None:
    csrf = _owner(harness)
    r = harness.client.post(
        "/api/v1/sources/google_places/review",
        json={
            "terms_url": "http://insecure.example/terms",
            "terms_version": "1",
            "review_notes": "x" * 30,
        },
        headers=csrf,
    )
    assert r.status_code == 422


def test_google_blocked_by_env_switch_even_when_enabled(harness: Harness) -> None:
    csrf = _owner(harness)
    _enable(harness, csrf, "google_places")
    row = next(
        r for r in harness.client.get("/api/v1/sources").json() if r["key"] == "google_places"
    )
    assert row["status"] == "ENABLED" and not row["usable"]
    assert "GOOGLE_PLACES_API_ENABLED is false." in row["blockers"]
    assert _search(harness, csrf).json()["code"] == "source_disabled"


# ---------------------------------------------------------------------- search


def test_mock_search_persists_only_place_ids(harness: Harness) -> None:
    csrf = _owner(harness)
    _enable(harness, csrf, "mock_places", review=False)
    r = _search(harness, csrf, "mock_places", page_size=3)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["transient"] is True
    assert body["attribution"] == {
        "text": "Mock data - not Google Maps",
        "required": True,
        "is_mock": True,
    }
    assert body["new_place_ids"] == 3
    names = [p["display_name"] for p in body["places"]]
    assert all(names)
    dump = _all_rows_text(harness)
    assert not any(n in dump for n in names)
    with harness.db() as db:
        assert db.scalar(select(func.count()).select_from(ExternalPlaceIdentifier)) == 3
        usage = db.scalars(select(ApiUsage)).one()
        assert (usage.provider, usage.sku, usage.outcome, usage.cost_milliminor) == (
            "mock_places", "MOCK", UsageOutcome.SUCCESS, 0,
        )  # fmt: skip
    again = _search(harness, csrf, "mock_places", page_size=3).json()
    assert again["new_place_ids"] == 0


def test_google_search_stores_place_id_but_no_maps_content(harness_factory: Any) -> None:
    h, google = _google_harness(harness_factory, None)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    r = _search(h, csrf)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["attribution"] == {"text": "Google Maps", "required": True, "is_mock": False}
    assert body["sku"] == "TEXT_SEARCH_PRO"
    assert body["places"][0]["display_name"] == GOOGLE_NAME
    assert (
        body["places"][0]["identifier_id"]
        == h.client.get("/api/v1/places/identifiers").json()[0]["id"]
    )
    assert body["places"][0]["google_maps_uri"] == "https://maps.google.com/?cid=777"
    assert len(google.calls) == 1

    dump = _all_rows_text(h)
    assert PLACE_ID in dump
    for restricted in (GOOGLE_NAME, GOOGLE_ADDRESS, "maps.google.com", "OPERATIONAL"):
        assert restricted not in dump, f"Maps content persisted: {restricted}"
    assert API_KEY not in dump
    assert API_KEY not in json.dumps(h.client.get("/api/v1/sources").json())
    with h.db() as db:
        usage = db.scalars(select(ApiUsage)).one()
        assert (usage.sku, usage.cost_milliminor, usage.estimated_cost_minor) == (
            "TEXT_SEARCH_PRO",
            3200,
            4,
        )


def test_unpriced_sku_refused_before_any_call(harness_factory: Any) -> None:
    h, google = _google_harness(harness_factory, None, google_places_sku_prices_minor_per_1000="{}")
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    r = _search(h, csrf)
    assert r.status_code == 409
    assert r.json()["code"] == "price_not_configured"
    assert google.calls == []


def test_daily_request_cap_and_budget(harness_factory: Any) -> None:
    h, google = _google_harness(harness_factory, None, google_places_daily_request_cap=2)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    assert _search(h, csrf).status_code == 200
    assert _search(h, csrf).status_code == 200
    r = _search(h, csrf)
    assert r.json()["code"] == "daily_request_cap_reached"
    assert len(google.calls) == 2
    usage = h.client.get("/api/v1/usage/google_places").json()
    assert usage["summary"]["today"] == {"requests": 2, "cost_minor": 7}
    assert usage["summary"]["exhausted"] is True and usage["summary"]["warning"] is True
    h.clock.advance(days=1)
    assert h.client.post("/api/v1/auth/refresh").status_code == 200
    assert _search(h, csrf).status_code == 200  # new UTC day


def test_daily_budget_exhausted(harness_factory: Any) -> None:
    h, google = _google_harness(harness_factory, None, google_places_daily_budget_minor=5)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    assert _search(h, csrf).status_code == 200  # 3.2 of 5
    r = _search(h, csrf)  # would be 6.4
    assert r.json()["code"] == "daily_budget_exhausted"
    assert len(google.calls) == 1


def test_provider_error_records_unbilled_usage(harness_factory: Any) -> None:
    h, google = _google_harness(harness_factory, None)
    google.search_status = 503
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    r = _search(h, csrf)
    assert r.status_code == 503
    assert r.json()["code"] == "provider_unavailable"
    with h.db() as db:
        usage = db.scalars(select(ApiUsage)).one()
        assert usage.outcome is UsageOutcome.ERROR and usage.cost_milliminor == 0


def test_campaign_request_cap(harness_factory: Any) -> None:
    h, _ = _google_harness(harness_factory, None, google_places_max_requests_per_campaign=1)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    with h.db() as db:
        owner_id = db.scalar(text("SELECT id FROM users LIMIT 1"))
        camp = Campaign(name="Test campaign", created_by_user_id=owner_id, daily_budget_minor=100)
        db.add(camp)
        db.commit()
        cid = str(camp.id)
    assert _search(h, csrf, campaign_id=cid).status_code == 200
    assert _search(h, csrf, campaign_id=cid).json()["code"] == "campaign_request_cap_reached"
    with h.db() as db:
        assert db.scalars(select(ExternalPlaceIdentifier.campaign_id)).one() is not None


def test_provider_rate_limit(harness_factory: Any) -> None:
    h, _ = _google_harness(harness_factory, None, google_places_rate_limit_per_minute=1)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    assert _search(h, csrf).status_code == 200
    assert _search(h, csrf).status_code == 429


# ---------------------------------------------------------------------- verification


def test_verify_place_website_creates_prospect_from_official_site_only(
    harness_factory: Any, site: FakeSite
) -> None:
    h, google = _google_harness(harness_factory, site)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    _search(h, csrf)
    ident = h.client.get("/api/v1/places/identifiers").json()[0]

    r = h.client.post(f"/api/v1/places/identifiers/{ident['id']}/verify-website", headers=csrf)
    assert r.status_code == 409  # official_website not enabled yet
    assert r.json()["code"] == "source_disabled"

    _enable(h, csrf, "official_website")
    r = h.client.post(f"/api/v1/places/identifiers/{ident['id']}/verify-website", headers=csrf)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["verification"]["status"] == "VERIFIED"
    assert body["verification"]["candidate_origin"] == "google_places:websiteUri (transient)"
    assert google.calls[-1].headers["X-Goog-FieldMask"] == "id,displayName,websiteUri,googleMapsUri"

    with h.db() as db:
        prospect = db.get(Prospect, body["prospect_id"])
        assert prospect is not None
        assert prospect.business_name == "Lahore Fixture Bakery"  # the site's words, not Google's
        assert prospect.verified_domain == "bakery.example.test"
        facts = db.scalars(
            select(ProspectSource).where(ProspectSource.prospect_id == prospect.id)
        ).all()
        assert {f.fact_field for f in facts} == {"business_name", "website_url", "verified_domain"}
        assert all(
            f.source_type.value == "OFFICIAL_WEBSITE" and f.source_key == "official_website"
            for f in facts
        )
        assert all(f.confidence >= 0.85 and f.terms_version == "2026-11-26" for f in facts)
        assert db.get(ExternalPlaceIdentifier, ident["id"]).prospect_id == prospect.id  # type: ignore[union-attr]
    dump = _all_rows_text(h)
    assert GOOGLE_NAME not in dump and GOOGLE_ADDRESS not in dump
    with h.db() as db:
        skus = set(db.scalars(select(ApiUsage.sku)))
    assert skus == {"TEXT_SEARCH_PRO", "PLACE_DETAILS_ENTERPRISE"}


def test_obsolete_place_id_marked(harness_factory: Any, site: FakeSite) -> None:
    h, google = _google_harness(harness_factory, site)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    _enable(h, csrf, "official_website")
    _search(h, csrf)
    google.details_status = 404
    ident = h.client.get("/api/v1/places/identifiers").json()[0]
    body = h.client.post(
        f"/api/v1/places/identifiers/{ident['id']}/verify-website", headers=csrf
    ).json()
    assert body["place_obsolete"] is True
    assert h.client.get("/api/v1/places/identifiers").json()[0]["status"] == "OBSOLETE"


def test_owner_supplied_url_verification(harness_factory: Any, site: FakeSite) -> None:
    h, _ = _google_harness(harness_factory, site)
    csrf = _owner(h)
    _enable(h, csrf, "official_website")
    r = h.client.post(
        "/api/v1/verification/website",
        json={
            "url": f"http://bakery.example.test:{site.port}/",
            "expected_name": "Fixture Bakery Shop",
        },
        headers=csrf,
    )
    body = r.json()
    assert body["verification"]["status"] == "HOLD"
    assert body["verification"]["reason_codes"] == ["weak_name_match"]
    assert body["prospect_id"] is None
    recent = h.client.get("/api/v1/verification/recent").json()
    assert recent[0]["candidate_origin"] == "owner"


def test_verification_of_internal_address_rejected(harness: Harness) -> None:
    csrf = _owner(harness)
    _enable(harness, csrf, "official_website")
    r = harness.client.post(
        "/api/v1/verification/website",
        json={"url": "http://169.254.169.254/latest/meta-data/", "expected_name": "Metadata"},
        headers=csrf,
    )
    assert r.json()["verification"]["status"] == "REJECTED"
    with harness.db() as db:
        assert db.scalar(select(func.count()).select_from(Prospect)) == 0


def test_refresh_place_ids(harness_factory: Any, site: FakeSite) -> None:
    from webforge_api.services.places import PlacesService

    h, google = _google_harness(harness_factory, site)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    _search(h, csrf)
    h.clock.advance(days=400)
    google.details_status = 404
    from webforge_api.net.safe_fetch import SafeFetcher
    from webforge_api.sources.registry import SourceRegistry
    from webforge_api.sources.usage import UsageService
    from webforge_api.sources.website import WebsiteVerifier

    with h.db() as db:
        svc = PlacesService(
            db, h.settings, h.crypto, SourceRegistry(db, h.settings, h.crypto, h.clock()),
            UsageService(db, h.settings, h.limiter, h.clock()),
            h.client.app.state.connectors,  # type: ignore[attr-defined]
            WebsiteVerifier(SafeFetcher(policy_for(site)), "ua"), h.clock(),
        )  # fmt: skip
        assert svc.refresh_place_ids() == {"checked": 1, "obsolete": 1, "changed": 0}
        assert db.scalars(select(ExternalPlaceIdentifier.status)).one() is PlaceIdStatus.OBSOLETE
        assert (
            db.scalars(select(ApiUsage.sku).order_by(ApiUsage.occurred_at.desc())).first()
            == "PLACE_DETAILS_IDS_ONLY"
        )
        assert svc.refresh_place_ids() == {"checked": 0, "obsolete": 0, "changed": 0}
    assert google.calls[-1].headers["X-Goog-FieldMask"] == "id"
    _ = timedelta


def test_domain_verification_history_kept(harness: Harness) -> None:
    csrf = _owner(harness)
    _enable(harness, csrf, "official_website")
    for _ in range(2):
        harness.client.post(
            "/api/v1/verification/website",
            json={"url": "https://does-not-resolve.invalid/", "expected_name": "Nobody"},
            headers=csrf,
        )
    with harness.db() as db:
        rows = db.scalars(select(DomainVerification)).all()
    assert len(rows) == 2 and all(r.status.value == "HOLD" for r in rows)
