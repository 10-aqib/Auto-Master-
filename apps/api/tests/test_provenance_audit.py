"""Internal pilot: the independent provenance audit passes on real flows and catches injected violations."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import text

from tests.fixtures_http import FakeSite
from tests.test_sources_api import _enable, _google_harness, _owner, _search, site  # noqa: F401 - fixture
from webforge_api.provenance_audit import audit


def _failed(report: dict[str, Any]) -> set[str]:
    return {c["code"] for c in report["checks"] if not c["ok"]}


def test_audit_passes_after_places_discovery_and_verification(
    harness_factory: Any,
    site: FakeSite,  # noqa: F811
) -> None:
    h, _ = _google_harness(harness_factory, site)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    _enable(h, csrf, "official_website")
    _search(h, csrf)
    ident = h.client.get("/api/v1/places/identifiers").json()[0]
    assert (
        h.client.post(
            f"/api/v1/places/identifiers/{ident['id']}/verify-website", headers=csrf
        ).status_code
        == 200
    )
    with h.db() as db:
        report = audit(db)
    assert report["ok"], _failed(report)
    assert (
        report["counts"]["prospects"] == 1
        and report["counts"]["facts"] == 4
        and report["counts"]["place_ids"] >= 1
    )


def test_audit_detects_injected_violations(harness_factory: Any, site: FakeSite) -> None:  # noqa: F811
    h, _ = _google_harness(harness_factory, site)
    csrf = _owner(h)
    _enable(h, csrf, "google_places")
    _enable(h, csrf, "official_website")
    _search(h, csrf)
    ident = h.client.get("/api/v1/places/identifiers").json()[0]
    pid = h.client.post(
        f"/api/v1/places/identifiers/{ident['id']}/verify-website", headers=csrf
    ).json()["prospect_id"]
    now = h.clock()
    with h.db() as db:
        # A name typed in from somewhere without a recorded source.
        db.execute(
            text("UPDATE prospects SET business_name = 'Name Copied From Maps' WHERE id = :id"),
            {"id": pid},
        )
        # A fact read from a page that is not on the prospect's verified domain.
        db.execute(
            text(
                "UPDATE prospect_sources SET source_url = 'https://directory.example.test/x' WHERE fact_field = 'industry'"
            )
        )
        # A Maps-supplied URL kept for a check that never verified.
        db.execute(text("INSERT INTO domain_verifications (id, candidate_url, candidate_origin, status, method, reason_codes, evidence, checked_at) "
                        "VALUES (gen_random_uuid(), 'https://kept.example.test/', :origin, 'HOLD', 'm', '{}', '{}', now())"), {"origin": "google_places:websiteUri (transient)"})  # fmt: skip
        # A cached provider value past its lifetime, and one allowed to live too long.
        for fetched, expires in (
            (now - timedelta(days=40), now - timedelta(days=10)),
            (now, now + timedelta(days=45)),
        ):
            db.execute(text("INSERT INTO transient_source_values (id, source_key, external_ref, field, value_encrypted, fetched_at, expires_at) "
                            "VALUES (gen_random_uuid(), 'google_places', :ref, 'location', '\\x00', :f, :e)"),
                       {"ref": str(fetched), "f": fetched, "e": expires})  # fmt: skip
        # A Place ID not refreshed for over a year.
        db.execute(
            text(
                "UPDATE external_place_identifiers SET last_checked_at = now() - interval '400 days', first_seen_at = now() - interval '400 days'"
            )
        )
        db.commit()
        report = audit(db)
    assert not report["ok"]
    assert {"prospect_business_name_backed", "official_site_on_verified_domain", "maps_urls_not_retained",
            "transient_cache_expired_purged", "transient_cache_within_30_days", "place_ids_refreshed"} <= _failed(report)  # fmt: skip
