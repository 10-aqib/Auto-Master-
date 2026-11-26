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
        self.pdf_html = ""
        self.pdf_transform: Any = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/selftest":
            return httpx.Response(200, json={"isolated": self.isolated})
        if request.url.path == "/pdf":
            body = json.loads(request.content)
            self.pdf_html = body["html"]
            html = self.pdf_transform(body["html"]) if self.pdf_transform else body["html"]
            return httpx.Response(
                200,
                content=fake_pdf(html),
                headers={"content-type": "application/pdf", "x-blocked-requests": "0"},
            )
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


def fake_pdf(html: str, *, pages: int = 12, images_per_page: int = 2) -> bytes:
    """A small but genuine PDF holding the document's text (WinAnsi) and image XObjects on every page."""
    import html as htmllib
    import textwrap

    text = re.sub(r"<style.*?</style>|<title.*?</title>", " ", html, flags=re.S)
    text = htmllib.unescape(re.sub(r"<[^>]+>", "\n", text))
    lines = [w for ln in text.splitlines() if ln.strip() for w in textwrap.wrap(ln.strip(), 95)]
    per = max(1, -(-len(lines) // pages))
    chunks = [lines[i : i + per] for i in range(0, len(lines), per)] or [["(empty)"]]
    while len(chunks) < pages:
        chunks.append(["Continued."])

    def esc(s: str) -> bytes:
        out = b""
        for ch in s.encode("cp1252", "replace"):
            c = bytes([ch])
            out += b"\\" + c if c in b"()\\" else (b"\\%03o" % ch if ch > 126 else c)
        return out

    objs: list[bytes] = [b"", b""]  # 1: catalog, 2: pages (filled later)
    objs.append(
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )  # 3
    objs.append(
        b"<< /Type /XObject /Subtype /Image /Width 1 /Height 1 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length 3 >>\nstream\n\x10\x20\x30\nendstream"
    )  # 4
    kids = []
    for chunk in chunks:
        body = (
            b"BT /F1 8 Tf 30 800 Td 10 TL "
            + b"".join(b"(" + esc(ln) + b") ' " for ln in chunk)
            + b"ET "
        )
        body += b"".join(
            b"q 20 0 0 20 %d 20 cm /Im%d Do Q " % (30 + 30 * i, i) for i in range(images_per_page)
        )
        objs.append(b"<< /Length %d >>\nstream\n" % len(body) + body + b"\nendstream")
        content = len(objs)
        xobj = b" ".join(b"/Im%d 4 0 R" % i for i in range(images_per_page))
        objs.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents %d 0 R /Resources << /Font << /F1 3 0 R >> /XObject << %s >> >> >>"
            % (content, xobj)
        )
        kids.append(len(objs))
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = b"<< /Type /Pages /Count %d /Kids [%s] >>" % (
        len(kids),
        b" ".join(b"%d 0 R" % k for k in kids),
    )
    out, offsets = b"%PDF-1.7\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1) + b"".join(
        b"%010d 00000 n \n" % off for off in offsets
    )
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return out
