"""/api/v1/sources, /api/v1/usage, /api/v1/places and /api/v1/verification."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from webforge_api.api.deps import (
    MetaDep,
    OwnerOnly,
    OwnerOrAdmin,
    PlacesServiceDep,
    RegistryDep,
    UsageDep,
)
from webforge_api.api.v1.schemas import StrictModel
from webforge_api.models import DomainVerification, SourceRegistration
from webforge_api.models.enums import SourceStatus
from webforge_api.services.places import VerifyResult
from webforge_api.sources.registry import SourceRegistry, TermsReview
from webforge_api.sources.usage import UsageSummary

router = APIRouter(tags=["sources"])


# ---------------------------------------------------------------------- schemas


class UsageWindowOut(BaseModel):
    requests: int
    cost_minor: int


class UsageSummaryOut(BaseModel):
    provider: str
    currency: str
    today: UsageWindowOut
    month: UsageWindowOut
    daily_budget_minor: int | None
    daily_request_cap: int | None
    budget_ratio: float | None
    cap_ratio: float | None
    warning: bool
    exhausted: bool

    @classmethod
    def of(cls, s: UsageSummary) -> UsageSummaryOut:
        return cls(
            provider=s.provider,
            currency=s.currency,
            today=UsageWindowOut(requests=s.today.requests, cost_minor=s.today.cost_minor),
            month=UsageWindowOut(requests=s.month.requests, cost_minor=s.month.cost_minor),
            daily_budget_minor=s.daily_budget_minor,
            daily_request_cap=s.daily_request_cap,
            budget_ratio=s.budget_ratio,
            cap_ratio=s.cap_ratio,
            warning=s.warning,
            exhausted=s.exhausted,
        )


class SourceOut(BaseModel):
    key: str
    display_name: str
    source_type: str
    status: SourceStatus
    description: str
    persistable_fields: list[str]
    cache_rules: dict[str, Any]
    attribution_required: bool
    attribution_text: str | None
    policy_urls: list[str]
    terms_url: str | None
    terms_version: str | None
    terms_reviewed_at: datetime | None
    review_notes: str | None
    status_changed_at: datetime | None
    status_reason: str | None
    usable: bool
    blockers: list[str]
    usage: UsageSummaryOut | None

    @classmethod
    def of(
        cls, row: SourceRegistration, registry: SourceRegistry, usage: UsageSummaryOut | None
    ) -> SourceOut:
        blockers = registry.blockers(row)
        return cls(
            key=row.key,
            display_name=row.display_name,
            source_type=row.source_type.value,
            status=row.status,
            description=row.description,
            persistable_fields=row.persistable_fields,
            cache_rules=row.cache_rules,
            attribution_required=row.attribution_required,
            attribution_text=row.attribution_text,
            policy_urls=row.policy_urls,
            terms_url=row.terms_url,
            terms_version=row.terms_version,
            terms_reviewed_at=row.terms_reviewed_at,
            review_notes=row.review_notes,
            status_changed_at=row.status_changed_at,
            status_reason=row.status_reason,
            usable=not blockers,
            blockers=blockers,
            usage=usage,
        )


class ReviewRequest(StrictModel):
    terms_url: str = Field(min_length=12, max_length=2048, pattern=r"^https://")
    terms_version: str = Field(min_length=1, max_length=64)
    review_notes: str = Field(min_length=20, max_length=4000)


class StatusRequest(StrictModel):
    reason: str = Field(min_length=3, max_length=500)


class DailyUsageOut(BaseModel):
    date: str
    requests: int
    cost_minor: int


class UsageReport(BaseModel):
    summary: UsageSummaryOut
    days: list[DailyUsageOut]


class SearchRequest(StrictModel):
    source_key: Literal["google_places", "mock_places"]
    text_query: str = Field(min_length=3, max_length=200)
    region_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    page_size: int = Field(default=10, ge=1, le=20)
    campaign_id: uuid.UUID | None = None


class PlaceOut(BaseModel):
    """Transient Maps content: display with attribution, never store."""

    place_id: str
    identifier_id: uuid.UUID
    display_name: str | None
    formatted_address: str | None
    business_status: str | None
    google_maps_uri: str | None


class AttributionOut(BaseModel):
    text: str
    required: bool
    is_mock: bool


class SearchResponse(BaseModel):
    source_key: str
    transient: Literal[True] = True
    attribution: AttributionOut
    sku: str
    stored_place_ids: int
    new_place_ids: int
    places: list[PlaceOut]


class IdentifierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider: str
    place_id: str
    status: str
    prospect_id: uuid.UUID | None
    campaign_id: uuid.UUID | None
    first_seen_at: datetime
    last_checked_at: datetime | None


class VerificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    method: str
    reason_codes: list[str]
    confidence: float | None
    candidate_url: str
    final_url: str | None
    domain: str | None
    candidate_origin: str
    evidence: dict[str, Any]
    checked_at: datetime
    prospect_id: uuid.UUID | None
    place_identifier_id: uuid.UUID | None


class VerifyResponse(BaseModel):
    verification: VerificationOut
    prospect_id: uuid.UUID | None
    place_obsolete: bool


class OwnerVerifyRequest(StrictModel):
    url: str = Field(min_length=8, max_length=2048, pattern=r"^https?://")
    expected_name: str = Field(min_length=2, max_length=200)


def _verify_response(result: VerifyResult) -> VerifyResponse:
    return VerifyResponse(
        verification=VerificationOut.model_validate(result.verification),
        prospect_id=result.prospect_id,
        place_obsolete=result.place_obsolete,
    )


# ---------------------------------------------------------------------- registry


def _usage_for(row: SourceRegistration, usage: UsageDep) -> UsageSummaryOut | None:
    if row.key in ("google_places", "mock_places"):
        return UsageSummaryOut.of(usage.summary(row.key))
    return None


@router.get("/sources", response_model=list[SourceOut])
def list_sources(_p: OwnerOrAdmin, registry: RegistryDep, usage: UsageDep) -> list[SourceOut]:
    return [SourceOut.of(r, registry, _usage_for(r, usage)) for r in registry.all()]


@router.post("/sources/{key}/review", response_model=SourceOut)
def review_source(
    key: str,
    body: ReviewRequest,
    principal: OwnerOnly,
    registry: RegistryDep,
    usage: UsageDep,
    meta: MetaDep,
) -> SourceOut:
    row = registry.record_review(
        principal, key, TermsReview(body.terms_url, body.terms_version, body.review_notes), meta
    )
    return SourceOut.of(row, registry, _usage_for(row, usage))


@router.post("/sources/{key}/enable", response_model=SourceOut)
def enable_source(
    key: str,
    body: StatusRequest,
    principal: OwnerOnly,
    registry: RegistryDep,
    usage: UsageDep,
    meta: MetaDep,
) -> SourceOut:
    row = registry.set_status(principal, key, SourceStatus.ENABLED, body.reason, meta)
    return SourceOut.of(row, registry, _usage_for(row, usage))


@router.post("/sources/{key}/disable", response_model=SourceOut)
def disable_source(
    key: str,
    body: StatusRequest,
    principal: OwnerOrAdmin,
    registry: RegistryDep,
    usage: UsageDep,
    meta: MetaDep,
) -> SourceOut:
    # Disabling is always allowed for owner and admins (fail-safe direction).
    row = registry.set_status(principal, key, SourceStatus.DISABLED, body.reason, meta)
    return SourceOut.of(row, registry, _usage_for(row, usage))


@router.get("/usage/{provider}", response_model=UsageReport)
def usage_report(
    provider: Literal["google_places", "mock_places"],
    _p: OwnerOrAdmin,
    usage: UsageDep,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
) -> UsageReport:
    return UsageReport(
        summary=UsageSummaryOut.of(usage.summary(provider)),
        days=[
            DailyUsageOut(date=d, requests=w.requests, cost_minor=w.cost_minor)
            for d, w in usage.recent_days(provider, days)
        ],
    )


# ---------------------------------------------------------------------- places


@router.post("/places/search", response_model=SearchResponse)
def places_search(
    body: SearchRequest, principal: OwnerOrAdmin, places: PlacesServiceDep, meta: MetaDep
) -> SearchResponse:
    result = places.search(
        principal,
        source_key=body.source_key,
        text_query=body.text_query,
        region_code=body.region_code,
        page_size=body.page_size,
        campaign_id=body.campaign_id,
        meta=meta,
    )
    return SearchResponse(
        source_key=result.source_key,
        attribution=AttributionOut(
            text=result.attribution.text,
            required=result.attribution.required,
            is_mock=result.attribution.is_mock,
        ),
        sku=result.sku,
        stored_place_ids=result.stored_place_ids,
        new_place_ids=result.new_place_ids,
        places=[
            PlaceOut(
                place_id=p.place_id,
                identifier_id=result.identifier_ids[p.place_id],
                display_name=p.display_name,
                formatted_address=p.formatted_address,
                business_status=p.business_status,
                google_maps_uri=p.google_maps_uri,
            )
            for p in result.places
        ],
    )


@router.get("/places/identifiers", response_model=list[IdentifierOut])
def list_identifiers(
    _p: OwnerOrAdmin,
    places: PlacesServiceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[IdentifierOut]:
    return [IdentifierOut.model_validate(r) for r in places.list_identifiers(limit)]


@router.post("/places/identifiers/{identifier_id}/verify-website", response_model=VerifyResponse)
def verify_place_website(
    identifier_id: uuid.UUID, principal: OwnerOrAdmin, places: PlacesServiceDep, meta: MetaDep
) -> VerifyResponse:
    return _verify_response(places.verify_place_website(principal, identifier_id, meta))


@router.post("/verification/website", response_model=VerifyResponse)
def verify_owner_website(
    body: OwnerVerifyRequest, principal: OwnerOrAdmin, places: PlacesServiceDep, meta: MetaDep
) -> VerifyResponse:
    return _verify_response(places.verify_owner_url(principal, body.url, body.expected_name, meta))


@router.get("/verification/recent", response_model=list[VerificationOut])
def recent_verifications(
    _p: OwnerOrAdmin,
    places: PlacesServiceDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[VerificationOut]:
    rows = places.db.scalars(
        select(DomainVerification).order_by(DomainVerification.checked_at.desc()).limit(limit)
    )
    return [VerificationOut.model_validate(r) for r in rows]
