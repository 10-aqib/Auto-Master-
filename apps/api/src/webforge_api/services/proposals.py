"""Proposal PDFs and token-protected previews (Phase 08). Nothing here sends email."""

from __future__ import annotations

import base64
import contextlib
import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.design.proposal import (
    FOOTER_NOTICE,
    TEMPLATE_VERSION,
    ProposalInput,
    build_html,
    check_pdf,
    opportunities_for,
)
from webforge_api.models import (
    AuditFinding,
    DesignBrief,
    DesignProject,
    DesignRender,
    PreviewDeployment,
    Proposal,
    Prospect,
    WebsiteAudit,
)
from webforge_api.models.enums import PreviewStatus, ProposalStatus, ProspectState, RunStatus
from webforge_api.security.crypto import Crypto
from webforge_api.services import activity
from webforge_api.services.audits import BrowserClient
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import ConflictError, NotFoundError
from webforge_api.services.jobs import JobError, JobSpec
from webforge_api.services.prospect_state import ALLOWED, LOCKED, transition
from webforge_api.services.renders import latest_validation
from webforge_api.storage import Storage, StorageError

PROPOSAL = JobSpec("proposal.generate", "audit", max_attempts=2)
TOKEN_BYTES = 32  # 256 bits of entropy; only a keyed hash is stored
SEVERITY_ORDER = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "INFO": 4}


@dataclass
class ProposalDeps:
    db: Session
    settings: Settings
    crypto: Crypto
    storage: Storage
    browser: BrowserClient
    now: datetime


def author(settings: Settings) -> dict[str, str]:
    return {"name": settings.concept_author_name, "title": settings.concept_author_title,
            "url": settings.concept_author_url, "github": settings.concept_author_github}  # fmt: skip


def _data_uri(storage: Storage, shot: dict[str, Any]) -> str:
    data = storage.get(shot["key"])
    if hashlib.sha256(data).hexdigest() != shot["sha256"]:
        raise JobError("integrity_mismatch", "A screenshot does not match its recorded hash.")
    return "data:image/png;base64," + base64.b64encode(data).decode()


def generate_proposal(
    deps: ProposalDeps, project_id: uuid.UUID, actor_user_id: uuid.UUID | None = None
) -> Proposal:
    db, s, now = deps.db, deps.settings, deps.now
    project = db.get(DesignProject, project_id, with_for_update=True)
    if project is None:
        raise JobError("not_found", "Design project not found.")
    prospect = db.get(Prospect, project.prospect_id)
    if prospect is None or prospect.state in LOCKED or prospect.do_not_contact:
        raise JobError("prospect_locked", "Prospect is locked; no proposal.")
    render = db.scalar(
        select(DesignRender).where(
            DesignRender.design_project_id == project.id, DesignRender.is_active.is_(True)
        )
    )
    if render is None or render.status != "APPROVED":
        raise JobError("no_active_concept", "Approve a concept before generating a proposal.")
    validation = latest_validation(db, render.id)
    if validation is None or validation.status != "READY":
        raise JobError("not_validated", "The active concept has no READY validation.")
    page_hashes = {p["slug"]: p["sha256"] for p in render.manifest.get("pages", [])}
    shots: dict[str, dict[str, str]] = {}
    for shot in validation.screenshots:
        if shot.get("html_sha256") != page_hashes.get(shot["slug"]):
            raise JobError(
                "version_mismatch", "Screenshots do not match the active concept version."
            )
        if shot["viewport"] in ("desktop", "mobile"):
            shots.setdefault(shot["slug"], {})[shot["viewport"]] = _data_uri(deps.storage, shot)
    if set(shots) != set(page_hashes) or any(len(v) != 2 for v in shots.values()):
        raise JobError(
            "screenshots_missing", "Desktop and mobile screenshots are required for all six pages."
        )
    brief_row = db.get(DesignBrief, render.brief_id)
    if brief_row is None or brief_row.brief is None:
        raise JobError("no_brief", "The concept's brief is missing.")
    facts = {f["field"]: str(f["value"]) for f in brief_row.facts_snapshot.get("facts", [])}
    business = facts.get("business_name") or prospect.business_name
    audit = db.scalar(select(WebsiteAudit).where(WebsiteAudit.prospect_id == prospect.id, WebsiteAudit.status == RunStatus.SUCCEEDED)
                      .order_by(WebsiteAudit.finished_at.desc().nulls_last()).limit(1))  # fmt: skip
    findings: list[dict[str, Any]] = []
    if audit is not None:
        rows = db.scalars(select(AuditFinding).where(AuditFinding.audit_id == audit.id))
        for f in sorted(rows, key=lambda r: SEVERITY_ORDER.get(r.severity.value, 9))[:8]:
            findings.append(
                {
                    "severity": f.severity.value.title(),
                    "description": f.description,
                    "viewport": f.viewport,
                    "category": f.category,
                }
            )
    inp = ProposalInput(
        business=business, prepared_on=now.strftime("%d %B %Y"), render_version=render.version,
        validated_on=validation.created_at.strftime("%d %B %Y"), checks_passed=int(validation.report["summary"]["passed"]),
        audit_date=audit.finished_at.strftime("%d %B %Y") if audit and audit.finished_at else None,
        audit_url=audit.url if audit else None, findings=findings, brief=brief_row.brief, shots=shots,
        author=author(s), contact_email=s.proposal_contact_email,
        opportunities=opportunities_for([f["category"] for f in findings]),
    )  # fmt: skip
    pdf = deps.browser.pdf(build_html(inp), FOOTER_NOTICE)
    checks = check_pdf(pdf, business=business, author=author(s), min_pages=10, min_images=12)
    ok = all(c["ok"] for c in checks)
    version = (
        db.scalar(
            select(func.max(Proposal.proposal_version)).where(
                Proposal.design_project_id == project.id
            )
        )
        or 0
    ) + 1
    proposal = Proposal(prospect_id=prospect.id, design_project_id=project.id, proposal_version=version,
                        template_version=TEMPLATE_VERSION, status=ProposalStatus.READY if ok else ProposalStatus.DRAFT,
                        generated_at=now, expires_at=now + timedelta(days=s.artifact_retention_days), render_id=render.id,
                        validation_id=validation.id, checks=checks)  # fmt: skip
    db.add(proposal)
    db.flush()
    if ok:
        stored = deps.storage.put(
            f"proposals/{proposal.id}/proposal-v{version}.pdf", pdf, "application/pdf"
        )
        proposal.pdf_storage_key, proposal.pdf_sha256, proposal.pdf_bytes = (
            stored.key,
            stored.sha256,
            stored.size,
        )
        proposal.page_count = int(
            next(c["detail"] for c in checks if c["code"] == "page_count_value")
        )
        proposal.summary = (
            f"Independent six-page redesign concept for {business} (concept v{render.version}): "
            f"{brief_row.brief['design_direction']['positioning']} "
            f"{len(findings)} dated observations from the current site; validated at three screen widths."
        )[:1000]
        if ProspectState.PROPOSAL_READY in ALLOWED[prospect.state]:
            transition(
                db,
                deps.crypto,
                prospect,
                ProspectState.PROPOSAL_READY,
                reason="proposal ready",
                now=now,
            )
    elif ProspectState.HUMAN_REVIEW in ALLOWED[prospect.state]:
        transition(
            db,
            deps.crypto,
            prospect,
            ProspectState.HUMAN_REVIEW,
            reason="proposal checks failed",
            now=now,
        )
    activity.record(db, deps.crypto, action="proposal.generated", actor_user_id=actor_user_id, system=actor_user_id is None,
                    entity_type="proposal", entity_id=proposal.id,
                    metadata={"version": version, "status": proposal.status.value, "failed": [c["code"] for c in checks if not c["ok"]]})  # fmt: skip
    db.commit()
    return proposal


# ----------------------------------------------------------------------------- previews


def token_hash(crypto: Crypto, token: str) -> str:
    return crypto.lookup_hash(token, purpose="preview-token")


def create_preview(db: Session, crypto: Crypto, settings: Settings, *, proposal_id: uuid.UUID, actor_user_id: uuid.UUID | None,
                   now: datetime, meta: RequestMeta | None, commit: bool = True) -> tuple[PreviewDeployment, str]:  # fmt: skip
    """Returns (row, url). The URL contains the raw token and is shown once; only its hash is stored."""
    proposal = db.get(Proposal, proposal_id)
    if proposal is None or proposal.deleted_at is not None:
        raise NotFoundError("not_found", "Proposal not found.")
    if proposal.status is not ProposalStatus.READY:
        raise ConflictError("proposal_not_ready", "Only READY proposals can have a preview link.")
    token = secrets.token_urlsafe(TOKEN_BYTES)
    expires = min(
        now + timedelta(days=settings.preview_retention_days),
        proposal.expires_at or now + timedelta(days=settings.preview_retention_days),
    )
    row = PreviewDeployment(proposal_id=proposal.id, token_hash=token_hash(crypto, token), route="/p/", status=PreviewStatus.ACTIVE,
                            created_at=now, expires_at=expires)  # fmt: skip
    db.add(row)
    db.flush()
    activity.record(db, crypto, action="preview.created", actor_user_id=actor_user_id, meta=meta, entity_type="preview",
                    entity_id=row.id, metadata={"expires_at": expires.isoformat()}, system=actor_user_id is None)  # fmt: skip
    if commit:
        db.commit()
    return row, f"{settings.preview_base_url}/p/{token}/"


def revoke_preview(
    db: Session,
    crypto: Crypto,
    *,
    preview_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    now: datetime,
    meta: RequestMeta,
) -> PreviewDeployment:
    row = db.get(PreviewDeployment, preview_id, with_for_update=True)
    if row is None:
        raise NotFoundError("not_found", "Preview not found.")
    if row.status is PreviewStatus.ACTIVE:
        row.status, row.revoked_at = PreviewStatus.REVOKED, now
        activity.record(
            db,
            crypto,
            action="preview.revoked",
            actor_user_id=actor_user_id,
            meta=meta,
            entity_type="preview",
            entity_id=row.id,
        )
    db.commit()
    return row


def _revoke_all(db: Session, proposal_id: uuid.UUID, now: datetime) -> None:
    db.execute(update(PreviewDeployment).where(PreviewDeployment.proposal_id == proposal_id, PreviewDeployment.status == PreviewStatus.ACTIVE)
               .values(status=PreviewStatus.REVOKED, revoked_at=now))  # fmt: skip


def delete_proposal(db: Session, crypto: Crypto, storage: Storage, *, proposal_id: uuid.UUID, actor_user_id: uuid.UUID | None,
                    now: datetime, meta: RequestMeta | None = None, reason: str = "deleted") -> Proposal:  # fmt: skip
    """Delete the PDF, revoke every preview and keep only audit metadata."""
    proposal = db.get(Proposal, proposal_id, with_for_update=True)
    if proposal is None:
        raise NotFoundError("not_found", "Proposal not found.")
    if proposal.pdf_storage_key:
        with contextlib.suppress(StorageError):  # already gone; the metadata update is what matters
            storage.delete(proposal.pdf_storage_key)
    proposal.pdf_storage_key = None
    proposal.deleted_at = now
    proposal.status = ProposalStatus.EXPIRED if reason == "expired" else ProposalStatus.REVOKED
    _revoke_all(db, proposal.id, now)
    activity.record(db, crypto, action=f"proposal.{reason}", actor_user_id=actor_user_id, meta=meta, system=actor_user_id is None,
                    entity_type="proposal", entity_id=proposal.id, metadata={"version": proposal.proposal_version})  # fmt: skip
    db.commit()
    return proposal


def purge_expired(
    db: Session, crypto: Crypto, storage: Storage, *, now: datetime
) -> dict[str, int]:
    """Retention: expire previews past their date and delete proposal PDFs past their TTL."""
    previews = db.execute(update(PreviewDeployment).where(PreviewDeployment.status == PreviewStatus.ACTIVE, PreviewDeployment.expires_at <= now)
                          .values(status=PreviewStatus.EXPIRED)).rowcount  # type: ignore[attr-defined]  # fmt: skip
    db.commit()
    ids = list(
        db.scalars(
            select(Proposal.id).where(Proposal.deleted_at.is_(None), Proposal.expires_at <= now)
        )
    )
    for pid in ids:
        delete_proposal(
            db, crypto, storage, proposal_id=pid, actor_user_id=None, now=now, reason="expired"
        )
    return {"previews_expired": int(previews or 0), "proposals_expired": len(ids)}


@dataclass
class PreviewTarget:
    preview: PreviewDeployment
    proposal: Proposal
    render: DesignRender


def resolve_token(db: Session, crypto: Crypto, token: str, now: datetime) -> PreviewTarget | None:
    """Return what a token may show, or None for unknown/expired/revoked/deleted (callers answer 404 either way)."""
    if not (20 <= len(token) <= 100) or not token.replace("-", "").replace("_", "").isalnum():
        return None
    row = db.scalar(
        select(PreviewDeployment).where(PreviewDeployment.token_hash == token_hash(crypto, token))
    )
    if row is None or row.status is not PreviewStatus.ACTIVE or row.expires_at <= now:
        return None
    proposal = db.get(Proposal, row.proposal_id)
    if (
        proposal is None
        or proposal.deleted_at is not None
        or proposal.status is not ProposalStatus.READY
        or proposal.render_id is None
    ):
        return None
    render = db.get(DesignRender, proposal.render_id)
    if render is None:
        return None
    return PreviewTarget(row, proposal, render)
