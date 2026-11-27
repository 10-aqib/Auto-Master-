"""Phase 11: backup encryption format, backup status and operational alerts."""

from __future__ import annotations

import base64
import io
import os
from datetime import timedelta
from typing import Any

import pytest

from tests.conftest import Harness
from tests.test_sources_api import _owner
from webforge_api import backup, ops_alerts
from webforge_api.models import ActivityLog, BackupRun

KEY = base64.urlsafe_b64encode(os.urandom(32)).decode()


def roundtrip(data: bytes, key: str = KEY) -> bytes:
    enc, dec = io.BytesIO(), io.BytesIO()
    backup.encrypt_stream(io.BytesIO(data), enc, backup.load_key(key))
    backup.decrypt_stream(io.BytesIO(enc.getvalue()), dec, backup.load_key(key))
    return dec.getvalue()


@pytest.mark.parametrize("size", [0, 1, backup.CHUNK - 1, backup.CHUNK, backup.CHUNK * 2 + 17])
def test_roundtrip_sizes(size: int) -> None:
    data = os.urandom(size)
    assert roundtrip(data) == data


def _encrypted(data: bytes) -> bytes:
    out = io.BytesIO()
    backup.encrypt_stream(io.BytesIO(data), out, backup.load_key(KEY))
    return out.getvalue()


def test_wrong_key_tamper_truncation_and_reordering_fail() -> None:
    blob = _encrypted(os.urandom(backup.CHUNK + 100))
    other = base64.urlsafe_b64encode(os.urandom(32)).decode()
    with pytest.raises(backup.BackupError, match="authentication"):
        backup.decrypt_stream(io.BytesIO(blob), io.BytesIO(), backup.load_key(other))
    tampered = bytearray(blob)
    tampered[40] ^= 1
    with pytest.raises(backup.BackupError):
        backup.decrypt_stream(io.BytesIO(bytes(tampered)), io.BytesIO(), backup.load_key(KEY))
    first_len = int.from_bytes(blob[4:8], "big")
    truncated = blob[
        : 4 + 4 + 12 + first_len
    ]  # drop the final chunk: the first chunk is not marked final
    with pytest.raises(backup.BackupError):
        backup.decrypt_stream(io.BytesIO(truncated), io.BytesIO(), backup.load_key(KEY))
    with pytest.raises(backup.BackupError, match="not a WFB1"):
        backup.decrypt_stream(io.BytesIO(b"PGDMP..."), io.BytesIO(), backup.load_key(KEY))


def test_key_validation() -> None:
    with pytest.raises(backup.BackupError):
        backup.load_key("")
    with pytest.raises(backup.BackupError):
        backup.load_key(base64.urlsafe_b64encode(b"short").decode())


def test_plaintext_is_not_visible_in_ciphertext() -> None:
    secret = b"owner@example.test password hash row" * 100
    assert b"owner@example.test" not in _encrypted(secret)


def _codes(alerts: list[Any]) -> set[str]:
    return {a.code for a in alerts}


def test_alerts_backups_logins_and_status(harness: Harness) -> None:
    _owner(harness)
    now = harness.clock()
    alerts = ops_alerts._db_checks(harness.db(), harness.settings, now, None)
    assert {"redis_unreachable", "backup_stale", "restore_test_stale"} <= _codes(alerts)
    ops = harness.client.get("/api/v1/operations").json()
    assert ops["backups"]["status"] == "unknown"
    with harness.db() as db:
        db.add(
            BackupRun(
                kind="backup",
                status="ok",
                finished_at=now - timedelta(hours=2),
                bytes=1234,
                location="local:/x",
            )
        )
        db.add(
            BackupRun(
                kind="restore_test", status="ok", finished_at=now - timedelta(hours=1), detail="ok"
            )
        )
        for _ in range(20):
            db.add(
                ActivityLog(
                    occurred_at=now, actor_type="anonymous", action="auth.login", outcome="failure"
                )
            )
        db.commit()
    alerts = ops_alerts._db_checks(harness.db(), harness.settings, now, None)
    assert "backup_stale" not in _codes(alerts) and "restore_test_stale" not in _codes(alerts)
    assert "login_anomaly" in _codes(alerts)
    assert harness.client.get("/api/v1/operations").json()["backups"]["status"] == "ok"
    with harness.db() as db:
        db.add(BackupRun(kind="backup", status="failed", finished_at=now, detail="disk full"))
        db.commit()
    assert "backup_failed" in _codes(
        ops_alerts._db_checks(harness.db(), harness.settings, now, None)
    )
    assert harness.client.get("/api/v1/operations").json()["backups"]["status"] == "stale"


def test_host_checks_skip_tls_for_http_urls(harness: Harness) -> None:
    alerts = ops_alerts._host_checks(harness.settings)
    assert "tls_check_failed" not in _codes(alerts)
