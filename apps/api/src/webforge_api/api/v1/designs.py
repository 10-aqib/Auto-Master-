"""/api/v1 design projects, AI briefs (Phase 05) and concept renders (Phase 06)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Response
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
    StorageDep,
)
from webforge_api.api.v1.discovery import JobOut
from webforge_api.models import (
    DesignBrief,
    DesignProject,
    DesignRender,
    DesignValidation,
    Prospect,
    WebsiteAudit,
)
from webforge_api.models.enums import ProspectState, RunStatus
from webforge_api.services.briefs import BRIEF, PROMPT_VERSION, review_brief
from webforge_api.services.errors import ConflictError, NotFoundError
from webforge_api.services.jobs import enqueue
from webforge_api.services.prospect_state import LOCKED
from webforge_api.services.renders import (
    RENDER,
    VALIDATE,
    activate_render,
    latest_approved_brief,
    page_html,
    review_render,
)
from webforge_api.services.validation import screenshot

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
    renderer_version: str | None
    created_at: datetime
    business_name: str | None = None


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


class RenderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    design_project_id: uuid.UUID
    brief_id: uuid.UUID
    version: int
    renderer_version: str
    status: str
    is_active: bool
    variant: str
    manifest: dict[str, Any]
    scan_issues: list[dict[str, Any]]
    review_notes: str | None
    reviewed_at: datetime | None
    created_at: datetime


class ValidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    render_id: uuid.UUID
    status: str
    validator_version: str
    browser_version: str | None
    site_sha256: str
    report: dict[str, Any]
    screenshots: list[dict[str, Any]]
    created_at: datetime


class DesignDetail(BaseModel):
    project: DesignProjectOut
    briefs: list[BriefOut]
    renders: list[RenderOut]
    validations: list[ValidationOut]


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
    stmt = (
        select(DesignProject, Prospect.business_name)
        .join(Prospect, Prospect.id == DesignProject.prospect_id)
        .order_by(DesignProject.created_at.desc())
        .limit(100)
    )
    if prospect_id:
        stmt = stmt.where(DesignProject.prospect_id == prospect_id)
    out = []
    for project, name in db.execute(stmt).all():
        item = DesignProjectOut.model_validate(project)
        item.business_name = name
        out.append(item)
    return out


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
    render_rows = db.scalars(
        select(DesignRender)
        .where(DesignRender.design_project_id == design_id)
        .order_by(DesignRender.version.desc())
    ).all()
    return DesignDetail(
        project=DesignProjectOut.model_validate(project),
        briefs=[BriefOut.model_validate(b) for b in briefs],
        renders=[RenderOut.model_validate(r) for r in render_rows],
        validations=[
            ValidationOut.model_validate(v)
            for v in db.scalars(
                select(DesignValidation)
                .where(DesignValidation.render_id.in_([r.id for r in render_rows]))
                .order_by(DesignValidation.created_at.desc())
            )
        ],
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


PageSlug = Literal["home", "services", "about", "trust", "inquiry", "contact"]
# Concept pages are untrusted-looking content: render them sandboxed, script-free and unframeable elsewhere.
CONCEPT_HEADERS = {
    "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
    "form-action 'none'; base-uri 'none'; frame-ancestors 'self'",
    "X-Content-Type-Options": "nosniff",
    "Cache-Control": "private, no-store",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Resource-Policy": "same-origin",
    "X-Robots-Tag": "noindex, nofollow",
}


@router.post("/designs/{design_id}/render", response_model=JobOut)
def start_render(
    design_id: uuid.UUID, principal: OwnerOrAdmin, db: DbDep, now: NowDep, meta: MetaDep
) -> JobOut:
    project = db.get(DesignProject, design_id)
    if project is None:
        raise NotFoundError("not_found", "Design project not found.")
    if latest_approved_brief(db, design_id) is None:
        raise ConflictError("no_approved_brief", "Approve a brief before rendering.")
    job, _ = enqueue(
        db, RENDER,
        idempotency_key=f"render:{design_id}:{now.isoformat()}",
        payload={"design_project_id": str(design_id), "requested_by": str(principal.user.id)},
        now=now, entity_type="design_project", entity_id=design_id,
        correlation_id=meta.request_id, created_by_user_id=principal.user.id,
    )  # fmt: skip
    db.commit()
    return JobOut.model_validate(job)


@router.get("/designs/renders/{render_id}/pages/{slug}")
def render_page(
    render_id: uuid.UUID, slug: PageSlug, _p: AnyStaff, db: DbDep, storage: StorageDep
) -> Response:
    return Response(
        page_html(db, storage, render_id, slug),
        media_type="text/html; charset=utf-8",
        headers=CONCEPT_HEADERS,
    )


@router.post("/designs/renders/{render_id}/review", response_model=RenderOut)
def review_render_endpoint(
    render_id: uuid.UUID,
    body: ReviewIn,
    principal: Reviewers,
    db: DbDep,
    crypto: CryptoDep,
    now: NowDep,
    meta: MetaDep,
) -> RenderOut:
    row = review_render(db, crypto, render_id=render_id, approve=body.approve, notes=body.notes,
                        actor_user_id=principal.user.id, now=now, meta=meta)  # fmt: skip
    return RenderOut.model_validate(row)


@router.post("/designs/renders/{render_id}/activate", response_model=RenderOut)
def activate_render_endpoint(
    render_id: uuid.UUID, principal: OwnerOrAdmin, db: DbDep, crypto: CryptoDep, meta: MetaDep
) -> RenderOut:
    return RenderOut.model_validate(
        activate_render(db, crypto, render_id=render_id, actor_user_id=principal.user.id, meta=meta)
    )


@router.post("/designs/renders/{render_id}/validate", response_model=JobOut)
def revalidate(
    render_id: uuid.UUID, principal: OwnerOrAdmin, db: DbDep, now: NowDep, meta: MetaDep
) -> JobOut:
    render = db.get(DesignRender, render_id)
    if render is None:
        raise NotFoundError("not_found", "Render not found.")
    if render.status not in ("RENDERED", "APPROVED"):
        raise ConflictError("not_validatable", f"Render is {render.status}.")
    job, _ = enqueue(db, VALIDATE, idempotency_key=f"validate:{render_id}:{now.isoformat()}",
                     payload={"render_id": str(render_id)}, now=now, entity_type="design_render", entity_id=render_id,
                     correlation_id=meta.request_id, created_by_user_id=principal.user.id)  # fmt: skip
    db.commit()
    return JobOut.model_validate(job)


@router.get("/designs/validations/{validation_id}/screenshots/{slug}/{viewport}")
def validation_screenshot(validation_id: uuid.UUID, slug: PageSlug, viewport: Literal["desktop", "tablet", "mobile"],
                          _p: AnyStaff, db: DbDep, storage: StorageDep) -> Response:  # fmt: skip
    data = screenshot(db, storage, validation_id, slug, viewport)
    if data is None:
        raise NotFoundError("not_found", "Screenshot not found.")
    return Response(
        data,
        media_type="image/png",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )
