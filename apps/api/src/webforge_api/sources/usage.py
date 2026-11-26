"""Provider usage, cost accounting and budget enforcement.

Each billable request is RESERVED before it is sent (serialised per provider with an advisory
lock), then marked SUCCESS or ERROR. Spend-causing requests stop at 100% of any budget or cap.
Prices are owner-configured per SKU; an unpriced SKU is refused (fail closed).
"""

from __future__ import annotations

import uuid
import zlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.logging_config import get_logger
from webforge_api.models import ApiUsage, Campaign
from webforge_api.models.enums import UsageOutcome
from webforge_api.security.rate_limit import RateLimiter, RateLimiterUnavailableError
from webforge_api.services.errors import RateLimitedError, ServiceError, UnavailableError

log = get_logger(__name__)
WARN_RATIO = 0.8


class BudgetExceededError(ServiceError):
    status_code = 409


@dataclass(frozen=True)
class ProviderLimits:
    daily_budget_minor: int | None  # None = unpriced (mock)
    daily_request_cap: int | None
    per_campaign_request_cap: int | None
    rate_per_minute: int
    prices: dict[str, int]  # SKU -> minor units per 1000 requests
    currency: str


def limits_for(provider: str, settings: Settings) -> ProviderLimits:
    if provider == "google_places":
        return ProviderLimits(
            daily_budget_minor=settings.google_places_daily_budget_minor,
            daily_request_cap=settings.google_places_daily_request_cap,
            per_campaign_request_cap=settings.google_places_max_requests_per_campaign,
            rate_per_minute=settings.google_places_rate_limit_per_minute,
            prices=settings.places_sku_prices,
            currency=settings.google_places_price_currency,
        )
    # Mock sources: free, still rate-limited and recorded.
    return ProviderLimits(None, None, None, 120, {}, "USD")


def day_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(frozen=True)
class UsageWindow:
    requests: int
    cost_milliminor: int

    @property
    def cost_minor(self) -> int:
        return -(-self.cost_milliminor // 1000)  # ceil


@dataclass(frozen=True)
class UsageSummary:
    provider: str
    currency: str
    today: UsageWindow
    month: UsageWindow
    daily_budget_minor: int | None
    daily_request_cap: int | None
    budget_ratio: float | None
    cap_ratio: float | None

    @property
    def warning(self) -> bool:
        return any(r is not None and r >= WARN_RATIO for r in (self.budget_ratio, self.cap_ratio))

    @property
    def exhausted(self) -> bool:
        return any(r is not None and r >= 1 for r in (self.budget_ratio, self.cap_ratio))


class UsageService:
    def __init__(
        self, db: Session, settings: Settings, limiter: RateLimiter, now: datetime
    ) -> None:
        self.db = db
        self.settings = settings
        self.limiter = limiter
        self.now = now

    def _window(
        self, provider: str, since: datetime, campaign_id: uuid.UUID | None = None
    ) -> UsageWindow:
        stmt = select(func.count(), func.coalesce(func.sum(ApiUsage.cost_milliminor), 0)).where(
            ApiUsage.provider == provider,
            ApiUsage.occurred_at >= since,
            ApiUsage.outcome != UsageOutcome.ERROR,
        )
        if campaign_id is not None:
            stmt = stmt.where(ApiUsage.campaign_id == campaign_id)
        count, cost = self.db.execute(stmt).one()
        return UsageWindow(requests=int(count), cost_milliminor=int(cost))

    def reserve(
        self, provider: str, sku: str, operation: str, campaign_id: uuid.UUID | None = None
    ) -> ApiUsage:
        limits = limits_for(provider, self.settings)
        try:
            if not self.limiter.hit(
                f"provider:{provider}", limit=limits.rate_per_minute, window_seconds=60
            ):
                raise RateLimitedError(
                    "provider_rate_limited", "Provider request rate limit reached."
                )
        except RateLimiterUnavailableError as exc:
            raise UnavailableError(
                "rate_limiter_unavailable", "Usage limits cannot be checked."
            ) from exc

        # Serialise check-and-reserve per provider so concurrent jobs cannot overspend.
        self.db.execute(
            select(func.pg_advisory_xact_lock(zlib.crc32(f"usage:{provider}".encode())))
        )
        cost = 0
        if limits.daily_budget_minor is not None:
            price = limits.prices.get(sku)
            if price is None:
                raise BudgetExceededError(
                    "price_not_configured",
                    f"No price configured for SKU {sku}; "
                    "set GOOGLE_PLACES_SKU_PRICES_MINOR_PER_1000.",
                )
            cost = price  # minor units per 1000 requests == milliminor per request
            today = self._window(provider, day_start(self.now))
            if limits.daily_budget_minor <= 0:
                raise BudgetExceededError("budget_not_configured", "Daily budget is 0.")
            if today.cost_milliminor + cost > limits.daily_budget_minor * 1000:
                raise BudgetExceededError(
                    "daily_budget_exhausted", "Daily provider budget reached."
                )
            if not limits.daily_request_cap or today.requests >= limits.daily_request_cap:
                raise BudgetExceededError("daily_request_cap_reached", "Daily request cap reached.")
            if campaign_id is not None:
                self._check_campaign(provider, campaign_id, cost, limits)

        usage = ApiUsage(
            provider=provider,
            operation=operation,
            sku=sku,
            campaign_id=campaign_id,
            units=1,
            outcome=UsageOutcome.RESERVED,
            cost_milliminor=cost,
            estimated_cost_minor=-(-cost // 1000),
            currency=limits.currency,
            occurred_at=self.now,
        )
        self.db.add(usage)
        self.db.commit()
        summary = self.summary(provider)
        if summary.warning:
            log.warning(
                "provider_budget_warning",
                provider=provider,
                budget_ratio=summary.budget_ratio,
                cap_ratio=summary.cap_ratio,
            )
        return usage

    def _check_campaign(
        self, provider: str, campaign_id: uuid.UUID, cost: int, limits: ProviderLimits
    ) -> None:
        campaign = self.db.get(Campaign, campaign_id)
        if campaign is None:
            raise ServiceError("campaign_not_found", "Campaign not found.", status_code=404)
        total = self._window(provider, datetime(1970, 1, 1, tzinfo=UTC), campaign_id)
        if not limits.per_campaign_request_cap or total.requests >= limits.per_campaign_request_cap:
            raise BudgetExceededError(
                "campaign_request_cap_reached", "Campaign request cap reached."
            )
        if campaign.daily_budget_minor <= 0:
            raise BudgetExceededError(
                "campaign_budget_not_configured", "Campaign daily budget is 0."
            )
        today = self._window(provider, day_start(self.now), campaign_id)
        if today.cost_milliminor + cost > campaign.daily_budget_minor * 1000:
            raise BudgetExceededError("campaign_budget_exhausted", "Campaign daily budget reached.")

    def finish(
        self, usage: ApiUsage, *, success: bool, provider_request_id: str | None = None
    ) -> None:
        usage.outcome = UsageOutcome.SUCCESS if success else UsageOutcome.ERROR
        usage.provider_request_id = provider_request_id
        if not success:  # failed requests are not billed by the provider
            usage.cost_milliminor = 0
            usage.estimated_cost_minor = 0
        self.db.commit()

    def summary(self, provider: str) -> UsageSummary:
        limits = limits_for(provider, self.settings)
        today = self._window(provider, day_start(self.now))
        month_start = day_start(self.now).replace(day=1)
        month = self._window(provider, month_start)
        budget_ratio = (
            today.cost_milliminor / (limits.daily_budget_minor * 1000)
            if limits.daily_budget_minor
            else None
        )
        cap_ratio = today.requests / limits.daily_request_cap if limits.daily_request_cap else None
        return UsageSummary(
            provider=provider,
            currency=limits.currency,
            today=today,
            month=month,
            daily_budget_minor=limits.daily_budget_minor,
            daily_request_cap=limits.daily_request_cap,
            budget_ratio=budget_ratio,
            cap_ratio=cap_ratio,
        )

    def recent_days(self, provider: str, days: int = 14) -> list[tuple[str, UsageWindow]]:
        start = day_start(self.now) - timedelta(days=days - 1)
        out = []
        for i in range(days):
            d0 = start + timedelta(days=i)
            stmt = select(func.count(), func.coalesce(func.sum(ApiUsage.cost_milliminor), 0)).where(
                ApiUsage.provider == provider,
                ApiUsage.occurred_at >= d0,
                ApiUsage.occurred_at < d0 + timedelta(days=1),
                ApiUsage.outcome != UsageOutcome.ERROR,
            )
            count, cost = self.db.execute(stmt).one()
            out.append((d0.date().isoformat(), UsageWindow(int(count), int(cost))))
        return out
