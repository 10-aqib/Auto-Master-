"""Phase 06: deterministic six-screen concept renderer, safety scan, versioning and rollback."""

from __future__ import annotations

import re
from typing import Any

import pytest
from sqlalchemy import select

from tests.conftest import Harness
from tests.test_audits import _resume
from tests.test_briefs import CTX, _ready_prospect, _rt, mock_brief
from tests.test_sources_api import _owner
from webforge_api.design.brief_schema import PAGE_SLUGS, DesignBrief
from webforge_api.design.renderer import render_site, scan_page, variant_for
from webforge_api.design.templates import NOTICE
from webforge_api.models import Asset, DesignRender, Job, Prospect
from webforge_api.models.enums import JobStatus, ProspectState, Role
from webforge_api.services.ai import MockBriefModel
from webforge_api.worker import drain

FACTS: list[dict[str, Any]] = list(CTX["facts"])  # type: ignore[arg-type]


def site(**brief_over: Any) -> Any:
    return render_site(DesignBrief.model_validate(mock_brief(**brief_over)), FACTS, industry="bakery",
                       author_name="Test Author", author_url="https://author.example.test")  # fmt: skip


def test_renders_six_self_contained_pages_with_notice() -> None:
    s = site()
    assert list(s.pages) == list(PAGE_SLUGS) and s.issues == [] and s.variant == "warm"
    for slug, raw in s.pages.items():
        html = raw.decode()
        assert NOTICE in html and html.count(NOTICE) >= 2  # banner and footer
        assert "<script" not in html.lower() and "http://" not in html.replace(
            'xmlns="http://www.w3.org/2000/svg"', ""
        )
        assert re.search(r'<html lang="en">', html) and html.count("<h1") == 1
        assert 'name="viewport"' in html and "prefers-reduced-motion" in html
        for other in PAGE_SLUGS:
            assert f'href="{other}"' in html  # relative navigation only
        assert 'aria-current="page"' in html and f'href="{slug}" aria-current="page"' in html


def test_render_is_deterministic() -> None:
    assert site().pages == site().pages


def test_inquiry_form_is_inert() -> None:
    html = site().pages["inquiry"].decode()
    form = re.search(r"<form.*?</form>", html, re.S)
    assert form is not None
    assert " action=" not in form.group(0) and " method=" not in form.group(0)
    assert " name=" not in form.group(0)  # nothing would be submitted even if a browser tried
    assert re.findall(r"<button[^>]*>", form.group(0)) == ['<button class="button" type="button">']
    assert "form-action 'none'" in html and "Demo only" in html
    for field_id in re.findall(r'<input id="([^"]+)"', form.group(0)):
        assert f'for="{field_id}"' in form.group(0)  # every field has a label


def test_untrusted_text_is_escaped_and_cannot_inject_markup() -> None:
    data = mock_brief()
    data["pages"][1]["sections"][0]["body"] = (
        "<script>alert(1)</script><img src=x onerror=alert(2)>"
    )
    data["pages"][1]["sections"][0]["heading"] = '"><a href="https://evil.test">x</a>'
    s = render_site(DesignBrief.model_validate(data), [{"id": "F1", "field": "business_name", "value": "<b>Evil</b> & Co"}],
                    industry=None, author_name="A", author_url="")  # fmt: skip
    assert s.issues == []
    html = s.pages["services"].decode()
    assert (
        "&lt;script&gt;" in html
        and "<script" not in html
        and "onerror=alert" not in html.replace("onerror=alert(2)&gt;", "")
    )
    assert 'href="https://evil.test"' not in html and "&lt;b&gt;Evil&lt;/b&gt; &amp; Co" in html


@pytest.mark.parametrize(
    ("snippet", "code"),
    [
        ("<script>x</script>", "script"),
        ('<div onclick="x">', "event_handler"),
        ('<a href="https://example.test">', "external_url"),
        ('<a href="//example.test">', "external_url"),
        ('<img src="data:image/png;base64,AA">', "external_url"),
        ("<iframe></iframe>", "embedded_content"),
        ('<link rel="stylesheet">', "embedded_content"),
        ("<style>@import 'x'</style>", "css_fetch"),
        ('<form action="/x">', "form_action"),
        ('<input name="email">', "named_field"),
        ("<button>Send</button>", "submit_button"),
    ],
)
def test_scan_rejects_unsafe_output(snippet: str, code: str) -> None:
    codes = {i["code"] for i in scan_page(f"<p>{NOTICE}</p>{snippet}")}
    assert code in codes


def test_scan_requires_notice() -> None:
    assert {i["code"] for i in scan_page("<p>hello</p>")} == {"missing_notice"}


def test_assumptions_are_labelled_and_contact_shows_only_verified_facts() -> None:
    s = site()
    assert "To be confirmed by the business" in s.pages["services"].decode()
    contact = s.pages["contact"].decode()
    assert "Contact details will be added once the business confirms them." in contact
    with_contact = render_site(DesignBrief.model_validate(mock_brief()),
                               [*FACTS, {"id": "F3", "field": "verified_domain", "value": "bakery.example.test"}],
                               industry="bakery", author_name="A", author_url="")  # fmt: skip
    assert (
        "<dt>Current website</dt><dd>bakery.example.test</dd>"
        in with_contact.pages["contact"].decode()
    )


def test_button_text_colour_keeps_contrast() -> None:
    data = mock_brief()
    data["palette"]["primary"] = "#F5D76E"  # light primary: white text would fail contrast
    html = (
        render_site(
            DesignBrief.model_validate(data),
            FACTS,
            industry="dental",
            author_name="A",
            author_url="",
        )
        .pages["home"]
        .decode()
    )
    assert "--btn-fg:#1A1A1A" in html


def test_industry_variants() -> None:
    assert variant_for("dental") == "clinical" and variant_for("bakery") == "warm"
    assert variant_for("automotive") == "solid" and variant_for(None) == "professional"


# ----------------------------------------------------------------------------- integration


def _approved_project(h: Harness, csrf: dict[str, str]) -> tuple[Prospect, str]:
    p = _ready_prospect(h)
    assert h.client.post(f"/api/v1/prospects/{p.id}/brief", headers=csrf).status_code == 200
    rt = _rt(h, MockBriefModel())
    try:
        drain(rt, ["design"])
    finally:
        rt.close()
    (design,) = h.client.get(f"/api/v1/designs?prospect_id={p.id}").json()
    brief = h.client.get(f"/api/v1/designs/{design['id']}").json()["briefs"][0]
    r = h.client.post(
        f"/api/v1/designs/briefs/{brief['id']}/review", json={"approve": True}, headers=csrf
    )
    assert r.status_code == 200
    return p, design["id"]


def _render(h: Harness, csrf: dict[str, str], design_id: str) -> dict[str, Any]:
    r = h.client.post(f"/api/v1/designs/{design_id}/render", headers=csrf)
    assert r.status_code == 200, r.text
    rt = _rt(h, MockBriefModel())
    try:
        drain(rt, ["design"])
    finally:
        rt.close()
    render: dict[str, Any] = h.client.get(f"/api/v1/designs/{design_id}").json()["renders"][0]
    return render


def test_render_store_preview_review_and_rollback(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    _, design_id = _approved_project(harness, csrf)
    first = _render(harness, csrf, design_id)
    assert first["status"] == "RENDERED" and first["version"] == 1 and not first["is_active"]
    assert [p["slug"] for p in first["manifest"]["pages"]] == list(PAGE_SLUGS)
    assert first["manifest"]["assets"][0]["license"] == "original-generated"

    page = harness.client.get(f"/api/v1/designs/renders/{first['id']}/pages/inquiry")
    assert page.status_code == 200 and page.headers["content-type"].startswith("text/html")
    csp = page.headers["content-security-policy"]
    assert (
        csp.startswith("sandbox;") and "default-src 'none'" in csp and "form-action 'none'" in csp
    )
    assert (
        page.headers["cache-control"] == "private, no-store"
        and page.headers["x-content-type-options"] == "nosniff"
    )
    assert NOTICE in page.text
    assert (
        harness.client.get(f"/api/v1/designs/renders/{first['id']}/pages/admin").status_code == 422
    )

    r = harness.client.post(
        f"/api/v1/designs/renders/{first['id']}/review",
        json={"approve": True, "notes": "good"},
        headers=csrf,
    )
    assert r.status_code == 200 and r.json()["is_active"] is True
    harness.clock.advance(seconds=5)  # same-second requests share an idempotency key
    second = _render(harness, csrf, design_id)
    assert (
        second["version"] == 2
        and second["manifest"]["site_sha256"] == first["manifest"]["site_sha256"]
    )
    harness.client.post(
        f"/api/v1/designs/renders/{second['id']}/review", json={"approve": True}, headers=csrf
    )
    renders = {
        r["version"]: r
        for r in harness.client.get(f"/api/v1/designs/{design_id}").json()["renders"]
    }
    assert renders[2]["is_active"] and not renders[1]["is_active"]
    # Rollback to version 1.
    assert harness.client.post(
        f"/api/v1/designs/renders/{first['id']}/activate", headers=csrf
    ).json()["is_active"]
    renders = {
        r["version"]: r
        for r in harness.client.get(f"/api/v1/designs/{design_id}").json()["renders"]
    }
    assert renders[1]["is_active"] and not renders[2]["is_active"]
    # Reviewed renders cannot be re-reviewed.
    assert (
        harness.client.post(
            f"/api/v1/designs/renders/{first['id']}/review", json={"approve": False}, headers=csrf
        ).status_code
        == 409
    )
    with harness.db() as db:
        assert db.scalars(select(Asset).where(Asset.provider == "webforge-renderer")).all()


def test_tampered_page_is_refused(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    _, design_id = _approved_project(harness, csrf)
    render = _render(harness, csrf, design_id)
    storage = harness.client.app.state.storage  # type: ignore[attr-defined]
    key = render["manifest"]["pages"][0]["key"]
    storage.put(key, b"<script>alert(1)</script>", "text/html")
    r = harness.client.get(f"/api/v1/designs/renders/{render['id']}/pages/home")
    assert r.status_code == 409 and r.json()["code"] == "integrity_mismatch"


def test_render_requires_approved_brief_and_role(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    p = _ready_prospect(harness)
    harness.client.post(f"/api/v1/prospects/{p.id}/brief", headers=csrf)
    rt = _rt(harness, MockBriefModel())
    try:
        drain(rt, ["design"])
    finally:
        rt.close()
    (design,) = harness.client.get(f"/api/v1/designs?prospect_id={p.id}").json()
    r = harness.client.post(f"/api/v1/designs/{design['id']}/render", headers=csrf)
    assert r.status_code == 409 and r.json()["code"] == "no_approved_brief"
    harness.client.cookies.clear()
    reviewer, secret = harness.create_user(Role.REVIEWER, mfa=True)
    rcsrf = {"X-CSRF-Token": harness.login_active(reviewer, secret)}
    assert (
        harness.client.post(f"/api/v1/designs/{design['id']}/render", headers=rcsrf).status_code
        == 403
    )


def test_locked_prospect_is_not_rendered(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    p, design_id = _approved_project(harness, csrf)
    assert (
        harness.client.post(f"/api/v1/designs/{design_id}/render", headers=csrf).status_code == 200
    )
    with harness.db() as db:
        prospect = db.get(Prospect, p.id)
        assert prospect is not None
        prospect.state = ProspectState.DO_NOT_CONTACT
        db.commit()
    rt = _rt(harness, MockBriefModel())
    try:
        drain(rt, ["design"])
    finally:
        rt.close()
    with harness.db() as db:
        job = db.scalars(select(Job).where(Job.job_type == "design.render")).one()
        assert (
            job.status in (JobStatus.FAILED, JobStatus.DEAD) and job.error_code == "prospect_locked"
        )
        assert db.scalars(select(DesignRender)).all() == []
