"""Deterministic judgement of offline concept validation evidence (validator-1).

The browser sandbox only measures; this module decides. Every check is pass / fail / unknown with a severity:
critical failures block "ready"; major failures are warnings the reviewer sees; minor are informational.
"""

from __future__ import annotations

import base64
import hashlib
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from webforge_api.design.brief_schema import PAGE_SLUGS

VALIDATOR_VERSION = "validator-1"
VIEWPORT_WIDTHS = {"desktop": 1440, "tablet": 768, "mobile": 390}
CONCEPT_ORIGIN = "https://concept.invalid"
# Failures the deterministic renderer can fix by re-rendering in safe mode (high-contrast palette).
REPAIRABLE = {"contrast", "focus_visible"}

Status = Literal["pass", "fail", "unknown"]
Severity = Literal["critical", "major", "minor"]


@dataclass
class Check:
    code: str
    status: Status
    severity: Severity
    message: str
    page: str | None = None
    viewport: str | None = None
    evidence: Any = None


def _check(out: list[Check], ok: bool | None, code: str, severity: Severity, message: str, page: str | None = None,
           viewport: str | None = None, evidence: Any = None) -> None:  # fmt: skip
    status: Status = "unknown" if ok is None else ("pass" if ok else "fail")
    out.append(
        Check(
            code, status, severity, message, page, viewport, evidence if status != "pass" else None
        )
    )


def evaluate(
    results: dict[str, dict[str, Any]], manifest_pages: list[dict[str, Any]]
) -> dict[str, Any]:
    """`results` maps slug -> browser /validate response. Returns the report (status, checks, summary)."""
    checks: list[Check] = []
    expected = {p["slug"]: p for p in manifest_pages}
    _check(checks, set(expected) == set(PAGE_SLUGS), "six_pages", "critical", "All six concept pages exist",
           evidence=sorted(expected))  # fmt: skip
    tokens: dict[str, Any] = {}
    for slug in PAGE_SLUGS:
        data = results.get(slug)
        if data is None:
            _check(checks, False, "page_validated", "critical", "Page was validated", slug)
            continue
        for r in data.get("results", []):
            vp = r.get("viewport")
            loc: dict[str, Any] = {"page": slug, "viewport": vp}
            loaded = not r.get("error") and r.get("status") == 200 and "metrics" in r
            _check(
                checks, loaded, "loads", "critical", "Page loads", evidence=r.get("error"), **loc
            )
            if not loaded:
                continue
            m = r["metrics"]
            width = VIEWPORT_WIDTHS.get(str(vp), m.get("viewport_width"))
            _check(checks, r.get("html_sha256") == expected.get(slug, {}).get("sha256"), "version_match", "critical",
                   "Validated HTML matches the stored render version", evidence=r.get("html_sha256"), **loc)  # fmt: skip
            png_ok = False
            if r.get("screenshot_png_b64"):
                png = base64.b64decode(r["screenshot_png_b64"])
                png_ok = png[:8] == b"\x89PNG\r\n\x1a\n" and hashlib.sha256(
                    png
                ).hexdigest() == r.get("screenshot_sha256")
            _check(
                checks,
                png_ok,
                "screenshot",
                "critical",
                "Screenshot captured and hash verified",
                **loc,
            )
            _check(checks, m["scroll_width"] <= width, "no_overflow", "critical", "No horizontal overflow",
                   evidence={"scroll_width": m["scroll_width"], "viewport": width, "elements": m.get("overflow_elements")}, **loc)  # fmt: skip
            _check(checks, not r.get("console_errors"), "console_clean", "critical", "No console errors",
                   evidence=r.get("console_errors"), **loc)  # fmt: skip
            _check(checks, not r.get("blocked_requests"), "no_external_requests", "critical",
                   "Page requests nothing outside the concept (no missing images/fonts)", evidence=r.get("blocked_requests"), **loc)  # fmt: skip
            _check(
                checks,
                not m.get("broken_images"),
                "images_load",
                "critical",
                "All images load",
                evidence=m.get("broken_images"),
                **loc,
            )
            _check(checks, bool(m.get("notice_visible_at_top")), "concept_notice", "critical",
                   "Concept notice is visible at the top", **loc)  # fmt: skip
            links = m.get("links", [])
            bad = [
                u
                for u in links
                if not (
                    u.startswith(CONCEPT_ORIGIN + "/") and urlsplit(u).path.strip("/") in expected
                )
            ]
            _check(
                checks,
                not bad,
                "routes",
                "critical",
                "Every link points to one of the six pages",
                evidence=bad[:10],
                **loc,
            )
            _check(
                checks,
                m.get("h1_count") == 1,
                "single_h1",
                "major",
                "Exactly one h1",
                evidence=m.get("h1_count"),
                **loc,
            )
            _check(checks, not m.get("heading_skipped"), "heading_order", "major", "Heading levels are not skipped",
                   evidence=m.get("heading_levels"), **loc)  # fmt: skip
            _check(checks, not m.get("unnamed_controls") and not m.get("unlabeled_fields"), "accessible_names", "major",
                   "Links, buttons and fields have accessible names",
                   evidence={"controls": m.get("unnamed_controls"), "fields": m.get("unlabeled_fields")}, **loc)  # fmt: skip
            _check(
                checks,
                not m.get("images_missing_alt"),
                "image_alt",
                "major",
                "Images have alt text",
                **loc,
            )
            _check(checks, not m.get("contrast_failures"), "contrast", "major", "Text contrast meets WCAG AA",
                   evidence=m.get("contrast_failures"), **loc)  # fmt: skip
            focus = r.get("focus") or []
            _check(checks, None if not focus else all(f.get("outline") or f.get("shadow") for f in focus), "focus_visible", "major",
                   "Keyboard focus is visible", evidence=[f for f in focus if not (f.get("outline") or f.get("shadow"))][:5], **loc)  # fmt: skip
            _check(
                checks,
                m.get("lang") == "en",
                "lang",
                "minor",
                "Page declares its language",
                evidence=m.get("lang"),
                **loc,
            )
            if m.get("forms"):
                form = r.get("form") or {}
                inert = (
                    form.get("navigated") is False
                    and form.get("requests_after_interaction") == 0
                    and m.get("named_fields") == 0
                )
                _check(checks, inert, "demo_form_inert", "critical", "Demo form cannot submit or collect data",
                       evidence={**form, "named_fields": m.get("named_fields")}, **loc)  # fmt: skip
            if vp == "desktop":
                tokens[slug] = {"tokens": m.get("tokens"), "font": m.get("body_font")}
    if tokens:
        first = next(iter(tokens.values()))
        _check(checks, all(t == first for t in tokens.values()), "consistent_tokens", "major",
               "Design tokens and fonts are identical on all pages", evidence=tokens)  # fmt: skip
    fails = [c for c in checks if c.status == "fail"]
    critical = [c for c in fails if c.severity == "critical"]
    repair = sorted({c.code for c in fails if c.code in REPAIRABLE})
    return {
        "validator_version": VALIDATOR_VERSION,
        "status": "READY" if not critical else "NEEDS_REVISION",
        "summary": {
            "checks": len(checks),
            "passed": sum(c.status == "pass" for c in checks),
            "failed_critical": len(critical),
            "failed_major": sum(c.severity == "major" for c in fails),
            "failed_minor": sum(c.severity == "minor" for c in fails),
            "unknown": sum(c.status == "unknown" for c in checks),
        },
        "repairable": repair,
        "checks": [asdict(c) for c in checks],
    }
