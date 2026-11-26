"""/api/v1 proposals and preview links (Phase 08). Nothing here sends email."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Response
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select

from webforge_api.api.deps import (
    AnyStaff,
    CryptoDep,
    DbDep,
    MetaDep,
    NowDep,
    OwnerOrAdmin,
    SettingsDep,
    StorageDep,
)
from webforge_api.api.v1.discovery import JobOut
from webforge_api.models import DesignProject, DesignRender, PreviewDeployment, Proposal
from webforge_api.services.errors import ConflictError, NotFoundError
from webforge_api.services.jobs import enqueue
from webforge_api.services.proposals import (
    PROPOSAL,
    create_preview,
    delete_proposal,
    revoke_preview,
)
from webforge_api.storage import StorageError

router = APIRouter(tags=["proposals"])


class PreviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    proposal_id: uuid.UUID
    status: str
    created_at: datetime
    expires_at: datetime
    revoked_at: datetime | None
    access_count: int
    last_accessed_at: datetime | None


class ProposalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    design_project_id: uuid.UUID
    render_id: uuid.UUID | None
    proposal_version: int
    template_version: str | None
    status: str
    generated_at: datetime | None
    expires_at: datetime | None
    deleted_at: datetime | None
    pdf_sha256: str | None
    pdf_bytes: int | None
    page_count: int | None
    summary: str | None
    checks: list[dict[str, Any]]
    previews: list[PreviewOut] = []


class PreviewCreated(BaseModel):
    preview: PreviewOut
    url: str
    note: str = (
        "Copy this link now. Only a hash of its token is stored, so it cannot be shown again."
    )


def _out(db: DbDep, p: Proposal) -> ProposalOut:
    out = ProposalOut.model_validate(p)
    out.previews = [PreviewOut.model_validate(v) for v in db.scalars(
        select(PreviewDeployment).where(PreviewDeployment.proposal_id == p.id).order_by(PreviewDeployment.created_at.desc()))]  # fmt: skip
    return out


@router.post("/designs/{design_id}/proposal", response_model=JobOut)
def start_proposal(
    design_id: uuid.UUID, principal: OwnerOrAdmin, db: DbDep, now: NowDep, meta: MetaDep
) -> JobOut:
    if db.get(DesignProject, design_id) is None:
        raise NotFoundError("not_found", "Design project not found.")
    active = db.scalar(
        select(DesignRender).where(
            DesignRender.design_project_id == design_id, DesignRender.is_active.is_(True)
        )
    )
    if active is None or active.status != "APPROVED":
        raise ConflictError(
            "no_active_concept", "Approve a validated concept before generating a proposal."
        )
    job, _ = enqueue(db, PROPOSAL, idempotency_key=f"proposal:{design_id}:{now.isoformat()}",
                     payload={"design_project_id": str(design_id), "requested_by": str(principal.user.id)}, now=now,
                     entity_type="design_project", entity_id=design_id, correlation_id=meta.request_id,
                     created_by_user_id=principal.user.id)  # fmt: skip
    db.commit()
    return JobOut.model_validate(job)


@router.get("/proposals", response_model=list[ProposalOut])
def list_proposals(
    _p: AnyStaff,
    db: DbDep,
    design_id: uuid.UUID | None = None,
    prospect_id: uuid.UUID | None = None,
) -> list[ProposalOut]:
    stmt = select(Proposal).order_by(Proposal.created_at.desc()).limit(100)
    if design_id:
        stmt = stmt.where(Proposal.design_project_id == design_id)
    if prospect_id:
        stmt = stmt.where(Proposal.prospect_id == prospect_id)
    return [_out(db, p) for p in db.scalars(stmt)]


@router.get("/proposals/{proposal_id}/pdf")
def proposal_pdf(proposal_id: uuid.UUID, _p: AnyStaff, db: DbDep, storage: StorageDep) -> Response:
    p = db.get(Proposal, proposal_id)
    if p is None or not p.pdf_storage_key or p.deleted_at is not None:
        raise NotFoundError("not_found", "Proposal PDF not found.")
    try:
        data = storage.get(p.pdf_storage_key)
    except StorageError as exc:
        raise NotFoundError("not_found", "Proposal PDF not found.") from exc

    if hashlib.sha256(data).hexdigest() != p.pdf_sha256:
        raise ConflictError("integrity_mismatch", "Stored PDF does not match its recorded hash.")
    return Response(data, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="proposal-v{p.proposal_version}.pdf"',
        "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})  # fmt: skip


@router.post("/proposals/{proposal_id}/previews", response_model=PreviewCreated)
def new_preview(
    proposal_id: uuid.UUID,
    principal: OwnerOrAdmin,
    db: DbDep,
    crypto: CryptoDep,
    settings: SettingsDep,
    now: NowDep,
    meta: MetaDep,
) -> PreviewCreated:
    row, url = create_preview(
        db,
        crypto,
        settings,
        proposal_id=proposal_id,
        actor_user_id=principal.user.id,
        now=now,
        meta=meta,
    )
    return PreviewCreated(preview=PreviewOut.model_validate(row), url=url)


@router.post("/previews/{preview_id}/revoke", response_model=PreviewOut)
def revoke(
    preview_id: uuid.UUID,
    principal: OwnerOrAdmin,
    db: DbDep,
    crypto: CryptoDep,
    now: NowDep,
    meta: MetaDep,
) -> PreviewOut:
    return PreviewOut.model_validate(
        revoke_preview(
            db, crypto, preview_id=preview_id, actor_user_id=principal.user.id, now=now, meta=meta
        )
    )


@router.post("/proposals/{proposal_id}/delete", response_model=ProposalOut)
def delete(
    proposal_id: uuid.UUID,
    principal: OwnerOrAdmin,
    db: DbDep,
    crypto: CryptoDep,
    storage: StorageDep,
    now: NowDep,
    meta: MetaDep,
) -> ProposalOut:
    p = delete_proposal(
        db,
        crypto,
        storage,
        proposal_id=proposal_id,
        actor_user_id=principal.user.id,
        now=now,
        meta=meta,
    )
    return _out(db, p)
