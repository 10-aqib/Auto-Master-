"""Offline PDF rendering for proposals (Phase 08).

The proposal HTML arrives in the request (screenshots embedded as data: URIs) and is served from memory at
https://proposal.invalid/. Every other request is aborted, DNS is disabled, and a fresh browser is used.
"""

from __future__ import annotations

import contextlib
from typing import Any

from playwright.async_api import Request, Route, async_playwright

from webforge_browser.validator import OFFLINE_ARGS

ORIGIN = "https://proposal.invalid/"
FOOTER = (
    '<div style="font:8px sans-serif;color:#555;width:100%;padding:0 12mm;display:flex;justify-content:space-between">'
    '<span>{notice}</span><span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>'
)


async def render_pdf(html: str, footer_notice: str) -> tuple[bytes, list[str]]:
    blocked: list[str] = []

    async def handle(route: Route, request: Request) -> None:
        if request.url == ORIGIN and request.method == "GET":
            await route.fulfill(status=200, content_type="text/html; charset=utf-8", body=html)
            return
        if len(blocked) < 20:
            blocked.append(request.url[:200])
        await route.abort("blockedbyclient")

    async with async_playwright() as p:
        browser = await p.chromium.launch(args=OFFLINE_ARGS, headless=True)
        try:
            context = await browser.new_context(
                accept_downloads=False, service_workers="block", java_script_enabled=False
            )
            await context.route("**/*", handle)
            page = await context.new_page()
            await page.goto(ORIGIN, wait_until="load", timeout=60_000)
            notice = footer_notice.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            pdf = await page.pdf(
                format="A4", print_background=True, display_header_footer=True,
                header_template="<span></span>", footer_template=FOOTER.format(notice=notice),
                margin={"top": "14mm", "bottom": "16mm", "left": "12mm", "right": "12mm"},
            )  # fmt: skip
        finally:
            with contextlib.suppress(Exception):
                await browser.close()
    return pdf, blocked


def metadata(pdf: bytes, blocked: list[str]) -> dict[str, Any]:
    return {"bytes": len(pdf), "blocked_requests": blocked}
