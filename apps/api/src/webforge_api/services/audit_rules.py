"""Deterministic audit rules: browser evidence -> findings + category scores (rules v1).

Each finding states what was observed, where, at which viewport, and how to reproduce it.
Categories without usable evidence are NOT_TESTED (score null), never guessed. Branding is
subjective and is not scored automatically in v1.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Any

RULES_VERSION = "1"
CATEGORIES = {
    "visual_structure": 20,
    "mobile_usability": 20,
    "navigation": 15,
    "branding": 10,
    "conversion": 15,
    "content_trust": 10,
    "technical": 10,
}
SLOW_LOAD_MS = 8000


@dataclass
class Finding:
    code: str
    category: str
    severity: str  # INFO | LOW | MEDIUM | HIGH
    title: str
    description: str
    observed_url: str
    viewport: str
    evidence: dict[str, Any]
    confidence: float
    reproduction: list[str]
    deduction: int


@dataclass
class AuditOutcome:
    status: str  # SUCCEEDED | FAILED
    error_summary: str | None
    findings: list[Finding] = field(default_factory=list)
    categories: dict[str, dict[str, Any]] = field(default_factory=dict)
    strengths: list[str] = field(default_factory=list)
    caveats: list[str] = field(default_factory=list)
    overall: float | None = None


def _vp(name: str, cap: dict[str, Any]) -> str:
    m = cap.get("metrics") or {}
    v = m.get("viewport") or {}
    return f"{name} {v.get('width', '?')}x{v.get('height', '?')}"


def evaluate(result: dict[str, Any]) -> AuditOutcome:
    desktop: dict[str, Any] = result.get("desktop") or {}
    mobile: dict[str, Any] = result.get("mobile") or {}
    pages: list[dict[str, Any]] = result.get("pages") or []
    d, m = desktop.get("metrics"), mobile.get("metrics")
    url = desktop.get("final_url") or result.get("requested_url", "")

    status = desktop.get("status")
    if d is None or status is None:
        return AuditOutcome(
            "FAILED", f"Homepage could not be loaded: {desktop.get('error') or 'no response'}"
        )
    if status in (401, 403, 429, 503):
        return AuditOutcome(
            "FAILED", f"Site refused automated access (HTTP {status}); nothing was scored."
        )
    if status >= 400:
        return AuditOutcome("FAILED", f"Homepage returned HTTP {status}; nothing was scored.")

    out = AuditOutcome("SUCCEEDED", None)
    tested: dict[str, bool] = {c: False for c in CATEGORIES}
    deductions: dict[str, int] = {c: 0 for c in CATEGORIES}

    def add(f: Finding) -> None:
        out.findings.append(f)
        deductions[f.category] += f.deduction

    dvp = _vp("desktop", desktop)
    # ---- visual structure (desktop)
    tested["visual_structure"] = True
    if d["h1_count"] == 0:
        add(Finding("MISSING_H1", "visual_structure", "MEDIUM", "No main heading",
                    "The homepage has no visible H1 heading, so the page's main topic is not clearly signposted.",
                    url, dvp, {"headings": d["headings"][:5]}, 0.95, ["Open the homepage", "Inspect headings"], 25))  # fmt: skip
    elif d["h1_count"] > 1:
        add(Finding("MULTIPLE_H1", "visual_structure", "LOW", "Several main headings",
                    f"The homepage has {d['h1_count']} visible H1 headings.", url, dvp,
                    {"h1_count": d["h1_count"]}, 0.9, ["Open the homepage", "Count H1 elements"], 10))  # fmt: skip
    levels = [h["level"] for h in d["headings"]]
    if any(b - a > 1 for a, b in itertools.pairwise(levels)):
        add(Finding("HEADING_LEVEL_SKIP", "visual_structure", "LOW", "Heading levels skip",
                    "Heading levels jump (for example H1 to H3), which weakens the page outline.",
                    url, dvp, {"levels": levels[:20]}, 0.9, ["Inspect heading order"], 10))  # fmt: skip
    if d["images_broken"]:
        add(Finding("BROKEN_IMAGES", "visual_structure", "MEDIUM", "Images fail to load",
                    f"{len(d['images_broken'])} image(s) on the homepage did not load.", url, dvp,
                    {"examples": d["images_broken"][:5]}, 0.95, ["Open the homepage", "Look for empty image areas"], 20))  # fmt: skip

    # ---- mobile usability
    if m is not None:
        tested["mobile_usability"] = True
        mvp = _vp("mobile", mobile)
        if not m.get("viewport_meta"):
            add(Finding("MOBILE_NO_VIEWPORT_META", "mobile_usability", "MEDIUM", "Not set up for mobile screens",
                        "The page has no viewport meta tag, so phones show a zoomed-out desktop layout.",
                        url, mvp, {}, 0.95, ["Open on a 390px-wide phone"], 30))  # fmt: skip
        overflow = m["scroll_width"] - m["client_width"]
        if overflow > 2:
            add(Finding("MOBILE_HORIZONTAL_OVERFLOW", "mobile_usability", "HIGH", "Content wider than the phone screen",
                        f"At {mvp}, the page is {m['scroll_width']}px wide, {overflow}px wider than the screen, so visitors must scroll sideways.",
                        url, mvp, {"scroll_width": m["scroll_width"], "client_width": m["client_width"]}, 0.95,
                        ["Open at 390px width", "Scroll horizontally"], 40))  # fmt: skip
        if m.get("small_text_ratio") is not None and m["small_text_ratio"] > 0.3:
            add(Finding("MOBILE_SMALL_TEXT", "mobile_usability", "MEDIUM", "Much of the text is very small on phones",
                        f"{round(m['small_text_ratio'] * 100)}% of visible text blocks use a font size under 12px at {mvp}.",
                        url, mvp, {"ratio": round(m["small_text_ratio"], 2)}, 0.85, ["Open at 390px width"], 20))  # fmt: skip
        if m.get("small_tap_targets", 0) > 5:
            add(Finding("MOBILE_SMALL_TAP_TARGETS", "mobile_usability", "LOW", "Small tap targets",
                        f"{m['small_tap_targets']} links or buttons are smaller than 32 by 32 px at {mvp}.",
                        url, mvp, {"count": m["small_tap_targets"]}, 0.8, ["Open at 390px width"], 10))  # fmt: skip
        if m.get("h1_lines") and m["h1_lines"] >= 5:
            add(Finding("MOBILE_LONG_HERO_HEADING", "mobile_usability", "LOW", "Main heading wraps to many lines",
                        f"At {mvp}, the main heading wraps to about {m['h1_lines']} lines.",
                        url, mvp, {"lines": m["h1_lines"]}, 0.8, ["Open at 390px width"], 10))  # fmt: skip
        if m["cta_count"] and not m["cta_above_fold"]:
            add(Finding("MOBILE_PRIMARY_ACTION_BELOW_FOLD", "conversion", "MEDIUM", "No action visible on the first phone screen",
                        f"At {mvp}, no call-to-action is visible before scrolling.", url, mvp,
                        {"cta_samples": m["cta_samples"]}, 0.85, ["Open at 390px width", "Do not scroll"], 15))  # fmt: skip
    else:
        out.caveats.append(
            "The mobile view could not be captured; mobile usability was not tested."
        )

    # ---- navigation
    tested["navigation"] = True
    if d["nav_links"] < 2:
        add(Finding("NAVIGATION_MISSING", "navigation", "HIGH", "No clear site navigation",
                    "The homepage has no header or navigation menu with at least two links.", url, dvp,
                    {"nav_links": d["nav_links"]}, 0.85, ["Open the homepage", "Look for a menu"], 50))  # fmt: skip
    broken = [
        p
        for p in pages
        if (p.get("status") or 0) >= 400 or (p.get("error") and not p.get("status"))
    ]
    if broken:
        add(Finding("BROKEN_INTERNAL_LINKS", "navigation", "MEDIUM", "Internal links lead to errors",
                    f"{len(broken)} of {len(pages)} internal pages checked returned an error.", url, dvp,
                    {"examples": [{"url": p["url"], "status": p.get("status")} for p in broken[:5]]}, 0.95,
                    ["Follow the listed links"], min(45, 15 * len(broken))))  # fmt: skip

    # ---- conversion
    tested["conversion"] = True
    if d["cta_count"] == 0:
        add(Finding("NO_CLEAR_CALL_TO_ACTION", "conversion", "HIGH", "No clear next step for visitors",
                    "No button or link invites visitors to book, call, order, request a quote or contact the business.",
                    url, dvp, {}, 0.8, ["Open the homepage", "Look for an action button"], 50))  # fmt: skip
    if d["contact_routes"] == 0:
        add(Finding("NO_CONTACT_ROUTE", "conversion", "MEDIUM", "No direct contact link",
                    "The homepage has no phone, email, WhatsApp or contact-page link.", url, dvp, {}, 0.85,
                    ["Open the homepage", "Look for contact links"], 20))  # fmt: skip

    # ---- content and trust
    tested["content_trust"] = True
    if not d["title"]:
        add(Finding("MISSING_TITLE", "content_trust", "LOW", "No page title", "The homepage has no <title>.", url, dvp, {}, 0.95, ["View page source"], 15))  # fmt: skip
    if not d["meta_description"]:
        add(Finding("MISSING_META_DESCRIPTION", "content_trust", "LOW", "No meta description",
                    "The homepage has no meta description for search results.", url, dvp, {}, 0.95, ["View page source"], 10))  # fmt: skip
    if url.startswith("http://"):
        add(Finding("NOT_HTTPS", "content_trust", "MEDIUM", "Not served over HTTPS",
                    "The homepage was served without HTTPS; browsers mark this as not secure.", url, dvp, {}, 0.95,
                    ["Open the site", "Check the address bar"], 30))  # fmt: skip
    if d["word_count"] < 50:
        add(Finding("VERY_LITTLE_TEXT", "content_trust", "LOW", "Very little text on the homepage",
                    f"The homepage shows about {d['word_count']} words.", url, dvp, {"words": d["word_count"]}, 0.8,
                    ["Open the homepage"], 15))  # fmt: skip

    # ---- technical
    tested["technical"] = True
    if not d["lang"]:
        add(Finding("MISSING_LANG", "technical", "LOW", "Page language not declared",
                    "The <html> element has no lang attribute (screen readers use it).", url, dvp, {}, 0.95, ["View page source"], 10))  # fmt: skip
    if d["images_missing_alt"]:
        add(Finding("IMAGES_MISSING_ALT", "technical", "LOW", "Images without text alternatives",
                    f"{d['images_missing_alt']} visible image(s) have no alt attribute.", url, dvp,
                    {"count": d["images_missing_alt"]}, 0.95, ["Inspect images"], 15))  # fmt: skip
    if desktop.get("console_errors"):
        add(Finding("CONSOLE_ERRORS", "technical", "LOW", "Script errors in the browser console",
                    f"{len(desktop['console_errors'])} console error(s) on load.", url, dvp,
                    {"examples": desktop["console_errors"][:3]}, 0.9, ["Open developer tools", "Reload"], 10))  # fmt: skip
    if (desktop.get("load_ms") or 0) > SLOW_LOAD_MS:
        add(Finding("SLOW_LOAD", "technical", "MEDIUM", "Slow to load in our test",
                    f"The homepage took {desktop['load_ms'] / 1000:.1f}s to finish loading in our test environment (one measurement; network conditions vary).",
                    url, dvp, {"load_ms": desktop["load_ms"]}, 0.6, ["Load the homepage"], 20))  # fmt: skip

    if d.get("consent_overlay"):
        out.caveats.append(
            "A cookie/consent overlay covered part of the page; some checks may be affected."
        )
    if result.get("timed_out"):
        out.caveats.append("The audit hit its time limit; not every internal page was checked.")
    out.caveats.append(
        "Branding is not scored automatically (it is subjective); see the screenshots."
    )

    for cat, weight in CATEGORIES.items():
        if not tested[cat]:
            out.categories[cat] = {"weight": weight, "score": None, "status": "NOT_TESTED"}
        else:
            out.categories[cat] = {
                "weight": weight,
                "score": max(0, 100 - deductions[cat]),
                "status": "TESTED",
            }
    passed_codes = {
        "visual_structure": "Clear heading structure and working images",
        "mobile_usability": "Fits phone screens without sideways scrolling",
        "navigation": "Navigation present and internal links work",
        "conversion": "Clear calls to action and contact routes",
        "content_trust": "Title, description and HTTPS in place",
        "technical": "Language, alt text and console are clean",
    }
    out.strengths = [
        text for cat, text in passed_codes.items() if out.categories[cat]["score"] == 100
    ]
    scored = [(c["weight"], c["score"]) for c in out.categories.values() if c["score"] is not None]
    total_w = sum(w for w, _ in scored)
    out.overall = round(sum(w * s for w, s in scored) / total_w, 1) if total_w else None
    return out
