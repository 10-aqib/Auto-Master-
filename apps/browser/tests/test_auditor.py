"""Evidence collection against deterministic fixture sites (direct, no proxy, test only)."""

from __future__ import annotations

from typing import Any

import pytest

from tests.conftest import Site
from webforge_browser.auditor import Limits, run_audit

GOOD = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Fixture Dental Clinic</title><meta name="description" content="Family dentistry in Lahore (fixture).">
<style>body{font:16px system-ui;margin:0} nav a{display:inline-block;padding:12px} .cta{display:inline-block;padding:14px 20px}</style>
</head><body><header><nav><a href="/">Home</a><a href="/services">Services</a><a href="/contact">Contact</a></nav></header>
<main><h1>Gentle dental care</h1><p>Fixture text.</p><a class="cta" href="/contact">Book an appointment</a>
<a href="tel:+920000000000">Call us</a><img src="/logo.png" alt="Logo"><h2>Services</h2></main></body></html>"""
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


async def audit(site: Site, path: str = "/", **kw: Any) -> dict[str, Any]:
    limits = Limits(
        max_pages=kw.pop("max_pages", 5), page_timeout_s=kw.pop("timeout", 10), total_timeout_s=60
    )
    return await run_audit(site.base + path, limits, proxy=None)


@pytest.fixture
def good(site: Site) -> Site:
    site.html("/", GOOD)
    site.html("/services", GOOD.replace("Gentle dental care", "Our services"))
    site.html("/contact", GOOD.replace("Gentle dental care", "Contact"))
    site.raw("/logo.png", "image/png", PNG)
    return site


async def test_responsive_site_evidence(good: Site) -> None:
    r = await audit(good)
    d, m = r["desktop"]["metrics"], r["mobile"]["metrics"]
    assert r["desktop"]["status"] == 200 and r["desktop"]["screenshot_png_b64"]
    assert d["title"] == "Fixture Dental Clinic" and d["lang"] == "en" and d["viewport_meta"]
    assert (
        d["h1_count"] == 1
        and d["nav_links"] == 3
        and d["cta_above_fold"]
        and d["contact_routes"] >= 2
    )
    assert d["images_broken"] == [] and d["images_missing_alt"] == 0
    assert m["scroll_width"] <= m["client_width"] + 2  # no horizontal overflow on mobile
    assert {p["url"].rstrip("/").rsplit("/", 1)[-1] for p in r["pages"]} == {"services", "contact"}
    assert r["browser_version"]


async def test_fixed_width_site_overflows_on_mobile(site: Site) -> None:
    site.html(
        "/",
        '<html><head><title>Old</title></head><body style="width:1200px"><h1>Wide</h1><p style="font-size:10px">tiny text</p></body></html>',
    )
    m = (await audit(site))["mobile"]["metrics"]
    assert m["viewport_meta"] is None
    assert m["scroll_width"] > m["client_width"] + 2


async def test_broken_images_and_404_nav(site: Site) -> None:
    site.html(
        "/",
        '<html><head><title>T</title></head><body><nav><a href="/missing">Missing</a><a href="/also-missing">X</a><a href="/">H</a></nav><h1>H</h1><img src="/nope.png"></body></html>',
    )
    r = await audit(site)
    assert (
        r["desktop"]["metrics"]["images_broken"]
        and r["desktop"]["metrics"]["images_missing_alt"] == 1
    )
    assert sorted(p["status"] for p in r["pages"]) == [404, 404]


async def test_missing_cta_and_heading_order(site: Site) -> None:
    site.html(
        "/",
        "<html><head><title>T</title></head><body><h3>Only h3</h3><p>No actions here.</p></body></html>",
    )
    d = (await audit(site))["desktop"]["metrics"]
    assert d["cta_count"] == 0 and d["h1_count"] == 0 and d["contact_routes"] == 0


async def test_slow_page_times_out_as_evidence(site: Site) -> None:
    site.html("/", "<h1>late</h1>", delay=3)
    r = await audit(site, timeout=1)
    assert r["desktop"]["error"] and "Timeout" in r["desktop"]["error"]
    assert r["desktop"]["metrics"] is None


async def test_oversized_media_not_downloaded(site: Site) -> None:
    site.html(
        "/",
        '<html><head><title>T</title></head><body><h1>V</h1><video src="/big.mp4" autoplay></video><a href="/file.zip">zip</a></body></html>',
    )
    site.raw("/big.mp4", "video/mp4", b"0" * 5_000_000)
    r = await audit(site)
    assert r["desktop"]["blocked_requests"] >= 1
    assert all(not p["url"].endswith(".zip") for p in r["pages"])


async def test_cookie_overlay_detected(site: Site) -> None:
    overlay = (
        '<div style="position:fixed;inset:0;background:#fff">We use cookies. Accept consent?</div>'
    )
    site.html("/", f"<html><head><title>T</title></head><body><h1>H</h1>{overlay}</body></html>")
    assert (await audit(site))["desktop"]["metrics"]["consent_overlay"] is True


async def test_bot_blocked_status_recorded(site: Site) -> None:
    site.html("/", "<h1>Access denied</h1>", status=403)
    assert (await audit(site))["desktop"]["status"] == 403


async def test_non_http_schemes_blocked(site: Site) -> None:
    site.html(
        "/",
        '<html><body><h1>x</h1><iframe src="file:///etc/passwd"></iframe><img src="ftp://example.test/a.png"></body></html>',
    )
    r = await audit(site)
    assert r["desktop"]["blocked_requests"] >= 1
