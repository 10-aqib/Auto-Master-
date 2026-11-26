"""A fake browser sandbox for concept validation: evidence is derived from the submitted HTML."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import struct
import zlib
from typing import Any

import httpx

from tests.conftest import Harness
from webforge_api.design.validation_rules import CONCEPT_ORIGIN, VIEWPORT_WIDTHS
from webforge_api.services.ai import MockBriefModel
from webforge_api.services.audits import BrowserClient
from webforge_api.worker import drain


def tiny_png(seed: str) -> bytes:
    raw = b"\x00" + hashlib.sha256(seed.encode()).digest()[:3]

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


class FakeValidator:
    """Answers /selftest and /validate. `defects` maps (slug, viewport) or slug -> metric overrides."""

    def __init__(
        self,
        isolated: bool = True,
        defects: dict[Any, dict[str, Any]] | None = None,
        status: int = 200,
    ) -> None:
        self.isolated = isolated
        self.defects = defects or {}
        self.status = status
        self.calls: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/selftest":
            return httpx.Response(200, json={"isolated": self.isolated})
        assert request.url.path == "/validate"
        body = json.loads(request.content)
        slug, pages = body["slug"], body["pages"]
        self.calls.append(slug)
        if self.status != 200:
            return httpx.Response(self.status, json={"detail": "fail"})
        html = pages[slug]
        results = []
        for vp, width in VIEWPORT_WIDTHS.items():
            png = tiny_png(f"{slug}-{vp}-{hashlib.sha256(html.encode()).hexdigest()}")
            metrics: dict[str, Any] = {
                "scroll_width": width, "viewport_width": width, "page_height": 1200, "overflow_elements": [],
                "h1_count": html.count("<h1"), "heading_levels": [1, 2], "heading_skipped": False,
                "unnamed_controls": [], "unlabeled_fields": [], "broken_images": [], "images_missing_alt": 0,
                "contrast_checked": 40, "contrast_failures": [],
                "notice_visible_at_top": "not the official website" in html,
                "links": [f"{CONCEPT_ORIGIN}/{h}" for h in re.findall(r'href="([a-z]+)"', html)],
                "forms": html.count("<form"), "named_fields": len(re.findall(r"<(?:input|textarea)[^>]*\sname=", html)),
                "tokens": {"--p": "#1F4E79"}, "body_font": "system-ui", "title": slug, "lang": "en",
            }  # fmt: skip
            result: dict[str, Any] = {
                "slug": slug, "viewport": vp, "status": 200, "html_sha256": hashlib.sha256(html.encode()).hexdigest(),
                "metrics": metrics, "screenshot_png_b64": base64.b64encode(png).decode(),
                "screenshot_sha256": hashlib.sha256(png).hexdigest(), "focus": [{"tag": "a", "outline": True, "shadow": False}],
                "console_errors": [], "blocked_requests": [],
            }  # fmt: skip
            if metrics["forms"]:
                result["form"] = {"navigated": False, "requests_after_interaction": 0}
            for key in (slug, (slug, vp)):
                over = self.defects.get(key, {})
                metrics.update(over.get("metrics", {}))
                result.update({k: v for k, v in over.items() if k != "metrics"})
            if "safe_mode_fixes" in self.defects and "a:focus,button:focus" in html:
                metrics["contrast_failures"] = []  # the repaired (safe-mode) render passes
            results.append(result)
        return httpx.Response(
            200, json={"slug": slug, "browser_version": "fake-1", "results": results}
        )


def run_validation(h: Harness, sandbox: FakeValidator | None = None) -> None:
    """Drain design + audit queues with a fake sandbox (validation runs on the audit queue)."""
    from tests.test_briefs import _rt

    rt = _rt(h, MockBriefModel())
    rt.browser = BrowserClient(
        "http://browser.test", transport=httpx.MockTransport(sandbox or FakeValidator())
    )
    try:
        drain(rt, ["audit", "design"])
    finally:
        rt.close()
