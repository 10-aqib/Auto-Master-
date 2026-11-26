from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from tests.conftest import make_settings
from webforge_api.api.health import Checker, get_dependency_checks
from webforge_api.config import Settings
from webforge_api.main import create_app


async def _ok(_s: Settings) -> None:
    return None


async def _boom(_s: Settings) -> None:
    raise ConnectionError("password=hunter2 host=10.0.0.5")


async def _hang(_s: Settings) -> None:
    await asyncio.sleep(30)


def _client(checks: dict[str, Checker]) -> Iterator[TestClient]:
    app = create_app(make_settings(readiness_timeout_seconds=0.2))
    app.dependency_overrides[get_dependency_checks] = lambda: checks
    with TestClient(app) as client:
        yield client


@pytest.fixture
def healthy() -> Iterator[TestClient]:
    yield from _client({"postgres": _ok, "redis": _ok})


@pytest.fixture
def degraded() -> Iterator[TestClient]:
    yield from _client({"postgres": _ok, "redis": _boom})


@pytest.fixture
def hanging() -> Iterator[TestClient]:
    yield from _client({"postgres": _hang, "redis": _ok})


def test_live(healthy: TestClient) -> None:
    r = healthy.get("/health/live")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_ready_when_dependencies_ok(healthy: TestClient) -> None:
    r = healthy.get("/health/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert set(body["checks"]) == {"postgres", "redis"}
    assert r.headers["cache-control"] == "no-store"


def test_not_ready_reports_failure_without_leaking_details(degraded: TestClient) -> None:
    r = degraded.get("/health/ready")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["redis"] == {
        "status": "fail",
        "latency_ms": None,
        "error": "ConnectionError",
    }
    assert "hunter2" not in json.dumps(body)


def test_ready_times_out_slow_dependency(hanging: TestClient) -> None:
    r = hanging.get("/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"]["postgres"]["error"] == "TimeoutError"


def test_real_checks_fail_when_services_unreachable() -> None:
    settings = make_settings(
        database_url="postgresql://u:p@127.0.0.1:1/x",
        redis_url="redis://127.0.0.1:1/0",
        readiness_timeout_seconds=1,
    )
    with TestClient(create_app(settings)) as client:
        r = client.get("/health/ready")
    assert r.status_code == 503
    assert {c["status"] for c in r.json()["checks"].values()} == {"fail"}


def test_request_id_generated(healthy: TestClient) -> None:
    r = healthy.get("/health/live")
    assert len(r.headers["x-request-id"]) == 32


def test_safe_request_id_propagated(healthy: TestClient) -> None:
    r = healthy.get("/health/live", headers={"X-Request-ID": "trace-abc-12345"})
    assert r.headers["x-request-id"] == "trace-abc-12345"


def test_unsafe_request_id_replaced(healthy: TestClient) -> None:
    r = healthy.get("/health/live", headers={"X-Request-ID": "bad id\r\ninjected"})
    assert r.headers["x-request-id"] != "bad id\r\ninjected"
    assert len(r.headers["x-request-id"]) == 32


def test_docs_disabled_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    app = create_app(make_settings(app_env="production"))
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_unknown_route_returns_404(healthy: TestClient) -> None:
    assert healthy.get("/does-not-exist").status_code == 404
