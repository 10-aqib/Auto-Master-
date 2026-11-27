"""Job handlers for discovery, verification and qualification.

Every handler re-checks the global pause and the campaign status when it runs (a paused system
defers work without consuming an attempt; a closed campaign cancels it).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import Campaign, ExternalPlaceIdentifier, Job, Prospect, ProspectCampaign
from webforge_api.models.enums import CampaignStatus, ProspectState
from webforge_api.security.crypto import Crypto
from webforge_api.services import controls, outreach
from webforge_api.services.ai import AIError, BriefModel
from webforge_api.services.audits import AUDIT, AuditDeps, BrowserClient, run_audit
from webforge_api.services.briefs import BriefDeps, generate_brief
from webforge_api.services.campaigns import DISCOVERY_VERIFY, QUALIFY
from webforge_api.services.context import RequestMeta
from webforge_api.services.email.provider import EmailProvider
from webforge_api.services.errors import ServiceError, UnavailableError
from webforge_api.services.jobs import JobCancelled, JobError, enqueue
from webforge_api.services.places import PlacesService
from webforge_api.services.proposals import ProposalDeps, generate_proposal
from webforge_api.services.prospect_state import LOCKED, transition
from webforge_api.services.qualification import qualify
from webforge_api.services.renders import RenderDeps, render_project
from webforge_api.services.validation import ValidationDeps, validate_render
from webforge_api.storage import Storage


class JobDeferred(Exception):  # noqa: N818 - control-flow signal
    """Re-queue later without consuming an attempt (e.g. while paused)."""

    def __init__(self, reason: str, seconds: int = 60) -> None:
        super().__init__(reason)
        self.seconds = seconds


@dataclass
class JobContext:
    db: Session
    settings: Settings
    crypto: Crypto
    now: datetime
    places: PlacesService
    storage: Storage | None = None
    browser: BrowserClient | None = None
    ai: BriefModel | None = None
    email: EmailProvider | None = None


def _meta(job: Job) -> RequestMeta:
    return RequestMeta(request_id=job.correlation_id)


def _require_running(ctx: JobContext, campaign_id: str | None) -> Campaign | None:
    if controls.is_paused(ctx.db, ctx.settings):
        raise JobDeferred("system paused")
    if not campaign_id:
        return None
    campaign = ctx.db.get(Campaign, uuid.UUID(campaign_id))
    if campaign is None:
        raise JobCancelled("campaign deleted")
    if campaign.status is CampaignStatus.PAUSED or campaign.status is CampaignStatus.DRAFT:
        raise JobDeferred("campaign paused", 300)
    if campaign.status is not CampaignStatus.ACTIVE:
        raise JobCancelled(f"campaign {campaign.status.value.lower()}")
    return campaign


def _service_error(exc: ServiceError) -> JobError:
    return JobError(
        exc.code, exc.message, retryable=isinstance(exc, UnavailableError) or exc.status_code == 429
    )


def handle_search(ctx: JobContext, job: Job) -> dict[str, Any]:
    p = job.payload
    campaign = _require_running(ctx, p.get("campaign_id"))
    assert campaign is not None  # noqa: S101 - search jobs always belong to a campaign
    have = ctx.db.scalar(
        select(ExternalPlaceIdentifier.id)
        .where(ExternalPlaceIdentifier.campaign_id == campaign.id)
        .limit(1)
    )
    count = (
        len(
            ctx.db.scalars(
                select(ExternalPlaceIdentifier.id).where(
                    ExternalPlaceIdentifier.campaign_id == campaign.id
                )
            ).all()
        )
        if have
        else 0
    )
    remaining = campaign.candidate_cap - count
    if remaining <= 0:
        raise JobCancelled("campaign candidate cap reached")
    try:
        result = ctx.places.search(
            None,
            source_key=p["source_key"],
            text_query=p["query"],
            region_code=p.get("region_code"),
            page_size=min(20, remaining),
            campaign_id=campaign.id,
            meta=_meta(job),
        )
    except ServiceError as exc:
        raise _service_error(exc) from exc
    queued = 0
    for identifier_id in result.identifier_ids.values():
        ident = ctx.db.get(ExternalPlaceIdentifier, identifier_id)
        if ident is None:
            continue
        if ident.campaign_id is None:
            ident.campaign_id = campaign.id
        if ident.prospect_id is not None:
            # Already verified (e.g. in another campaign): link and qualify for this campaign.
            ctx.db.execute(
                pg_insert(ProspectCampaign)
                .values(prospect_id=ident.prospect_id, campaign_id=campaign.id, added_at=ctx.now)
                .on_conflict_do_nothing(index_elements=["prospect_id", "campaign_id"])
            )
            _, created = enqueue(
                ctx.db,
                QUALIFY,
                idempotency_key=f"qualify:{ident.prospect_id}:{campaign.id}:{ctx.now.date()}",
                payload={"prospect_id": str(ident.prospect_id), "campaign_id": str(campaign.id)},
                now=ctx.now,
                entity_type="prospect",
                entity_id=ident.prospect_id,
                correlation_id=job.correlation_id,
            )
        else:
            _, created = enqueue(
                ctx.db,
                DISCOVERY_VERIFY,
                idempotency_key=f"verify:{identifier_id}",
                payload={"identifier_id": str(identifier_id), "campaign_id": str(campaign.id)},
                now=ctx.now,
                entity_type="place_identifier",
                entity_id=identifier_id,
                correlation_id=job.correlation_id,
            )
        queued += int(created)
    ctx.db.commit()
    return {
        "results": len(result.places),
        "new_place_ids": result.new_place_ids,
        "follow_up_jobs": queued,
    }


def handle_verify(ctx: JobContext, job: Job) -> dict[str, Any]:
    p = job.payload
    campaign = _require_running(ctx, p.get("campaign_id"))
    ident = ctx.db.get(ExternalPlaceIdentifier, uuid.UUID(p["identifier_id"]))
    if ident is None:
        raise JobCancelled("identifier removed")
    if ident.prospect_id is None:
        try:
            outcome = ctx.places.verify_place_website(None, ident.id, _meta(job))
        except ServiceError as exc:
            raise _service_error(exc) from exc
        prospect_id = outcome.prospect_id
        status = outcome.verification.status.value
    else:
        prospect_id, status = ident.prospect_id, "ALREADY_LINKED"
    if prospect_id is not None:
        scope = campaign.id if campaign else "none"
        enqueue(
            ctx.db,
            QUALIFY,
            idempotency_key=f"qualify:{prospect_id}:{scope}:{ctx.now.date()}",
            payload={
                "prospect_id": str(prospect_id),
                "campaign_id": str(campaign.id) if campaign else None,
            },
            now=ctx.now,
            entity_type="prospect",
            entity_id=prospect_id,
            correlation_id=job.correlation_id,
        )
        ctx.db.commit()
    return {"verification": status, "prospect_id": str(prospect_id) if prospect_id else None}


def handle_qualify(ctx: JobContext, job: Job) -> dict[str, Any]:
    p = job.payload
    if controls.is_paused(ctx.db, ctx.settings):
        raise JobDeferred("system paused")
    prospect = ctx.db.get(Prospect, uuid.UUID(p["prospect_id"]))
    if prospect is None:
        raise JobCancelled("prospect removed")
    if prospect.state is ProspectState.VERIFIED:
        transition(
            ctx.db,
            ctx.crypto,
            prospect,
            ProspectState.QUALIFYING,
            reason="qualification started",
            now=ctx.now,
        )
    campaign_id = uuid.UUID(p["campaign_id"]) if p.get("campaign_id") else None
    result = qualify(
        ctx.db,
        ctx.crypto,
        prospect.id,
        campaign_id=campaign_id,
        now=ctx.now,
        apply_state=prospect.state not in LOCKED,
    )
    if (
        "awaiting_audit_evidence" in result.reason_codes
        and prospect.website_url
        and prospect.state not in LOCKED
        and not prospect.do_not_contact
    ):
        enqueue(
            ctx.db,
            AUDIT,
            idempotency_key=f"audit:{prospect.id}:{ctx.settings.audit_version}:{ctx.now.date()}",
            payload={"prospect_id": str(prospect.id), "campaign_id": p.get("campaign_id")},
            now=ctx.now,
            entity_type="prospect",
            entity_id=prospect.id,
            correlation_id=job.correlation_id,
        )
    ctx.db.commit()
    return {
        "outcome": result.outcome.value,
        "score": float(result.score) if result.score is not None else None,
    }


def handle_audit(ctx: JobContext, job: Job) -> dict[str, Any]:
    if controls.is_paused(ctx.db, ctx.settings):
        raise JobDeferred("system paused")
    if ctx.storage is None or ctx.browser is None:
        raise JobError("misconfigured", "Audit worker has no storage or browser client.")
    audit = run_audit(
        AuditDeps(ctx.db, ctx.settings, ctx.crypto, ctx.storage, ctx.browser, ctx.now),
        uuid.UUID(job.payload["prospect_id"]),
    )
    campaign_id = job.payload.get("campaign_id")
    enqueue(
        ctx.db,
        QUALIFY,
        idempotency_key=f"qualify:{audit.prospect_id}:after-audit:{audit.id}",
        payload={"prospect_id": str(audit.prospect_id), "campaign_id": campaign_id},
        now=ctx.now,
        entity_type="prospect",
        entity_id=audit.prospect_id,
        correlation_id=job.correlation_id,
    )
    ctx.db.commit()
    return {
        "audit_id": str(audit.id),
        "status": audit.status.value,
        "overall": (audit.scores or {}).get("overall"),
    }


def handle_brief(ctx: JobContext, job: Job) -> dict[str, Any]:
    if controls.is_paused(ctx.db, ctx.settings):
        raise JobDeferred("system paused")
    if ctx.ai is None:
        raise JobError("ai_not_configured", "Design worker has no AI provider.")
    actor = job.payload.get("requested_by")
    try:
        row = generate_brief(
            BriefDeps(ctx.db, ctx.settings, ctx.crypto, ctx.ai, ctx.now),
            uuid.UUID(job.payload["prospect_id"]),
            uuid.UUID(actor) if actor else None,
        )
    except AIError as exc:
        raise JobError(exc.code, str(exc), retryable=exc.retryable) from exc
    return {"brief_id": str(row.id), "version": row.version, "status": row.status}


def handle_render(ctx: JobContext, job: Job) -> dict[str, Any]:
    if controls.is_paused(ctx.db, ctx.settings):
        raise JobDeferred("system paused")
    if ctx.storage is None:
        raise JobError("misconfigured", "Design worker has no storage.")
    actor = job.payload.get("requested_by")
    row = render_project(
        RenderDeps(ctx.db, ctx.settings, ctx.crypto, ctx.storage, ctx.now),
        uuid.UUID(job.payload["design_project_id"]),
        uuid.UUID(actor) if actor else None,
        correlation_id=job.correlation_id,
    )
    return {"render_id": str(row.id), "version": row.version, "status": row.status}


def handle_validate(ctx: JobContext, job: Job) -> dict[str, Any]:
    if controls.is_paused(ctx.db, ctx.settings):
        raise JobDeferred("system paused")
    if ctx.storage is None or ctx.browser is None:
        raise JobError("misconfigured", "Validation worker has no storage or browser client.")
    row = validate_render(
        ValidationDeps(ctx.db, ctx.settings, ctx.crypto, ctx.storage, ctx.browser, ctx.now),
        uuid.UUID(job.payload["render_id"]),
        job.correlation_id,
    )
    return {"validation_id": str(row.id), "status": row.status, **row.report["summary"]}


def handle_proposal(ctx: JobContext, job: Job) -> dict[str, Any]:
    if controls.is_paused(ctx.db, ctx.settings):
        raise JobDeferred("system paused")
    if ctx.storage is None or ctx.browser is None:
        raise JobError("misconfigured", "Proposal worker has no storage or browser client.")
    actor = job.payload.get("requested_by")
    row = generate_proposal(
        ProposalDeps(ctx.db, ctx.settings, ctx.crypto, ctx.storage, ctx.browser, ctx.now),
        uuid.UUID(job.payload["design_project_id"]),
        uuid.UUID(actor) if actor else None,
    )
    return {"proposal_id": str(row.id), "version": row.proposal_version, "status": row.status.value}


def handle_email_send(ctx: JobContext, job: Job) -> dict[str, Any]:
    if controls.is_paused(ctx.db, ctx.settings, "email_pause"):
        raise JobDeferred("email paused", seconds=300)  # queued mail stays unsent while paused
    if ctx.email is None:
        raise JobError("misconfigured", "No email provider configured.")
    try:
        msg = outreach.send(
            ctx.db,
            ctx.settings,
            ctx.crypto,
            ctx.email,
            message_id=uuid.UUID(job.payload["message_id"]),
            now=ctx.now,
        )
    except outreach.SendDeferred as exc:
        raise JobDeferred(str(exc), seconds=exc.seconds) from exc
    return {"status": msg.status.value, "error_code": msg.error_code}


def handle_email_reconcile(ctx: JobContext, job: Job) -> dict[str, Any]:
    if ctx.email is None:
        raise JobError("misconfigured", "No email provider configured.")
    msg = outreach.reconcile(
        ctx.db, ctx.crypto, ctx.email, message_id=uuid.UUID(job.payload["message_id"]), now=ctx.now
    )
    return {"status": msg.status.value}


HANDLERS = {
    "email.send": handle_email_send,
    "email.reconcile": handle_email_reconcile,
    "proposal.generate": handle_proposal,
    "design.validate": handle_validate,
    "design.render": handle_render,
    "design.brief": handle_brief,
    "prospect.audit": handle_audit,
    "discovery.search": handle_search,
    "discovery.verify": handle_verify,
    "prospect.qualify": handle_qualify,
}
