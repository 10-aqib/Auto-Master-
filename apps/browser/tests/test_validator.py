"""Offline concept validation (Phase 07) against small fixture pages."""

from __future__ import annotations

import base64
from typing import Any

from fastapi.testclient import TestClient

from webforge_browser import app as app_module
from webforge_browser.validator import run_validation

NOTICE = '<div class="notice">Independent redesign concept — not the official website.</div>'
GOOD_CSS = (
    "body{margin:0;font:16px/1.5 sans-serif;color:#111;background:#fff}"
    "a:focus-visible,button:focus-visible,input:focus-visible{outline:3px solid #c2410c}"
    ".notice{background:#111;color:#fff;padding:8px}"
)


def page(body: str, css: str = GOOD_CSS) -> str:
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width, initial-scale=1"><title>t</title><style>{css}</style></head>'
            f'<body>{NOTICE}<nav><a href="home">Home</a> <a href="contact">Contact</a></nav>{body}</body></html>')  # fmt: skip


GOOD = {
    "home": page("<main><h1>Welcome</h1><p>Hello.</p><h2>More</h2><p>Text.</p></main>"),
    "contact": page(
        '<main><h1>Contact</h1><form><label for="n">Name</label><input id="n" type="text">'
        '<label for="e">Email</label><input id="e" type="text"><button type="button">Send</button></form></main>'
    ),
}


def first(result: dict[str, Any]) -> dict[str, Any]:
    r: dict[str, Any] = result["results"][0]
    return r


async def test_clean_page_passes_and_screenshots_are_high_resolution() -> None:
    out = await run_validation(GOOD, "home", ["mobile", "desktop"])
    mobile, desktop = out["results"]
    m = mobile["metrics"]
    assert m["scroll_width"] == 390 and not m["overflow_elements"]
    assert m["h1_count"] == 1 and not m["heading_skipped"] and m["contrast_failures"] == []
    assert (
        m["notice_visible_at_top"]
        and not mobile["console_errors"]
        and not mobile["blocked_requests"]
    )
    assert {link.rsplit("/", 1)[-1] for link in m["links"]} == {"home", "contact"}
    png = base64.b64decode(desktop["screenshot_png_b64"])
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
    width = int.from_bytes(png[16:20], "big")
    assert width == 2880  # 1440 css px at device scale 2
    assert any(f["outline"] for f in mobile["focus"])


async def test_inert_form_does_not_navigate_or_request() -> None:
    r = first(await run_validation(GOOD, "contact", ["desktop"]))
    assert r["form"] == {"navigated": False, "requests_after_interaction": 0}
    assert r["metrics"]["unlabeled_fields"] == []


async def test_submitting_form_is_detected() -> None:
    pages = {
        **GOOD,
        "contact": page(
            '<main><h1>C</h1><form action="home"><input aria-label="n" name="n"><button>Go</button></form></main>'
        ),
    }
    r = first(await run_validation(pages, "contact", ["desktop"]))
    assert r["form"]["navigated"] is True
    assert r["metrics"]["named_fields"] == 1


async def test_problem_fixtures_are_reported() -> None:
    bad_css = GOOD_CSS + ".wide{width:1200px}.faint{color:#ccc}a:focus-visible{outline:none}"
    body = (
        '<main><h2>No h1</h2><h4>Skipped</h4><div class="wide">wide</div><p class="faint">low contrast</p>'
        '<img src="https://cdn.example.test/x.png"><a href="https://elsewhere.test/"></a>'
        '<input id="x"><script>throw new Error("boom")</script></main>'
    )
    pages = {**GOOD, "home": page(body, bad_css)}
    r = first(await run_validation(pages, "home", ["mobile"]))
    m = r["metrics"]
    assert m["scroll_width"] > 390 and m["overflow_elements"]
    assert m["h1_count"] == 0 and m["heading_skipped"]
    assert any(f["text"] == "low contrast" for f in m["contrast_failures"])
    assert m["broken_images"] and m["images_missing_alt"] == 1
    assert m["unnamed_controls"] and m["unlabeled_fields"] == ["x"]
    assert any("cdn.example.test" in b for b in r["blocked_requests"])  # never fetched
    assert any("boom" in e for e in r["console_errors"])


async def test_missing_notice_and_broken_link_targets() -> None:
    pages = {"home": GOOD["home"].replace(NOTICE, ""), "contact": GOOD["contact"]}
    m = first(await run_validation(pages, "home", ["desktop"]))["metrics"]
    assert m["notice_visible_at_top"] is False
    pages = {"home": GOOD["home"]}  # nav links to "contact" which is not supplied
    r = first(await run_validation(pages, "home", ["desktop"]))
    assert any(link.endswith("/contact") for link in r["metrics"]["links"])


def test_validate_endpoint_rejects_bad_input() -> None:
    client = TestClient(app_module.app)
    assert (
        client.post("/validate", json={"pages": {"home": "x"}, "slug": "about"}).status_code == 422
    )
    assert (
        client.post(
            "/validate", json={"pages": {"home": "x"}, "slug": "home", "viewports": ["watch"]}
        ).status_code
        == 422
    )
    assert client.post("/validate", json={"pages": {"../x": "x"}, "slug": "home"}).status_code in (
        413,
        422,
    )
    assert (
        client.post(
            "/validate", json={"pages": {"home": "x"}, "slug": "home", "extra": 1}
        ).status_code
        == 422
    )


async def test_csp_form_action_none_blocks_implicit_submission() -> None:
    csp = '<meta http-equiv="Content-Security-Policy" content="form-action \'none\'">'
    single = page(
        '<main><h1>C</h1><form><label for="n">Name</label><input id="n" type="text"></form></main>'
    )
    pages = {**GOOD, "contact": single.replace("<title>", csp + "<title>")}
    r = first(await run_validation(pages, "contact", ["desktop"]))
    assert r["form"]["navigated"] is False
