"""Source terms/permission registry. Connectors without a recorded terms review stay disabled."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import SourceRegistration
from webforge_api.models.enums import SourceStatus, SourceType
from webforge_api.security.crypto import Crypto
from webforge_api.services import activity
from webforge_api.services.auth import Principal
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import ConflictError, NotFoundError, ServiceError


class SourceDisabledError(ServiceError):
    status_code = 409


@dataclass(frozen=True)
class TermsReview:
    terms_url: str
    terms_version: str
    review_notes: str


class SourceRegistry:
    def __init__(self, db: Session, settings: Settings, crypto: Crypto, now: datetime) -> None:
        self.db = db
        self.settings = settings
        self.crypto = crypto
        self.now = now

    def all(self) -> list[SourceRegistration]:
        rows = self.db.scalars(select(SourceRegistration).order_by(SourceRegistration.key))
        # Mock sources do not exist as far as production is concerned.
        return [
            r
            for r in rows
            if not (self.settings.is_production and r.source_type is SourceType.MOCK)
        ]

    def get(self, key: str) -> SourceRegistration:
        row = self.db.scalar(select(SourceRegistration).where(SourceRegistration.key == key))
        if row is None or (self.settings.is_production and row.source_type is SourceType.MOCK):
            raise NotFoundError("not_found", "Unknown source.")
        return row

    def blockers(self, row: SourceRegistration) -> list[str]:
        """Reasons the source cannot be used right now (empty = usable)."""
        reasons: list[str] = []
        if row.status is not SourceStatus.ENABLED:
            reasons.append("Source is disabled in the registry.")
        if row.source_type is SourceType.MOCK and self.settings.is_production:
            reasons.append("Mock sources cannot be used in production.")
        if row.key == "google_places":
            if not self.settings.google_places_api_enabled:
                reasons.append("GOOGLE_PLACES_API_ENABLED is false.")
            if not self.settings.google_maps_api_key.get_secret_value():
                reasons.append("GOOGLE_MAPS_API_KEY is not set.")
            if self.settings.google_places_daily_budget_minor <= 0:
                reasons.append("GOOGLE_PLACES_DAILY_BUDGET_MINOR is 0.")
            if self.settings.google_places_daily_request_cap <= 0:
                reasons.append("GOOGLE_PLACES_DAILY_REQUEST_CAP is 0.")
        return reasons

    def require_usable(self, key: str) -> SourceRegistration:
        row = self.get(key)
        reasons = self.blockers(row)
        if reasons:
            raise SourceDisabledError("source_disabled", " ".join(reasons))
        return row

    def record_review(
        self, actor: Principal, key: str, review: TermsReview, meta: RequestMeta
    ) -> SourceRegistration:
        row = self.get(key)
        row.terms_url = review.terms_url
        row.terms_version = review.terms_version
        row.review_notes = review.review_notes
        row.terms_reviewed_at = self.now
        row.reviewed_by_user_id = actor.user.id
        activity.record(
            self.db,
            self.crypto,
            action="source.terms_reviewed",
            actor_user_id=actor.user.id,
            meta=meta,
            entity_type="source",
            entity_id=key,
            metadata={"terms_version": review.terms_version},
        )
        self.db.commit()
        return row

    def set_status(
        self, actor: Principal, key: str, status: SourceStatus, reason: str, meta: RequestMeta
    ) -> SourceRegistration:
        row = self.get(key)
        if status is SourceStatus.ENABLED:
            if row.source_type is SourceType.MOCK and self.settings.is_production:
                raise ConflictError(
                    "mock_in_production", "Mock sources cannot be enabled in production."
                )
            if row.source_type is not SourceType.MOCK and row.terms_reviewed_at is None:
                raise ConflictError(
                    "terms_review_required", "Record a terms review before enabling this source."
                )
        row.status = status
        row.status_changed_at = self.now
        row.status_changed_by_user_id = actor.user.id
        row.status_reason = reason
        activity.record(
            self.db,
            self.crypto,
            action="source.enabled" if status is SourceStatus.ENABLED else "source.disabled",
            actor_user_id=actor.user.id,
            meta=meta,
            entity_type="source",
            entity_id=key,
            metadata={"reason": reason[:200]},
        )
        self.db.commit()
        return row
