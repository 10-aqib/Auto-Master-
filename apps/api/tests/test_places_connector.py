"""Field masks, SKUs and the Google Places connector (via a mock HTTP transport: no network)."""

from __future__ import annotations

import json

import httpx
import pytest
import structlog

from webforge_api.logging_config import configure_logging
from webforge_api.sources.places import (
    GooglePlacesConnector,
    MockPlacesConnector,
    PlacesError,
    TextSearchRequest,
    validate_place_id,
)
from webforge_api.sources.places_fields import (
    DETAILS_REFRESH_ID,
    DETAILS_WEBSITE,
    SEARCH_IDS,
    SEARCH_PREVIEW,
    Endpoint,
    FieldMask,
    FieldMaskError,
)

API_KEY = "AIzaTESTKEY-not-real-0123456789abcdef"
PLACE_ID = "ChIJTestPlaceId0123456789"


def test_field_mask_required_and_no_wildcard() -> None:
    with pytest.raises(FieldMaskError, match="required"):
        FieldMask(Endpoint.TEXT_SEARCH, ())
    for bad in ("*", "places.*", "places.reviews", "places.photos", "places.rating", "websiteUri"):
        with pytest.raises(FieldMaskError):
            FieldMask(Endpoint.TEXT_SEARCH, (bad,))
    with pytest.raises(FieldMaskError):
        FieldMask(Endpoint.PLACE_DETAILS, ("places.id",))
    with pytest.raises(FieldMaskError, match="Duplicate"):
        FieldMask(Endpoint.PLACE_DETAILS, ("id", "id"))


def test_skus_follow_highest_tier() -> None:
    assert SEARCH_IDS.sku == "TEXT_SEARCH_IDS_ONLY"
    assert SEARCH_PREVIEW.sku == "TEXT_SEARCH_PRO"
    assert DETAILS_WEBSITE.sku == "PLACE_DETAILS_ENTERPRISE"
    assert DETAILS_REFRESH_ID.sku == "PLACE_DETAILS_IDS_ONLY"
    assert SEARCH_PREVIEW.header == (
        "places.id,places.displayName,places.formattedAddress,places.businessStatus,"
        "places.googleMapsUri,nextPageToken"
    )


class Recorder:
    def __init__(self, responses: list[httpx.Response]) -> None:
        self.responses = responses
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self.responses.pop(0)


def _connector(*responses: httpx.Response) -> tuple[GooglePlacesConnector, Recorder]:
    rec = Recorder(list(responses))
    return GooglePlacesConnector(API_KEY, transport=httpx.MockTransport(rec)), rec


def test_text_search_request_shape() -> None:
    body = {
        "places": [
            {"id": PLACE_ID, "displayName": {"text": "Fixture Bakery", "languageCode": "en"},
             "formattedAddress": "1 Test St", "businessStatus": "OPERATIONAL",
             "googleMapsUri": "https://maps.google.com/?cid=1"},
            {"displayName": {"text": "no id: dropped"}},
        ],
        "nextPageToken": "tok",
    }  # fmt: skip
    conn, rec = _connector(httpx.Response(200, json=body))
    page = conn.search_text(
        TextSearchRequest("bakeries in Lahore", region_code="PK", page_size=50), SEARCH_PREVIEW
    )
    req = rec.requests[0]
    assert req.method == "POST"
    assert str(req.url) == "https://places.googleapis.com/v1/places:searchText"
    assert req.headers["X-Goog-FieldMask"] == SEARCH_PREVIEW.header
    assert req.headers["X-Goog-Api-Key"] == API_KEY
    assert API_KEY not in str(req.url)
    sent = json.loads(req.content)
    assert sent == {
        "textQuery": "bakeries in Lahore",
        "languageCode": "en",
        "pageSize": 20,
        "regionCode": "PK",
    }
    assert [p.place_id for p in page.places] == [PLACE_ID]
    assert page.places[0].display_name == "Fixture Bakery"
    assert page.next_page_token == "tok"


def test_place_details_and_not_found() -> None:
    conn, rec = _connector(
        httpx.Response(200, json={"id": PLACE_ID, "websiteUri": "https://bakery.example.test/"}),
        httpx.Response(404, json={"error": {"status": "NOT_FOUND"}}),
    )
    place = conn.place_details(PLACE_ID, DETAILS_WEBSITE)
    assert place is not None and place.website_uri == "https://bakery.example.test/"
    assert rec.requests[0].headers["X-Goog-FieldMask"] == "id,displayName,websiteUri,googleMapsUri"
    assert conn.place_details(PLACE_ID, DETAILS_WEBSITE) is None


@pytest.mark.parametrize(
    ("status", "code", "retryable"),
    [(400, "provider_bad_request", False), (403, "provider_forbidden", False),
     (429, "provider_rate_limited", True), (503, "provider_unavailable", True)],
)  # fmt: skip
def test_provider_errors_mapped(status: int, code: str, retryable: bool) -> None:
    conn, _ = _connector(httpx.Response(status, json={"error": {"message": f"key={API_KEY}"}}))
    with pytest.raises(PlacesError) as info:
        conn.search_text(TextSearchRequest("x y z"), SEARCH_IDS)
    assert info.value.code == code
    assert info.value.retryable is retryable
    assert API_KEY not in str(info.value)


def test_wrong_mask_for_endpoint_rejected() -> None:
    conn, rec = _connector()
    with pytest.raises(PlacesError):
        conn.place_details(PLACE_ID, SEARCH_IDS)
    with pytest.raises(PlacesError):
        conn.search_text(TextSearchRequest("abc"), DETAILS_WEBSITE)
    assert rec.requests == []


@pytest.mark.parametrize("bad", ["../../admin", "short", "a b c d e f g h", "x" * 301, "id/../x"])
def test_place_id_validation(bad: str) -> None:
    with pytest.raises(PlacesError):
        validate_place_id(bad)


def test_missing_api_key_refused() -> None:
    with pytest.raises(PlacesError, match="not set"):
        GooglePlacesConnector("")


def test_api_key_never_logged(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging("DEBUG", json_output=True)
    conn, _ = _connector(httpx.Response(200, json={"places": []}))
    conn.search_text(TextSearchRequest("bakeries"), SEARCH_IDS)
    structlog.get_logger().info("done")
    assert API_KEY not in capsys.readouterr().out


def test_mock_connector_deterministic_and_respects_mask() -> None:
    mock = MockPlacesConnector()
    a = mock.search_text(TextSearchRequest("Bakeries Lahore", page_size=3), SEARCH_PREVIEW)
    b = mock.search_text(TextSearchRequest("bakeries lahore", page_size=3), SEARCH_PREVIEW)
    assert [p.place_id for p in a.places] == [p.place_id for p in b.places]
    assert len(a.places) == 3 and a.places[0].website_uri is None
    ids_only = mock.search_text(TextSearchRequest("Bakeries Lahore"), SEARCH_IDS)
    assert ids_only.places[0].display_name is None
    details = mock.place_details(a.places[0].place_id, DETAILS_WEBSITE)
    assert (
        details is not None
        and details.website_uri
        and details.website_uri.endswith(".example.test/")
    )
    assert mock.place_details("ChIJunknown-id-000", DETAILS_WEBSITE) is None
