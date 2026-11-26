"""Website audits via the isolated browser sandbox.

The worker never browses itself: it asks the sandbox (no secrets, no DB access, internet only via
the SSRF-filtering egress proxy). Before auditing, the sandbox's isolation self-test must pass;
otherwise real crawling is refused.
"""

from __future__ import annotations

import base64
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import AuditFinding, Prospect, WebsiteAudit
from webforge_api.models.enums import ProspectState, RunStatus, Severity
from webforge_api.security.crypto import Crypto
from webforge_api.services.audit_rules import RULES_VERSION, evaluate
from webforge_api.services.jobs import JobError, JobSpec
from webforge_api.services.prospect_state import ALLOWED, LOCKED, transition
from webforge_api.storage import Storage

AUDIT = JobSpec("prospect.audit", "audit", max_attempts=2)
SELFTEST_TTL_SECONDS = 600


class BrowserClient:
    def __init__(self, base_url: str, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(
            base_url=base_url,
            transport=transport,
            timeout=httpx.Timeout(660, connect=5),
            trust_env=False,
        )
        self._selftest: tuple[float, dict[str, Any]] | None = None

    def selftest(self) -> dict[str, Any]:
        if self._selftest and time.monotonic() - self._selftest[0] < SELFTEST_TTL_SECONDS:
            return self._selftest[1]
        try:
            r = self._client.get("/selftest", timeout=60)
            r.raise_for_status()
            data: dict[str, Any] = r.json()
        except httpx.HTTPError as exc:
            raise JobError(
                "browser_unavailable", "Browser sandbox unreachable.", retryable=True
            ) from exc
        self._selftest = (time.monotonic(), data)
        return data

    def audit(self, url: str, settings: Settings) -> dict[str, Any]:
        body = {
            "url": url,
            "max_pages": settings.browser_max_pages,
            "max_depth": settings.browser_max_depth,
            "page_timeout_s": settings.browser_page_timeout_seconds,
            "total_timeout_s": settings.browser_job_timeout_seconds,
            "user_agent": settings.website_fetch_user_agent,
        }
        try:
            r = self._client.post("/audit", json=body)
        except httpx.HTTPError as exc:
            raise JobError(
                "browser_unavailable", "Browser sandbox request failed.", retryable=True
            ) from exc
        if r.status_code >= 500:
            raise JobError(
                "browser_error",
                f"Browser sandbox returned {r.status_code}.",
                retryable=r.status_code in (502, 503, 504),
            )
        if r.status_code >= 400:
            raise JobError(
                "browser_rejected", f"Browser sandbox rejected the request ({r.status_code})."
            )
        data: dict[str, Any] = r.json()
        return data

    def validate(self, pages: dict[str, str], slug: str) -> dict[str, Any]:
        """Offline validation of one concept page at desktop, tablet and mobile widths."""
        try:
            r = self._client.post("/validate", json={"pages": pages, "slug": slug}, timeout=180)
        except httpx.HTTPError as exc:
            raise JobError(
                "browser_unavailable", "Browser sandbox request failed.", retryable=True
            ) from exc
        if r.status_code >= 400:
            raise JobError(
                "browser_error" if r.status_code >= 500 else "browser_rejected",
                f"Browser sandbox returned {r.status_code} for validation.",
                retryable=r.status_code in (502, 503, 504),
            )
        data: dict[str, Any] = r.json()
        return data

    def pdf(self, html: str, footer_notice: str) -> bytes:
        """Render a self-contained proposal document to PDF, offline."""
        try:
            r = self._client.post(
                "/pdf", json={"html": html, "footer_notice": footer_notice}, timeout=240
            )
        except httpx.HTTPError as exc:
            raise JobError(
                "browser_unavailable", "Browser sandbox request failed.", retryable=True
            ) from exc
        if r.status_code >= 400 or not r.content.startswith(b"%PDF-"):
            raise JobError(
                "pdf_failed",
                f"Browser sandbox could not render the PDF ({r.status_code}).",
                retryable=r.status_code in (502, 503, 504),
            )
        if r.headers.get("x-blocked-requests", "0") != "0":
            raise JobError(
                "pdf_external_requests", "The proposal document tried to load external resources."
            )
        return r.content

    def close(self) -> None:
        self._client.close()


@dataclass
class AuditDeps:
    db: Session
    settings: Settings
    crypto: Crypto
    storage: Storage
    browser: BrowserClient
    now: datetime


def run_audit(deps: AuditDeps, prospect_id: uuid.UUID) -> WebsiteAudit:
    db, now = deps.db, deps.now
    prospect = db.get(Prospect, prospect_id, with_for_update=True)
    if prospect is None:
        raise JobError("not_found", "Prospect not found.")
    if prospect.state in LOCKED or prospect.do_not_contact:
        raise JobError("prospect_locked", f"Prospect is {prospect.state.value}; not auditing.")
    if not prospect.website_url:
        raise JobError("no_website", "Prospect has no verified website.")

    selftest = deps.browser.selftest()
    if not selftest.get("isolated"):
        raise JobError(
            "isolation_unproven", "Browser isolation self-test failed; real crawling is disabled."
        )

    audit = WebsiteAudit(
        prospect_id=prospect.id,
        url=prospect.website_url,
        status=RunStatus.RUNNING,
        audit_version=f"{deps.settings.audit_version}/rules-{RULES_VERSION}",
        started_at=now,
    )
    db.add(audit)
    if ProspectState.AUDITING in ALLOWED[prospect.state]:
        transition(
            db, deps.crypto, prospect, ProspectState.AUDITING, reason="audit started", now=now
        )
    db.commit()

    try:
        result = deps.browser.audit(prospect.website_url, deps.settings)
    except JobError as exc:
        audit.status = RunStatus.FAILED
        audit.error_summary = str(exc)
        audit.finished_at = now
        db.commit()
        raise

    outcome = evaluate(result)
    keys: dict[str, str] = {}
    for view in ("desktop", "mobile"):
        b64 = (result.get(view) or {}).get("screenshot_png_b64")
        if b64:
            key = f"audits/{audit.id}/{view}.png"
            deps.storage.put(key, base64.b64decode(b64), "image/png")
            keys[view] = key
    audit.desktop_screenshot_key = keys.get("desktop")
    audit.mobile_screenshot_key = keys.get("mobile")
    audit.browser_version = str(result.get("browser_version", ""))[:64] or None
    audit.performance_source = "playwright-load-timing (single run, indicative only)"
    audit.finished_at = now
    audit.status = RunStatus.SUCCEEDED if outcome.status == "SUCCEEDED" else RunStatus.FAILED
    audit.error_summary = outcome.error_summary
    audit.scores = {
        "rules_version": RULES_VERSION,
        "overall": outcome.overall,
        "categories": outcome.categories,
        "strengths": outcome.strengths,
        "caveats": outcome.caveats,
        "pages_checked": 1 + len(result.get("pages") or []),
        "limits": result.get("limits"),
    }
    for f in outcome.findings:
        db.add(
            AuditFinding(
                audit_id=audit.id,
                category=f.category,
                severity=Severity(f.severity),
                code=f.code,
                description=f"{f.title}. {f.description}",
                evidence_url=f.observed_url[:2048],
                evidence_text=str(f.evidence)[:4000],
                screenshot_key=keys.get("mobile" if f.viewport.startswith("mobile") else "desktop"),
                viewport=f.viewport[:32],
                confidence=f.confidence,
                observed_at=now,
                reproduction_steps="\n".join(f.reproduction),
            )
        )
    if audit.status is RunStatus.SUCCEEDED and ProspectState.AUDITED in ALLOWED[prospect.state]:
        transition(
            db, deps.crypto, prospect, ProspectState.AUDITED, reason="audit finished", now=now
        )
    elif audit.status is RunStatus.FAILED and ProspectState.HUMAN_REVIEW in ALLOWED[prospect.state]:
        transition(
            db,
            deps.crypto,
            prospect,
            ProspectState.HUMAN_REVIEW,
            reason="audit could not run",
            now=now,
        )
    db.commit()
    return audit
