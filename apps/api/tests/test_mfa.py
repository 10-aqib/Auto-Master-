"""TOTP enrolment, verification, replay protection, recovery codes and enforcement."""

from __future__ import annotations

import pyotp
from sqlalchemy import select

from tests.conftest import PASSWORD, Harness
from webforge_api.models import MfaRecoveryCode, User, UserSession
from webforge_api.models.enums import Role


def _csrf(body: dict) -> dict[str, str]:  # type: ignore[type-arg]
    return {"X-CSRF-Token": body["csrf_token"]}


def test_owner_without_mfa_must_enroll_before_anything_else(harness: Harness) -> None:
    owner, _ = harness.create_user(Role.OWNER)
    body = harness.login(owner.email)
    assert body["session"]["state"] == "mfa_enrollment_required"
    r = harness.client.get("/api/v1/users")
    assert r.status_code == 403
    assert r.json()["code"] == "mfa_enrollment_required"
    assert harness.client.get("/api/v1/auth/me").status_code == 200


def test_full_enrollment_flow(harness: Harness) -> None:
    owner, _ = harness.create_user(Role.OWNER)
    body = harness.login(owner.email)
    setup = harness.client.post("/api/v1/auth/mfa/setup", headers=_csrf(body)).json()
    assert setup["otpauth_uri"].startswith("otpauth://totp/")
    assert setup["qr_svg_data_uri"].startswith("data:image/svg+xml")
    with harness.db() as db:
        stored = db.get(User, owner.id)
        assert stored is not None and stored.mfa_pending_secret_encrypted is not None
        assert setup["secret"].encode() not in stored.mfa_pending_secret_encrypted

    bad = harness.client.post(
        "/api/v1/auth/mfa/enable", json={"code": "000000"}, headers=_csrf(body)
    )
    assert bad.status_code == 401
    code = pyotp.TOTP(setup["secret"]).at(harness.clock())
    r = harness.client.post("/api/v1/auth/mfa/enable", json={"code": code}, headers=_csrf(body))
    assert r.status_code == 200
    enabled = r.json()
    assert len(enabled["recovery_codes"]) == 10
    assert enabled["session"]["state"] == "active"
    assert harness.client.get("/api/v1/users").status_code == 200
    with harness.db() as db:
        hashes = db.scalars(select(MfaRecoveryCode.code_hash)).all()
        assert enabled["recovery_codes"][0] not in hashes


def test_login_with_mfa_requires_second_factor(harness: Harness) -> None:
    user, secret = harness.create_user(Role.ADMIN, mfa=True)
    assert secret
    body = harness.login(user.email)
    assert body["session"]["state"] == "mfa_pending"
    assert harness.client.get("/api/v1/users").json()["code"] == "mfa_pending"
    # A pending session cannot be refreshed into a full one.
    assert harness.client.post("/api/v1/auth/refresh").json()["code"] == "mfa_pending"

    pending_access = harness.cookie("wf_at")
    r = harness.client.post(
        "/api/v1/auth/mfa/verify", json={"code": harness.totp(secret)}, headers=_csrf(body)
    )
    assert r.status_code == 200
    assert r.json()["session"]["state"] == "active"
    assert harness.cookie("wf_at") != pending_access
    # The pending session was replaced (no session fixation).
    harness.client.cookies.set("wf_at", pending_access or "")
    assert harness.client.get("/api/v1/auth/me").status_code == 401


def test_totp_code_cannot_be_replayed(harness: Harness) -> None:
    user, secret = harness.create_user(Role.ADMIN, mfa=True)
    assert secret
    code = harness.totp(secret)
    body = harness.login(user.email)
    assert (
        harness.client.post(
            "/api/v1/auth/mfa/verify", json={"code": code}, headers=_csrf(body)
        ).status_code
        == 200
    )
    body = harness.login(user.email)
    r = harness.client.post("/api/v1/auth/mfa/verify", json={"code": code}, headers=_csrf(body))
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_mfa_code"


def test_mfa_pending_session_expires_quickly(harness: Harness) -> None:
    user, secret = harness.create_user(Role.ADMIN, mfa=True)
    assert secret
    body = harness.login(user.email)
    harness.clock.advance(minutes=6)
    r = harness.client.post(
        "/api/v1/auth/mfa/verify", json={"code": harness.totp(secret)}, headers=_csrf(body)
    )
    assert r.status_code == 401


def test_recovery_code_works_once(harness: Harness) -> None:
    owner, _ = harness.create_user(Role.OWNER)
    body = harness.login(owner.email)
    setup = harness.client.post("/api/v1/auth/mfa/setup", headers=_csrf(body)).json()
    codes = harness.client.post(
        "/api/v1/auth/mfa/enable",
        json={"code": pyotp.TOTP(setup["secret"]).at(harness.clock())},
        headers=_csrf(body),
    ).json()["recovery_codes"]

    body = harness.login(owner.email)
    r = harness.client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": codes[0].upper(), "method": "recovery"},
        headers=_csrf(body),
    )
    assert r.status_code == 200
    assert harness.client.get("/api/v1/auth/me").json()["session"]["recovery_codes_remaining"] == 9

    body = harness.login(owner.email)
    again = harness.client.post(
        "/api/v1/auth/mfa/verify",
        json={"code": codes[0], "method": "recovery"},
        headers=_csrf(body),
    )
    assert again.status_code == 401


def test_enabling_mfa_revokes_other_sessions(harness: Harness) -> None:
    owner, _ = harness.create_user(Role.OWNER)
    harness.login(owner.email)
    body = harness.login(owner.email)
    setup = harness.client.post("/api/v1/auth/mfa/setup", headers=_csrf(body)).json()
    harness.client.post(
        "/api/v1/auth/mfa/enable",
        json={"code": pyotp.TOTP(setup["secret"]).at(harness.clock())},
        headers=_csrf(body),
    )
    with harness.db() as db:
        active = db.scalars(
            select(UserSession).where(
                UserSession.user_id == owner.id, UserSession.revoked_at.is_(None)
            )
        ).all()
    assert len(active) == 1 and active[0].mfa_verified


def test_owner_cannot_disable_required_mfa(harness: Harness) -> None:
    owner, secret = harness.create_user(Role.OWNER, mfa=True)
    csrf = harness.login_active(owner, secret)
    r = harness.client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": PASSWORD, "code": harness.totp(secret, steps_ahead=1)},  # type: ignore[arg-type]
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "mfa_required_for_role"


def test_reviewer_can_disable_optional_mfa(harness: Harness) -> None:
    user, secret = harness.create_user(Role.REVIEWER, mfa=True)
    assert secret
    csrf = harness.login_active(user, secret)
    r = harness.client.post(
        "/api/v1/auth/mfa/disable",
        json={"password": PASSWORD, "code": harness.totp(secret, steps_ahead=1)},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 204
    with harness.db() as db:
        stored = db.get(User, user.id)
        assert stored is not None and not stored.mfa_enabled and stored.mfa_secret_encrypted is None


def test_regenerate_recovery_codes(harness: Harness) -> None:
    user, secret = harness.create_user(Role.ADMIN, mfa=True)
    assert secret
    csrf = harness.login_active(user, secret)
    r = harness.client.post(
        "/api/v1/auth/mfa/recovery-codes",
        json={"code": harness.totp(secret, steps_ahead=1)},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    assert len(r.json()["recovery_codes"]) == 10


def test_mfa_verify_rate_limited(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = harness_factory(login_rate_limit_per_ip_per_minute=3)
    user, _ = h.create_user(Role.ADMIN, mfa=True)
    body = h.login(user.email)
    codes = [
        h.client.post(
            "/api/v1/auth/mfa/verify", json={"code": "123456"}, headers=_csrf(body)
        ).status_code
        for _ in range(4)
    ]
    assert codes[-1] == 429
