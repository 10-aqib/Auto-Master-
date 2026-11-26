"""Maintenance CLI: Place ID refresh and transient purge (mock source; no network)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from tests.conftest import Harness
from webforge_api.cli import main
from webforge_api.models import ExternalPlaceIdentifier, SourceRegistration
from webforge_api.models.enums import PlaceIdStatus, SourceStatus
from webforge_api.sources.transient import TransientStore


def _env(h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    s = h.settings
    for name, value in {
        "DATABASE_URL": s.database_url.get_secret_value(),
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "APP_SECRET_KEY": s.app_secret_key.get_secret_value(),
        "JWT_SIGNING_KEY": s.jwt_signing_key.get_secret_value(),
        "ENCRYPTION_KEY": s.encryption_key.get_secret_value(),
        "LOOKUP_HASH_KEY": s.lookup_hash_key.get_secret_value(),
    }.items():
        monkeypatch.setenv(name, value)


def test_purge_transient_cli(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    past = datetime.now(UTC) - timedelta(days=40)
    with harness.db() as db:
        TransientStore(db, harness.crypto, past).put(
            "google_places", "ChIJz", "location", "1,2", 86400
        )
    _env(harness, monkeypatch)
    assert main(["purge-transient"]) == 0
    assert "Purged 1 expired" in capsys.readouterr().out


def test_refresh_cli_fails_closed_when_rate_limiter_down(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    with harness.db() as db:
        reg = db.scalars(
            select(SourceRegistration).where(SourceRegistration.key == "mock_places")
        ).one()
        reg.status = SourceStatus.ENABLED
        db.add(ExternalPlaceIdentifier(provider="mock_places", place_id="mock_0123456789_01",
                                       last_checked_at=datetime.now(UTC) - timedelta(days=500)))  # fmt: skip
        db.commit()
    _env(harness, monkeypatch)
    assert main(["refresh-place-ids"]) == 1  # Redis unreachable -> refuse, never call unthrottled
    assert "Usage limits cannot be checked" in capsys.readouterr().err
    with harness.db() as db:
        assert db.scalars(select(ExternalPlaceIdentifier.status)).one() is PlaceIdStatus.ACTIVE
