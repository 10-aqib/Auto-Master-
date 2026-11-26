from __future__ import annotations

import os
import threading
import time
from collections.abc import Callable, Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", "/opt/pw-browsers")

Handler = Callable[[], tuple[int, str, bytes]]


class Site:
    def __init__(self) -> None:
        self.routes: dict[str, Handler] = {}
        self.port = 0

    def html(self, path: str, body: str, status: int = 200, delay: float = 0) -> None:
        def h() -> tuple[int, str, bytes]:
            if delay:
                time.sleep(delay)
            return status, "text/html; charset=utf-8", body.encode()

        self.routes[path] = h

    def raw(self, path: str, ctype: str, data: bytes) -> None:
        self.routes[path] = lambda: (200, ctype, data)

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}"


@pytest.fixture
def site() -> Iterator[Site]:
    s = Site()

    class H(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            h = s.routes.get(self.path.split("?")[0])
            status, ctype, data = h() if h else (404, "text/html", b"<h1>Not found</h1>")
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except OSError:
                pass

        def log_message(self, *a: object) -> None:
            return None

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    srv.daemon_threads = True
    s.port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield s
    srv.shutdown()
