"""Provenance rules (independent sources only) and the policy-bound transient cache."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from tests.conftest import Harness
from webforge_api.models import Prospect, SourceRegistration, TransientSourceValue
from webforge_api.models.enums import SourceStatus
from webforge_api.services.provenance import FactEvidence, ProvenanceError, record_fact
from webforge_api.sources.transient import TransientPolicyError, TransientStore


def _prospect(h: Harness) -> Prospect:
    with h.db() as db:
        p = Prospect(business_name="Fixture Co")
        db.add(p)
        db.commit()
        db.expunge(p)
    return p


def _source(h: Harness, key: str, enabled: bool = True) -> SourceRegistration:
    with h.db() as db:
        src = db.scalars(select(SourceRegistration).where(SourceRegistration.key == key)).one()
        if enabled:
            src.status = SourceStatus.ENABLED
            src.terms_url, src.terms_version = "https://example.test/terms", "v1"
            src.terms_reviewed_at = datetime.now(UTC)
            owner, _ = h.create_user()
            src.reviewed_by_user_id = owner.id
            db.commit()
        db.expunge(src)
    return src


def _evidence(src: SourceRegistration, **kw: object) -> FactEvidence:
    values: dict[str, object] = {
        "source": src, "source_url": "https://fixture.example.test/", "retrieved_at": datetime.now(UTC),
        "confidence": 0.9, "method": "test",
    }  # fmt: skip
    values |= kw
    return FactEvidence(**values)  # type: ignore[arg-type]


def test_maps_source_cannot_back_a_fact(harness: Harness) -> None:
    p = _prospect(harness)
    places = _source(harness, "google_places")
    with harness.db() as db, pytest.raises(ProvenanceError) as info:
        record_fact(
            db, prospect_id=p.id, field="business_name", value="X", evidence=_evidence(places)
        )
    assert info.value.code == "source_not_independent"


def test_database_rejects_maps_provenance_even_if_code_is_bypassed(harness: Harness) -> None:
    p = _prospect(harness)
    with harness.db() as db, pytest.raises(IntegrityError):
        db.execute(
            text(
                "INSERT INTO prospect_sources (prospect_id, source_type, source_name, fact_field,"
                " safe_value, retrieved_at, confidence, verification_method, is_independent)"
                " VALUES (:p, 'GOOGLE_PLACES', 'Google', 'business_name', 'X', now(), 0.9, 'x', false)"
            ),
            {"p": p.id},
        )
        db.commit()


def test_fact_rules(harness: Harness) -> None:
    p = _prospect(harness)
    website = _source(harness, "official_website")
    with harness.db() as db:
        with pytest.raises(ProvenanceError, match="may not supply"):
            record_fact(db, prospect_id=p.id, field="phone", value="1", evidence=_evidence(website))
        with pytest.raises(ProvenanceError, match="source URL"):
            record_fact(db, prospect_id=p.id, field="business_name", value="X",
                        evidence=_evidence(website, source_url=""))  # fmt: skip
        row = record_fact(
            db,
            prospect_id=p.id,
            field="business_name",
            value="Fixture Co",
            evidence=_evidence(website),
        )
        db.commit()
        assert row.value_hash and row.is_independent and row.source_key == "official_website"


def test_disabled_source_cannot_back_a_fact(harness: Harness) -> None:
    p = _prospect(harness)
    website = _source(harness, "official_website", enabled=False)
    with harness.db() as db, pytest.raises(ProvenanceError, match="disabled"):
        record_fact(
            db, prospect_id=p.id, field="business_name", value="X", evidence=_evidence(website)
        )


def test_transient_cache_follows_registry_rules(harness: Harness) -> None:
    now = datetime.now(UTC)
    with harness.db() as db:
        store = TransientStore(db, harness.crypto, now)
        with pytest.raises(TransientPolicyError, match="may not be cached"):
            store.put("google_places", "ChIJx", "displayName", "Name", 60)
        with pytest.raises(TransientPolicyError, match="at most"):
            store.put("google_places", "ChIJx", "location", "1,2", 31 * 86400)
        store.put("google_places", "ChIJx", "location", "31.52,74.35", 30 * 86400)
        assert store.get("google_places", "ChIJx", "location") == "31.52,74.35"
        raw = db.scalars(select(TransientSourceValue.value_encrypted)).one()
        assert b"31.52" not in raw

    with harness.db() as db:
        later = TransientStore(db, harness.crypto, now + timedelta(days=31))
        assert later.get("google_places", "ChIJx", "location") is None
        assert later.purge_expired() == 1
        assert db.scalar(select(func.count()).select_from(TransientSourceValue)) == 0


def test_purge_disallowed_after_policy_change(harness: Harness) -> None:
    now = datetime.now(UTC)
    with harness.db() as db:
        TransientStore(db, harness.crypto, now).put(
            "google_places", "ChIJy", "location", "1,2", 3600
        )
        reg = db.scalars(
            select(SourceRegistration).where(SourceRegistration.key == "google_places")
        ).one()
        reg.cache_rules = {}
        db.commit()
        assert TransientStore(db, harness.crypto, now).purge_disallowed() == 1
