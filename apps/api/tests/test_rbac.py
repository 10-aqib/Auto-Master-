"""Positive and negative route access for every role."""

from __future__ import annotations

import uuid

import pytest

from tests.conftest import Harness
from webforge_api.models.enums import Role

ALL = (Role.OWNER, Role.ADMIN, Role.REVIEWER, Role.READ_ONLY)

# (method, path, roles allowed). Path "{target}" is replaced by a READ_ONLY user's id.
MATRIX = [
    ("GET", "/api/v1/auth/me", ALL),
    ("GET", "/api/v1/auth/sessions", ALL),
    ("GET", "/api/v1/users", (Role.OWNER, Role.ADMIN)),
    ("GET", "/api/v1/activity", (Role.OWNER, Role.ADMIN)),
    ("POST", "/api/v1/users/{target}/revoke-sessions", (Role.OWNER, Role.ADMIN)),
    ("POST", "/api/v1/users/{target}/reset-mfa", (Role.OWNER,)),
    ("PATCH", "/api/v1/users/{target}", (Role.OWNER, Role.ADMIN)),
]


def _login_as(harness: Harness, role: Role) -> str:
    mfa = role in (Role.OWNER, Role.ADMIN)
    user, secret = harness.create_user(role, mfa=mfa)
    return harness.login_active(user, secret)


@pytest.mark.parametrize("role", ALL)
@pytest.mark.parametrize(("method", "path", "allowed"), MATRIX)
def test_route_access(
    harness: Harness, role: Role, method: str, path: str, allowed: tuple[Role, ...]
) -> None:
    target, _ = harness.create_user(Role.READ_ONLY)
    csrf = _login_as(harness, role)
    kwargs: dict[str, object] = {"headers": {"X-CSRF-Token": csrf}}
    if method == "PATCH":
        kwargs["json"] = {"display_name": "Renamed"}
    r = harness.client.request(method, path.format(target=target.id), **kwargs)  # type: ignore[arg-type]
    if role in allowed:
        assert r.status_code in (200, 204), (role, path, r.text)
    else:
        assert r.status_code == 403, (role, path, r.text)
        assert r.json()["code"] == "forbidden"


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("GET", "/api/v1/users"),
        ("GET", "/api/v1/activity"),
        ("GET", "/api/v1/auth/sessions"),
        ("POST", f"/api/v1/users/{uuid.uuid4()}/reset-mfa"),
    ],
)
def test_unauthenticated_requests_rejected(harness: Harness, method: str, path: str) -> None:
    r = harness.client.request(method, path)
    assert r.status_code == 401
    assert r.json()["code"] == "not_authenticated"


def test_forged_access_token_rejected(harness: Harness) -> None:
    import jwt

    user, _ = harness.create_user(Role.OWNER)
    forged = jwt.encode(
        {"typ": "access", "sid": str(uuid.uuid4()), "sub": str(user.id), "iss": "webforge-api",
         "iat": 0, "exp": 9999999999},
        "wrong-key-wrong-key-wrong-key-wrong-key",
        algorithm="HS256",
    )  # fmt: skip
    harness.set_cookie("wf_at", forged)
    r = harness.client.get("/api/v1/users")
    assert r.status_code == 401
    assert r.json()["code"] == "invalid_token"


def test_alg_none_token_rejected(harness: Harness) -> None:
    import base64
    import json

    def b64(d: dict[str, object]) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    token = (
        f"{b64({'alg': 'none', 'typ': 'JWT'})}.{b64({'typ': 'access', 'sid': str(uuid.uuid4())})}."
    )
    harness.set_cookie("wf_at", token)
    assert harness.client.get("/api/v1/auth/me").status_code == 401


def test_password_change_required_gates_other_routes(harness: Harness) -> None:
    user, _ = harness.create_user(Role.REVIEWER, password_change_required=True)
    body = harness.login(user.email)
    assert body["session"]["state"] == "password_change_required"
    r = harness.client.get("/api/v1/auth/sessions")
    assert r.status_code == 403
    assert r.json()["code"] == "password_change_required"
