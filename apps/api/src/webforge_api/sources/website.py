"""Independent verification of a business's official website.

Only the business's own public pages are used as evidence. robots.txt is honoured (RFC 9309:
4xx = allowed, 5xx/unreachable = treat as disallowed). No forms, logins or CAPTCHAs, and a
candidate URL is never derived from a business name: it must come from a source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any
from urllib import robotparser
from urllib.parse import urlsplit, urlunsplit

from webforge_api.models.enums import DomainVerificationStatus
from webforge_api.net.safe_fetch import FetchBlockedError, FetchFailedError, SafeFetcher
from webforge_api.net.urls import InvalidUrlError, normalize_url, same_site, site_domain
from webforge_api.sources.names import similarity, title_segments

VERIFY_THRESHOLD = 0.85
WEAK_THRESHOLD = 0.5
METHOD = "official_website_name_match"
ORG_TYPES = {
    "organization", "localbusiness", "store", "restaurant", "corporation", "professionalservice",
    "medicalbusiness", "dentist", "legalservice", "homeandconstructionbusiness",
    "foodestablishment",
    "automotivebusiness", "healthandbeautybusiness", "lodgingbusiness", "financialservice",
    "educationalorganization", "sportsactivitylocation", "bakery", "cafeorcoffeeshop",
}  # fmt: skip
PARKED_MARKERS = (
    "this domain is for sale", "buy this domain", "domain is parked", "parked free",
    "this domain may be for sale", "sedoparking", "parkingcrew", "bodis.com", "dan.com",
    "hugedomains", "afternic", "domain name is for sale", "godaddy.com/forsale",
)  # fmt: skip


@dataclass
class PageSignals:
    title: str | None = None
    og_site_name: str | None = None
    application_name: str | None = None
    h1: str | None = None
    jsonld_names: list[str] = field(default_factory=list)
    jsonld_urls: list[str] = field(default_factory=list)
    text_sample: str = ""


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.signals = PageSignals()
        self._in: str | None = None
        self._buf: list[str] = []
        self._text: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("style", "noscript"):
            self._skip += 1
        if tag == "meta":
            key = (a.get("property") or a.get("name") or "").lower()
            content = a.get("content", "").strip()[:300]
            if key == "og:site_name" and content:
                self.signals.og_site_name = content
            elif key == "application-name" and content:
                self.signals.application_name = content
        elif tag == "title" or (tag == "h1" and self.signals.h1 is None):
            self._in, self._buf = tag, []
        elif tag == "script" and a.get("type", "").lower() == "application/ld+json":
            self._in, self._buf = "jsonld", []
        elif tag == "script":
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "noscript") and self._skip:
            self._skip -= 1
        if tag == "script" and self._in != "jsonld" and self._skip:
            self._skip -= 1
            return
        if self._in == "title" and tag == "title":
            self.signals.title = " ".join("".join(self._buf).split())[:300] or None
            self._in = None
        elif self._in == "h1" and tag == "h1":
            self.signals.h1 = " ".join("".join(self._buf).split())[:300] or None
            self._in = None
        elif self._in == "jsonld" and tag == "script":
            self._parse_jsonld("".join(self._buf))
            self._in = None

    def handle_data(self, data: str) -> None:
        if self._in:
            self._buf.append(data)
        if not self._skip and self._in != "jsonld" and sum(map(len, self._text)) < 5000:
            self._text.append(data)

    def _parse_jsonld(self, raw: str) -> None:
        try:
            data: Any = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return
        stack = [data]
        seen = 0
        while stack and seen < 200:
            item = stack.pop()
            seen += 1
            if isinstance(item, list):
                stack.extend(item)
            elif isinstance(item, dict):
                types = item.get("@type", [])
                types = [types] if isinstance(types, str) else types
                if any(isinstance(t, str) and t.lower() in ORG_TYPES for t in types):
                    if isinstance(item.get("name"), str):
                        self.signals.jsonld_names.append(item["name"].strip()[:300])
                    if isinstance(item.get("url"), str):
                        self.signals.jsonld_urls.append(item["url"].strip()[:500])
                stack.extend(
                    v for k, v in item.items() if k == "@graph" or isinstance(v, dict | list)
                )

    def finish(self) -> PageSignals:
        self.close()
        self.signals.text_sample = " ".join(" ".join(self._text).split())[:2000]
        return self.signals


def extract_signals(html_text: str) -> PageSignals:
    parser = _Extractor()
    parser.feed(html_text[:2_000_000])
    return parser.finish()


def looks_parked(signals: PageSignals) -> bool:
    haystack = " ".join(filter(None, [signals.title, signals.text_sample])).lower()
    return any(marker in haystack for marker in PARKED_MARKERS)


@dataclass
class VerificationOutcome:
    status: DomainVerificationStatus
    method: str
    reason_codes: list[str]
    candidate_url: str
    final_url: str | None = None
    domain: str | None = None
    confidence: float | None = None
    declared_name: str | None = None  # the site's own words; never Maps content
    evidence: dict[str, Any] = field(default_factory=dict)


def _hold(url: str, *codes: str, **kw: Any) -> VerificationOutcome:
    return VerificationOutcome(DomainVerificationStatus.HOLD, METHOD, list(codes), url, **kw)


def _reject(url: str, *codes: str, **kw: Any) -> VerificationOutcome:
    return VerificationOutcome(DomainVerificationStatus.REJECTED, METHOD, list(codes), url, **kw)


class WebsiteVerifier:
    def __init__(self, fetcher: SafeFetcher, user_agent: str) -> None:
        self.fetcher = fetcher
        self.user_agent = user_agent

    def _robots_allows(self, url: str) -> bool | None:
        """True/False per robots.txt; None when robots.txt could not be evaluated.
        Raises FetchBlockedError when the site is not a safe target, and FetchFailedError when
        the site cannot be reached at all."""
        parts = urlsplit(url)
        robots_url = urlunsplit((parts.scheme, parts.netloc, "/robots.txt", "", ""))
        try:
            result = self.fetcher.get(robots_url, accept="text/plain")
        except FetchFailedError as exc:
            if exc.code in ("dns_failed", "connect_failed"):
                raise
            return None
        if 400 <= result.status < 500:
            return True
        if result.status >= 500 or result.status < 200:
            return None
        parser = robotparser.RobotFileParser()
        parser.parse(result.text()[:100_000].splitlines())
        return parser.can_fetch(self.user_agent, url)

    def verify(self, candidate_url: str | None, expected_name: str | None) -> VerificationOutcome:
        if not candidate_url:
            return _hold("", "no_website_listed")
        try:
            url = normalize_url(candidate_url)
        except InvalidUrlError:
            return _reject(candidate_url, "invalid_url")

        try:
            allowed = self._robots_allows(url)
        except FetchBlockedError as exc:
            return _reject(url, f"blocked_{exc.code}")
        except FetchFailedError as exc:
            return _hold(url, f"unreachable_{exc.code}")
        if allowed is None:
            return _hold(url, "robots_unavailable")
        if not allowed:
            return _hold(url, "robots_disallowed")

        try:
            page = self.fetcher.get(url)
        except FetchBlockedError as exc:
            return _reject(url, f"blocked_{exc.code}")
        except FetchFailedError as exc:
            return _hold(url, f"unreachable_{exc.code}")

        final = page.final_url
        base = {"final_url": final, "domain": site_domain(final)}
        if page.status >= 400:
            return _hold(url, f"http_{page.status}", **base)
        if page.content_type not in ("text/html", "application/xhtml+xml"):
            return _hold(url, "not_html", **base)
        if not same_site(url, final):
            return _hold(url, "redirected_off_site", **base)

        signals = extract_signals(page.text())
        if looks_parked(signals):
            return _reject(url, "parked_domain", **base)
        if any(not same_site(final, u) for u in signals.jsonld_urls if u.startswith("http")):
            return _hold(url, "structured_data_points_elsewhere", **base)
        if not expected_name:
            return _hold(url, "no_expected_name", **base)

        candidates: list[tuple[str, float, str]] = []  # (signal, weight, text)
        candidates += [("jsonld_name", 0.95, n) for n in signals.jsonld_names]
        if signals.og_site_name:
            candidates.append(("og_site_name", 0.9, signals.og_site_name))
        if signals.application_name:
            candidates.append(("application_name", 0.85, signals.application_name))
        if signals.title:
            candidates += [("title", 0.8, s) for s in title_segments(signals.title)]
        if signals.h1:
            candidates.append(("h1", 0.75, signals.h1))

        scored = sorted(
            (
                (similarity(expected_name, text), weight, sig, text)
                for sig, weight, text in candidates
            ),
            key=lambda c: (c[0], c[1]),
            reverse=True,
        )
        evidence = {
            "signals_checked": [sig for sig, _, _ in candidates],
            "pages_fetched": 1,
            "robots_txt": "allowed",
            "redirects": len(page.redirects),
        }
        if not scored:
            return _hold(url, "no_name_signals", evidence=evidence, **base)
        best_score, weight, signal, text = scored[0]
        evidence |= {
            "matched_signal": signal,
            "match_score": round(best_score, 3),
            "excerpt": text[:200],
        }
        if best_score >= VERIFY_THRESHOLD:
            return VerificationOutcome(
                DomainVerificationStatus.VERIFIED,
                METHOD,
                [],
                url,
                confidence=round(min(1.0, weight * best_score), 3),
                declared_name=text,
                evidence=evidence,
                **base,
            )
        if best_score >= WEAK_THRESHOLD:
            return _hold(url, "weak_name_match", evidence=evidence, **base)
        return _reject(url, "name_mismatch", evidence=evidence, **base)
