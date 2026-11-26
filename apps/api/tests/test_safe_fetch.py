"""SSRF, DNS-rebinding, redirect and resource-limit defences of SafeFetcher."""

from __future__ import annotations

import datetime as dt
import ssl
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from tests.fixtures_http import FakeSite, fake_site, html, redirect, slow
from webforge_api.net.safe_fetch import (
    FetchBlockedError,
    FetchFailedError,
    FetchPolicy,
    SafeFetcher,
    is_public_address,
)
from webforge_api.net.urls import InvalidUrlError, normalize_url, same_site, site_domain

HOST = "site.example.test"


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1", "127.8.8.8", "10.1.2.3", "172.16.0.1", "192.168.1.1", "169.254.169.254",
        "100.64.0.1", "0.0.0.0", "224.0.0.1", "255.255.255.255", "198.18.0.1", "::1", "::",
        "fe80::1", "fc00::1", "fd00:ec2::254", "::ffff:127.0.0.1", "::ffff:10.0.0.1",
        "::ffff:169.254.169.254", "2002:7f00:1::1", "::127.0.0.1", "2001:db8::1", "not-an-ip",
    ],
)  # fmt: skip
def test_non_public_addresses_rejected(ip: str) -> None:
    assert not is_public_address(ip)


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "93.184.215.14", "2606:4700:4700::1111"])
def test_public_addresses_allowed(ip: str) -> None:
    assert is_public_address(ip)


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("ftp://example.com/", "invalid_url"),
        ("file:///etc/passwd", "invalid_url"),
        ("javascript:alert(1)", "invalid_url"),
        ("gopher://example.com/", "invalid_url"),
        ("http://user:pw@example.com/", "invalid_url"),
        ("http://example.com:22/", "blocked_port"),
        ("http://127.0.0.1/", "blocked_address"),
        ("http://[::1]/", "blocked_address"),
        ("http://169.254.169.254/latest/meta-data/", "blocked_address"),
        ("http://[::ffff:127.0.0.1]/", "blocked_address"),
    ],
)
def test_url_level_blocks(url: str, code: str) -> None:
    with pytest.raises(FetchBlockedError) as info:
        SafeFetcher(FetchPolicy()).get(url)
    assert info.value.code == code


@pytest.mark.parametrize("host", ["localhost", "2130706433", "0x7f.0.0.1", "127.1"])
def test_hosts_resolving_to_loopback_blocked_by_default_policy(host: str) -> None:
    with fake_site() as site:
        policy = FetchPolicy(allowed_ports=frozenset({site.port}))
        with pytest.raises(FetchBlockedError) as info:
            SafeFetcher(policy).get(f"http://{host}:{site.port}/")
        assert info.value.code == "blocked_address"
        assert site.requests == []  # nothing reached the server


def _test_policy(site: FakeSite, **kw: object) -> FetchPolicy:
    """Allows 127.0.0.1 ONLY, resolving fake test hosts to it (simulates a public site)."""
    mapping = {
        HOST: ["127.0.0.1"],
        f"www.{HOST}": ["127.0.0.1"],
        "other.example.test": ["127.0.0.1"],
    }
    extra: dict[str, list[str]] = kw.pop("extra_dns", {})  # type: ignore[assignment]
    mapping |= extra

    def resolver(host: str, _port: int) -> list[str]:
        if host not in mapping:
            raise OSError("NXDOMAIN")
        return list(mapping[host])

    return FetchPolicy(
        allowed_ports=frozenset({site.port, 80, 443}),
        address_allowed=lambda ip: ip == "127.0.0.1",
        resolver=resolver,
        **kw,  # type: ignore[arg-type]
    )


@pytest.fixture
def site() -> Iterator[FakeSite]:
    with fake_site() as s:
        yield s


def test_successful_fetch_sends_original_host_header(site: FakeSite) -> None:
    site.page("/", "<title>Hi</title>")
    result = SafeFetcher(_test_policy(site)).get(f"http://{HOST}:{site.port}/")
    assert result.status == 200
    assert result.connected_ip == "127.0.0.1"
    assert "Hi" in result.text()
    assert site.requests == [("/", f"{HOST}:{site.port}")]


def test_mixed_dns_answers_are_refused(site: FakeSite) -> None:
    site.page("/", "x")
    policy = _test_policy(site, extra_dns={HOST: ["127.0.0.1", "10.0.0.5"]})
    with pytest.raises(FetchBlockedError, match="non-public"):
        SafeFetcher(policy).get(f"http://{HOST}:{site.port}/")
    assert site.requests == []


def test_rebinding_cannot_change_the_connected_address(site: FakeSite) -> None:
    """Resolution happens once per connection and the vetted IP is the one used."""
    site.page("/", "x")
    calls: list[str] = []
    answers = iter([["127.0.0.1"], ["169.254.169.254"]])

    def rebinding_resolver(host: str, _port: int) -> list[str]:
        calls.append(host)
        return next(answers)

    policy = FetchPolicy(
        allowed_ports=frozenset({site.port}),
        address_allowed=lambda ip: ip == "127.0.0.1",
        resolver=rebinding_resolver,
    )
    result = SafeFetcher(policy).get(f"http://{HOST}:{site.port}/")
    assert result.connected_ip == "127.0.0.1"
    assert calls == [HOST]


@pytest.mark.parametrize(
    ("location", "code"),
    [
        ("http://10.0.0.1/", "blocked_address"),
        ("http://169.254.169.254/latest/meta-data/", "blocked_address"),
        ("file:///etc/passwd", "invalid_url"),
        ("http://metadata.example.test:{port}/", "blocked_address"),
    ],
)
def test_redirects_are_revalidated(site: FakeSite, location: str, code: str) -> None:
    site.route("/", lambda _h: redirect(location.format(port=site.port)))
    policy = _test_policy(site, extra_dns={"metadata.example.test": ["169.254.169.254"]})
    with pytest.raises(FetchBlockedError) as info:
        SafeFetcher(policy).get(f"http://{HOST}:{site.port}/")
    assert info.value.code == code


def test_redirect_loop_bounded(site: FakeSite) -> None:
    site.route("/a", lambda _h: redirect("/b"))
    site.route("/b", lambda _h: redirect("/a"))
    with pytest.raises(FetchBlockedError) as info:
        SafeFetcher(_test_policy(site, max_redirects=3)).get(f"http://{HOST}:{site.port}/a")
    assert info.value.code == "too_many_redirects"


def test_same_site_redirect_followed(site: FakeSite) -> None:
    site.route("/", lambda _h: redirect(f"http://www.{HOST}:{site.port}/home", 301))
    site.page("/home", "<p>home</p>")
    result = SafeFetcher(_test_policy(site)).get(f"http://{HOST}:{site.port}/")
    assert result.final_url == f"http://www.{HOST}:{site.port}/home"
    assert result.redirects == [f"http://{HOST}:{site.port}/"]


def test_oversized_body_truncated(site: FakeSite) -> None:
    site.route("/", lambda _h: html("x" * 50_000))
    result = SafeFetcher(_test_policy(site, max_bytes=1000)).get(f"http://{HOST}:{site.port}/")
    assert result.truncated
    assert len(result.body) == 1000


def test_slow_response_times_out(site: FakeSite) -> None:
    site.route("/", slow(2.0))
    policy = _test_policy(site, read_timeout=0.3, total_timeout=0.5)
    with pytest.raises(FetchFailedError) as info:
        SafeFetcher(policy).get(f"http://{HOST}:{site.port}/")
    assert info.value.code == "timeout"


def test_unresolvable_host_fails_cleanly(site: FakeSite) -> None:
    with pytest.raises(FetchFailedError) as info:
        SafeFetcher(_test_policy(site)).get(f"http://nowhere.example.test:{site.port}/")
    assert info.value.code == "dns_failed"


def test_tls_certificates_are_verified(tmp_path: Path) -> None:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)])
    now = dt.datetime.now(dt.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=1))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(HOST)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    (tmp_path / "c.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    (tmp_path / "k.pem").write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )

    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), H)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(tmp_path / "c.pem", tmp_path / "k.pem")
    server.socket = ctx.wrap_socket(server.socket, server_side=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_address[1]
    try:
        policy = FetchPolicy(
            allowed_ports=frozenset({port}),
            address_allowed=lambda ip: ip == "127.0.0.1",
            resolver=lambda _h, _p: ["127.0.0.1"],
        )
        with pytest.raises(FetchFailedError):
            SafeFetcher(policy).get(f"https://{HOST}:{port}/")
    finally:
        server.shutdown()


def test_url_helpers() -> None:
    assert (
        normalize_url("HTTPS://Bäckerei.Example:443/Path#frag")
        == "https://xn--bckerei-5wa.example/Path"
    )
    assert normalize_url("http://example.com") == "http://example.com/"
    assert site_domain("https://www.Example.com/x") == "example.com"
    assert same_site("https://www.example.com/", "https://example.com/about")
    assert not same_site("https://example.com/", "https://example.com.evil.test/")
    with pytest.raises(InvalidUrlError):
        normalize_url("mailto:a@b.test")
