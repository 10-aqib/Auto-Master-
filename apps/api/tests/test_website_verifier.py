"""Independent official-website verification against local fake sites."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from tests.fixtures_http import FakeSite, fake_site, html, redirect
from webforge_api.models.enums import DomainVerificationStatus as S
from webforge_api.net.safe_fetch import FetchPolicy, SafeFetcher
from webforge_api.sources.names import normalize_name, similarity
from webforge_api.sources.website import VerificationOutcome, WebsiteVerifier, extract_signals

HOST = "bakery.example.test"
UA = "WEBFORGE-AI-Verifier/test"


def policy_for(site: FakeSite) -> FetchPolicy:
    dns = {
        HOST: ["127.0.0.1"],
        f"www.{HOST}": ["127.0.0.1"],
        "elsewhere.example.test": ["127.0.0.1"],
    }

    def resolver(host: str, _port: int) -> list[str]:
        if host not in dns:
            raise OSError("NXDOMAIN")
        return dns[host]

    return FetchPolicy(
        allowed_ports=frozenset({site.port}),
        address_allowed=lambda ip: ip == "127.0.0.1",
        resolver=resolver,
        user_agent=UA,
        total_timeout=5,
    )


@pytest.fixture
def site() -> Iterator[FakeSite]:
    with fake_site() as s:
        yield s


def verify(site: FakeSite, name: str | None, path: str = "/") -> VerificationOutcome:
    v = WebsiteVerifier(SafeFetcher(policy_for(site)), UA)
    return v.verify(f"http://{HOST}:{site.port}{path}", name)


JSONLD = """<script type="application/ld+json">
{"@context":"https://schema.org","@type":"Bakery","name":"Lahore Fixture Bakery","url":"http://bakery.example.test/"}
</script>"""


def test_structured_data_name_match_verifies(site: FakeSite) -> None:
    site.page(
        "/",
        f"<html><head><title>Home</title>{JSONLD}</head><body><h1>Fresh bread</h1></body></html>",
    )
    out = verify(site, "Lahore Fixture Bakery (Pvt) Ltd")
    assert out.status is S.VERIFIED
    assert out.declared_name == "Lahore Fixture Bakery"
    assert out.domain == HOST
    assert out.evidence["matched_signal"] == "jsonld_name"
    assert out.confidence is not None and out.confidence >= 0.85


def test_title_segment_match_verifies_with_lower_confidence(site: FakeSite) -> None:
    site.page("/", "<title>Welcome | Lahore Fixture Bakery</title>")
    out = verify(site, "Lahore Fixture Bakery")
    assert out.status is S.VERIFIED
    assert out.evidence["matched_signal"] == "title"
    assert out.confidence is not None and out.confidence < 0.85


def test_weak_match_held(site: FakeSite) -> None:
    site.page("/", '<meta property="og:site_name" content="Lahore Fixture Sweets">')
    out = verify(site, "Lahore Fixture Bakery")
    assert out.status is S.HOLD
    assert out.reason_codes == ["weak_name_match"]


def test_unrelated_site_rejected(site: FakeSite) -> None:
    site.page("/", "<title>Quantum Plumbing Solutions</title>")
    out = verify(site, "Lahore Fixture Bakery")
    assert out.status is S.REJECTED
    assert out.reason_codes == ["name_mismatch"]


def test_parked_domain_rejected(site: FakeSite) -> None:
    site.page(
        "/",
        "<title>bakery.example.test</title><p>This domain is for sale! Buy this domain today.</p>",
    )
    out = verify(site, "Lahore Fixture Bakery")
    assert out.reason_codes == ["parked_domain"]


def test_robots_disallow_respected(site: FakeSite) -> None:
    site.route(
        "/robots.txt",
        lambda _h: (200, {"Content-Type": "text/plain"}, b"User-agent: *\nDisallow: /\n"),
    )
    site.page("/", "<title>Lahore Fixture Bakery</title>")
    out = verify(site, "Lahore Fixture Bakery")
    assert out.reason_codes == ["robots_disallowed"]
    assert [p for p, _ in site.requests] == ["/robots.txt"]  # homepage never fetched


def test_robots_server_error_treated_as_disallow(site: FakeSite) -> None:
    site.route("/robots.txt", lambda _h: (503, {}, b""))
    assert verify(site, "X Y").reason_codes == ["robots_unavailable"]


def test_off_site_redirect_held(site: FakeSite) -> None:
    site.route("/", lambda _h: redirect(f"http://elsewhere.example.test:{site.port}/landing"))
    site.page("/landing", "<title>Lahore Fixture Bakery</title>")
    assert verify(site, "Lahore Fixture Bakery").reason_codes == ["redirected_off_site"]


def test_www_redirect_still_same_site(site: FakeSite) -> None:
    site.route("/", lambda _h: redirect(f"http://www.{HOST}:{site.port}/home"))
    site.page("/home", "<title>Lahore Fixture Bakery</title>")
    out = verify(site, "Lahore Fixture Bakery")
    assert out.status is S.VERIFIED
    assert out.domain == HOST


def test_structured_data_pointing_elsewhere_held(site: FakeSite) -> None:
    site.page(
        "/",
        '<script type="application/ld+json">{"@type":"Organization","name":"Lahore Fixture Bakery",'
        '"url":"https://another-company.example/"}</script>',
    )
    assert verify(site, "Lahore Fixture Bakery").reason_codes == [
        "structured_data_points_elsewhere"
    ]


def test_no_website_and_no_expected_name(site: FakeSite) -> None:
    v = WebsiteVerifier(SafeFetcher(policy_for(site)), UA)
    assert v.verify(None, "Anything").reason_codes == ["no_website_listed"]
    assert site.requests == []  # no domain is ever guessed from the name
    site.page("/", "<title>Lahore Fixture Bakery</title>")
    assert verify(site, None).reason_codes == ["no_expected_name"]


def test_private_address_rejected_by_default_policy() -> None:
    v = WebsiteVerifier(SafeFetcher(FetchPolicy()), UA)
    out = v.verify("http://169.254.169.254/latest/meta-data/", "Metadata")
    assert out.status is S.REJECTED
    assert out.reason_codes == ["blocked_blocked_address"]


def test_http_error_and_non_html_held(site: FakeSite) -> None:
    site.route("/", lambda _h: html("gone", 410))
    assert verify(site, "A B").reason_codes == ["http_410"]
    site.route("/", lambda _h: (200, {"Content-Type": "application/pdf"}, b"%PDF"))
    assert verify(site, "A B").reason_codes == ["not_html"]


def test_signal_extraction_ignores_scripts_and_handles_graph() -> None:
    doc = """<html><head><title>Shop</title>
    <script>var name = "Fake Name From JS";</script>
    <script type="application/ld+json">{"@graph":[{"@type":"WebSite","name":"Site"},
      {"@type":["LocalBusiness"],"name":"Graph Business","url":"https://graph.example/"}]}</script>
    <script type="application/ld+json">{ invalid json</script>
    </head><body><h1>Hello</h1><h1>Second</h1></body></html>"""
    s = extract_signals(doc)
    assert s.jsonld_names == ["Graph Business"]
    assert s.h1 == "Hello"
    assert "Fake Name From JS" not in s.text_sample


@pytest.mark.parametrize(
    ("a", "b", "low", "high"),
    [
        ("Lahore Fixture Bakery (Pvt) Ltd", "Lahore Fixture Bakery", 1.0, 1.0),
        ("Café Zürich & Co", "cafe zurich", 1.0, 1.0),
        ("Smile Dental Clinic", "Smile Dental", 0.85, 1.0),
        ("Dental", "Smile Dental Clinic Lahore", 0.0, 0.4),
        ("Bakery", "Acme Bakery", 0.0, 0.5),
        ("Acme Plumbing", "Zenith Bakery", 0.0, 0.0),
    ],
)
def test_name_similarity(a: str, b: str, low: float, high: float) -> None:
    assert low <= similarity(a, b) <= high
    assert normalize_name("The ACME, Ltd.") == "acme"


def test_unresolvable_site_reported_unreachable(site: FakeSite) -> None:
    v = WebsiteVerifier(SafeFetcher(policy_for(site)), UA)
    out = v.verify(f"http://nowhere.example.test:{site.port}/", "Anything")
    assert out.status is S.HOLD
    assert out.reason_codes == ["unreachable_dns_failed"]
