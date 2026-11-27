"""Offline validation of rendered concept pages (Phase 07).

Pages are supplied in the request body and served to Chromium from memory at https://concept.invalid/<slug>.
Every other request is aborted and reported, DNS is disabled and no proxy route exists, so validation never
touches the network. The browser is fresh per call and closed afterwards. Screenshots are taken before any
interaction so they show no focus rings, typed text or overlays.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
from typing import Any
from urllib.parse import urlsplit

from playwright.async_api import Browser, Page, Request, Route, async_playwright

ORIGIN = "https://concept.invalid"
VIEWPORTS = {
    "desktop": {"width": 1440, "height": 900, "mobile": False},
    "tablet": {"width": 768, "height": 1024, "mobile": True},
    "mobile": {"width": 390, "height": 844, "mobile": True},
}
MAX_SHOT_HEIGHT = 8000
OFFLINE_ARGS = [
    "--host-resolver-rules=MAP * ~NOTFOUND",
    "--proxy-server=http://127.0.0.1:9",  # nothing should ever reach it; requests are fulfilled or aborted first
    "--disable-background-networking",
    "--disable-component-update",
    "--disable-sync",
    "--no-first-run",
    "--disable-dev-shm-usage",
]

CHECKS_JS = r"""
(vw) => {
  const doc = document.documentElement;
  const parse = (c) => { const m = c.match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(',').map(Number); return {r:p[0], g:p[1], b:p[2], a: p.length > 3 ? p[3] : 1}; };
  const lum = ({r,g,b}) => { const f = (v) => { v /= 255; return v <= 0.04045 ? v/12.92 : Math.pow((v+0.055)/1.055, 2.4); };
    return 0.2126*f(r) + 0.7152*f(g) + 0.0722*f(b); };
  const ratio = (a, b) => { const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x); return (hi + 0.05) / (lo + 0.05); };
  const bgOf = (el) => { for (let e = el; e; e = e.parentElement) { const c = parse(getComputedStyle(e).backgroundColor);
      if (c && c.a > 0.5) return c; } return {r:255, g:255, b:255, a:1}; };
  const visible = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && r.left > -500; };
  const contrastFails = []; let checked = 0;
  for (const el of document.querySelectorAll('body *')) {
    if (el.closest('svg') || !visible(el)) continue;
    const hasText = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim().length > 0);
    if (!hasText) continue;
    const s = getComputedStyle(el); const fg = parse(s.color); if (!fg) continue;
    const size = parseFloat(s.fontSize); const bold = parseInt(s.fontWeight, 10) >= 700;
    const need = (size >= 24 || (bold && size >= 18.66)) ? 3 : 4.5;
    const r = ratio(fg, bgOf(el)); checked++;
    if (r < need && contrastFails.length < 20) contrastFails.push({tag: el.tagName.toLowerCase(), ratio: Math.round(r*100)/100, need,
      text: el.textContent.trim().slice(0, 60)});
  }
  const headings = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')].map((h) => Number(h.tagName[1]));
  let skipped = false; for (let i = 1; i < headings.length; i++) if (headings[i] > headings[i-1] + 1) skipped = true;
  const unnamed = [...document.querySelectorAll('a, button')].filter((e) => !(e.getAttribute('aria-label') || e.textContent.trim()))
    .map((e) => e.outerHTML.slice(0, 80));
  const unlabeled = [...document.querySelectorAll('input, textarea, select')].filter((e) =>
    !(e.labels && e.labels.length) && !e.getAttribute('aria-label')).map((e) => e.id || e.tagName.toLowerCase());
  const imgs = [...document.querySelectorAll('img')];
  const brokenImages = imgs.filter((i) => !i.complete || i.naturalWidth === 0).map((i) => (i.getAttribute('src') || '').slice(0, 80));
  const missingAlt = imgs.filter((i) => !i.hasAttribute('alt')).length;
  const overflow = [...document.querySelectorAll('body *')].filter((e) => { const r = e.getBoundingClientRect();
    return r.width > 0 && r.right > vw + 1 && !e.closest('svg'); }).slice(0, 5).map((e) => e.tagName.toLowerCase() + '.' + e.className);
  const notice = document.querySelector('.notice');
  const nr = notice ? notice.getBoundingClientRect() : null;
  const rootStyle = getComputedStyle(doc);
  const tokens = {}; for (const v of ['--p','--s','--a','--bg','--sf','--t','--m','--r']) tokens[v] = rootStyle.getPropertyValue(v).trim();
  return {
    scroll_width: doc.scrollWidth, viewport_width: vw, page_height: doc.scrollHeight,
    overflow_elements: overflow, h1_count: headings.filter((h) => h === 1).length, heading_levels: headings,
    heading_skipped: skipped, unnamed_controls: unnamed.slice(0, 10), unlabeled_fields: unlabeled.slice(0, 10),
    broken_images: brokenImages, images_missing_alt: missingAlt, contrast_checked: checked, contrast_failures: contrastFails,
    notice_visible_at_top: !!(nr && nr.top >= 0 && nr.top < 200 && nr.height > 0 && /not the official website/i.test(notice.textContent)),
    links: [...document.querySelectorAll('a[href]')].map((a) => a.href),
    forms: document.querySelectorAll('form').length,
    named_fields: document.querySelectorAll('form [name]').length,
    tokens, body_font: getComputedStyle(document.body).fontFamily, title: document.title,
    lang: doc.getAttribute('lang') || '',
  };
}
"""

FOCUS_JS = r"""
() => { const e = document.activeElement; if (!e || e === document.body) return null; const s = getComputedStyle(e);
  return {tag: e.tagName.toLowerCase(), text: (e.textContent || e.id || '').trim().slice(0, 40),
          outline: s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) >= 1, shadow: s.boxShadow !== 'none'}; }
"""


class _Server:
    """Serves the supplied pages from memory and records every other request."""

    def __init__(self, pages: dict[str, str]) -> None:
        self.pages = pages
        self.blocked: list[str] = []
        self.served = 0

    async def handle(self, route: Route, request: Request) -> None:
        url = urlsplit(request.url)
        slug = url.path.strip("/")
        if (
            f"{url.scheme}://{url.netloc}" == ORIGIN
            and slug in self.pages
            and request.method == "GET"
        ):
            self.served += 1
            await route.fulfill(
                status=200, content_type="text/html; charset=utf-8", body=self.pages[slug]
            )
            return
        if len(self.blocked) < 20:
            self.blocked.append(f"{request.method} {request.url[:200]}")
        await route.abort("blockedbyclient")


async def _open(
    browser: Browser, server: _Server, viewport: dict[str, Any]
) -> tuple[Any, Page, list[str]]:
    context = await browser.new_context(
        viewport={"width": viewport["width"], "height": viewport["height"]},
        is_mobile=viewport["mobile"], has_touch=viewport["mobile"], device_scale_factor=2,
        accept_downloads=False, service_workers="block", java_script_enabled=True, offline=False,
        reduced_motion="reduce",
    )  # fmt: skip
    await context.route("**/*", server.handle)
    page = await context.new_page()
    console: list[str] = []
    page.on(
        "console",
        lambda m: console.append(m.text[:200]) if m.type == "error" and len(console) < 20 else None,
    )
    page.on("pageerror", lambda e: console.append(str(e)[:200]) if len(console) < 20 else None)
    return context, page, console


async def _check_page(
    browser: Browser, pages: dict[str, str], slug: str, vp_name: str
) -> dict[str, Any]:
    vp = VIEWPORTS[vp_name]
    server = _Server(pages)
    context, page, console = await _open(browser, server, vp)
    result: dict[str, Any] = {
        "slug": slug,
        "viewport": vp_name,
        "html_sha256": hashlib.sha256(pages[slug].encode()).hexdigest(),
    }
    try:
        try:
            response = await page.goto(f"{ORIGIN}/{slug}", wait_until="load", timeout=20_000)
            result["status"] = response.status if response else None
        except Exception as exc:
            result["error"] = type(exc).__name__ + ": " + str(exc).split("\n", 1)[0][:200]
            return result
        result["metrics"] = await page.evaluate(CHECKS_JS, vp["width"])
        height = min(int(result["metrics"]["page_height"]), MAX_SHOT_HEIGHT)
        png = await page.screenshot(
            clip={"x": 0, "y": 0, "width": vp["width"], "height": max(height, vp["height"])},
            animations="disabled", caret="hide",
        )  # fmt: skip
        result["screenshot_png_b64"] = base64.b64encode(png).decode()
        result["screenshot_sha256"] = hashlib.sha256(png).hexdigest()
        # Keyboard focus visibility (after the screenshot, so captures stay clean).
        focus: list[dict[str, Any]] = []
        for _ in range(6):
            await page.keyboard.press("Tab")
            info = await page.evaluate(FOCUS_JS)
            if info:
                focus.append(info)
        result["focus"] = focus
        # Demo forms must never submit or navigate.
        if result["metrics"]["forms"]:
            before, requests_before = page.url, server.served + len(server.blocked)
            navigations: list[str] = []
            page.on(
                "framenavigated",
                lambda f: navigations.append(f.url) if f == page.main_frame else None,
            )
            # Every interaction is bounded: a form that submits navigates away, and the remaining steps must
            # not hang or crash the run; the navigation itself is the evidence.
            fields = page.locator("form input, form textarea")
            with contextlib.suppress(Exception):
                if await fields.count():
                    await fields.first.fill("Validation Test", timeout=2000)
                    await fields.first.press("Enter", no_wait_after=True, timeout=2000)
            await page.wait_for_timeout(300)
            if not navigations and page.url == before:
                buttons = page.locator("form button")
                for i in range(await buttons.count()):
                    with contextlib.suppress(Exception):
                        await buttons.nth(i).click(no_wait_after=True, timeout=2000)
            await page.wait_for_timeout(400)
            result["form"] = {
                "navigated": bool(navigations) or page.url != before,
                "requests_after_interaction": server.served + len(server.blocked) - requests_before,
            }
    finally:
        result["console_errors"] = console
        result["blocked_requests"] = server.blocked
        await context.close()
    return result


async def run_validation(pages: dict[str, str], slug: str, viewports: list[str]) -> dict[str, Any]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(args=OFFLINE_ARGS, headless=True)
        try:
            results = []
            for vp in viewports:
                results.append(await _check_page(browser, pages, slug, vp))
            version = browser.version
        finally:
            with contextlib.suppress(Exception):
                await browser.close()
    return {"slug": slug, "browser_version": version, "results": results}


def run_validation_sync(pages: dict[str, str], slug: str, viewports: list[str]) -> dict[str, Any]:
    return asyncio.run(run_validation(pages, slug, viewports))
