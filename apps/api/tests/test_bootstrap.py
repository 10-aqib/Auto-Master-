"""One-time owner bootstrap (service and CLI)."""

from __future__ import annotations

import io

import pytest
from sqlalchemy import select

from tests.conftest import PASSWORD, Harness
from webforge_api.cli import main
from webforge_api.models import ActivityLog, User
from webforge_api.models.enums import Role
from webforge_api.services.bootstrap import bootstrap_owner
from webforge_api.services.errors import ConflictError, ServiceError


def test_bootstrap_creates_single_owner_once(harness: Harness) -> None:
    with harness.db() as db:
        owner = bootstrap_owner(
            db,
            harness.crypto,
            email="Owner@Example.test",
            display_name="Muhammad Aqib",
            password=PASSWORD,
        )
        assert owner.role is Role.OWNER and owner.email == "owner@example.test"
        assert owner.password_hash.startswith("$argon2id$")
        assert db.scalar(select(ActivityLog).where(ActivityLog.action == "owner.bootstrapped"))
    with harness.db() as db, pytest.raises(ConflictError):
        bootstrap_owner(
            db, harness.crypto, email="b@example.test", display_name="B", password=PASSWORD
        )


def test_bootstrap_refused_when_any_user_exists(harness: Harness) -> None:
    harness.create_user(Role.REVIEWER)
    with harness.db() as db, pytest.raises(ConflictError):
        bootstrap_owner(
            db, harness.crypto, email="o@example.test", display_name="O", password=PASSWORD
        )


def test_bootstrap_enforces_password_policy(harness: Harness) -> None:
    with harness.db() as db, pytest.raises(ServiceError):
        bootstrap_owner(
            db, harness.crypto, email="o@example.test", display_name="O", password="weak"
        )


def test_owner_must_enroll_mfa_on_first_login(harness: Harness) -> None:
    with harness.db() as db:
        bootstrap_owner(
            db, harness.crypto, email="o@example.test", display_name="O", password=PASSWORD
        )
    assert harness.login("o@example.test")["session"]["state"] == "mfa_enrollment_required"


def test_cli_bootstrap_and_migrate(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    s = harness.settings
    for name, value in {
        "DATABASE_URL": s.database_url.get_secret_value(),
        "APP_SECRET_KEY": s.app_secret_key.get_secret_value(),
        "JWT_SIGNING_KEY": s.jwt_signing_key.get_secret_value(),
        "ENCRYPTION_KEY": s.encryption_key.get_secret_value(),
        "LOOKUP_HASH_KEY": s.lookup_hash_key.get_secret_value(),
    }.items():
        monkeypatch.setenv(name, value)
    assert main(["migrate"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert (
        main(
            [
                "bootstrap-owner",
                "--email",
                "cli@example.test",
                "--name",
                "CLI Owner",
                "--password-stdin",
            ]
        )
        == 0
    )
    monkeypatch.setattr("sys.stdin", io.StringIO(PASSWORD + "\n"))
    assert (
        main(["bootstrap-owner", "--email", "x@example.test", "--name", "X", "--password-stdin"])
        == 1
    )
    out = capsys.readouterr()
    assert "Owner created" in out.out
    assert PASSWORD not in out.out + out.err
    with harness.db() as db:
        assert db.scalar(select(User.email).where(User.role == Role.OWNER)) == "cli@example.test"
    assert main(["purge-expired"]) == 0
