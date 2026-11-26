"""URL and domain normalisation. Never invents a domain: it only normalises what it is given."""

from __future__ import annotations

import ipaddress
from urllib.parse import urlsplit, urlunsplit

import idna


class InvalidUrlError(ValueError):
    pass


def normalize_host(host: str) -> str:
    """Lower-case, strip a trailing dot, and convert IDNs to punycode (A-labels)."""
    host = host.strip().rstrip(".").lower()
    if not host:
        raise InvalidUrlError("empty host")
    try:
        return idna.encode(host, uts46=True).decode("ascii")
    except idna.IDNAError as exc:
        raise InvalidUrlError("invalid host name") from exc


def normalize_url(url: str) -> str:
    """Canonical http(s) URL: lower-case scheme/host, punycode, no default port or fragment."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise InvalidUrlError("only http and https URLs are allowed")
    if parts.username or parts.password:
        raise InvalidUrlError("URLs with credentials are not allowed")
    if not parts.hostname:
        raise InvalidUrlError("URL has no host")
    try:
        ip = ipaddress.ip_address(parts.hostname)
        host = f"[{ip.compressed}]" if ip.version == 6 else ip.compressed
    except ValueError:
        host = normalize_host(parts.hostname)
    try:
        port = parts.port
    except ValueError as exc:
        raise InvalidUrlError("invalid port") from exc
    netloc = host if port in (None, 80 if scheme == "http" else 443) else f"{host}:{port}"
    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def site_domain(url_or_host: str) -> str:
    """Host without a leading `www.` (used to compare sites, not to guess them)."""
    host = urlsplit(url_or_host).hostname if "://" in url_or_host else url_or_host
    if not host:
        raise InvalidUrlError("URL has no host")
    host = normalize_host(host)
    return host[4:] if host.startswith("www.") else host


def same_site(a: str, b: str) -> bool:
    """True when both URLs are on the same site, treating `www.` and the bare host as equal."""
    return site_domain(a) == site_domain(b)
