"""Login, logout, refresh rotation/reuse, revocation, lockout and session expiry."""

from __future__ import annotations

from sqlalchemy import select

from tests.conftest import PASSWORD, Harness
from webforge_api.models import ActivityLog, UserSession
from webforge_api.models.enums import Role

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


def test_login_success_sets_secure_cookie_attributes(harness: Harness) -> None:
    user, _ = harness.create_user(Role.REVIEWER)
    r = harness.client.post(LOGIN, json={"email": user.email.upper(), "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["session"]["state"] == "active"
    assert "password_hash" not in r.text
    assert PASSWORD not in r.text
    cookies = r.headers.get_list("set-cookie")
    at = next(c for c in cookies if c.startswith("wf_at="))
    rt = next(c for c in cookies if c.startswith("wf_rt="))
    csrf = next(c for c in cookies if c.startswith("wf_csrf="))
    for c in (at, rt):
        assert "HttpOnly" in c
        assert "SameSite=lax" in c
        assert "Path=/" in c
    assert "HttpOnly" not in csrf
    assert body["csrf_token"] in csrf


def test_secure_cookies_use_host_prefix(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = harness_factory(cookie_secure=True)
    user, _ = h.create_user(Role.REVIEWER)
    r = h.client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    cookies = r.headers.get_list("set-cookie")
    assert any(c.startswith("__Host-wf_at=") and "Secure" in c for c in cookies)
    assert any(c.startswith("__Host-wf_rt=") and "Secure" in c for c in cookies)


def test_login_failure_is_generic_for_unknown_and_wrong_password(harness: Harness) -> None:
    user, _ = harness.create_user(Role.REVIEWER)
    wrong = harness.client.post(LOGIN, json={"email": user.email, "password": "nope-nope-nope"})
    unknown = harness.client.post(
        LOGIN, json={"email": "ghost@example.test", "password": "nope-nope-nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["message"] == unknown.json()["message"]
    assert wrong.json()["code"] == unknown.json()["code"] == "invalid_credentials"
    assert wrong.json()["correlation_id"]


def test_inactive_user_cannot_log_in(harness: Harness) -> None:
    user, _ = harness.create_user(Role.REVIEWER)
    with harness.db() as db:
        db.get(type(user), user.id).is_active = False  # type: ignore[union-attr]
        db.commit()
    r = harness.client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 401


def test_me_requires_authentication(harness: Harness) -> None:
    r = harness.client.get(ME)
    assert r.status_code == 401
    assert r.json()["code"] == "not_authenticated"


def test_me_after_login(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.login(user.email)
    r = harness.client.get(ME)
    assert r.status_code == 200
    assert r.json()["user"]["email"] == user.email
    assert "password_hash" not in r.text


def test_logout_revokes_session_and_clears_cookies(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    csrf = harness.login(user.email)["csrf_token"]
    access = harness.cookie("wf_at")
    r = harness.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    assert harness.cookie("wf_at") is None
    # Replaying the old access token fails: the session row is revoked.
    harness.set_cookie("wf_at", access or "")
    assert harness.client.get(ME).json()["code"] == "session_revoked"


def test_logout_requires_csrf_token(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.login(user.email)
    r = harness.client.post("/api/v1/auth/logout")
    assert r.status_code == 403
    assert r.json()["code"] == "csrf_failed"
    r = harness.client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "0" * 64})
    assert r.json()["code"] == "csrf_failed"


def test_cross_origin_post_rejected(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    r = harness.client.post(
        LOGIN,
        json={"email": user.email, "password": PASSWORD},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "origin_not_allowed"
    ok = harness.client.post(
        LOGIN,
        json={"email": user.email, "password": PASSWORD},
        headers={"Origin": "http://localhost:3000"},
    )
    assert ok.status_code == 200


def test_access_token_expiry_then_refresh_rotates(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.login(user.email)
    first_refresh = harness.cookie("wf_rt")
    harness.clock.advance(minutes=16)
    assert harness.client.get(ME).json()["code"] == "token_expired"

    r = harness.client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    assert harness.cookie("wf_rt") not in (None, first_refresh)
    assert harness.client.get(ME).status_code == 200


def test_refresh_reuse_after_grace_revokes_session(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.login(user.email)
    stolen = harness.cookie("wf_rt")
    assert harness.client.post("/api/v1/auth/refresh").status_code == 200
    harness.clock.advance(seconds=31)

    harness.set_cookie("wf_rt", stolen or "")
    r = harness.client.post("/api/v1/auth/refresh")
    assert r.status_code == 401
    assert r.json()["code"] == "refresh_token_reused"
    with harness.db() as db:
        session = db.scalars(select(UserSession).where(UserSession.user_id == user.id)).one()
        assert session.revoke_reason == "refresh_token_reuse"
        assert db.scalar(
            select(ActivityLog).where(ActivityLog.action == "auth.refresh.reuse_detected")
        )
    # The legitimate holder of the newest token is also logged out.
    assert harness.client.get(ME).status_code == 401


def test_concurrent_refresh_within_grace_does_not_revoke(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.login(user.email)
    original = harness.cookie("wf_rt")
    assert harness.client.post("/api/v1/auth/refresh").status_code == 200
    harness.set_cookie("wf_rt", original or "")
    r = harness.client.post("/api/v1/auth/refresh")
    assert r.status_code == 200
    assert not any(c.startswith("wf_rt=") for c in r.headers.get_list("set-cookie"))


def test_refresh_fails_after_refresh_window(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.login(user.email)
    harness.clock.advance(days=8)
    assert harness.client.post("/api/v1/auth/refresh").json()["code"] == "session_revoked"


def test_absolute_session_lifetime_enforced(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.login(user.email)
    for _ in range(5):  # keep refreshing for 30+ days
        harness.clock.advance(days=6, hours=23)
        harness.client.post("/api/v1/auth/refresh")
    r = harness.client.post("/api/v1/auth/refresh")
    assert r.status_code == 401


def test_logout_all_revokes_every_session(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.login(user.email)  # session A
    csrf = harness.login(user.email)["csrf_token"]  # session B (current cookies)
    r = harness.client.post("/api/v1/auth/logout-all", headers={"X-CSRF-Token": csrf})
    assert r.json()["count"] == 2
    with harness.db() as db:
        rows = db.scalars(select(UserSession).where(UserSession.user_id == user.id)).all()
        assert all(s.revoked_at is not None for s in rows)


def test_list_and_revoke_own_sessions(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.login(user.email)
    csrf = harness.login(user.email)["csrf_token"]
    sessions = harness.client.get("/api/v1/auth/sessions").json()
    assert len(sessions) == 2
    other = next(s for s in sessions if not s["current"])
    r = harness.client.delete(
        f"/api/v1/auth/sessions/{other['id']}", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 204
    assert len(harness.client.get("/api/v1/auth/sessions").json()) == 1


def test_cannot_revoke_someone_elses_session(harness: Harness) -> None:
    a, _ = harness.create_user(Role.READ_ONLY)
    b, _ = harness.create_user(Role.READ_ONLY)
    harness.login(b.email)
    with harness.db() as db:
        b_session = db.scalars(select(UserSession).where(UserSession.user_id == b.id)).one()
    csrf = harness.login(a.email)["csrf_token"]
    r = harness.client.delete(
        f"/api/v1/auth/sessions/{b_session.id}", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 404


def test_account_lockout_after_repeated_failures(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = harness_factory(account_lockout_threshold=3, login_rate_limit_per_account_per_hour=100)
    user, _ = h.create_user(Role.READ_ONLY)
    for _ in range(3):
        h.client.post(LOGIN, json={"email": user.email, "password": "wrong-password-1"})
    # Correct password is refused while locked, with the same generic message.
    r = h.client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_credentials"
    h.clock.advance(minutes=16)
    assert h.client.post(LOGIN, json={"email": user.email, "password": PASSWORD}).status_code == 200
    with h.db() as db:
        assert db.scalar(select(ActivityLog).where(ActivityLog.action == "auth.account.locked"))


def test_login_rate_limited_per_ip(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = harness_factory(login_rate_limit_per_ip_per_minute=3)
    for i in range(3):
        h.client.post(LOGIN, json={"email": f"x{i}@example.test", "password": "whatever-123"})
    r = h.client.post(LOGIN, json={"email": "y@example.test", "password": "whatever-123"})
    assert r.status_code == 429
    assert r.json()["code"] == "rate_limited"
    assert r.headers["retry-after"] == "60"


def test_login_rate_limited_per_account(harness_factory) -> None:  # type: ignore[no-untyped-def]
    h = harness_factory(
        login_rate_limit_per_account_per_hour=2, login_rate_limit_per_ip_per_minute=50
    )
    for _ in range(2):
        h.client.post(LOGIN, json={"email": "victim@example.test", "password": "guess-guess-1"})
    r = h.client.post(LOGIN, json={"email": "VICTIM@example.test", "password": "guess-guess-1"})
    assert r.status_code == 429


def test_rate_limiter_outage_fails_closed(harness: Harness) -> None:
    from webforge_api.security.rate_limit import RateLimiterUnavailableError

    class Broken:
        def hit(self, key: str, *, limit: int, window_seconds: int) -> bool:
            raise RateLimiterUnavailableError

        def reset(self, key: str) -> None:
            raise RateLimiterUnavailableError

    harness.client.app.state.rate_limiter = Broken()  # type: ignore[attr-defined]
    user, _ = harness.create_user(Role.READ_ONLY)
    r = harness.client.post(LOGIN, json={"email": user.email, "password": PASSWORD})
    assert r.status_code == 503


def test_validation_errors_do_not_echo_input(harness: Harness) -> None:
    secret = "my-super-secret-password-value"
    r = harness.client.post(LOGIN, json={"email": "not-an-email", "password": secret, "extra": 1})
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "validation_error"
    assert "email" in body["field_errors"]
    assert "extra" in body["field_errors"]
    assert secret not in r.text


def test_login_activity_logged_without_password(harness: Harness) -> None:
    user, _ = harness.create_user(Role.READ_ONLY)
    harness.client.post(LOGIN, json={"email": user.email, "password": "wrong-password-xyz"})
    harness.login(user.email)
    with harness.db() as db:
        rows = db.scalars(select(ActivityLog).where(ActivityLog.action == "auth.login")).all()
    assert {r.outcome for r in rows} == {"failure", "success"}
    dump = str([r.metadata_json for r in rows])
    assert "wrong-password-xyz" not in dump
    assert PASSWORD not in dump
    assert all(r.ip_hash is None or len(r.ip_hash) == 64 for r in rows)


def test_password_rehash_not_needed_for_current_params(harness: Harness) -> None:
    from webforge_api.security import passwords

    assert not passwords.needs_rehash(passwords.hash_password(PASSWORD))
