"""Phase 07: offline responsive validation, screenshots, report and bounded repair."""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from tests.conftest import Harness
from tests.fake_validator import FakeValidator, run_validation
from tests.test_audits import _resume
from tests.test_renders import _approved_project, _render
from tests.test_sources_api import _owner
from webforge_api.design.validation_rules import evaluate
from webforge_api.models import DesignValidation, Job, Prospect
from webforge_api.models.enums import JobStatus, ProspectState


def detail(h: Harness, design_id: str) -> dict[str, Any]:
    d: dict[str, Any] = h.client.get(f"/api/v1/designs/{design_id}").json()
    return d


def setup(h: Harness) -> tuple[dict[str, str], Prospect, str, dict[str, Any]]:
    csrf = _owner(h)
    _resume(h, csrf)
    p, design_id = _approved_project(h, csrf)
    render = _render(h, csrf, design_id)
    return csrf, p, design_id, render


def test_clean_render_is_ready_with_eighteen_screenshots(harness: Harness) -> None:
    csrf, p, design_id, render = setup(harness)
    sandbox = FakeValidator()
    run_validation(harness, sandbox)
    assert sorted(sandbox.calls) == sorted(
        ["home", "services", "about", "trust", "inquiry", "contact"]
    )
    (v,) = detail(harness, design_id)["validations"]
    assert (
        v["status"] == "READY"
        and v["render_id"] == render["id"]
        and v["site_sha256"] == render["manifest"]["site_sha256"]
    )
    assert len(v["screenshots"]) == 18 and {s["viewport"] for s in v["screenshots"]} == {
        "desktop",
        "tablet",
        "mobile",
    }
    assert (
        v["report"]["summary"]["failed_critical"] == 0
        and v["report"]["validator_version"] == "validator-1"
    )
    page_hashes = {pg["slug"]: pg["sha256"] for pg in render["manifest"]["pages"]}
    assert all(s["html_sha256"] == page_hashes[s["slug"]] for s in v["screenshots"])
    shot = harness.client.get(f"/api/v1/designs/validations/{v['id']}/screenshots/inquiry/mobile")
    assert (
        shot.status_code == 200
        and shot.content[:4] == b"\x89PNG"
        and shot.headers["cache-control"] == "private, no-store"
    )
    with harness.db() as db:
        prospect = db.get(Prospect, p.id)
        assert prospect is not None and prospect.state is ProspectState.VALIDATING
    ok = harness.client.post(
        f"/api/v1/designs/renders/{render['id']}/review", json={"approve": True}, headers=csrf
    )
    assert ok.status_code == 200 and ok.json()["is_active"]


def test_unvalidated_render_cannot_be_approved(harness: Harness) -> None:
    csrf, _, _, render = setup(harness)
    r = harness.client.post(
        f"/api/v1/designs/renders/{render['id']}/review", json={"approve": True}, headers=csrf
    )
    assert r.status_code == 409 and r.json()["code"] == "not_validated"


@pytest.mark.parametrize(
    ("defect", "code"),
    [
        (
            {
                ("home", "mobile"): {
                    "metrics": {"scroll_width": 620, "overflow_elements": ["div.wide"]}
                }
            },
            "no_overflow",
        ),
        ({"services": {"console_errors": ["boom"]}}, "console_clean"),
        (
            {"about": {"blocked_requests": ["GET https://fonts.example.test/x.woff2"]}},
            "no_external_requests",
        ),
        ({"trust": {"metrics": {"broken_images": ["x.png"]}}}, "images_load"),
        ({"contact": {"metrics": {"links": ["https://concept.invalid/pricing"]}}}, "routes"),
        (
            {"inquiry": {"form": {"navigated": True, "requests_after_interaction": 1}}},
            "demo_form_inert",
        ),
        ({"home": {"metrics": {"notice_visible_at_top": False}}}, "concept_notice"),
        ({"home": {"html_sha256": "0" * 64}}, "version_match"),
        ({"home": {"screenshot_sha256": "f" * 64}}, "screenshot"),
        ({"home": {"status": 500}}, "loads"),
    ],
)
def test_critical_failures_need_revision(
    harness: Harness, defect: dict[Any, Any], code: str
) -> None:
    _, p, design_id, _ = setup(harness)
    run_validation(harness, FakeValidator(defects=defect))
    (v,) = detail(harness, design_id)["validations"]
    assert v["status"] == "NEEDS_REVISION"
    failed = [c for c in v["report"]["checks"] if c["status"] == "fail"]
    assert any(c["code"] == code and c["severity"] == "critical" for c in failed), failed
    assert all(
        c["evidence"] is not None or c["code"] in ("screenshot", "concept_notice", "loads")
        for c in failed
    )
    with harness.db() as db:
        prospect = db.get(Prospect, p.id)
        assert prospect is not None and prospect.state is ProspectState.HUMAN_REVIEW


def test_major_issues_are_warnings_not_blockers(harness: Harness) -> None:
    _, _, design_id, _ = setup(harness)
    run_validation(
        harness,
        FakeValidator(
            defects={"about": {"metrics": {"heading_skipped": True, "unlabeled_fields": ["x"]}}}
        ),
    )
    (v,) = detail(harness, design_id)["validations"]
    assert v["status"] == "READY" and v["report"]["summary"]["failed_major"] >= 2


def test_contrast_failure_triggers_one_safe_mode_repair(harness: Harness) -> None:
    _, _, design_id, first = setup(harness)
    bad = {"metrics": {"contrast_failures": [{"tag": "p", "ratio": 3.1, "need": 4.5, "text": "x"}]}}
    sandbox = FakeValidator(defects={"home": bad, "safe_mode_fixes": {}})
    run_validation(harness, sandbox)
    d = detail(harness, design_id)
    renders = {r["version"]: r for r in d["renders"]}
    assert set(renders) == {1, 2}
    assert (
        renders[2]["manifest"]["safe_mode"] is True
        and renders[2]["manifest"]["repair_of"] == first["id"]
    )
    by_render = {v["render_id"]: v for v in d["validations"]}
    assert by_render[renders[2]["id"]]["report"]["summary"]["failed_major"] == 0


def test_repair_is_bounded(harness: Harness) -> None:
    _, _, design_id, _ = setup(harness)
    bad = {"metrics": {"contrast_failures": [{"tag": "p", "ratio": 3.1, "need": 4.5, "text": "x"}]}}
    run_validation(harness, FakeValidator(defects={"home": bad}))  # safe mode does not fix it here
    d = detail(harness, design_id)
    assert len(d["renders"]) == 2 and len(d["validations"]) == 2  # original + exactly one repair


def test_isolation_unproven_blocks_validation(harness: Harness) -> None:
    _, _, design_id, _ = setup(harness)
    run_validation(harness, FakeValidator(isolated=False))
    assert detail(harness, design_id)["validations"] == []
    with harness.db() as db:
        job = db.scalars(select(Job).where(Job.job_type == "design.validate")).one()
        assert (
            job.status in (JobStatus.FAILED, JobStatus.DEAD)
            and job.error_code == "isolation_unproven"
        )


def test_tampered_stored_page_stops_validation(harness: Harness) -> None:
    _, _, _, render = setup(harness)
    storage = harness.client.app.state.storage  # type: ignore[attr-defined]
    storage.put(render["manifest"]["pages"][0]["key"], b"<p>changed</p>", "text/html")
    run_validation(harness, FakeValidator())
    with harness.db() as db:
        job = db.scalars(select(Job).where(Job.job_type == "design.validate")).one()
        assert job.error_code == "integrity_mismatch"
        assert db.scalars(select(DesignValidation)).all() == []


def test_missing_page_and_unknown_focus() -> None:
    pages = [{"slug": "home", "sha256": "x"}]
    report = evaluate({}, pages)
    codes = {c["code"]: c for c in report["checks"]}
    assert report["status"] == "NEEDS_REVISION" and codes["six_pages"]["status"] == "fail"
