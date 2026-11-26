"""Offline concept validation: run the sandbox checks, store screenshots and the report, repair once."""

from __future__ import annotations

import base64
import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.design.brief_schema import PAGE_SLUGS
from webforge_api.design.validation_rules import VALIDATOR_VERSION, evaluate
from webforge_api.models import DesignPage, DesignProject, DesignRender, DesignValidation, Prospect
from webforge_api.models.enums import ProspectState
from webforge_api.security.crypto import Crypto
from webforge_api.services import activity
from webforge_api.services.audits import BrowserClient
from webforge_api.services.jobs import JobError
from webforge_api.services.prospect_state import ALLOWED, LOCKED, transition
from webforge_api.services.renders import RenderDeps, render_project
from webforge_api.storage import Storage

MAX_SAFE_MODE_REPAIRS = (
    1  # bounded: one deterministic repair render per brief version, never AI regeneration
)


@dataclass
class ValidationDeps:
    db: Session
    settings: Settings
    crypto: Crypto
    storage: Storage
    browser: BrowserClient
    now: datetime


def validate_render(
    deps: ValidationDeps, render_id: uuid.UUID, correlation_id: str | None = None
) -> DesignValidation:
    db, now = deps.db, deps.now
    render = db.get(DesignRender, render_id)
    if render is None:
        raise JobError("not_found", "Render not found.")
    if render.status not in ("RENDERED", "APPROVED"):
        raise JobError("not_validatable", f"Render is {render.status}.")
    project = db.get(DesignProject, render.design_project_id)
    prospect = db.get(Prospect, project.prospect_id) if project else None
    if project is None or prospect is None or prospect.state in LOCKED or prospect.do_not_contact:
        raise JobError("prospect_locked", "Prospect is locked; not validating.")
    if not deps.browser.selftest().get("isolated"):
        raise JobError(
            "isolation_unproven", "Browser isolation self-test failed; validation is disabled."
        )
    if ProspectState.VALIDATING in ALLOWED[prospect.state]:
        transition(
            db,
            deps.crypto,
            prospect,
            ProspectState.VALIDATING,
            reason="concept validation started",
            now=now,
        )
        db.commit()

    pages: dict[str, str] = {}
    for p in render.manifest.get("pages", []):
        data = deps.storage.get(p["key"])
        if hashlib.sha256(data).hexdigest() != p["sha256"]:
            raise JobError(
                "integrity_mismatch", f"Stored page {p['slug']} does not match its hash."
            )
        pages[p["slug"]] = data.decode()
    results: dict[str, dict[str, Any]] = {}
    browser_version: str | None = None
    for slug in PAGE_SLUGS:
        if slug in pages:
            results[slug] = deps.browser.validate(pages, slug)
            browser_version = results[slug].get("browser_version")
    report = evaluate(results, render.manifest.get("pages", []))
    attempt = (
        db.scalar(
            select(func.count())
            .select_from(DesignValidation)
            .where(DesignValidation.render_id == render.id)
        )
        or 0
    ) + 1
    shots: list[dict[str, Any]] = []
    prefix = f"designs/{project.id}/r{render.version}/validation-{attempt}"
    for slug, result in results.items():
        for r in result.get("results", []):
            if not r.get("screenshot_png_b64"):
                continue
            png = base64.b64decode(r["screenshot_png_b64"])
            if hashlib.sha256(png).hexdigest() != r.get("screenshot_sha256"):
                continue  # already a critical failure in the report
            stored = deps.storage.put(f"{prefix}/{slug}-{r['viewport']}.png", png, "image/png")
            shots.append({"slug": slug, "viewport": r["viewport"], "key": stored.key, "sha256": stored.sha256,
                          "bytes": stored.size, "html_sha256": r.get("html_sha256")})  # fmt: skip
    row = DesignValidation(render_id=render.id, status=report["status"], validator_version=VALIDATOR_VERSION,
                           browser_version=browser_version, site_sha256=render.manifest.get("site_sha256", ""),
                           report=report, screenshots=shots, created_at=now)  # fmt: skip
    db.add(row)
    for page in db.scalars(
        select(DesignPage).where(
            DesignPage.design_project_id == project.id, DesignPage.version == render.version
        )
    ):
        desktop = next(
            (s for s in shots if s["slug"] == page.slug and s["viewport"] == "desktop"), None
        )
        if desktop:
            page.screenshot_key = desktop["key"]
    db.flush()
    activity.record(db, deps.crypto, action="design.validated", actor_user_id=None, system=True,
                    entity_type="design_render", entity_id=render.id,
                    metadata={"status": report["status"], **report["summary"]})  # fmt: skip
    db.commit()

    repaired = False
    if report["repairable"] and not render.manifest.get("safe_mode"):
        repairs = db.scalar(
            select(func.count())
            .select_from(DesignRender)
            .where(
                DesignRender.brief_id == render.brief_id,
                DesignRender.manifest["safe_mode"].as_boolean().is_(True),
            )
        )
        if (repairs or 0) < MAX_SAFE_MODE_REPAIRS:
            render_project(RenderDeps(db, deps.settings, deps.crypto, deps.storage, now), project.id,
                           safe_mode=True, repair_of=render.id, correlation_id=correlation_id)  # fmt: skip
            repaired = True
    if report["status"] != "READY" and not repaired:
        prospect = db.get(Prospect, project.prospect_id)
        if prospect is not None and ProspectState.HUMAN_REVIEW in ALLOWED[prospect.state]:
            transition(
                db,
                deps.crypto,
                prospect,
                ProspectState.HUMAN_REVIEW,
                reason="concept needs revision",
                now=now,
            )
            db.commit()
    return row


def screenshot(
    db: Session, storage: Storage, validation_id: uuid.UUID, slug: str, viewport: str
) -> bytes | None:
    row = db.get(DesignValidation, validation_id)
    shot = next(
        (
            s
            for s in (row.screenshots if row else [])
            if s["slug"] == slug and s["viewport"] == viewport
        ),
        None,
    )
    if shot is None:
        return None
    data = storage.get(shot["key"])
    return data if hashlib.sha256(data).hexdigest() == shot["sha256"] else None
