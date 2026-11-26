"""Isolation self-test: proves from inside the sandbox that internal targets are unreachable.

Direct TCP must fail for everything (the sandbox network has no route out). Through the egress
proxy, internal and metadata targets must be refused. Audits are refused unless this passes.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

DIRECT_TARGETS = [
    ("postgres", 5432), ("redis", 6379), ("api", 8000), ("dashboard", 3000), ("worker", 8000),
    ("169.254.169.254", 80), ("127.0.0.1", 22), ("1.1.1.1", 443), ("8.8.8.8", 53),
]  # fmt: skip
PROXY_DENY_TARGETS = [
    "169.254.169.254:80", "127.0.0.1:8000", "10.0.0.1:443", "postgres:5432", "redis:6379",
    "api:8000", "[::1]:443", "metadata.google.internal:80",
]  # fmt: skip


async def _tcp(host: str, port: int) -> bool:
    try:
        _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), 2.0)
    except (OSError, TimeoutError):
        return False
    writer.close()
    return True


async def _proxy_connect(proxy_host: str, proxy_port: int, target: str) -> int | None:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(proxy_host, proxy_port), 3)
    except (OSError, TimeoutError):
        return None
    try:
        writer.write(f"CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n".encode())
        await writer.drain()
        line = await asyncio.wait_for(reader.readline(), 8)
        parts = line.decode(errors="replace").split()
        return int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
    except (OSError, TimeoutError, ValueError):
        return None
    finally:
        writer.close()


async def run_selftest(proxy: str | None) -> dict[str, Any]:
    direct = {f"{h}:{p}": await _tcp(h, p) for h, p in DIRECT_TARGETS}
    via_proxy: dict[str, int | None] = {}
    proxy_reachable = False
    if proxy:
        host, _, port = proxy.removeprefix("http://").rstrip("/").partition(":")
        proxy_reachable = await _tcp(host, int(port or 3128))
        for target in PROXY_DENY_TARGETS:
            via_proxy[target] = await _proxy_connect(host, int(port or 3128), target)
    direct_ok = not any(direct.values())
    proxy_ok = bool(proxy) and proxy_reachable and all(s == 403 for s in via_proxy.values())
    return {
        "isolated": direct_ok and proxy_ok,
        "direct_connections_blocked": direct_ok,
        "direct": direct,
        "proxy_configured": bool(proxy),
        "proxy_reachable": proxy_reachable,
        "proxy_denies_internal": proxy_ok,
        "via_proxy": via_proxy,
        "env_has_no_secrets": not any(
            k
            for k in os.environ
            if any(
                s in k.upper() for s in ("PASSWORD", "SECRET", "DATABASE_URL", "API_KEY", "TOKEN")
            )
        ),
    }
