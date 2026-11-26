from __future__ import annotations

from fastapi.testclient import TestClient

from webforge_browser import app as app_module


def test_refuses_to_browse_without_proxy(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(app_module, "PROXY", None)
    monkeypatch.delenv("ALLOW_NO_PROXY", raising=False)
    client = TestClient(app_module.app)
    r = client.post("/audit", json={"url": "https://example.test/"})
    assert r.status_code == 503


def test_rejects_bad_input() -> None:
    client = TestClient(app_module.app)
    assert client.post("/audit", json={"url": "file:///etc/passwd"}).status_code == 422
    assert client.post("/audit", json={"url": "https://x.test/", "extra": 1}).status_code == 422
    assert client.get("/docs").status_code == 404


async def test_selftest_reports_not_isolated_on_a_normal_host() -> None:
    from webforge_browser.selftest import run_selftest

    result = await run_selftest(None)
    assert result["isolated"] is False  # no proxy configured -> never claims isolation
