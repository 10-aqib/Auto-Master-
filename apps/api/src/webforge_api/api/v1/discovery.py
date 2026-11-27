"""/api/v1 campaigns, prospects, jobs and system controls (Phase 03)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from webforge_api.api.deps import (
    AnyStaff,
    CampaignServiceDep,
    CryptoDep,
    DbDep,
    MetaDep,
    NowDep,
    OwnerOrAdmin,
    Reviewers,
    SettingsDep,
)
from webforge_api.api.v1.schemas import StrictModel
from webforge_api.models import (
    Campaign,
    DomainVerification,
    ExternalPlaceIdentifier,
    Job,
    Prospect,
    ProspectCampaign,
    ProspectMerge,
    ProspectSource,
    QualificationResult,
    SystemControl,
    User,
)
from webforge_api.models.enums import CampaignStatus, JobStatus, ProspectState, Role
from webforge_api.services import controls
from webforge_api.services import jobs as jobqueue
from webforge_api.services.campaigns import QUALIFY, CampaignInput
from webforge_api.services.dedupe import merge_prospects
from webforge_api.services.errors import NotFoundError, ServiceError
from webforge_api.services.jobs import enqueue
from webforge_api.services.prospect_state import reopen, transition
from webforge_api.sources.industries import INDUSTRIES

router = APIRouter(tags=["discovery"])
NON_IDEMPOTENT_JOB_TYPES = frozenset({"outreach.send"})


# ---------------------------------------------------------------------- campaigns


class CampaignIn(StrictModel):
    name: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    target_countries: list[str] = Field(default_factory=list, max_length=20)
    target_regions: list[str] = Field(default_factory=list, max_length=20)
    industries: list[str] = Field(default_factory=list, max_length=10)
    queries: list[Annotated[str, Field(min_length=3, max_length=200)]] = Field(
        min_length=1, max_length=10
    )
    source_key: Literal["google_places", "mock_places"]
    region_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    candidate_cap: int = Field(ge=1, le=1000)
    daily_budget_minor: int = Field(ge=0, le=10_000_000)
    monthly_budget_minor: int = Field(ge=0, le=100_000_000)

    def to_input(self) -> CampaignInput:
        return CampaignInput(**self.model_dump())


class CampaignOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None
    status: CampaignStatus
    target_countries: list[str]
    target_regions: list[str]
    industries: list[str]
    filters: dict[str, Any]
    candidate_cap: int
    daily_budget_minor: int
    monthly_budget_minor: int
    sending_mode: str
    created_at: datetime
    updated_at: datetime


class ReadinessOut(BaseModel):
    code: str
    ok: bool
    message: str


class CampaignDetail(BaseModel):
    campaign: CampaignOut
    readiness: list[ReadinessOut]
    stats: dict[str, Any]


class StatusChange(StrictModel):
    reason: str = Field(default="", max_length=500)


class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_type: str
    queue: str
    status: JobStatus
    attempts: int
    max_attempts: int
    entity_type: str | None
    entity_id: str | None
    available_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None
    correlation_id: str | None
    result: dict[str, Any] | None
    created_at: datetime


@router.get("/industries")
def industries(_p: AnyStaff) -> dict[str, str]:
    return INDUSTRIES


@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(_p: AnyStaff, svc: CampaignServiceDep) -> list[CampaignOut]:
    return [CampaignOut.model_validate(c) for c in svc.all()]


@router.post("/campaigns", response_model=CampaignOut, status_code=201)
def create_campaign(
    body: CampaignIn, principal: OwnerOrAdmin, svc: CampaignServiceDep, meta: MetaDep
) -> CampaignOut:
    return CampaignOut.model_validate(svc.create(principal, body.to_input(), meta))


def _detail(svc: CampaignServiceDep, campaign: Campaign) -> CampaignDetail:
    return CampaignDetail(
        campaign=CampaignOut.model_validate(campaign),
        readiness=[
            ReadinessOut(code=c.code, ok=c.ok, message=c.message) for c in svc.readiness(campaign)
        ],
        stats=svc.stats(campaign.id),
    )


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
def get_campaign(campaign_id: uuid.UUID, _p: AnyStaff, svc: CampaignServiceDep) -> CampaignDetail:
    return _detail(svc, svc.get(campaign_id))


@router.put("/campaigns/{campaign_id}", response_model=CampaignOut)
def update_campaign(
    campaign_id: uuid.UUID,
    body: CampaignIn,
    principal: OwnerOrAdmin,
    svc: CampaignServiceDep,
    meta: MetaDep,
) -> CampaignOut:
    return CampaignOut.model_validate(svc.update(principal, campaign_id, body.to_input(), meta))


@router.post("/campaigns/{campaign_id}/discover", response_model=list[JobOut])
def run_discovery(
    campaign_id: uuid.UUID, principal: OwnerOrAdmin, svc: CampaignServiceDep, meta: MetaDep
) -> list[JobOut]:
    return [JobOut.model_validate(j) for j in svc.run_discovery(principal, campaign_id, meta)]


_ACTIONS = {
    "activate": CampaignStatus.ACTIVE,
    "pause": CampaignStatus.PAUSED,
    "resume": CampaignStatus.ACTIVE,
    "complete": CampaignStatus.COMPLETED,
    "archive": CampaignStatus.ARCHIVED,
}


@router.post("/campaigns/{campaign_id}/{action}", response_model=CampaignDetail)
def campaign_action(
    campaign_id: uuid.UUID,
    action: Literal["activate", "pause", "resume", "complete", "archive"],
    body: StatusChange,
    principal: OwnerOrAdmin,
    svc: CampaignServiceDep,
    meta: MetaDep,
) -> CampaignDetail:
    campaign = svc.set_status(principal, campaign_id, _ACTIONS[action], body.reason, meta)
    return _detail(svc, campaign)


# ---------------------------------------------------------------------- prospects


class ProspectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    business_name: str
    verified_domain: str | None
    branch_key: str
    website_url: str | None
    industry: str | None
    country_code: str | None
    state: ProspectState
    qualification_score: float | None
    qualification_band: str | None
    do_not_contact: bool
    first_seen_at: datetime
    last_verified_at: datetime | None
    state_changed_at: datetime


class ProspectPage(BaseModel):
    items: list[ProspectOut]
    total: int
    offset: int
    limit: int


class SourceFactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fact_field: str
    safe_value: str | None
    source_type: str
    source_name: str
    source_url: str | None
    retrieved_at: datetime
    confidence: float
    verification_method: str
    terms_version: str | None


class QualificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    rubric_version: str
    outcome: str
    score: float | None
    evidence_coverage: float
    components: dict[str, Any]
    reason_codes: list[str]
    campaign_id: uuid.UUID | None
    created_at: datetime


class ProspectDetail(BaseModel):
    prospect: ProspectOut
    facts: list[SourceFactOut]
    verifications: list[dict[str, Any]]
    place_ids: list[dict[str, Any]]
    campaigns: list[dict[str, Any]]
    qualifications: list[QualificationOut]
    merges: list[dict[str, Any]]


@router.get("/prospects", response_model=ProspectPage)
def list_prospects(
    _p: AnyStaff,
    db: DbDep,
    campaign_id: uuid.UUID | None = None,
    state: ProspectState | None = None,
    band: str | None = Query(default=None, max_length=20),
    q: str | None = Query(default=None, max_length=100),
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ProspectPage:
    stmt = select(Prospect)
    if campaign_id:
        stmt = stmt.join(ProspectCampaign, ProspectCampaign.prospect_id == Prospect.id).where(
            ProspectCampaign.campaign_id == campaign_id
        )
    if state:
        stmt = stmt.where(Prospect.state == state)
    else:
        stmt = stmt.where(Prospect.state != ProspectState.MERGED)
    if band:
        stmt = stmt.where(Prospect.qualification_band == band)
    if q:
        like = f"%{q.lower()}%"
        stmt = stmt.where(
            or_(func.lower(Prospect.business_name).like(like), Prospect.verified_domain.like(like))
        )
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(
        stmt.order_by(Prospect.created_at.desc(), Prospect.id).offset(offset).limit(limit)
    )
    return ProspectPage(
        items=[ProspectOut.model_validate(r) for r in rows], total=total, offset=offset, limit=limit
    )


@router.get("/prospects/{prospect_id}", response_model=ProspectDetail)
def get_prospect(prospect_id: uuid.UUID, _p: AnyStaff, db: DbDep) -> ProspectDetail:
    prospect = db.get(Prospect, prospect_id)
    if prospect is None:
        raise NotFoundError("not_found", "Prospect not found.")
    facts = db.scalars(
        select(ProspectSource)
        .where(ProspectSource.prospect_id == prospect_id)
        .order_by(ProspectSource.retrieved_at.desc())
    )
    verifs = db.scalars(
        select(DomainVerification)
        .where(DomainVerification.prospect_id == prospect_id)
        .order_by(DomainVerification.checked_at.desc())
    )
    ids = db.scalars(
        select(ExternalPlaceIdentifier).where(ExternalPlaceIdentifier.prospect_id == prospect_id)
    )
    camps = db.execute(
        select(Campaign.id, Campaign.name, ProspectCampaign.added_at)
        .join(ProspectCampaign, ProspectCampaign.campaign_id == Campaign.id)
        .where(ProspectCampaign.prospect_id == prospect_id)
    ).all()
    quals = db.scalars(
        select(QualificationResult)
        .where(QualificationResult.prospect_id == prospect_id)
        .order_by(QualificationResult.created_at.desc())
        .limit(10)
    )
    merges = db.scalars(
        select(ProspectMerge).where(
            or_(
                ProspectMerge.into_prospect_id == prospect_id,
                ProspectMerge.from_prospect_id == prospect_id,
            )
        )
    )
    return ProspectDetail(
        prospect=ProspectOut.model_validate(prospect),
        facts=[SourceFactOut.model_validate(f) for f in facts],
        verifications=[
            {"id": str(v.id), "status": v.status.value, "domain": v.domain, "final_url": v.final_url,
             "reason_codes": v.reason_codes, "confidence": float(v.confidence) if v.confidence is not None else None,
             "evidence": v.evidence, "checked_at": v.checked_at.isoformat(), "origin": v.candidate_origin}
            for v in verifs
        ],
        place_ids=[{"provider": i.provider, "place_id": i.place_id, "status": i.status.value} for i in ids],
        campaigns=[{"id": str(c[0]), "name": c[1], "added_at": c[2].isoformat()} for c in camps],
        qualifications=[QualificationOut.model_validate(x) for x in quals],
        merges=[{"from": str(m.from_prospect_id), "into": str(m.into_prospect_id), "reason": m.reason,
                 "merged_at": m.merged_at.isoformat(), "snapshot": m.snapshot} for m in merges],
    )  # fmt: skip


class ReviewIn(StrictModel):
    decision: Literal["approve", "reject", "do_not_contact", "hold", "reopen"]
    reason: str = Field(min_length=3, max_length=500)


@router.post("/prospects/{prospect_id}/review", response_model=ProspectOut)
def review_prospect(
    prospect_id: uuid.UUID,
    body: ReviewIn,
    principal: Reviewers,
    db: DbDep,
    crypto: CryptoDep,
    now: NowDep,
    meta: MetaDep,
) -> ProspectOut:
    prospect = db.get(Prospect, prospect_id, with_for_update=True)
    if prospect is None:
        raise NotFoundError("not_found", "Prospect not found.")
    actor = principal.user.id
    if body.decision == "reopen":
        if principal.user.role not in (Role.OWNER, Role.ADMIN):
            raise ServiceError(
                "forbidden", "Only the owner or an admin can reopen.", status_code=403
            )
        reopen(
            db,
            crypto,
            prospect,
            role=principal.user.role,
            actor_user_id=actor,
            reason=body.reason,
            now=now,
            meta=meta,
        )
    elif body.decision == "do_not_contact":
        prospect.do_not_contact = True
        transition(
            db,
            crypto,
            prospect,
            ProspectState.DO_NOT_CONTACT,
            reason=body.reason,
            now=now,
            actor_user_id=actor,
            meta=meta,
        )
    else:
        target = {
            "approve": ProspectState.QUALIFIED,
            "reject": ProspectState.REJECTED,
            "hold": ProspectState.HUMAN_REVIEW,
        }[body.decision]
        transition(
            db,
            crypto,
            prospect,
            target,
            reason=body.reason,
            now=now,
            actor_user_id=actor,
            meta=meta,
        )
    db.commit()
    return ProspectOut.model_validate(prospect)


@router.post("/prospects/{prospect_id}/qualify", response_model=JobOut)
def requalify(
    prospect_id: uuid.UUID,
    principal: OwnerOrAdmin,
    db: DbDep,
    now: NowDep,
    meta: MetaDep,
    campaign_id: uuid.UUID | None = None,
) -> JobOut:
    if db.get(Prospect, prospect_id) is None:
        raise NotFoundError("not_found", "Prospect not found.")
    job, _ = enqueue(
        db,
        QUALIFY,
        idempotency_key=f"qualify:{prospect_id}:{campaign_id or 'none'}:manual:{now.isoformat()}",
        payload={
            "prospect_id": str(prospect_id),
            "campaign_id": str(campaign_id) if campaign_id else None,
        },
        now=now,
        entity_type="prospect",
        entity_id=prospect_id,
        correlation_id=meta.request_id,
        created_by_user_id=principal.user.id,
    )
    db.commit()
    return JobOut.model_validate(job)


class MergeIn(StrictModel):
    from_prospect_id: uuid.UUID
    into_prospect_id: uuid.UUID
    reason: str = Field(min_length=5, max_length=500)


@router.post("/prospects/merge", response_model=dict[str, str])
def merge(
    body: MergeIn, principal: OwnerOrAdmin, db: DbDep, crypto: CryptoDep, now: NowDep, meta: MetaDep
) -> dict[str, str]:
    m = merge_prospects(
        db,
        crypto,
        principal,
        from_id=body.from_prospect_id,
        into_id=body.into_prospect_id,
        reason=body.reason,
        now=now,
        meta=meta,
    )
    return {"merge_id": str(m.id), "into_prospect_id": str(m.into_prospect_id)}


# ---------------------------------------------------------------------- jobs


class JobPage(BaseModel):
    items: list[JobOut]
    total: int
    counts: dict[str, int]


@router.get("/jobs", response_model=JobPage)
def list_jobs(
    _p: OwnerOrAdmin,
    db: DbDep,
    status: JobStatus | None = None,
    queue: str | None = Query(default=None, max_length=32),
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> JobPage:
    stmt = select(Job)
    if status:
        stmt = stmt.where(Job.status == status)
    if queue:
        stmt = stmt.where(Job.queue == queue)
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Job.created_at.desc()).offset(offset).limit(limit))
    counts = dict(db.execute(select(Job.status, func.count()).group_by(Job.status)).all())
    return JobPage(
        items=[JobOut.model_validate(j) for j in rows],
        total=total,
        counts={k.value: int(v) for k, v in counts.items()},
    )


@router.post("/jobs/{job_id}/retry", response_model=JobOut)
def retry_job(job_id: uuid.UUID, _p: OwnerOrAdmin, db: DbDep, now: NowDep) -> JobOut:
    return JobOut.model_validate(
        jobqueue.manual_retry(db, job_id, now, non_idempotent=NON_IDEMPOTENT_JOB_TYPES)
    )


@router.post("/jobs/{job_id}/cancel", response_model=JobOut)
def cancel_job(job_id: uuid.UUID, _p: OwnerOrAdmin, db: DbDep, now: NowDep) -> JobOut:
    return JobOut.model_validate(jobqueue.cancel(db, job_id, now))


# ---------------------------------------------------------------------- controls


class ControlOut(BaseModel):
    key: str
    enabled: bool
    effective: bool
    description: str
    reason: str | None
    updated_at: datetime
    updated_by_user_id: uuid.UUID | None
    updated_by_name: str | None = None
    env_override: bool


class ControlIn(StrictModel):
    enabled: bool
    reason: str = Field(min_length=3, max_length=500)


def _control_out(row: SystemControl, db: DbDep, settings: SettingsDep) -> ControlOut:
    override = settings.global_pause or (row.key == "email_pause" and settings.email_pause)
    return ControlOut(
        key=row.key,
        enabled=row.enabled,
        effective=controls.is_paused(db, settings, row.key),
        description=controls.describe(row.key),
        reason=row.reason,
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
        updated_by_name=(
            user.display_name if (user := db.get(User, row.updated_by_user_id)) else None
        )
        if row.updated_by_user_id
        else None,
        env_override=override,
    )


@router.get("/controls", response_model=list[ControlOut])
def list_controls(_p: AnyStaff, db: DbDep, settings: SettingsDep) -> list[ControlOut]:
    return [_control_out(r, db, settings) for r in controls.list_controls(db)]


@router.put("/controls/{key}", response_model=ControlOut)
def set_control(
    key: str,
    body: ControlIn,
    principal: OwnerOrAdmin,
    db: DbDep,
    settings: SettingsDep,
    crypto: CryptoDep,
    now: NowDep,
    meta: MetaDep,
) -> ControlOut:
    # Pausing is open to owner and admins; resuming (turning a pause off) is owner-only.
    if not body.enabled and principal.user.role is not Role.OWNER:
        raise ServiceError("forbidden", "Only the owner can resume.", status_code=403)
    row = controls.set_control(db, crypto, principal, key, body.enabled, body.reason, now, meta)
    return _control_out(row, db, settings)
