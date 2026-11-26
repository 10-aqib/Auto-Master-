"""Tiny local HTTP server for fetcher and verifier tests (fake sites, no internet)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

Route = Callable[[BaseHTTPRequestHandler], tuple[int, dict[str, str], bytes]]


def html(body: str, status: int = 200) -> tuple[int, dict[str, str], bytes]:
    return status, {"Content-Type": "text/html; charset=utf-8"}, body.encode()


def redirect(location: str, status: int = 302) -> tuple[int, dict[str, str], bytes]:
    return status, {"Location": location}, b""


@dataclass
class FakeSite:
    port: int
    routes: dict[str, Route] = field(default_factory=dict)
    requests: list[tuple[str, str]] = field(default_factory=list)  # (path, host header)

    def route(self, path: str, handler: Route) -> None:
        self.routes[path] = handler

    def page(self, path: str, body: str, status: int = 200) -> None:
        self.routes[path] = lambda _h: html(body, status)


@contextmanager
def fake_site() -> Iterator[FakeSite]:
    site = FakeSite(port=0)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            site.requests.append((path, self.headers.get("Host", "")))
            handler = site.routes.get(path)
            if handler is None:
                status, headers, body = 404, {"Content-Type": "text/plain"}, b"not found"
            else:
                status, headers, body = handler(self)
            self.send_response(status)
            for k, v in headers.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args: object) -> None:
            return None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    site.port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield site
    finally:
        server.shutdown()
        server.server_close()


def slow(seconds: float) -> Route:
    def handler(_h: BaseHTTPRequestHandler) -> tuple[int, dict[str, str], bytes]:
        time.sleep(seconds)
        return html("<p>late</p>")

    return handler
