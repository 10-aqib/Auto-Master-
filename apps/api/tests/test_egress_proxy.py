"""Egress proxy SSRF policy (local fake site; no internet)."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator

import httpx
import pytest

from tests.fixtures_http import FakeSite, fake_site, redirect
from webforge_api.egress_proxy import ProxyPolicy, serve


class ProxyThread:
    def __init__(self, policy: ProxyPolicy) -> None:
        self.loop = asyncio.new_event_loop()
        self.port = 0
        ready = threading.Event()

        async def start() -> None:
            server = await serve("127.0.0.1", 0, policy)
            self.port = server.sockets[0].getsockname()[1]
            self.server = server
            ready.set()

        def run() -> None:
            self.loop.run_until_complete(start())
            self.loop.run_forever()

        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        ready.wait(5)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def stop(self) -> None:
        self.loop.call_soon_threadsafe(self.server.close)
        self.loop.call_soon_threadsafe(self.loop.stop)


@pytest.fixture
def site() -> Iterator[FakeSite]:
    with fake_site() as s:
        s.page("/", "<h1>fixture</h1>")
        s.page("/big", "x" * 200_000)
        yield s


def _proxy(site: FakeSite, **kw: object) -> ProxyThread:
    policy = ProxyPolicy(
        allowed_ports=frozenset({site.port, 443}),
        address_allowed=lambda ip: ip == "127.0.0.1",  # pretend the fixture is public
        static_dns={
            "shop.example.test": ["127.0.0.1"],
            "mixed.example.test": ["127.0.0.1", "10.0.0.7"],
            "meta.example.test": ["169.254.169.254"],
        },
        **kw,  # type: ignore[arg-type]
    )
    return ProxyThread(policy)


def _client(p: ProxyThread) -> httpx.Client:
    return httpx.Client(proxy=p.url, timeout=5, trust_env=False)


def test_allowed_http_through_proxy(site: FakeSite) -> None:
    p = _proxy(site)
    try:
        with _client(p) as c:
            r = c.get(f"http://shop.example.test:{site.port}/")
        assert r.status_code == 200 and "fixture" in r.text
        assert site.requests[-1][1] == f"shop.example.test:{site.port}"
    finally:
        p.stop()


@pytest.mark.parametrize(
    "target",
    ["mixed.example.test", "meta.example.test", "127.0.0.2", "169.254.169.254", "10.1.2.3"],
)
def test_internal_targets_refused(site: FakeSite, target: str) -> None:
    p = _proxy(site)
    try:
        with _client(p) as c:
            r = c.get(f"http://{target}:{site.port}/")
        assert r.status_code == 403
        assert site.requests == []
    finally:
        p.stop()


def test_default_policy_blocks_loopback_and_metadata(site: FakeSite) -> None:
    p = ProxyThread(ProxyPolicy(allowed_ports=frozenset({site.port, 80, 443})))
    try:
        with _client(p) as c:
            for url in (
                f"http://127.0.0.1:{site.port}/",
                f"http://localhost:{site.port}/",
                "http://169.254.169.254/latest/",
            ):
                assert c.get(url).status_code == 403
        assert site.requests == []
    finally:
        p.stop()


def test_connect_tunnel_policy(site: FakeSite) -> None:
    p = _proxy(site)

    async def connect(target: str) -> str:
        reader, writer = await asyncio.open_connection("127.0.0.1", p.port)
        writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        await writer.drain()
        line = (await reader.readline()).decode()
        writer.close()
        return line

    try:
        assert " 200 " in asyncio.run(connect(f"shop.example.test:{site.port}"))
        assert " 403 " in asyncio.run(connect("meta.example.test:443"))
        assert " 403 " in asyncio.run(connect("shop.example.test:22"))  # port not allowed
        assert " 400 " in asyncio.run(connect("::1:443"))
    finally:
        p.stop()


def test_byte_cap_truncates_large_responses(site: FakeSite) -> None:
    p = _proxy(site, max_bytes=50_000)
    try:
        with _client(p) as c, pytest.raises(httpx.HTTPError):
            c.get(f"http://shop.example.test:{site.port}/big").read()
    finally:
        p.stop()


def test_redirect_target_is_checked_again_by_the_client_request(site: FakeSite) -> None:
    site.route("/r", lambda _h: redirect("http://meta.example.test/"))
    p = _proxy(site)
    try:
        with httpx.Client(proxy=p.url, timeout=5, trust_env=False, follow_redirects=True) as c:
            r = c.get(f"http://shop.example.test:{site.port}/r")
        assert r.status_code == 403  # the redirected hop goes through the proxy and is refused
    finally:
        p.stop()


def test_malformed_requests_rejected(site: FakeSite) -> None:
    p = _proxy(site)

    async def raw(data: bytes) -> str:
        reader, writer = await asyncio.open_connection("127.0.0.1", p.port)
        writer.write(data)
        await writer.drain()
        line = (await reader.readline()).decode()
        writer.close()
        return line

    try:
        assert " 400 " in asyncio.run(raw(b"GET /relative HTTP/1.1\r\nHost: x\r\n\r\n"))
        assert " 400 " in asyncio.run(raw(b"garbage\r\n\r\n"))
    finally:
        p.stop()
