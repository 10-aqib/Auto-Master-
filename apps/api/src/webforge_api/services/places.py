"""Places discovery and independent website verification.

Policy summary (checked 2026-11-26, see docs/compliance/source-policies.md):
- Only the Place ID from Google Places is persisted. Names, addresses, websites, statuses and
  Maps links are returned to the caller transiently and must be shown with attribution.
- A business is recorded as a prospect only after its own website independently confirms it.
- The website URL is never guessed: it comes from the source (transiently) or from the owner.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import (
    DomainVerification,
    ExternalPlaceIdentifier,
    Prospect,
    ProspectCampaign,
    SourceRegistration,
)
from webforge_api.models.enums import DomainVerificationStatus, PlaceIdStatus, ProspectState
from webforge_api.security.crypto import Crypto
from webforge_api.services import activity
from webforge_api.services.auth import Principal
from webforge_api.services.context import RequestMeta
from webforge_api.services.dedupe import branch_key_for, follow_merges
from webforge_api.services.errors import NotFoundError, ServiceError, UnavailableError
from webforge_api.services.provenance import FactEvidence, record_fact
from webforge_api.sources.places import (
    PlaceRecord,
    PlacesConnector,
    PlacesError,
    TextSearchRequest,
)
from webforge_api.sources.places_fields import (
    DETAILS_REFRESH_ID,
    DETAILS_WEBSITE,
    SEARCH_PREVIEW,
    FieldMask,
)
from webforge_api.sources.registry import SourceRegistry
from webforge_api.sources.usage import UsageService
from webforge_api.sources.website import VerificationOutcome, WebsiteVerifier

ConnectorLookup = Callable[[str], PlacesConnector]


@dataclass(frozen=True)
class Attribution:
    text: str
    required: bool
    is_mock: bool


@dataclass(frozen=True)
class SearchResult:
    source_key: str
    places: list[PlaceRecord]  # transient
    stored_place_ids: int
    new_place_ids: int
    attribution: Attribution
    sku: str
    identifier_ids: dict[str, uuid.UUID]


@dataclass(frozen=True)
class VerifyResult:
    verification: DomainVerification
    outcome: VerificationOutcome
    prospect_id: uuid.UUID | None
    place_obsolete: bool = False


MAPS_ORIGIN_SUFFIX = ":websiteUri (transient)"
NOT_RETAINED = "(not retained: Maps content)"


def _provider_error(exc: PlacesError) -> ServiceError:
    if exc.retryable:
        return UnavailableError(exc.code, str(exc))
    return ServiceError(exc.code, str(exc), status_code=502)


class PlacesService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        crypto: Crypto,
        registry: SourceRegistry,
        usage: UsageService,
        connectors: ConnectorLookup,
        verifier: WebsiteVerifier,
        now: datetime,
    ) -> None:
        self.db = db
        self.settings = settings
        self.crypto = crypto
        self.registry = registry
        self.usage = usage
        self.connectors = connectors
        self.verifier = verifier
        self.now = now

    # ------------------------------------------------------------------ calls with accounting

    def _call[T](
        self,
        source_key: str,
        mask: FieldMask,
        operation: str,
        campaign_id: uuid.UUID | None,
        fn: Callable[[PlacesConnector], T],
    ) -> T:
        self.registry.require_usable(source_key)
        connector = self.connectors(source_key)
        sku = "MOCK" if connector.is_mock else mask.sku
        reservation = self.usage.reserve(source_key, sku, operation, campaign_id)
        try:
            result = fn(connector)
        except PlacesError as exc:
            self.usage.finish(reservation, success=False)
            raise _provider_error(exc) from exc
        except Exception:
            self.usage.finish(reservation, success=False)
            raise
        self.usage.finish(reservation, success=True)
        return result

    def _attribution(self, reg: SourceRegistration, is_mock: bool) -> Attribution:
        return Attribution(
            text=reg.attribution_text or reg.display_name,
            required=reg.attribution_required,
            is_mock=is_mock,
        )

    # ------------------------------------------------------------------ search

    def search(
        self,
        actor: Principal | None,
        *,
        source_key: str,
        text_query: str,
        region_code: str | None,
        page_size: int,
        campaign_id: uuid.UUID | None,
        meta: RequestMeta,
    ) -> SearchResult:
        request = TextSearchRequest(
            text_query=text_query.strip(),
            region_code=region_code,
            language_code=self.settings.google_places_language_code,
            page_size=page_size,
        )
        page = self._call(
            source_key,
            SEARCH_PREVIEW,
            "text_search",
            campaign_id,
            lambda c: c.search_text(request, SEARCH_PREVIEW),
        )
        # Persist Place IDs only (the documented storage exception).
        new = 0
        identifier_ids: dict[str, uuid.UUID] = {}
        for place in page.places:
            stmt: Any = (
                insert(ExternalPlaceIdentifier)
                .values(
                    provider=source_key,
                    place_id=place.place_id,
                    campaign_id=campaign_id,
                    first_seen_at=self.now,
                    last_checked_at=self.now,
                )
                .on_conflict_do_update(
                    index_elements=["provider", "place_id"],
                    set_={"last_checked_at": self.now, "status": PlaceIdStatus.ACTIVE.value},
                )
                # xmax = 0 only for freshly inserted rows (PostgreSQL upsert idiom).
                .returning(ExternalPlaceIdentifier.id, literal_column("(xmax = 0)"))
            )
            row_id, inserted = self.db.execute(stmt).one()
            identifier_ids[place.place_id] = row_id
            new += int(bool(inserted))
        reg = self.registry.get(source_key)
        connector = self.connectors(source_key)
        activity.record(
            self.db,
            self.crypto,
            action="places.search",
            actor_user_id=actor.user.id if actor else None,
            system=actor is None,
            meta=meta,
            entity_type="source",
            entity_id=source_key,
            metadata={"results": len(page.places), "new_place_ids": new, "sku": SEARCH_PREVIEW.sku},
        )
        self.db.commit()
        return SearchResult(
            source_key=source_key,
            places=page.places,
            stored_place_ids=len(page.places),
            new_place_ids=new,
            attribution=self._attribution(reg, connector.is_mock),
            sku=SEARCH_PREVIEW.sku,
            identifier_ids=identifier_ids,
        )

    def list_identifiers(self, limit: int = 100) -> list[ExternalPlaceIdentifier]:
        return list(
            self.db.scalars(
                select(ExternalPlaceIdentifier)
                .order_by(ExternalPlaceIdentifier.first_seen_at.desc())
                .limit(limit)
            )
        )

    # ------------------------------------------------------------------ verification

    def _store_verification(
        self,
        actor: Principal | None,
        outcome: VerificationOutcome,
        origin: str,
        identifier: ExternalPlaceIdentifier | None,
    ) -> DomainVerification:
        # A website URL that came from Google (websiteUri) is Maps Content. It is kept only when the
        # business's own site independently confirmed it (VERIFIED); else only the outcome is kept.
        from_maps = origin.endswith(MAPS_ORIGIN_SUFFIX)
        redact = from_maps and outcome.status is not DomainVerificationStatus.VERIFIED
        row = DomainVerification(
            place_identifier_id=identifier.id if identifier else None,
            candidate_url=NOT_RETAINED if redact else (outcome.candidate_url[:2048] or "(none)"),
            final_url=None if redact else outcome.final_url,
            domain=None if redact else outcome.domain,
            candidate_origin=origin,
            status=outcome.status,
            method=outcome.method,
            reason_codes=outcome.reason_codes,
            confidence=outcome.confidence,
            evidence={} if redact else outcome.evidence,
            checked_at=self.now,
            checked_by_user_id=actor.user.id if actor else None,
        )
        self.db.add(row)
        self.db.flush()
        return row

    def _record_verified_prospect(
        self,
        verification: DomainVerification,
        outcome: VerificationOutcome,
        campaign_id: uuid.UUID | None,
    ) -> uuid.UUID:
        """Create or attach a prospect using only facts the official website itself states.

        Dedupe key = verified domain + branch key (a location-specific path on a shared site).
        Different branches stay separate; a merged prospect redirects to its survivor. Existing
        rejected / do-not-contact decisions are never reset by rediscovery.
        """
        website_src = self.registry.require_usable("official_website")
        if not (outcome.domain and outcome.final_url and outcome.declared_name):
            raise ServiceError("incomplete_verification", "Verification evidence is incomplete.")
        branch = branch_key_for(outcome.final_url)
        prospect = self.db.scalar(
            select(Prospect)
            .where(Prospect.verified_domain == outcome.domain, Prospect.branch_key == branch)
            .order_by(Prospect.created_at)
            .limit(1)
        )
        prospect = follow_merges(self.db, prospect)
        if prospect is None:
            prospect = Prospect(
                business_name=outcome.declared_name[:300],
                verified_domain=outcome.domain,
                branch_key=branch,
                website_url=outcome.final_url,
                industry=outcome.industry,
                state=ProspectState.VERIFIED,
                state_changed_at=self.now,
                first_seen_at=self.now,
                last_verified_at=self.now,
            )
            self.db.add(prospect)
            self.db.flush()
        else:
            prospect.last_verified_at = self.now
            if outcome.industry and not prospect.industry:
                prospect.industry = outcome.industry
        evidence = FactEvidence(
            source=website_src,
            source_url=outcome.final_url,
            retrieved_at=self.now,
            confidence=outcome.confidence or 0.0,
            method=outcome.method,
            evidence_note=f"signal={outcome.evidence.get('matched_signal')}",
        )
        facts = [
            ("business_name", outcome.declared_name[:300]),
            ("website_url", outcome.final_url),
            ("verified_domain", outcome.domain),
        ]
        if outcome.industry:
            facts.append(("industry", outcome.industry))
        for field, value in facts:
            record_fact(
                self.db, prospect_id=prospect.id, field=field, value=value, evidence=evidence
            )
        if campaign_id is not None:
            self.db.execute(
                insert(ProspectCampaign)
                .values(prospect_id=prospect.id, campaign_id=campaign_id, added_at=self.now)
                .on_conflict_do_nothing(index_elements=["prospect_id", "campaign_id"])
            )
        verification.prospect_id = prospect.id
        return prospect.id

    def verify_place_website(
        self, actor: Principal | None, identifier_id: uuid.UUID, meta: RequestMeta
    ) -> VerifyResult:
        identifier = self.db.get(ExternalPlaceIdentifier, identifier_id)
        if identifier is None:
            raise NotFoundError("not_found", "Place identifier not found.")
        self.registry.require_usable("official_website")
        place = self._call(
            identifier.provider,
            DETAILS_WEBSITE,
            "place_details",
            identifier.campaign_id,
            lambda c: c.place_details(identifier.place_id, DETAILS_WEBSITE),
        )
        identifier.last_checked_at = self.now
        if place is None:
            identifier.status = PlaceIdStatus.OBSOLETE
            outcome = VerificationOutcome(
                DomainVerificationStatus.HOLD, "place_lookup", ["place_id_obsolete"], ""
            )
            row = self._store_verification(
                actor, outcome, f"{identifier.provider}:place_id", identifier
            )
            self.db.commit()
            return VerifyResult(row, outcome, None, place_obsolete=True)

        # websiteUri and displayName are Maps Content: used transiently for this check only.
        outcome = self.verifier.verify(place.website_uri, place.display_name)
        origin = f"{identifier.provider}{MAPS_ORIGIN_SUFFIX}"
        return self._finish_verification(actor, outcome, origin, identifier, meta)

    def verify_owner_url(
        self, actor: Principal, url: str, expected_name: str, meta: RequestMeta
    ) -> VerifyResult:
        self.registry.require_usable("official_website")
        outcome = self.verifier.verify(url, expected_name)
        return self._finish_verification(actor, outcome, "owner", None, meta)

    def _finish_verification(
        self,
        actor: Principal | None,
        outcome: VerificationOutcome,
        origin: str,
        identifier: ExternalPlaceIdentifier | None,
        meta: RequestMeta,
    ) -> VerifyResult:
        row = self._store_verification(actor, outcome, origin, identifier)
        prospect_id = None
        if outcome.status is DomainVerificationStatus.VERIFIED:
            campaign_id = identifier.campaign_id if identifier else None
            prospect_id = self._record_verified_prospect(row, outcome, campaign_id)
            if identifier is not None:
                identifier.prospect_id = prospect_id
        activity.record(
            self.db,
            self.crypto,
            action="website.verification",
            actor_user_id=actor.user.id if actor else None,
            system=actor is None,
            meta=meta,
            entity_type="domain_verification",
            entity_id=row.id,
            metadata={
                "status": outcome.status.value,
                "reasons": outcome.reason_codes,
                "origin": origin,
            },
        )
        self.db.commit()
        return VerifyResult(row, outcome, prospect_id)

    # ------------------------------------------------------------------ maintenance

    def refresh_place_ids(self, *, older_than_days: int = 365, limit: int = 100) -> dict[str, int]:
        """Google recommends refreshing Place IDs older than 12 months (IDs-only Place Details)."""
        cutoff = self.now - timedelta(days=older_than_days)
        rows = list(
            self.db.scalars(
                select(ExternalPlaceIdentifier)
                .where(
                    ExternalPlaceIdentifier.status == PlaceIdStatus.ACTIVE,
                    (ExternalPlaceIdentifier.last_checked_at.is_(None))
                    | (ExternalPlaceIdentifier.last_checked_at < cutoff),
                )
                .order_by(ExternalPlaceIdentifier.last_checked_at.nulls_first())
                .limit(limit)
            )
        )
        counts = {"checked": 0, "obsolete": 0, "changed": 0}
        for row in rows:

            def lookup(c: PlacesConnector, pid: str = row.place_id) -> PlaceRecord | None:
                return c.place_details(pid, DETAILS_REFRESH_ID)

            place = self._call(row.provider, DETAILS_REFRESH_ID, "place_id_refresh", None, lookup)
            counts["checked"] += 1
            row.last_checked_at = self.now
            if place is None:
                row.status = PlaceIdStatus.OBSOLETE
                counts["obsolete"] += 1
            elif place.place_id and place.place_id != row.place_id:
                taken = self.db.scalar(
                    select(ExternalPlaceIdentifier.id).where(
                        ExternalPlaceIdentifier.provider == row.provider,
                        ExternalPlaceIdentifier.place_id == place.place_id,
                    )
                )
                if taken is None:
                    row.place_id = place.place_id
                else:  # the new ID is already stored; retire this duplicate
                    row.status = PlaceIdStatus.OBSOLETE
                counts["changed"] += 1
            self.db.commit()
        return counts
