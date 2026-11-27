"""Independent provenance audit (internal pilot).

    python -m webforge_api.provenance_audit          prints a JSON report; exit 1 when any check fails

Read-only SQL over the stored data. It does not reuse the code paths that wrote the data, so it checks what is
actually in the database: every prospect fact has an independent, allowed source; every displayed prospect field
is backed by a recorded fact; no Google Maps Content is retained beyond what the terms permit.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

ALLOWED_SOURCES = ("OFFICIAL_WEBSITE", "REGISTRY", "LICENSED_PROVIDER", "OWNER_PROVIDED")
PROSPECT_FIELDS = ("business_name", "website_url", "verified_domain", "industry")


@dataclass
class Check:
    code: str
    description: str
    violations: int
    examples: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.violations == 0


def _q(db: Session, sql: str, **params: Any) -> list[Any]:
    return list(db.execute(text(sql), params).all())


def audit(db: Session) -> dict[str, Any]:
    checks: list[Check] = []

    def add(code: str, description: str, rows: list[Any]) -> None:
        checks.append(
            Check(
                code,
                description,
                len(rows),
                [" | ".join(str(c) for c in r)[:160] for r in rows[:5]],
            )
        )

    add("fact_source_allowed", "Every fact comes from an allowed, independent source (never Google Maps).",
        _q(db, "SELECT id, source_type, source_name FROM prospect_sources "
               "WHERE source_type::text <> ALL(:allowed) OR NOT is_independent", allowed=list(ALLOWED_SOURCES)))  # fmt: skip
    add("fact_has_evidence", "Every fact records a value or hash, a retrieval time, a method and a confidence in [0, 1].",
        _q(db, "SELECT id, fact_field FROM prospect_sources WHERE retrieved_at IS NULL OR verification_method IS NULL "
               "OR (safe_value IS NULL AND value_hash IS NULL) OR confidence < 0 OR confidence > 1"))  # fmt: skip
    add("official_site_on_verified_domain", "Facts from an official website were read on that prospect's verified domain.",
        _q(db, "SELECT s.id, s.source_url, p.verified_domain FROM prospect_sources s JOIN prospects p ON p.id = s.prospect_id "
               "WHERE s.source_type = 'OFFICIAL_WEBSITE' AND (p.verified_domain IS NULL OR s.source_url IS NULL OR NOT ("
               "split_part(split_part(s.source_url, '://', 2), '/', 1) = p.verified_domain OR "
               "split_part(split_part(s.source_url, '://', 2), '/', 1) LIKE '%.' || p.verified_domain OR "
               "split_part(split_part(split_part(s.source_url, '://', 2), '/', 1), ':', 1) = p.verified_domain))"))  # fmt: skip
    for f in PROSPECT_FIELDS:
        add(f"prospect_{f}_backed", f"Every prospect's {f} matches a recorded fact for that field.",
            _q(db, f"SELECT p.id, p.{f} FROM prospects p WHERE p.{f} IS NOT NULL AND p.state <> 'MERGED' AND NOT EXISTS ("  # noqa: S608
                   f"SELECT 1 FROM prospect_sources s WHERE s.prospect_id = p.id AND s.fact_field = :f AND s.safe_value = p.{f})", f=f))  # fmt: skip
    add("place_ids_only", "Google place records hold only the provider, Place ID, status and timestamps.",
        _q(db, "SELECT column_name FROM information_schema.columns WHERE table_name = 'external_place_identifiers' "
               "AND column_name NOT IN ('id','prospect_id','campaign_id','provider','place_id','status','first_seen_at',"
               "'last_checked_at','created_at','updated_at')"))  # fmt: skip
    add(
        "place_ids_refreshed",
        "Place IDs were checked within the last 12 months (Google's refresh recommendation).",
        _q(
            db,
            "SELECT id, place_id FROM external_place_identifiers WHERE coalesce(last_checked_at, first_seen_at) < now() - interval '365 days'",
        ),
    )
    add("maps_urls_not_retained", "A website URL from Google is kept only when the business's own site confirmed it.",
        _q(db, "SELECT id, candidate_url FROM domain_verifications WHERE candidate_origin LIKE :maps_origin "
               "AND status <> 'VERIFIED' AND (candidate_url <> '(not retained: Maps content)' OR domain IS NOT NULL OR final_url IS NOT NULL)",
               maps_origin="%:websiteUri (transient)"))  # fmt: skip
    add(
        "transient_cache_expired_purged",
        "No cached provider value is kept past its permitted lifetime.",
        _q(
            db,
            "SELECT id, source_key, field FROM transient_source_values WHERE expires_at <= now()",
        ),
    )
    add(
        "transient_cache_within_30_days",
        "No cached provider value was ever allowed to live longer than 30 days.",
        _q(
            db,
            "SELECT id, source_key, field FROM transient_source_values WHERE expires_at - fetched_at > interval '30 days'",
        ),
    )
    add("contacts_from_official_sources", "Every email contact was published on the official site or given by the business.",
        _q(db, "SELECT id, verification_method FROM email_contacts "
               "WHERE verification_method NOT IN ('published_on_official_website','provided_by_business') OR source_url IS NULL"))  # fmt: skip
    add("brief_facts_exist", "Every fact an AI brief cites existed in its facts snapshot.",
        _q(db, "SELECT b.id, f FROM design_briefs b, jsonb_array_elements_text(coalesce(b.brief->'facts_used','[]'::jsonb)) f "
               "WHERE NOT EXISTS (SELECT 1 FROM jsonb_array_elements(b.facts_snapshot->'facts') x WHERE x->>'id' = f)"))  # fmt: skip
    counts = dict(_q(db, "SELECT 'prospects', count(*) FROM prospects UNION ALL SELECT 'facts', count(*) FROM prospect_sources "
                         "UNION ALL SELECT 'place_ids', count(*) FROM external_place_identifiers "
                         "UNION ALL SELECT 'domain_checks', count(*) FROM domain_verifications"))  # fmt: skip
    return {"ok": all(c.ok for c in checks), "counts": counts,
            "checks": [asdict(c) | {"ok": c.ok} for c in checks]}  # fmt: skip


def main() -> int:
    from webforge_api.config import get_settings
    from webforge_api.db.session import build_engine, build_sessionmaker

    engine = build_engine(get_settings())
    try:
        with build_sessionmaker(engine)() as db:
            report = audit(db)
    finally:
        engine.dispose()
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
