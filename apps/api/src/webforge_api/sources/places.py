"""Places connectors: Google Places API (New) over HTTPS, and a deterministic mock.

Everything a connector returns except the Place ID is Google Maps Content: callers must treat
it as transient (show with attribution, never persist).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from webforge_api.logging_config import get_logger
from webforge_api.sources.places_fields import Endpoint, FieldMask

log = get_logger(__name__)

PLACES_BASE_URL = "https://places.googleapis.com/v1"
PLACE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{10,300}$")
MAX_PAGE_SIZE = 20


class PlacesError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class TextSearchRequest:
    text_query: str
    region_code: str | None = None
    language_code: str = "en"
    page_size: int = 10
    page_token: str | None = None


@dataclass(frozen=True)
class PlaceRecord:
    """Transient. Only `place_id` may be stored."""

    place_id: str
    display_name: str | None = None
    formatted_address: str | None = None
    business_status: str | None = None
    google_maps_uri: str | None = None
    website_uri: str | None = None


@dataclass(frozen=True)
class TextSearchPage:
    places: list[PlaceRecord]
    next_page_token: str | None
    provider_request_id: str | None = None


class PlacesConnector(Protocol):
    source_key: str
    is_mock: bool

    def search_text(self, request: TextSearchRequest, mask: FieldMask) -> TextSearchPage: ...

    def place_details(self, place_id: str, mask: FieldMask) -> PlaceRecord | None:
        """None when the Place ID is obsolete (NOT_FOUND)."""
        ...


def validate_place_id(place_id: str) -> str:
    if not PLACE_ID_RE.fullmatch(place_id):
        raise PlacesError("invalid_place_id", "Place ID has an invalid format.")
    return place_id


def _record(data: dict[str, Any]) -> PlaceRecord:
    name = data.get("displayName")
    return PlaceRecord(
        place_id=str(data.get("id", "")),
        display_name=name.get("text") if isinstance(name, dict) else None,
        formatted_address=data.get("formattedAddress"),
        business_status=data.get("businessStatus"),
        google_maps_uri=data.get("googleMapsUri"),
        website_uri=data.get("websiteUri"),
    )


class GooglePlacesConnector:
    source_key = "google_places"
    is_mock = False

    def __init__(
        self, api_key: str, *, transport: httpx.BaseTransport | None = None, timeout: float = 10.0
    ) -> None:
        if not api_key:
            raise PlacesError("not_configured", "GOOGLE_MAPS_API_KEY is not set.")
        self._client = httpx.Client(
            base_url=PLACES_BASE_URL,
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
            # The key travels only in this header: never in URLs, logs or responses.
            headers={"X-Goog-Api-Key": api_key, "Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def _call(self, method: str, path: str, mask: FieldMask, **kwargs: Any) -> httpx.Response:
        try:
            response = self._client.request(
                method, path, headers={"X-Goog-FieldMask": mask.header}, **kwargs
            )
        except httpx.TimeoutException as exc:
            raise PlacesError(
                "provider_timeout", "Google Places timed out.", retryable=True
            ) from exc
        except httpx.HTTPError as exc:
            raise PlacesError(
                "provider_unreachable", "Google Places is unreachable.", retryable=True
            ) from exc
        log.info(
            "places_request",
            path=path.split("/")[1][:20],
            status=response.status_code,
            sku=mask.sku,
        )
        return response

    @staticmethod
    def _raise_for(response: httpx.Response) -> None:
        status = response.status_code
        if status == 429:
            raise PlacesError(
                "provider_rate_limited", "Google Places quota exceeded.", retryable=True
            )
        if status >= 500:
            raise PlacesError(
                "provider_unavailable", "Google Places is unavailable.", retryable=True
            )
        if status in (401, 403):
            raise PlacesError(
                "provider_forbidden", "Google Places rejected the API key or project."
            )
        if status >= 400:
            raise PlacesError(
                "provider_bad_request", f"Google Places rejected the request ({status})."
            )

    def search_text(self, request: TextSearchRequest, mask: FieldMask) -> TextSearchPage:
        if mask.endpoint is not Endpoint.TEXT_SEARCH:
            raise PlacesError("invalid_mask", "Text Search requires a Text Search field mask.")
        body: dict[str, Any] = {
            "textQuery": request.text_query,
            "languageCode": request.language_code,
            "pageSize": max(1, min(request.page_size, MAX_PAGE_SIZE)),
        }
        if request.region_code:
            body["regionCode"] = request.region_code
        if request.page_token:
            body["pageToken"] = request.page_token
        response = self._call("POST", "/places:searchText", mask, json=body)
        self._raise_for(response)
        data = response.json()
        return TextSearchPage(
            places=[_record(p) for p in data.get("places", []) if p.get("id")],
            next_page_token=data.get("nextPageToken"),
        )

    def place_details(self, place_id: str, mask: FieldMask) -> PlaceRecord | None:
        if mask.endpoint is not Endpoint.PLACE_DETAILS:
            raise PlacesError("invalid_mask", "Place Details requires a Place Details field mask.")
        response = self._call("GET", f"/places/{validate_place_id(place_id)}", mask)
        if response.status_code == 404:
            return None
        self._raise_for(response)
        return _record(response.json())


class MockPlacesConnector:
    """Deterministic fake places for development and CI. Makes no network calls."""

    source_key = "mock_places"
    is_mock = True

    @staticmethod
    def _make(seed: str, index: int, mask_fields: tuple[str, ...]) -> PlaceRecord:
        fields = {f.removeprefix("places.") for f in mask_fields}
        place_id = f"mock_{seed}_{index:02d}"
        return PlaceRecord(
            place_id=place_id,
            display_name=f"Fixture Business {seed[:4].upper()}-{index}"
            if "displayName" in fields
            else None,
            formatted_address=f"{index} Test Street, Example City"
            if "formattedAddress" in fields
            else None,
            business_status="OPERATIONAL" if "businessStatus" in fields else None,
            google_maps_uri=None,
            website_uri=f"https://fixture-{seed}-{index}.example.test/"
            if "websiteUri" in fields
            else None,
        )

    def search_text(self, request: TextSearchRequest, mask: FieldMask) -> TextSearchPage:
        seed = hashlib.sha256(request.text_query.strip().lower().encode()).hexdigest()[:10]
        count = max(1, min(request.page_size, 5))
        return TextSearchPage(
            places=[self._make(seed, i + 1, mask.fields) for i in range(count)],
            next_page_token=None,
        )

    def place_details(self, place_id: str, mask: FieldMask) -> PlaceRecord | None:
        match = re.fullmatch(r"mock_([0-9a-f]{10})_(\d{2})", place_id)
        if not match:
            return None
        return self._make(match.group(1), int(match.group(2)), mask.fields)


class ConnectorFactory:
    """Builds connectors by source key; the Google client is created once and reused."""

    def __init__(self, api_key: str, transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._transport = transport
        self._google: GooglePlacesConnector | None = None

    def __call__(self, key: str) -> PlacesConnector:
        if key == "mock_places":
            return MockPlacesConnector()
        if key == "google_places":
            if self._google is None:
                self._google = GooglePlacesConnector(self._api_key, transport=self._transport)
            return self._google
        raise PlacesError("unsupported_source", "This source has no Places connector.")

    def close(self) -> None:
        if self._google is not None:
            self._google.close()
