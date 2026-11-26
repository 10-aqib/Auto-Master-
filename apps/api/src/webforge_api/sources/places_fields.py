"""Google Places API (New) field masks and billing SKUs.

Checked 2026-11-26 against:
- https://developers.google.com/maps/documentation/places/web-service/choose-fields
- https://developers.google.com/maps/documentation/places/web-service/text-search
- https://developers.google.com/maps/documentation/places/web-service/place-details
- https://developers.google.com/maps/documentation/places/web-service/usage-and-billing
A request is billed at the highest SKU among its fields. `*` must not be used in production.
Only the fields this application needs are allowed; adding one requires a code change + review.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum


class Tier(IntEnum):
    IDS_ONLY = 0
    ESSENTIALS = 1
    PRO = 2
    ENTERPRISE = 3


class Endpoint(StrEnum):
    TEXT_SEARCH = "TEXT_SEARCH"
    PLACE_DETAILS = "PLACE_DETAILS"


# Allowed fields per endpoint with their SKU tier. Anything else is refused.
ALLOWED_FIELDS: dict[Endpoint, dict[str, Tier]] = {
    Endpoint.TEXT_SEARCH: {
        "places.id": Tier.IDS_ONLY,
        "places.name": Tier.IDS_ONLY,
        "nextPageToken": Tier.IDS_ONLY,
        "places.displayName": Tier.PRO,
        "places.formattedAddress": Tier.PRO,
        "places.businessStatus": Tier.PRO,
        "places.googleMapsUri": Tier.PRO,
    },
    Endpoint.PLACE_DETAILS: {
        "id": Tier.IDS_ONLY,
        "name": Tier.IDS_ONLY,
        "displayName": Tier.PRO,
        "businessStatus": Tier.PRO,
        "googleMapsUri": Tier.PRO,
        "websiteUri": Tier.ENTERPRISE,
    },
}


class FieldMaskError(ValueError):
    pass


@dataclass(frozen=True)
class FieldMask:
    endpoint: Endpoint
    fields: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.fields:
            raise FieldMaskError("A field mask is required (Google has no default field list).")
        allowed = ALLOWED_FIELDS[self.endpoint]
        for f in self.fields:
            if "*" in f:
                raise FieldMaskError("Wildcard field masks are not allowed.")
            if f not in allowed:
                raise FieldMaskError(f"Field {f!r} is not allowed for {self.endpoint.value}.")
        if len(set(self.fields)) != len(self.fields):
            raise FieldMaskError("Duplicate fields in field mask.")

    @property
    def header(self) -> str:
        return ",".join(self.fields)

    @property
    def tier(self) -> Tier:
        return max(ALLOWED_FIELDS[self.endpoint][f] for f in self.fields)

    @property
    def sku(self) -> str:
        return f"{self.endpoint.value}_{self.tier.name}"


# The masks the application actually uses (one per purpose, minimal by design).
SEARCH_IDS = FieldMask(Endpoint.TEXT_SEARCH, ("places.id", "nextPageToken"))
SEARCH_PREVIEW = FieldMask(
    Endpoint.TEXT_SEARCH,
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.businessStatus",
        "places.googleMapsUri",
        "nextPageToken",
    ),
)
DETAILS_WEBSITE = FieldMask(
    Endpoint.PLACE_DETAILS, ("id", "displayName", "websiteUri", "googleMapsUri")
)
DETAILS_REFRESH_ID = FieldMask(Endpoint.PLACE_DETAILS, ("id",))

KNOWN_SKUS = tuple(f"{e.value}_{t.name}" for e in Endpoint for t in Tier)
