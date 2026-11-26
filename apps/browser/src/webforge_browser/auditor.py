"""Evidence collection for website audits. Judgement (findings, scores) happens in the API.

Safety: every request goes through the egress proxy (SSRF policy); non-http(s) requests and
downloads are blocked; service workers are blocked; each audit uses a fresh browser that is
closed afterwards; nothing on the page is clicked, typed into or submitted.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urldefrag, urlsplit

from playwright.async_api import Browser, Page, Request, Route, async_playwright

METRICS_JS = (Path(__file__).parent / "metrics.js").read_text()
DESKTOP = {"width": 1440, "height": 1000}
MOBILE = {"width": 390, "height": 844}
BLOCKED_RESOURCE_TYPES = {"media", "websocket", "eventsource", "manifest"}
MAX_SCREENSHOT_HEIGHT = 6000


@dataclass
class Limits:
    max_pages: int = 10
    max_depth: int = 2
    page_timeout_s: float = 30
    total_timeout_s: float = 300
    max_requests_per_page: int = 150
    user_agent: str = "WEBFORGE-AI-Audit/0.1"


def chromium_args(proxy: str | None) -> list[str]:
    args = [
        "--disable-dev-shm-usage",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
        "--no-first-run",
        "--disable-quic",
        "--force-webrtc-ip-handling-policy=disable_non_proxied_udp",
        "--webrtc-ip-handling-policy=disable_non_proxied_udp",
    ]
    if proxy:
        # Do not let Chromium bypass the proxy for localhost/loopback.
        args.append("--proxy-bypass-list=<-loopback>")
    return args


async def launch(p: Any, proxy: str | None) -> Browser:
    kwargs: dict[str, Any] = {"args": chromium_args(proxy), "headless": True}
    if proxy:
        kwargs["proxy"] = {"server": proxy}
    browser: Browser = await p.chromium.launch(**kwargs)
    return browser


@dataclass
class PageCapture:
    url: str
    final_url: str | None = None
    status: int | None = None
    error: str | None = None
    load_ms: int | None = None
    metrics: dict[str, Any] | None = None
    console_errors: list[str] = field(default_factory=list)
    failed_requests: list[str] = field(default_factory=list)
    requests: int = 0
    blocked_requests: int = 0
    screenshot_png_b64: str | None = None
    depth: int = 0

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


async def _guard(route: Route, request: Request, counter: dict[str, int], limit: int) -> None:
    scheme = urlsplit(request.url).scheme
    if scheme not in ("http", "https") or request.resource_type in BLOCKED_RESOURCE_TYPES:
        counter["blocked"] += 1
        await route.abort("blockedbyclient")
        return
    counter["total"] += 1
    if counter["total"] > limit:
        counter["blocked"] += 1
        await route.abort("blockedbyclient")
        return
    await route.continue_()


async def capture(
    browser: Browser,
    url: str,
    viewport: dict[str, int],
    *,
    mobile: bool,
    limits: Limits,
    screenshot: bool,
    depth: int = 0,
) -> PageCapture:
    cap = PageCapture(url=url, depth=depth)
    context = await browser.new_context(
        viewport={"width": viewport["width"], "height": viewport["height"]},
        is_mobile=mobile,
        has_touch=mobile,
        device_scale_factor=1,
        accept_downloads=False,
        service_workers="block",
        user_agent=limits.user_agent,
        java_script_enabled=True,
        bypass_csp=False,
    )
    counter = {"total": 0, "blocked": 0}
    try:
        page: Page = await context.new_page()
        await page.route("**/*", lambda r, q: _guard(r, q, counter, limits.max_requests_per_page))
        page.on(
            "console",
            lambda m: (
                cap.console_errors.append(m.text[:300])
                if m.type == "error" and len(cap.console_errors) < 20
                else None
            ),
        )
        page.on(
            "requestfailed",
            lambda r: (
                cap.failed_requests.append(r.url[:300]) if len(cap.failed_requests) < 20 else None
            ),
        )
        page.on("download", lambda d: asyncio.ensure_future(d.cancel()))
        started = time.monotonic()
        try:
            response = await page.goto(url, wait_until="load", timeout=limits.page_timeout_s * 1000)
        except Exception as exc:  # navigation errors are evidence, not crashes
            cap.error = type(exc).__name__ + ": " + str(exc).split("\n", 1)[0][:200]
            return cap
        cap.load_ms = int((time.monotonic() - started) * 1000)
        cap.status = response.status if response else None
        cap.final_url = page.url
        with contextlib.suppress(Exception):  # best-effort settle
            await page.wait_for_load_state("networkidle", timeout=3000)
        cap.metrics = await page.evaluate(METRICS_JS)
        if screenshot:
            height = min(
                int(cap.metrics.get("page_height") or viewport["height"]), MAX_SCREENSHOT_HEIGHT
            )
            png = await page.screenshot(
                full_page=False,
                clip={
                    "x": 0,
                    "y": 0,
                    "width": viewport["width"],
                    "height": max(height, viewport["height"]),
                },
                animations="disabled",
            )
            cap.screenshot_png_b64 = base64.b64encode(png).decode()
    finally:
        cap.requests = counter["total"]
        cap.blocked_requests = counter["blocked"]
        await context.close()
    return cap


def _same_site_links(base: str, links: list[str]) -> list[str]:
    origin = urlsplit(base)
    out = []
    for link in links:
        u = urldefrag(link).url
        parts = urlsplit(u)
        if (parts.scheme, parts.netloc) == (origin.scheme, origin.netloc) and u.rstrip(
            "/"
        ) != base.rstrip("/"):
            low = parts.path.lower()
            if not low.endswith(
                (
                    ".pdf",
                    ".zip",
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".gif",
                    ".webp",
                    ".svg",
                    ".mp4",
                    ".doc",
                    ".docx",
                    ".xls",
                    ".xlsx",
                )
            ):
                out.append(u)
    return list(dict.fromkeys(out))


async def run_audit(url: str, limits: Limits, proxy: str | None) -> dict[str, Any]:
    deadline = time.monotonic() + limits.total_timeout_s
    async with async_playwright() as p:
        browser = await launch(p, proxy)
        try:
            desktop = await capture(
                browser, url, DESKTOP, mobile=False, limits=limits, screenshot=True
            )
            mobile = await capture(
                browser,
                desktop.final_url or url,
                MOBILE,
                mobile=True,
                limits=limits,
                screenshot=True,
            )
            pages: list[PageCapture] = []
            frontier = [
                (link, 1)
                for link in _same_site_links(
                    desktop.final_url or url, (desktop.metrics or {}).get("same_origin_links", [])
                )
            ]
            seen = {desktop.final_url or url}
            while frontier and len(pages) < limits.max_pages - 1 and time.monotonic() < deadline:
                link, depth = frontier.pop(0)
                if link in seen or depth > limits.max_depth:
                    continue
                seen.add(link)
                cap = await capture(
                    browser,
                    link,
                    DESKTOP,
                    mobile=False,
                    limits=limits,
                    screenshot=False,
                    depth=depth,
                )
                pages.append(cap)
                if depth < limits.max_depth and cap.metrics:
                    frontier.extend(
                        (n, depth + 1)
                        for n in _same_site_links(link, cap.metrics.get("same_origin_links", []))
                        if n not in seen
                    )
            browser_version = browser.version
        finally:
            await browser.close()
    return {
        "requested_url": url,
        "browser_version": browser_version,
        "desktop": desktop.as_dict(),
        "mobile": mobile.as_dict(),
        "pages": [c.as_dict() for c in pages],
        "limits": limits.__dict__,
        "timed_out": time.monotonic() > deadline,
    }
