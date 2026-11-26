"""SSRF-filtering forward proxy for the browser sandbox: `python -m webforge_api.egress_proxy`.

The browser container sits on an internal-only network; this proxy is its only way out.
- Supports CONNECT (HTTPS tunnels) and absolute-form plain HTTP requests.
- Ports 80/443 only. The destination host is resolved HERE; if any answer is non-public the
  request is refused (403), and the connection is made to the vetted IP (no DNS rebinding).
- Per-connection byte and time limits; bounded concurrency. Logs host + decision only.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field

from webforge_api.logging_config import configure_logging, get_logger
from webforge_api.net.safe_fetch import is_public_address

log = get_logger("webforge_api.egress_proxy")


@dataclass
class ProxyPolicy:
    allowed_ports: frozenset[int] = frozenset({80, 443})
    max_bytes: int = 50 * 1024 * 1024  # per connection, both directions
    idle_timeout: float = 30.0
    max_connection_seconds: float = 180.0
    max_concurrency: int = 64
    address_allowed: Callable[[str], bool] = is_public_address
    static_dns: dict[str, list[str]] = field(default_factory=dict)  # tests only


class Denied(Exception):  # noqa: N818
    def __init__(self, status: int, reason: str) -> None:
        super().__init__(reason)
        self.status = status


async def resolve(host: str, port: int, policy: ProxyPolicy) -> str:
    host = host.strip("[]").rstrip(".").lower()
    if port not in policy.allowed_ports:
        raise Denied(403, "port not allowed")
    if host in policy.static_dns:
        addresses = policy.static_dns[host]
    else:
        try:
            infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=1)
        except OSError as exc:
            raise Denied(502, "dns failed") from exc
        addresses = list(dict.fromkeys(str(i[4][0]) for i in infos))
    if not addresses:
        raise Denied(502, "no addresses")
    if not all(policy.address_allowed(a) for a in addresses):
        raise Denied(403, "non-public address")
    return addresses[0]


async def _pipe(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    budget: list[int],
    policy: ProxyPolicy,
) -> None:
    try:
        while True:
            chunk = await asyncio.wait_for(reader.read(65536), policy.idle_timeout)
            if not chunk:
                break
            budget[0] -= len(chunk)
            if budget[0] < 0:
                break
            writer.write(chunk)
            await writer.drain()
    except (OSError, TimeoutError, asyncio.IncompleteReadError):
        pass
    finally:
        with contextlib.suppress(Exception):
            writer.close()


def _split_host_port(authority: str, default: int) -> tuple[str, int]:
    if authority.startswith("["):
        host, sep, rest = authority[1:].partition("]")
        if not sep:
            raise Denied(400, "bad host")
        port_s = rest[1:] if rest.startswith(":") else ""
    elif authority.count(":") == 1:
        host, port_s = authority.split(":")
    elif ":" in authority:
        raise Denied(400, "bad host")
    else:
        host, port_s = authority, ""
    if (port_s and not port_s.isdigit()) or not host:
        raise Denied(400, "bad host or port")
    return host, int(port_s) if port_s else default


async def _respond(writer: asyncio.StreamWriter, status: int, reason: str) -> None:
    body = f"{status} {reason}\n".encode()
    head = (
        f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
    )
    writer.write(head.encode() + body)
    with contextlib.suppress(Exception):
        await writer.drain()
    writer.close()


class EgressProxy:
    def __init__(self, policy: ProxyPolicy) -> None:
        self.policy = policy
        self._slots = asyncio.Semaphore(policy.max_concurrency)

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        async with self._slots:
            try:
                await asyncio.wait_for(
                    self._handle(reader, writer), self.policy.max_connection_seconds
                )
            except TimeoutError:
                writer.close()
            except Denied as exc:
                await _respond(writer, exc.status, str(exc))
            except Exception:  # never crash the server on one bad client
                writer.close()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
        if len(head) > 16384:
            raise Denied(431, "headers too large")
        lines = head.decode("latin-1").split("\r\n")
        try:
            method, target, version = lines[0].split(" ")
        except ValueError as exc:
            raise Denied(400, "bad request line") from exc
        budget = [self.policy.max_bytes]
        if method.upper() == "CONNECT":
            host, port = _split_host_port(target, 443)
            ip = await resolve(host, port, self.policy)
            log.info("egress_allowed", host=host[:100], port=port, mode="connect")
            up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(ip, port), 10)
            writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await writer.drain()
            await asyncio.gather(
                _pipe(reader, up_writer, budget, self.policy),
                _pipe(up_reader, writer, budget, self.policy),
            )
            return
        if not target.lower().startswith("http://"):
            raise Denied(400, "absolute http URL or CONNECT required")
        rest = target[7:]
        authority, _, path = rest.partition("/")
        host, port = _split_host_port(authority, 80)
        ip = await resolve(host, port, self.policy)
        log.info("egress_allowed", host=host[:100], port=port, mode="http")
        headers = [
            h
            for h in lines[1:]
            if h and not h.lower().startswith(("proxy-", "connection:", "keep-alive:"))
        ]
        request = (
            f"{method} /{path} {version}\r\n"
            + "\r\n".join(headers)
            + "\r\nConnection: close\r\n\r\n"
        )
        up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(ip, port), 10)
        up_writer.write(request.encode("latin-1"))
        await up_writer.drain()
        await asyncio.gather(
            _pipe(reader, up_writer, budget, self.policy),
            _pipe(up_reader, writer, budget, self.policy),
        )


async def serve(host: str, port: int, policy: ProxyPolicy) -> asyncio.Server:
    proxy = EgressProxy(policy)
    return await asyncio.start_server(proxy.handle, host, port, limit=65536)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="webforge_api.egress_proxy")
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - container-internal network only
    parser.add_argument("--port", type=int, default=3128)
    args = parser.parse_args(argv)
    configure_logging("INFO")

    async def run() -> None:
        server = await serve(args.host, args.port, ProxyPolicy())
        log.info("egress_proxy_started", port=args.port)
        async with server:
            await server.serve_forever()

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
