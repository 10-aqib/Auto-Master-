"""Campaign lifecycle: DRAFT -> ACTIVE <-> PAUSED -> COMPLETED / ARCHIVED."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import Campaign, ExternalPlaceIdentifier, Job, ProspectCampaign
from webforge_api.models.enums import CampaignStatus, JobStatus, SendingMode
from webforge_api.security.crypto import Crypto
from webforge_api.services import activity, controls
from webforge_api.services.auth import Principal
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import ConflictError, NotFoundError, ServiceError
from webforge_api.services.jobs import JobSpec, enqueue
from webforge_api.sources.industries import INDUSTRIES
from webforge_api.sources.registry import SourceRegistry

DISCOVERY_SEARCH = JobSpec("discovery.search", "discovery", max_attempts=3)
DISCOVERY_VERIFY = JobSpec("discovery.verify", "verification", max_attempts=3)
QUALIFY = JobSpec("prospect.qualify", "qualification", max_attempts=3)

EDITABLE_STATES = {CampaignStatus.DRAFT, CampaignStatus.PAUSED}
TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.DRAFT: {CampaignStatus.ACTIVE, CampaignStatus.ARCHIVED},
    CampaignStatus.ACTIVE: {CampaignStatus.PAUSED, CampaignStatus.COMPLETED},
    CampaignStatus.PAUSED: {
        CampaignStatus.ACTIVE,
        CampaignStatus.COMPLETED,
        CampaignStatus.ARCHIVED,
    },
    CampaignStatus.COMPLETED: {CampaignStatus.ARCHIVED},
    CampaignStatus.ARCHIVED: set(),
}


@dataclass(frozen=True)
class CampaignInput:
    name: str
    description: str | None
    target_countries: list[str]
    target_regions: list[str]
    industries: list[str]
    queries: list[str]
    source_key: str
    region_code: str | None
    candidate_cap: int
    daily_budget_minor: int
    monthly_budget_minor: int


@dataclass(frozen=True)
class ReadinessCheck:
    code: str
    ok: bool
    message: str


def _validate_input(data: CampaignInput) -> None:
    errors: dict[str, str] = {}
    bad = [i for i in data.industries if i not in INDUSTRIES]
    if bad:
        errors["industries"] = f"Unknown industries: {', '.join(bad)}"
    if any(len(c) != 2 or not c.isalpha() or not c.isupper() for c in data.target_countries):
        errors["target_countries"] = "Use ISO 3166-1 alpha-2 codes, e.g. PK."
    if data.region_code and data.region_code not in data.target_countries:
        errors["region_code"] = "Region code must be one of the target countries."
    if len({q.strip().lower() for q in data.queries}) != len(data.queries):
        errors["queries"] = "Queries must be unique."
    if data.source_key not in ("google_places", "mock_places"):
        errors["source_key"] = "Unsupported discovery source."
    if errors:
        raise ServiceError(
            "invalid_campaign",
            "Some campaign fields are invalid.",
            status_code=422,
            field_errors=errors,
        )


class CampaignService:
    def __init__(self, db: Session, settings: Settings, crypto: Crypto, now: datetime) -> None:
        self.db = db
        self.settings = settings
        self.crypto = crypto
        self.now = now

    def get(self, campaign_id: uuid.UUID) -> Campaign:
        campaign = self.db.get(Campaign, campaign_id)
        if campaign is None:
            raise NotFoundError("not_found", "Campaign not found.")
        return campaign

    def all(self) -> list[Campaign]:
        return list(self.db.scalars(select(Campaign).order_by(Campaign.created_at.desc())))

    def _apply(self, campaign: Campaign, data: CampaignInput) -> None:
        campaign.name = data.name.strip()
        campaign.description = data.description
        campaign.target_countries = data.target_countries
        campaign.target_regions = data.target_regions
        campaign.industries = data.industries
        campaign.filters = {
            "queries": [q.strip() for q in data.queries],
            "source_key": data.source_key,
            "region_code": data.region_code,
        }
        campaign.candidate_cap = data.candidate_cap
        campaign.daily_budget_minor = data.daily_budget_minor
        campaign.monthly_budget_minor = data.monthly_budget_minor

    def create(self, actor: Principal, data: CampaignInput, meta: RequestMeta) -> Campaign:
        _validate_input(data)
        campaign = Campaign(
            created_by_user_id=actor.user.id,
            status=CampaignStatus.DRAFT,
            sending_mode=SendingMode.DISABLED,
        )
        self._apply(campaign, data)
        self.db.add(campaign)
        self.db.flush()
        self._log(actor, campaign, "campaign.created", meta)
        self.db.commit()
        return campaign

    def update(
        self, actor: Principal, campaign_id: uuid.UUID, data: CampaignInput, meta: RequestMeta
    ) -> Campaign:
        campaign = self.get(campaign_id)
        if campaign.status not in EDITABLE_STATES:
            raise ConflictError("not_editable", "Pause the campaign before editing it.")
        _validate_input(data)
        self._apply(campaign, data)
        self._log(actor, campaign, "campaign.updated", meta)
        self.db.commit()
        return campaign

    def readiness(self, campaign: Campaign) -> list[ReadinessCheck]:
        filters = campaign.filters or {}
        source_key = str(filters.get("source_key", ""))
        checks = [
            ReadinessCheck(
                "queries", bool(filters.get("queries")), "At least one discovery search."
            ),
            ReadinessCheck("candidate_cap", campaign.candidate_cap > 0, "Candidate cap above 0."),
            ReadinessCheck(
                "campaign_budget",
                campaign.daily_budget_minor > 0 or source_key == "mock_places",
                "Daily campaign budget above 0 (paid sources).",
            ),
            ReadinessCheck(
                "countries", bool(campaign.target_countries), "At least one target country."
            ),
        ]
        try:
            reg = SourceRegistry(self.db, self.settings, self.crypto, self.now)
            blockers = reg.blockers(reg.get(source_key))
        except ServiceError:
            blockers = ["Unknown source."]
        checks.append(
            ReadinessCheck(
                "source", not blockers, "Discovery source usable: " + (" ".join(blockers) or "yes")
            )
        )
        website = SourceRegistry(self.db, self.settings, self.crypto, self.now)
        web_blockers = website.blockers(website.get("official_website"))
        checks.append(
            ReadinessCheck(
                "verification", not web_blockers, "Official-website verification enabled."
            )
        )
        return checks

    def set_status(
        self,
        actor: Principal,
        campaign_id: uuid.UUID,
        to: CampaignStatus,
        reason: str,
        meta: RequestMeta,
    ) -> Campaign:
        campaign = self.db.get(Campaign, campaign_id, with_for_update=True)
        if campaign is None:
            raise NotFoundError("not_found", "Campaign not found.")
        if to not in TRANSITIONS[campaign.status]:
            raise ConflictError(
                "invalid_transition", f"Cannot move from {campaign.status} to {to}."
            )
        if to is CampaignStatus.ACTIVE:
            failing = [c for c in self.readiness(campaign) if not c.ok]
            if failing:
                raise ConflictError(
                    "not_ready",
                    "Campaign is not ready: " + "; ".join(c.message for c in failing),
                )
        previous = campaign.status
        campaign.status = to
        if to in (CampaignStatus.PAUSED, CampaignStatus.COMPLETED, CampaignStatus.ARCHIVED):
            # Stop queued work for this campaign (running jobs re-check status themselves).
            for job in self.db.scalars(
                select(Job).where(
                    Job.status.in_([JobStatus.QUEUED, JobStatus.RETRYING]),
                    Job.payload["campaign_id"].astext == str(campaign.id),
                    Job.queue.in_(["discovery", "verification"]),
                )
            ):
                if to is not CampaignStatus.PAUSED:
                    job.status = JobStatus.CANCELLED
                    job.finished_at = self.now
                    job.error_code = "campaign_closed"
        self._log(
            actor,
            campaign,
            f"campaign.{to.value.lower()}",
            meta,
            {"from": previous.value, "reason": reason[:200]},
        )
        self.db.commit()
        return campaign

    def run_discovery(
        self, actor: Principal, campaign_id: uuid.UUID, meta: RequestMeta
    ) -> list[Job]:
        """Queue one search job per query for today's UTC window (idempotent per day)."""
        campaign = self.get(campaign_id)
        if campaign.status is not CampaignStatus.ACTIVE:
            raise ConflictError("not_active", "Activate the campaign first.")
        if controls.is_paused(self.db, self.settings):
            raise ConflictError(
                "system_paused", "The system is paused. Resume it in Settings first."
            )
        filters = campaign.filters or {}
        window = self.now.date().isoformat()
        jobs: list[Job] = []
        for query in filters.get("queries", []):
            digest = hashlib.sha256(query.lower().encode()).hexdigest()[:16]
            job, _ = enqueue(
                self.db,
                DISCOVERY_SEARCH,
                idempotency_key=f"discover:{campaign.id}:{window}:{digest}",
                payload={
                    "campaign_id": str(campaign.id),
                    "query": query,
                    "source_key": filters.get("source_key"),
                    "region_code": filters.get("region_code"),
                },
                now=self.now,
                entity_type="campaign",
                entity_id=campaign.id,
                correlation_id=meta.request_id,
                created_by_user_id=actor.user.id,
            )
            jobs.append(job)
        self._log(actor, campaign, "campaign.discovery_queued", meta, {"jobs": len(jobs)})
        self.db.commit()
        return jobs

    def stats(self, campaign_id: uuid.UUID) -> dict[str, Any]:
        ids = self.db.scalar(
            select(func.count())
            .select_from(ExternalPlaceIdentifier)
            .where(ExternalPlaceIdentifier.campaign_id == campaign_id)
        )
        prospects = self.db.scalar(
            select(func.count())
            .select_from(ProspectCampaign)
            .where(ProspectCampaign.campaign_id == campaign_id)
        )
        jobs = dict(
            self.db.execute(
                select(Job.status, func.count())
                .where(Job.payload["campaign_id"].astext == str(campaign_id))
                .group_by(Job.status)
            ).all()
        )
        return {
            "candidates": int(ids or 0),
            "prospects": int(prospects or 0),
            "jobs": {k.value: int(v) for k, v in jobs.items()},
        }

    def _log(
        self,
        actor: Principal,
        campaign: Campaign,
        action: str,
        meta: RequestMeta,
        extra: dict[str, Any] | None = None,
    ) -> None:
        activity.record(
            self.db,
            self.crypto,
            action=action,
            actor_user_id=actor.user.id,
            meta=meta,
            entity_type="campaign",
            entity_id=campaign.id,
            metadata=extra or {},
        )
