"""SSRF-resistant HTTP fetching for untrusted public URLs.

Defences:
- http/https only, allow-listed ports, no credentials in URLs, no proxies.
- DNS is resolved here; if ANY answer is not a public unicast address the request is refused
  (covers loopback, private, link-local/cloud metadata, CGNAT, multicast, reserved and
  IPv4-mapped/compatible IPv6 forms).
- The TCP connection is made to the exact address that was vetted (no second lookup), which
  defeats DNS rebinding. TLS still verifies the certificate for the original host name.
- Redirects are followed manually; every hop is re-validated. Hop count, time and bytes are bounded.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlsplit

import httpcore

from webforge_api.net.urls import InvalidUrlError, normalize_url

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
Resolver = Callable[[str, int], list[str]]

# Explicit deny list on top of `is_global` (defence in depth; some ranges are easy to miss).
_BLOCKED_NETWORKS = [
    ipaddress.ip_network(n)
    for n in (
        "0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16",
        "172.16.0.0/12", "192.0.0.0/24", "192.0.2.0/24", "192.88.99.0/24", "192.168.0.0/16",
        "198.18.0.0/15", "198.51.100.0/24", "203.0.113.0/24", "224.0.0.0/4", "240.0.0.0/4",
        "255.255.255.255/32", "::/128", "::1/128", "64:ff9b::/96", "64:ff9b:1::/48",
        "100::/64", "2001::/23", "2001:db8::/32", "2002::/16", "fc00::/7", "fe80::/10",
        "ff00::/8", "fd00:ec2::254/128",
    )
]  # fmt: skip


class FetchBlockedError(Exception):
    """The request was refused for safety reasons (never retried)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class FetchFailedError(Exception):
    """The request could not be completed (network, timeout, TLS)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _embedded_ipv4(addr: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    if addr.sixtofour is not None:
        return addr.sixtofour
    if addr.teredo is not None:
        return addr.teredo[1]
    packed = addr.packed
    if packed[:12] == b"\x00" * 12:  # deprecated IPv4-compatible ::a.b.c.d
        return ipaddress.IPv4Address(packed[12:])
    return None


def is_public_address(ip: str) -> bool:
    try:
        addr: IPAddress = ipaddress.ip_address(ip.split("%", 1)[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address):
        inner = _embedded_ipv4(addr)
        if inner is not None and not is_public_address(str(inner)):
            return False
    if any(addr in net for net in _BLOCKED_NETWORKS):
        return False
    return addr.is_global and not addr.is_multicast


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(info[4][0]) for info in infos))


@dataclass(frozen=True)
class FetchPolicy:
    allowed_ports: frozenset[int] = frozenset({80, 443})
    max_redirects: int = 5
    max_bytes: int = 5 * 1024 * 1024
    connect_timeout: float = 10.0
    read_timeout: float = 15.0
    total_timeout: float = 30.0
    user_agent: str = "WEBFORGE-AI-Verifier"
    # Tests may inject an address check; production always uses is_public_address.
    address_allowed: Callable[[str], bool] = is_public_address
    resolver: Resolver = system_resolver


@dataclass
class FetchResult:
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    truncated: bool
    redirects: list[str] = field(default_factory=list)
    connected_ip: str | None = None

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";", 1)[0].strip().lower()

    def text(self) -> str:
        charset = "utf-8"
        for part in self.headers.get("content-type", "").split(";")[1:]:
            key, _, value = part.strip().partition("=")
            if key.lower() == "charset" and value:
                charset = value.strip("\"'")
        try:
            return self.body.decode(charset, errors="replace")
        except LookupError:
            return self.body.decode("utf-8", errors="replace")


class _PinnedBackend(httpcore.NetworkBackend):
    """Resolves and vets the host, then connects to the vetted IP only."""

    def __init__(self, policy: FetchPolicy) -> None:
        self._policy = policy
        self._inner = httpcore.SyncBackend()
        self.connected_ip: str | None = None

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        try:
            addresses = self._policy.resolver(host, port)
        except (OSError, UnicodeError) as exc:
            raise FetchFailedError("dns_failed", "The host name could not be resolved.") from exc
        if not addresses:
            raise FetchFailedError("dns_failed", "The host name has no addresses.")
        # Refuse if ANY answer is internal: mixed answers are a rebinding technique.
        if not all(self._policy.address_allowed(a) for a in addresses):
            raise FetchBlockedError("blocked_address", "The host resolves to a non-public address.")
        last_error: Exception | None = None
        for ip in addresses:
            try:
                stream = self._inner.connect_tcp(ip, port, timeout, local_address, socket_options)
            except httpcore.ConnectError as exc:
                last_error = exc
                continue
            self.connected_ip = ip
            return stream
        raise FetchFailedError("connect_failed", "Could not connect to the host.") from last_error

    def connect_unix_socket(
        self,
        path: str,
        timeout: float | None = None,
        socket_options: Iterable[httpcore.SOCKET_OPTION] | None = None,
    ) -> httpcore.NetworkStream:
        raise FetchBlockedError("blocked_scheme", "Unix sockets are not allowed.")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


def _validate_url(url: str, policy: FetchPolicy) -> str:
    try:
        normalized = normalize_url(url)
    except InvalidUrlError as exc:
        raise FetchBlockedError("invalid_url", str(exc)) from exc
    parts = urlsplit(normalized)
    port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
    if port not in policy.allowed_ports:
        raise FetchBlockedError("blocked_port", f"Port {port} is not allowed.")
    host = parts.hostname or ""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None and not policy.address_allowed(str(literal)):
        raise FetchBlockedError("blocked_address", "The URL points to a non-public address.")
    return normalized


class SafeFetcher:
    def __init__(self, policy: FetchPolicy) -> None:
        self.policy = policy

    def get(self, url: str, *, accept: str = "text/html,application/xhtml+xml") -> FetchResult:
        policy = self.policy
        deadline = time.monotonic() + policy.total_timeout
        current = _validate_url(url, policy)
        redirects: list[str] = []
        backend = _PinnedBackend(policy)
        # No proxy, no environment configuration: the pinned backend must make the connection.
        with httpcore.ConnectionPool(network_backend=backend, max_connections=2, retries=0) as pool:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise FetchFailedError("timeout", "The website took too long to respond.")
                timeouts = {
                    "connect": min(policy.connect_timeout, remaining),
                    "read": min(policy.read_timeout, remaining),
                    "write": min(policy.read_timeout, remaining),
                    "pool": min(policy.connect_timeout, remaining),
                }
                headers = [
                    (b"User-Agent", policy.user_agent.encode()),
                    (b"Accept", accept.encode()),
                    (b"Accept-Encoding", b"identity"),
                ]
                try:
                    with pool.stream(
                        "GET", current, headers=headers, extensions={"timeout": timeouts}
                    ) as response:
                        status = response.status
                        resp_headers = {
                            k.decode("latin-1").lower(): v.decode("latin-1")
                            for k, v in response.headers
                        }
                        if status in (301, 302, 303, 307, 308) and "location" in resp_headers:
                            if len(redirects) >= policy.max_redirects:
                                raise FetchBlockedError("too_many_redirects", "Too many redirects.")
                            redirects.append(current)
                            current = _validate_url(
                                urljoin(current, resp_headers["location"]), policy
                            )
                            continue
                        body = bytearray()
                        truncated = False
                        for chunk in response.iter_stream():
                            body.extend(chunk)
                            if len(body) > policy.max_bytes:
                                del body[policy.max_bytes :]
                                truncated = True
                                break
                            if time.monotonic() > deadline:
                                raise FetchFailedError("timeout", "The website took too long.")
                except (FetchBlockedError, FetchFailedError):
                    raise
                except httpcore.TimeoutException as exc:
                    raise FetchFailedError(
                        "timeout", "The website took too long to respond."
                    ) from exc
                except httpcore.ConnectError as exc:
                    raise FetchFailedError(
                        "connect_failed", "Could not connect to the host."
                    ) from exc
                except httpcore.UnsupportedProtocol as exc:
                    raise FetchBlockedError("blocked_scheme", "Unsupported protocol.") from exc
                except (httpcore.ProtocolError, httpcore.NetworkError) as exc:
                    raise FetchFailedError("network_error", "The connection failed.") from exc
                return FetchResult(
                    url=url,
                    final_url=current,
                    status=status,
                    headers=resp_headers,
                    body=bytes(body),
                    truncated=truncated,
                    redirects=redirects,
                    connected_ip=backend.connected_ip,
                )
