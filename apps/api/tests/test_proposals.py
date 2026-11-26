"""Phase 08: proposal PDFs, token-protected previews on a separate origin, expiry, revocation, deletion."""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from tests.conftest import Harness
from tests.fake_validator import FakeValidator, run_validation
from tests.test_audits import _resume
from tests.test_renders import _approved_project, _render
from tests.test_sources_api import _owner
from webforge_api.design.proposal import ProposalInput, build_html
from webforge_api.models import Job, PreviewDeployment, Prospect
from webforge_api.models.enums import JobStatus, ProspectState
from webforge_api.preview import create_preview_app
from webforge_api.security.rate_limit import MemoryRateLimiter
from webforge_api.services.proposals import purge_expired

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def ready_concept(h: Harness) -> tuple[dict[str, str], Prospect, str]:
    csrf = _owner(h)
    _resume(h, csrf)
    p, design_id = _approved_project(h, csrf)
    render = _render(h, csrf, design_id)
    run_validation(h)
    r = h.client.post(
        f"/api/v1/designs/renders/{render['id']}/review", json={"approve": True}, headers=csrf
    )
    assert r.status_code == 200, r.text
    return csrf, p, design_id


def make_proposal(
    h: Harness, csrf: dict[str, str], design_id: str, sandbox: FakeValidator | None = None
) -> dict[str, Any]:
    r = h.client.post(f"/api/v1/designs/{design_id}/proposal", headers=csrf)
    assert r.status_code == 200, r.text
    assert r.json()["queue"] == "audit"
    run_validation(h, sandbox)
    proposals = h.client.get(f"/api/v1/proposals?design_id={design_id}").json()
    assert proposals, "no proposal created"
    out: dict[str, Any] = proposals[0]
    return out


def preview_client(
    h: Harness, limiter: MemoryRateLimiter | None = None, **settings: Any
) -> TestClient:
    s = h.settings.model_copy(update=settings) if settings else h.settings
    app = create_preview_app(s, rate_limiter=limiter or MemoryRateLimiter(), clock=h.clock,
                             storage=h.client.app.state.storage)  # type: ignore[attr-defined]  # fmt: skip
    return TestClient(app, base_url="http://preview.test", follow_redirects=False)


def test_proposal_pdf_is_generated_checked_and_downloadable(harness: Harness) -> None:
    csrf, p, design_id = ready_concept(harness)
    sandbox = FakeValidator()
    proposal = make_proposal(harness, csrf, design_id, sandbox)
    assert (
        proposal["status"] == "READY"
        and proposal["page_count"] == 12
        and proposal["template_version"] == "proposal-1"
    )
    assert all(c["ok"] for c in proposal["checks"]), proposal["checks"]
    assert "Fixture Bakery" in proposal["summary"]
    html = sandbox.pdf_html
    for expected in ("Website Redesign Concept for Fixture Bakery", "Muhammad Aqib", "Website Developer",
                     "https://aqibkhn.space", "https://github.com/10-aqib",
                     "Independent website redesign concept — not the official website of Fixture Bakery.",
                     "not guaranteed results", "not affiliated with, endorsed or authorised"):  # fmt: skip
        assert expected in html, expected
    assert html.count("data:image/png;base64,") == 12  # desktop + mobile for six pages
    assert not UUID_RE.search(html.replace("data:image/png;base64,", ""))  # no internal IDs
    assert "write to" not in html  # no contact email configured -> nothing invented
    assert "http://" not in html and 'src="https' not in html  # nothing external to load
    pdf = harness.client.get(f"/api/v1/proposals/{proposal['id']}/pdf")
    assert (
        pdf.status_code == 200
        and pdf.content.startswith(b"%PDF-")
        and pdf.headers["cache-control"] == "private, no-store"
    )
    with harness.db() as db:
        prospect = db.get(Prospect, p.id)
        assert prospect is not None and prospect.state is ProspectState.PROPOSAL_READY


def test_failed_pdf_checks_hold_the_proposal(harness: Harness) -> None:
    csrf, p, design_id = ready_concept(harness)
    sandbox = FakeValidator()
    sandbox.pdf_transform = lambda html: html.replace(
        "Independent website redesign concept", "Concept"
    )
    proposal = make_proposal(harness, csrf, design_id, sandbox)
    assert proposal["status"] == "DRAFT" and proposal["pdf_sha256"] is None
    assert {c["code"] for c in proposal["checks"] if not c["ok"]} == {"concept_notice"}
    r = harness.client.post(f"/api/v1/proposals/{proposal['id']}/previews", headers=csrf)
    assert r.status_code == 409 and r.json()["code"] == "proposal_not_ready"
    with harness.db() as db:
        prospect = db.get(Prospect, p.id)
        assert prospect is not None and prospect.state is ProspectState.HUMAN_REVIEW


def test_proposal_requires_an_approved_concept(harness: Harness) -> None:
    csrf = _owner(harness)
    _resume(harness, csrf)
    _, design_id = _approved_project(harness, csrf)
    r = harness.client.post(f"/api/v1/designs/{design_id}/proposal", headers=csrf)
    assert r.status_code == 409 and r.json()["code"] == "no_active_concept"


def test_screenshot_version_mismatch_is_refused(harness: Harness) -> None:
    csrf, _, design_id = ready_concept(harness)
    with harness.db() as db:
        db.execute(
            text(
                "UPDATE design_validations SET screenshots = jsonb_set(screenshots, '{0,html_sha256}', '\"0\"')"
            )
        )
        db.commit()
    harness.client.post(f"/api/v1/designs/{design_id}/proposal", headers=csrf)
    run_validation(harness)
    with harness.db() as db:
        job = db.scalars(select(Job).where(Job.job_type == "proposal.generate")).one()
        assert (
            job.status in (JobStatus.FAILED, JobStatus.DEAD)
            and job.error_code == "version_mismatch"
        )


def test_preview_link_lifecycle_on_separate_origin(harness: Harness) -> None:
    csrf, _, design_id = ready_concept(harness)
    proposal = make_proposal(harness, csrf, design_id)
    created = harness.client.post(
        f"/api/v1/proposals/{proposal['id']}/previews", headers=csrf
    ).json()
    url = created["url"]
    assert url.startswith(harness.settings.preview_base_url + "/p/")
    token = url.rstrip("/").rsplit("/", 1)[-1]
    assert len(token) >= 43  # 32 random bytes, base64url
    with harness.db() as db:
        rows = db.execute(text("SELECT token_hash, route FROM preview_deployments")).all()
        assert rows and all(token not in (r.token_hash + r.route) for r in rows)
        assert rows[0].token_hash != token
    client = preview_client(harness)
    root = client.get(f"/p/{token}/")
    assert root.status_code == 302 and root.headers["location"] == f"/p/{token}/home"
    page = client.get(f"/p/{token}/home")
    assert page.status_code == 200 and "Independent redesign concept" in page.text
    h = page.headers
    assert (
        h["content-security-policy"].startswith("sandbox;")
        and "frame-ancestors 'none'" in h["content-security-policy"]
    )
    assert (
        h["x-frame-options"] == "DENY" and "noindex" in h["x-robots-tag"] and "set-cookie" not in h
    )
    assert h["referrer-policy"] == "no-referrer" and h["cache-control"] == "private, no-store"
    form_page = client.get(f"/p/{token}/inquiry").text
    assert " name=" not in re.search(r"<form.*?</form>", form_page, re.S).group(0)  # type: ignore[union-attr]
    pdf = client.get(f"/p/{token}/proposal.pdf")
    assert (
        pdf.status_code == 200
        and pdf.headers["content-type"] == "application/pdf"
        and pdf.content.startswith(b"%PDF-")
    )
    for bad in (f"/p/{token}/admin", f"/p/{token}/../home", "/p/" + "A" * 43 + "/home", f"/p/{token[:-1]}x/home",
                "/docs", "/openapi.json", "/api/v1/auth/me", "/"):  # fmt: skip
        assert client.get(bad).status_code == 404, bad
    assert client.post(f"/p/{token}/home").status_code == 405
    with harness.db() as db:
        row = db.scalars(select(PreviewDeployment)).one()
        assert row.access_count == 3 and row.last_accessed_at is not None

    # Revocation is immediate.
    assert (
        harness.client.post(
            f"/api/v1/previews/{created['preview']['id']}/revoke", headers=csrf
        ).json()["status"]
        == "REVOKED"
    )
    assert client.get(f"/p/{token}/home").status_code == 404


def test_preview_expires_after_retention_window(harness: Harness) -> None:
    csrf, _, design_id = ready_concept(harness)
    proposal = make_proposal(harness, csrf, design_id)
    token = (
        harness.client.post(f"/api/v1/proposals/{proposal['id']}/previews", headers=csrf)
        .json()["url"]
        .rstrip("/")
        .rsplit("/", 1)[-1]
    )
    client = preview_client(harness)
    assert client.get(f"/p/{token}/home").status_code == 200
    harness.clock.advance(days=harness.settings.preview_retention_days, seconds=1)
    assert client.get(f"/p/{token}/home").status_code == 404


def test_delete_and_retention_purge_remove_artifacts(harness: Harness) -> None:
    csrf, _, design_id = ready_concept(harness)
    proposal = make_proposal(harness, csrf, design_id)
    token = (
        harness.client.post(f"/api/v1/proposals/{proposal['id']}/previews", headers=csrf)
        .json()["url"]
        .rstrip("/")
        .rsplit("/", 1)[-1]
    )
    storage = harness.client.app.state.storage  # type: ignore[attr-defined]
    key = f"proposals/{proposal['id']}/proposal-v1.pdf"
    assert storage.exists(key)
    deleted = harness.client.post(f"/api/v1/proposals/{proposal['id']}/delete", headers=csrf).json()
    assert (
        deleted["status"] == "REVOKED"
        and deleted["deleted_at"]
        and deleted["previews"][0]["status"] == "REVOKED"
    )
    assert not storage.exists(key)
    assert preview_client(harness).get(f"/p/{token}/proposal.pdf").status_code == 404
    assert harness.client.get(f"/api/v1/proposals/{proposal['id']}/pdf").status_code == 404

    # A second proposal expires through the retention job.
    harness.clock.advance(seconds=5)
    second = make_proposal(harness, csrf, design_id)
    harness.clock.advance(days=harness.settings.artifact_retention_days + 1)
    with harness.db() as db:
        counts = purge_expired(db, harness.crypto, storage, now=harness.clock())
    assert counts["proposals_expired"] == 1
    with harness.db() as db:  # (the staff session itself has expired by now)
        status = db.execute(
            text("SELECT status FROM proposals WHERE id = :id"), {"id": second["id"]}
        ).scalar_one()
    assert status == "EXPIRED" and not storage.exists(f"proposals/{second['id']}/proposal-v2.pdf")


def test_preview_rate_limit(harness: Harness) -> None:
    csrf, _, design_id = ready_concept(harness)
    proposal = make_proposal(harness, csrf, design_id)
    token = (
        harness.client.post(f"/api/v1/proposals/{proposal['id']}/previews", headers=csrf)
        .json()["url"]
        .rstrip("/")
        .rsplit("/", 1)[-1]
    )
    client = preview_client(harness, preview_rate_limit_per_minute=10)
    codes = [client.get(f"/p/{token}/home").status_code for _ in range(11)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_tokens_are_unique_and_roles_enforced(harness: Harness) -> None:
    csrf, _, design_id = ready_concept(harness)
    proposal = make_proposal(harness, csrf, design_id)
    urls = {
        harness.client.post(f"/api/v1/proposals/{proposal['id']}/previews", headers=csrf).json()[
            "url"
        ]
        for _ in range(3)
    }
    assert len(urls) == 3
    harness.client.cookies.clear()
    from webforge_api.models.enums import Role

    reviewer, secret = harness.create_user(Role.REVIEWER, mfa=True)
    rcsrf = {"X-CSRF-Token": harness.login_active(reviewer, secret)}
    assert (
        harness.client.post(
            f"/api/v1/proposals/{proposal['id']}/previews", headers=rcsrf
        ).status_code
        == 403
    )
    assert (
        harness.client.post(f"/api/v1/proposals/{proposal['id']}/delete", headers=rcsrf).status_code
        == 403
    )


@pytest.mark.parametrize("email", ["", "hello@owner-domain.example"])
def test_contact_email_only_when_supplied(email: str) -> None:
    from tests.test_briefs import mock_brief

    inp = ProposalInput(business='<b>"Evil" & Co</b>', prepared_on="1 Jan 2027", render_version=1, validated_on="1 Jan 2027",
                        checks_passed=293, audit_date=None, audit_url=None, findings=[], brief=mock_brief(),
                        shots={s: {"desktop": "data:image/png;base64,AA", "mobile": "data:image/png;base64,AA"}
                               for s in ("home", "services", "about", "trust", "inquiry", "contact")},
                        author={"name": "A", "title": "T", "url": "https://a.example", "github": ""}, contact_email=email)  # fmt: skip
    html = build_html(inp)
    assert "&lt;b&gt;&#34;Evil&#34; &amp; Co&lt;/b&gt;" in html and '<b>"Evil"' not in html
    assert ("write to hello@owner-domain.example" in html) is bool(email)
    assert "GitHub:" not in html  # omitted when not configured


def test_production_requires_separate_https_preview_origin() -> None:
    from tests.conftest import make_settings

    s = make_settings(
        app_url="https://app.example.test",
        api_url="https://api.example.test",
        preview_base_url="https://app.example.test",
    )
    assert any("separate origin" in p for p in s.production_problems())
    s = make_settings(
        app_url="https://app.example.test",
        api_url="https://api.example.test",
        preview_base_url="http://preview.example.test",
    )
    assert any("PREVIEW_BASE_URL must use https" in p for p in s.production_problems())
    s = make_settings(
        app_url="https://app.example.test",
        api_url="https://api.example.test",
        preview_base_url="https://preview.example.test",
    )
    assert not any("PREVIEW" in p for p in s.production_problems())
