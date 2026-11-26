"""/api/v1 audits (Phase 04)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from webforge_api.api.deps import (
    AnyStaff,
    DbDep,
    MetaDep,
    NowDep,
    OwnerOrAdmin,
    SettingsDep,
    StorageDep,
)
from webforge_api.api.v1.discovery import JobOut
from webforge_api.models import AuditFinding, Prospect, WebsiteAudit
from webforge_api.services.audits import AUDIT
from webforge_api.services.errors import ConflictError, NotFoundError
from webforge_api.services.jobs import enqueue
from webforge_api.services.prospect_state import LOCKED
from webforge_api.storage import StorageError

router = APIRouter(tags=["audits"])


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: str
    severity: str
    code: str
    description: str
    evidence_url: str | None
    evidence_text: str | None
    viewport: str | None
    confidence: float | None
    observed_at: datetime
    reproduction_steps: str | None


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    url: str
    status: str
    audit_version: str
    started_at: datetime | None
    finished_at: datetime | None
    desktop_screenshot_key: str | None
    mobile_screenshot_key: str | None
    browser_version: str | None
    performance_source: str | None
    scores: dict[str, Any]
    error_summary: str | None
    created_at: datetime


class AuditDetail(BaseModel):
    audit: AuditOut
    findings: list[FindingOut]


@router.post("/prospects/{prospect_id}/audit", response_model=JobOut)
def start_audit(
    prospect_id: uuid.UUID,
    principal: OwnerOrAdmin,
    db: DbDep,
    settings: SettingsDep,
    now: NowDep,
    meta: MetaDep,
) -> JobOut:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None:
        raise NotFoundError("not_found", "Prospect not found.")
    if prospect.state in LOCKED or prospect.do_not_contact:
        raise ConflictError("prospect_locked", f"Prospect is {prospect.state.value}.")
    if not prospect.website_url:
        raise ConflictError("no_website", "Prospect has no verified website.")
    job, _ = enqueue(
        db,
        AUDIT,
        idempotency_key=f"audit:{prospect_id}:{settings.audit_version}:manual:{now.isoformat()}",
        payload={"prospect_id": str(prospect_id), "campaign_id": None},
        now=now,
        entity_type="prospect",
        entity_id=prospect_id,
        correlation_id=meta.request_id,
        created_by_user_id=principal.user.id,
    )
    db.commit()
    return JobOut.model_validate(job)


@router.get("/audits", response_model=list[AuditOut])
def list_audits(_p: AnyStaff, db: DbDep, prospect_id: uuid.UUID | None = None) -> list[AuditOut]:
    stmt = select(WebsiteAudit).order_by(WebsiteAudit.created_at.desc()).limit(100)
    if prospect_id:
        stmt = stmt.where(WebsiteAudit.prospect_id == prospect_id)
    return [AuditOut.model_validate(a) for a in db.scalars(stmt)]


@router.get("/audits/{audit_id}", response_model=AuditDetail)
def get_audit(audit_id: uuid.UUID, _p: AnyStaff, db: DbDep) -> AuditDetail:
    audit = db.get(WebsiteAudit, audit_id)
    if audit is None:
        raise NotFoundError("not_found", "Audit not found.")
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3, "CRITICAL": -1}
    findings = sorted(
        db.scalars(select(AuditFinding).where(AuditFinding.audit_id == audit_id)),
        key=lambda f: order.get(f.severity.value, 9),
    )
    return AuditDetail(
        audit=AuditOut.model_validate(audit),
        findings=[FindingOut.model_validate(f) for f in findings],
    )


@router.get("/audits/{audit_id}/screenshots/{view}")
def audit_screenshot(
    audit_id: uuid.UUID,
    view: Literal["desktop", "mobile"],
    _p: AnyStaff,
    db: DbDep,
    storage: StorageDep,
) -> Response:
    audit = db.get(WebsiteAudit, audit_id)
    key = (
        (audit.desktop_screenshot_key if view == "desktop" else audit.mobile_screenshot_key)
        if audit
        else None
    )
    if not key:
        raise NotFoundError("not_found", "Screenshot not found.")
    try:
        data = storage.get(key)
    except StorageError as exc:
        raise NotFoundError("not_found", "Screenshot not found.") from exc
    return Response(
        data,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
