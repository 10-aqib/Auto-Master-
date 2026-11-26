"""User administration rules and password changes."""

from __future__ import annotations

from sqlalchemy import select

from tests.conftest import PASSWORD, Harness
from webforge_api.models import ActivityLog, User, UserSession
from webforge_api.models.enums import Role

NEW_PW = "Another-Strong-Passphrase-7"


def _owner(harness: Harness) -> tuple[User, str]:
    owner, secret = harness.create_user(Role.OWNER, mfa=True)
    return owner, harness.login_active(owner, secret)


def test_owner_creates_admin_with_forced_password_change(harness: Harness) -> None:
    _, csrf = _owner(harness)
    r = harness.client.post(
        "/api/v1/users",
        json={
            "email": "New.Admin@Example.test",
            "display_name": "New Admin",
            "role": "ADMIN",
            "initial_password": "Temporary-Pass-12345",
        },
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["email"] == "new.admin@example.test"
    assert body["password_change_required"] is True
    assert "Temporary-Pass-12345" not in r.text


def test_cannot_create_second_owner(harness: Harness) -> None:
    _, csrf = _owner(harness)
    r = harness.client.post(
        "/api/v1/users",
        json={"email": "o2@example.test", "display_name": "O2", "role": "OWNER",
              "initial_password": "Temporary-Pass-12345"},
        headers={"X-CSRF-Token": csrf},
    )  # fmt: skip
    assert r.status_code == 403


def test_admin_limited_to_reviewer_and_read_only(harness: Harness) -> None:
    admin, secret = harness.create_user(Role.ADMIN, mfa=True)
    csrf = harness.login_active(admin, secret)
    payload = {
        "email": "a2@example.test",
        "display_name": "A2",
        "initial_password": "Temporary-Pass-12345",
    }
    assert (
        harness.client.post(
            "/api/v1/users", json={**payload, "role": "ADMIN"}, headers={"X-CSRF-Token": csrf}
        ).status_code
        == 403
    )
    assert (
        harness.client.post(
            "/api/v1/users", json={**payload, "role": "REVIEWER"}, headers={"X-CSRF-Token": csrf}
        ).status_code
        == 201
    )

    other_admin, _ = harness.create_user(Role.ADMIN)
    r = harness.client.patch(
        f"/api/v1/users/{other_admin.id}", json={"is_active": False}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 403
    reviewer, _ = harness.create_user(Role.REVIEWER)
    r = harness.client.patch(
        f"/api/v1/users/{reviewer.id}", json={"role": "READ_ONLY"}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 403  # only the owner changes roles


def test_duplicate_email_conflict(harness: Harness) -> None:
    _, csrf = _owner(harness)
    existing, _ = harness.create_user(Role.REVIEWER)
    r = harness.client.post(
        "/api/v1/users",
        json={"email": existing.email.upper(), "display_name": "Dup", "role": "REVIEWER",
              "initial_password": "Temporary-Pass-12345"},
        headers={"X-CSRF-Token": csrf},
    )  # fmt: skip
    assert r.status_code == 409
    assert r.json()["field_errors"] == {"email": "Already in use."}


def test_weak_initial_password_rejected(harness: Harness) -> None:
    _, csrf = _owner(harness)
    r = harness.client.post(
        "/api/v1/users",
        json={"email": "w@example.test", "display_name": "W", "role": "REVIEWER",
              "initial_password": "short"},
        headers={"X-CSRF-Token": csrf},
    )  # fmt: skip
    assert r.status_code == 422
    assert "initial_password" in r.json()["field_errors"]


def test_deactivation_revokes_sessions_immediately(harness: Harness) -> None:
    from fastapi.testclient import TestClient

    victim, _ = harness.create_user(Role.REVIEWER)
    other = TestClient(harness.client.app)
    other.post("/api/v1/auth/login", json={"email": victim.email, "password": PASSWORD})
    assert other.get("/api/v1/auth/me").status_code == 200

    _, csrf = _owner(harness)
    r = harness.client.patch(
        f"/api/v1/users/{victim.id}", json={"is_active": False}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 200 and r.json()["is_active"] is False
    assert other.get("/api/v1/auth/me").status_code == 401


def test_role_change_revokes_sessions_and_is_logged(harness: Harness) -> None:
    target, _ = harness.create_user(Role.READ_ONLY)
    harness.login(target.email)
    _, csrf = _owner(harness)
    r = harness.client.patch(
        f"/api/v1/users/{target.id}", json={"role": "REVIEWER"}, headers={"X-CSRF-Token": csrf}
    )
    assert r.json()["role"] == "REVIEWER"
    with harness.db() as db:
        sessions = db.scalars(select(UserSession).where(UserSession.user_id == target.id)).all()
        assert all(s.revoke_reason == "role_changed" for s in sessions)
        log = db.scalar(select(ActivityLog).where(ActivityLog.action == "user.updated"))
        assert log is not None
        assert log.metadata_json["changes"]["role"] == {"from": "READ_ONLY", "to": "REVIEWER"}


def test_cannot_modify_self_or_owner(harness: Harness) -> None:
    owner, csrf = _owner(harness)
    r = harness.client.patch(
        f"/api/v1/users/{owner.id}", json={"is_active": False}, headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 403
    assert r.json()["code"] == "cannot_modify_self"


def test_owner_resets_admin_mfa(harness: Harness) -> None:
    admin, _ = harness.create_user(Role.ADMIN, mfa=True)
    _, csrf = _owner(harness)
    r = harness.client.post(f"/api/v1/users/{admin.id}/reset-mfa", headers={"X-CSRF-Token": csrf})
    assert r.status_code == 204
    with harness.db() as db:
        stored = db.get(User, admin.id)
        assert stored is not None and not stored.mfa_enabled


def test_change_password_flow(harness: Harness) -> None:
    user, _ = harness.create_user(Role.REVIEWER, password_change_required=True)
    harness.login(user.email)  # other session
    csrf = harness.login(user.email)["csrf_token"]

    wrong = harness.client.post(
        "/api/v1/auth/password",
        json={"current_password": "not-it-at-all", "new_password": NEW_PW},
        headers={"X-CSRF-Token": csrf},
    )
    assert wrong.status_code == 401
    same = harness.client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": PASSWORD},
        headers={"X-CSRF-Token": csrf},
    )
    assert same.status_code == 422
    weak = harness.client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": "aaaaaaaaaaaaaa"},
        headers={"X-CSRF-Token": csrf},
    )
    assert weak.status_code == 422

    ok = harness.client.post(
        "/api/v1/auth/password",
        json={"current_password": PASSWORD, "new_password": NEW_PW},
        headers={"X-CSRF-Token": csrf},
    )
    assert ok.status_code == 200
    assert ok.json()["session"]["state"] == "active"
    with harness.db() as db:
        active = db.scalars(
            select(UserSession).where(
                UserSession.user_id == user.id, UserSession.revoked_at.is_(None)
            )
        ).all()
        assert len(active) == 1  # every older session was revoked
    assert harness.client.get("/api/v1/auth/sessions").status_code == 200
    assert (
        harness.client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": NEW_PW}
        ).status_code
        == 200
    )


def test_activity_endpoint_paginates_and_filters(harness: Harness) -> None:
    from fastapi.testclient import TestClient

    _owner(harness)
    other = TestClient(harness.client.app)
    for i in range(5):
        other.post("/api/v1/auth/login", json={"email": f"n{i}@example.test", "password": "x" * 12})

    seen: list[str] = []
    cursor = None
    while True:
        params: dict[str, str | int] = {"limit": 2, "action": "auth.login"}
        if cursor:
            params["cursor"] = cursor
        page = harness.client.get("/api/v1/activity", params=params).json()
        seen += [item["id"] for item in page["items"]]
        assert all(item["action"] == "auth.login" for item in page["items"])
        cursor = page["next_cursor"]
        if not cursor:
            break
    assert len(seen) == len(set(seen)) == 6  # 5 failures + the owner's login
    bad = harness.client.get("/api/v1/activity", params={"cursor": "!!notbase64"})
    assert bad.status_code == 400
