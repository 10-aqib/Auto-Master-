"""/api/v1 design projects and AI briefs (Phase 05)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from webforge_api.api.deps import (
    AnyStaff,
    CryptoDep,
    DbDep,
    MetaDep,
    NowDep,
    OwnerOrAdmin,
    Reviewers,
)
from webforge_api.api.v1.discovery import JobOut
from webforge_api.models import DesignBrief, DesignProject, Prospect, WebsiteAudit
from webforge_api.models.enums import ProspectState, RunStatus
from webforge_api.services.briefs import BRIEF, PROMPT_VERSION, review_brief
from webforge_api.services.errors import ConflictError, NotFoundError
from webforge_api.services.jobs import enqueue
from webforge_api.services.prospect_state import LOCKED

router = APIRouter(tags=["designs"])
BRIEF_READY_STATES = {
    ProspectState.AUDITED, ProspectState.GENERATING_DESIGN, ProspectState.HUMAN_REVIEW,
    ProspectState.VALIDATING, ProspectState.PROPOSAL_READY,
}  # fmt: skip


class DesignProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    audit_id: uuid.UUID | None
    status: str
    brief_schema_version: str | None
    prompt_version: str | None
    model: str | None
    current_version: int
    created_at: datetime


class BriefOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    design_project_id: uuid.UUID
    version: int
    status: str
    brief: dict[str, Any] | None
    schema_version: str
    prompt_version: str
    model: str
    facts_snapshot: dict[str, Any]
    validation_issues: list[dict[str, Any]]
    attempts: int
    input_tokens: int
    output_tokens: int
    cost_milliminor: int
    review_notes: str | None
    reviewed_at: datetime | None
    created_at: datetime


class DesignDetail(BaseModel):
    project: DesignProjectOut
    briefs: list[BriefOut]


class ReviewIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approve: bool
    notes: str = Field(default="", max_length=2000)


@router.post("/prospects/{prospect_id}/brief", response_model=JobOut)
def start_brief(
    prospect_id: uuid.UUID, principal: OwnerOrAdmin, db: DbDep, now: NowDep, meta: MetaDep
) -> JobOut:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None:
        raise NotFoundError("not_found", "Prospect not found.")
    if prospect.state in LOCKED or prospect.do_not_contact:
        raise ConflictError("prospect_locked", f"Prospect is {prospect.state.value}.")
    if prospect.state not in BRIEF_READY_STATES:
        raise ConflictError("not_audited", "Run a successful audit before generating a brief.")
    audited = db.scalar(
        select(WebsiteAudit.id)
        .where(WebsiteAudit.prospect_id == prospect_id, WebsiteAudit.status == RunStatus.SUCCEEDED)
        .limit(1)
    )
    if audited is None:
        raise ConflictError("not_audited", "Run a successful audit before generating a brief.")
    job, _ = enqueue(
        db, BRIEF,
        idempotency_key=f"brief:{prospect_id}:{PROMPT_VERSION}:{now.isoformat()}",
        payload={"prospect_id": str(prospect_id), "requested_by": str(principal.user.id)},
        now=now, entity_type="prospect", entity_id=prospect_id,
        correlation_id=meta.request_id, created_by_user_id=principal.user.id,
    )  # fmt: skip
    db.commit()
    return JobOut.model_validate(job)


@router.get("/designs", response_model=list[DesignProjectOut])
def list_designs(
    _p: AnyStaff, db: DbDep, prospect_id: uuid.UUID | None = None
) -> list[DesignProjectOut]:
    stmt = select(DesignProject).order_by(DesignProject.created_at.desc()).limit(100)
    if prospect_id:
        stmt = stmt.where(DesignProject.prospect_id == prospect_id)
    return [DesignProjectOut.model_validate(p) for p in db.scalars(stmt)]


@router.get("/designs/{design_id}", response_model=DesignDetail)
def get_design(design_id: uuid.UUID, _p: AnyStaff, db: DbDep) -> DesignDetail:
    project = db.get(DesignProject, design_id)
    if project is None:
        raise NotFoundError("not_found", "Design project not found.")
    briefs = db.scalars(
        select(DesignBrief)
        .where(DesignBrief.design_project_id == design_id)
        .order_by(DesignBrief.version.desc())
    )
    return DesignDetail(
        project=DesignProjectOut.model_validate(project),
        briefs=[BriefOut.model_validate(b) for b in briefs],
    )


@router.post("/designs/briefs/{brief_id}/review", response_model=BriefOut)
def review(
    brief_id: uuid.UUID,
    body: ReviewIn,
    principal: Reviewers,
    db: DbDep,
    crypto: CryptoDep,
    now: NowDep,
    meta: MetaDep,
) -> BriefOut:
    row = review_brief(db, crypto, brief_id=brief_id, approve=body.approve, notes=body.notes,
                       actor_user_id=principal.user.id, now=now, meta=meta)  # fmt: skip
    return BriefOut.model_validate(row)
