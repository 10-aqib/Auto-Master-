"""Owner overview (Phase 10): pipeline analytics, budgets, review queues and operational health.

Read-only aggregation over existing tables. No open/click tracking exists, so none is reported.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

import redis
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import (
    ApiUsage,
    BackupRun,
    Campaign,
    ComplianceAssessment,
    DesignBrief,
    DesignRender,
    DesignValidation,
    Job,
    OutreachMessage,
    Proposal,
    Prospect,
    ProspectCampaign,
    Reply,
    SystemControl,
)
from webforge_api.models.enums import (
    JobStatus,
    MessageStatus,
    ProposalStatus,
    ProspectState,
    UsageOutcome,
)
from webforge_api.services import controls
from webforge_api.sources.usage import day_start

WARN_RATIO = 0.8
HEARTBEAT_PREFIX = "webforge:worker:"
HEARTBEAT_TTL_SECONDS = 60
# Funnel stage -> prospect states that have reached at least that stage (cumulative, pipeline order).
PIPELINE = [s.value for s in (
    ProspectState.DISCOVERED, ProspectState.SOURCE_VERIFYING, ProspectState.VERIFIED, ProspectState.DEDUPLICATED,
    ProspectState.QUALIFYING, ProspectState.QUALIFIED, ProspectState.AUDITING, ProspectState.AUDITED,
    ProspectState.GENERATING_DESIGN, ProspectState.VALIDATING, ProspectState.PROPOSAL_READY, ProspectState.COMPLIANCE_CHECK,
    ProspectState.SCHEDULED, ProspectState.SENT, ProspectState.DELIVERED, ProspectState.REPLIED, ProspectState.INTERESTED,
    ProspectState.CLIENT)]  # fmt: skip


def _month_start(now: datetime) -> datetime:
    return day_start(now).replace(day=1)


def _ratio(used: float, limit: float) -> float | None:
    return None if limit <= 0 else round(used / limit, 3)


def budgets(db: Session, settings: Settings, now: datetime) -> list[dict[str, Any]]:
    """Today's usage against each hard limit. Status: ok / warning (>= 80%) / stopped (>= 100% or limit 0)."""
    today = day_start(now)

    def spend(provider: str) -> tuple[int, int]:
        cost, count = db.execute(select(func.coalesce(func.sum(ApiUsage.cost_milliminor), 0), func.count())
                                 .where(ApiUsage.provider == provider, ApiUsage.occurred_at >= today, ApiUsage.outcome != UsageOutcome.ERROR)).one()  # fmt: skip
        return int(cost), int(count)

    places_cost, places_requests = spend("google_places")
    ai_cost, ai_calls = spend("anthropic")
    sent = int(db.scalar(select(func.count()).select_from(OutreachMessage).where(
        OutreachMessage.last_attempt_at >= today, OutreachMessage.status.in_((MessageStatus.SENDING, MessageStatus.ACCEPTED, MessageStatus.SENT,
                                                                             MessageStatus.DELIVERED, MessageStatus.BOUNCED, MessageStatus.COMPLAINED)))) or 0)  # fmt: skip
    rows = [
        {"key": "places_spend", "label": "Google Places spend today", "used": places_cost / 1000, "limit": settings.google_places_daily_budget_minor, "unit": "cents"},
        {"key": "places_requests", "label": "Google Places requests today", "used": places_requests, "limit": settings.google_places_daily_request_cap, "unit": "requests"},
        {"key": "ai_spend", "label": "AI spend today", "used": ai_cost / 1000, "limit": settings.ai_daily_budget_minor, "unit": "cents", "calls": ai_calls},
        {"key": "email_daily", "label": "Emails sent today", "used": sent, "limit": settings.email_daily_max, "unit": "messages"},
    ]  # fmt: skip
    for r in rows:
        ratio = _ratio(float(str(r["used"])), float(str(r["limit"])))
        r["ratio"] = ratio
        r["status"] = (
            "stopped" if ratio is None or ratio >= 1 else "warning" if ratio >= WARN_RATIO else "ok"
        )
        if ratio is None:
            r["note"] = "Limit is 0: this activity is blocked until the owner sets a budget."
    return rows


def _counts(db: Session, column: Any, *where: Any) -> dict[str, int]:
    q = select(column, func.count()).group_by(column)
    for w in where:
        q = q.where(w)
    return {(k.value if hasattr(k, "value") else str(k)): int(v) for k, v in db.execute(q).all()}


def overview(
    db: Session,
    settings: Settings,
    now: datetime,
    campaign_id: str | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    filters: list[Any] = []
    if campaign_id:
        filters.append(
            Prospect.id.in_(
                select(ProspectCampaign.prospect_id).where(
                    ProspectCampaign.campaign_id == campaign_id
                )
            )
        )
    if country:
        filters.append(Prospect.country_code == country)
    states = _counts(db, Prospect.state, *filters)
    reached: dict[str, int] = {}
    for i, stage in enumerate(PIPELINE):
        reached[stage] = sum(states.get(s, 0) for s in PIPELINE[i:])
    msg_filter = (
        [OutreachMessage.prospect_id.in_(select(Prospect.id).where(*filters))] if filters else []
    )
    messages = _counts(db, OutreachMessage.status, *msg_filter)
    reply_filter = [Reply.prospect_id.in_(select(Prospect.id).where(*filters))] if filters else []
    replies = _counts(db, Reply.classification, *reply_filter)
    holds = db.execute(select(func.unnest(ComplianceAssessment.reason_codes).label("r"), func.count())
                       .where(ComplianceAssessment.decision != "ELIGIBLE", ComplianceAssessment.assessed_at >= now - timedelta(days=30))
                       .group_by("r").order_by(func.count().desc()).limit(10)).all()  # fmt: skip
    by_campaign = [{"campaign_id": str(cid), "name": name, "status": status.value, "prospects": int(n)}
                   for cid, name, status, n in db.execute(select(Campaign.id, Campaign.name, Campaign.status, func.count(ProspectCampaign.prospect_id))
                                                          .outerjoin(ProspectCampaign, ProspectCampaign.campaign_id == Campaign.id)
                                                          .group_by(Campaign.id).order_by(Campaign.created_at.desc()).limit(20)).all()]  # fmt: skip
    by_country = [{"country": c or "unknown", "prospects": int(n)} for c, n in db.execute(
        select(Prospect.country_code, func.count()).group_by(Prospect.country_code).order_by(func.count().desc()).limit(20)).all()]  # fmt: skip
    month = _month_start(now)
    spend = [{"provider": p, "cost_cents": round(int(c) / 1000, 2), "calls": int(n)} for p, c, n in db.execute(
        select(ApiUsage.provider, func.coalesce(func.sum(ApiUsage.cost_milliminor), 0), func.count())
        .where(ApiUsage.occurred_at >= month, ApiUsage.outcome != UsageOutcome.ERROR).group_by(ApiUsage.provider)).all()]  # fmt: skip
    return {
        "funnel": [
            {"stage": s, "reached": reached[s], "current": states.get(s, 0)} for s in PIPELINE
        ],
        "holds_and_exits": {
            k: states.get(k, 0)
            for k in (
                "HUMAN_REVIEW",
                "POLICY_HOLD",
                "FAILED",
                "REJECTED",
                "DO_NOT_CONTACT",
                "UNSUBSCRIBED",
                "BOUNCED",
                "MERGED",
                "EXPIRED",
            )
        },
        "messages": messages,
        "replies": replies,
        "outcomes": {
            "sent": sum(
                messages.get(k, 0)
                for k in ("ACCEPTED", "SENT", "DELIVERED", "BOUNCED", "COMPLAINED")
            ),
            "delivered": messages.get("DELIVERED", 0),
            "bounced": messages.get("BOUNCED", 0),
            "complained": messages.get("COMPLAINED", 0),
            "replied": sum(replies.values()),
            "opted_out": replies.get("OPT_OUT", 0),
            "interested": replies.get("INTERESTED", 0),
            "converted": states.get("CLIENT", 0),
        },
        "hold_reasons": [{"reason": r, "count": int(n)} for r, n in holds],
        "by_campaign": by_campaign,
        "by_country": by_country,
        "spend_this_month": spend,
        "budgets": budgets(db, settings, now),
        "tracking_note": "Opens and clicks are not tracked (privacy default).",
        "filters": {"campaign_id": campaign_id, "country": country},
    }


def review_queues(db: Session) -> dict[str, list[dict[str, Any]]]:
    def prospects(state: ProspectState) -> list[dict[str, Any]]:
        rows = db.execute(select(Prospect.id, Prospect.business_name, Prospect.state_changed_at).where(Prospect.state == state)
                          .order_by(Prospect.state_changed_at).limit(50)).all()  # fmt: skip
        return [
            {"id": str(i), "title": n, "since": t.isoformat(), "href": f"/prospects/{i}"}
            for i, n, t in rows
        ]

    briefs = db.execute(select(DesignBrief.id, DesignBrief.design_project_id, DesignBrief.version, DesignBrief.validation_issues, DesignBrief.created_at)
                        .where(DesignBrief.status == "NEEDS_REVIEW").order_by(DesignBrief.created_at).limit(50)).all()  # fmt: skip
    latest_validation = (
        select(DesignValidation.render_id, func.max(DesignValidation.created_at).label("at"))
        .group_by(DesignValidation.render_id)
        .subquery()
    )
    revisions = db.execute(select(DesignRender.id, DesignRender.design_project_id, DesignRender.version, DesignValidation.report)
                           .join(DesignValidation, DesignValidation.render_id == DesignRender.id)
                           .join(latest_validation, (latest_validation.c.render_id == DesignValidation.render_id) & (latest_validation.c.at == DesignValidation.created_at))
                           .where(DesignValidation.status == "NEEDS_REVISION", DesignRender.status == "RENDERED").limit(50)).all()  # fmt: skip
    proposals = db.execute(select(Proposal.id, Proposal.design_project_id, Proposal.proposal_version, Proposal.checks)
                           .where(Proposal.status == ProposalStatus.DRAFT, Proposal.deleted_at.is_(None)).limit(50)).all()  # fmt: skip
    holds = db.execute(select(OutreachMessage.id, OutreachMessage.prospect_id, OutreachMessage.error_code, OutreachMessage.created_at)
                       .where(OutreachMessage.status == MessageStatus.DRAFT).order_by(OutreachMessage.created_at).limit(50)).all()  # fmt: skip
    awaiting = db.execute(select(OutreachMessage.id, OutreachMessage.prospect_id, OutreachMessage.created_at)
                          .where(OutreachMessage.status == MessageStatus.PENDING_REVIEW).limit(50)).all()  # fmt: skip
    replies = db.execute(select(Reply.id, Reply.prospect_id, Reply.classification, Reply.received_at)
                         .where(Reply.needs_human_review.is_(True), Reply.handled_at.is_(None)).order_by(Reply.received_at).limit(50)).all()  # fmt: skip
    return {
        "source_and_evidence_review": prospects(ProspectState.HUMAN_REVIEW),
        "compliance_holds": [{"id": str(i), "title": f"Outreach held: {code or 'hold'}", "since": t.isoformat(), "href": f"/prospects/{p}"} for i, p, code, t in holds]
        + [{"id": str(p), "title": "Prospect on policy hold", "since": s, "href": f"/prospects/{p}"} for p, s in
           [(x["id"], x["since"]) for x in prospects(ProspectState.POLICY_HOLD)]],
        "awaiting_send_approval": [{"id": str(i), "title": "Eligible message awaiting owner approval", "since": t.isoformat(), "href": f"/prospects/{p}"} for i, p, t in awaiting],
        "content_claims": [{"id": str(i), "title": f"Brief v{v}: {len(issues or [])} issue(s)", "since": t.isoformat(), "href": f"/designs/{d}"} for i, d, v, issues, t in briefs],
        "concept_revisions": [{"id": str(i), "title": f"Concept v{v}: {rep.get('summary', {}).get('failed_critical', 0)} critical check(s) failed", "since": "", "href": f"/designs/{d}"}
                              for i, d, v, rep in revisions],
        "proposal_checks": [{"id": str(i), "title": f"Proposal v{v}: {', '.join(c['code'] for c in (checks or []) if not c.get('ok'))}", "since": "", "href": f"/designs/{d}"}
                            for i, d, v, checks in proposals],
        "uncertain_replies": [{"id": str(i), "title": f"Reply: {(c or 'UNCERTAIN').lower()}", "since": t.isoformat(), "href": "/replies"} for i, p, c, t in replies],
    }  # fmt: skip


# ----------------------------------------------------------------------------- operations


def record_heartbeat(client: redis.Redis, worker_id: str, queues: list[str], now: datetime) -> None:
    client.set(
        HEARTBEAT_PREFIX + worker_id,
        json.dumps({"queues": queues, "at": now.isoformat()}),
        ex=HEARTBEAT_TTL_SECONDS,
    )


def workers(client: redis.Redis | None) -> list[dict[str, Any]] | None:
    if client is None:
        return None
    try:
        out = []
        for key in client.scan_iter(HEARTBEAT_PREFIX + "*", count=100):
            raw = client.get(key)
            if raw:
                data = json.loads(raw)
                name = key.decode() if isinstance(key, bytes) else str(key)
                out.append({"worker": name.removeprefix(HEARTBEAT_PREFIX), **data})
        return sorted(out, key=lambda w: w["worker"])
    except redis.RedisError:
        return None


def backup_status(db: Session, now: datetime) -> dict[str, Any]:
    def latest(kind: str, status: str | None = None) -> BackupRun | None:
        q = select(BackupRun).where(BackupRun.kind == kind)
        if status:
            q = q.where(BackupRun.status == status)
        return db.scalar(q.order_by(BackupRun.finished_at.desc()).limit(1))

    backup, restore, last = latest("backup", "ok"), latest("restore_test", "ok"), latest("backup")
    if backup is None:
        return {
            "status": "unknown",
            "at": None,
            "restore_test_at": None,
            "detail": "No backup recorded yet. Run infrastructure/scripts/backup.sh.",
        }
    problems = []
    if now - backup.finished_at > timedelta(hours=26):
        problems.append("last successful backup is older than 26 h")
    if restore is None or now - restore.finished_at > timedelta(days=8):
        problems.append("no successful restore test in 8 days")
    if last is not None and last.status == "failed":
        problems.append("the most recent backup failed")
    return {"status": "stale" if problems else "ok", "at": backup.finished_at.isoformat(),
            "restore_test_at": restore.finished_at.isoformat() if restore else None,
            "detail": "; ".join(problems) or f"{backup.bytes} bytes, {backup.location or 'local only'}"}  # fmt: skip


def operations(
    db: Session, settings: Settings, now: datetime, client: redis.Redis | None
) -> dict[str, Any]:
    queues = []
    for queue, status, n, oldest in db.execute(select(Job.queue, Job.status, func.count(), func.min(Job.created_at))
                                               .where(Job.status.in_((JobStatus.QUEUED, JobStatus.RETRYING, JobStatus.RUNNING)))
                                               .group_by(Job.queue, Job.status)).all():  # fmt: skip
        queues.append(
            {
                "queue": queue,
                "status": status.value,
                "count": int(n),
                "oldest_age_seconds": int((now - oldest).total_seconds()) if oldest else 0,
            }
        )
    dead = int(
        db.scalar(select(func.count()).select_from(Job).where(Job.status == JobStatus.DEAD)) or 0
    )
    failures = [{"job_type": t, "error_code": c, "count": int(n)} for t, c, n in db.execute(
        select(Job.job_type, Job.error_code, func.count()).where(Job.status.in_((JobStatus.FAILED, JobStatus.DEAD)), Job.updated_at >= now - timedelta(days=1))
        .group_by(Job.job_type, Job.error_code).order_by(func.count().desc()).limit(20)).all()]  # fmt: skip
    provider_errors = [{"provider": p, "count": int(n)} for p, n in db.execute(
        select(ApiUsage.provider, func.count()).where(ApiUsage.outcome == UsageOutcome.ERROR, ApiUsage.occurred_at >= now - timedelta(days=1))
        .group_by(ApiUsage.provider)).all()]  # fmt: skip
    pauses = [{"key": r.key, "enabled": r.enabled, "effective": controls.is_paused(db, settings, r.key) if r.key in controls.KNOWN_CONTROLS else r.enabled,
               "reason": r.reason, "updated_at": r.updated_at.isoformat(), "updated_by_user_id": str(r.updated_by_user_id) if r.updated_by_user_id else None}
              for r in db.scalars(select(SystemControl).order_by(SystemControl.key))]  # fmt: skip
    return {
        "workers": workers(client),
        "worker_note": "Workers publish a heartbeat every few seconds; a missing worker disappears after 60 seconds.",
        "queues": queues,
        "dead_letter": dead,
        "failures_24h": failures,
        "provider_errors_24h": provider_errors,
        "budgets": budgets(db, settings, now),
        "pauses": pauses,
        "backups": backup_status(db, now),
    }  # fmt: skip
