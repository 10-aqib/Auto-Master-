"""Content-integrity checks for AI briefs (and later rendered concepts).

JSON Schema guarantees shape; these rules guarantee honesty: no invented testimonials, awards,
certifications, years in business, prices, statistics, superlatives, guarantees or contact details,
and every "verified_fact" section must cite facts that actually exist.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

from webforge_api.design.brief_schema import PAGE_SLUGS, DesignBrief

PROHIBITED: list[tuple[str, re.Pattern[str]]] = [
    ("testimonial", re.compile(r"\b(testimonials?|reviews? from|our (happy |satisfied )?(clients|customers|patients) say|rated \d)", re.I)),
    ("quotation", re.compile(r"[“”\"][^“”\"]{12,}[“”\"]\s*[-\u2013\u2014]\s*\w")),
    ("award", re.compile(r"\b(award[- ]?winning|awards?|winner of|recogni[sz]ed as)\b", re.I)),
    ("certification", re.compile(r"\b(certified|accredited|licensed|iso \d{3,5}|registered with)\b", re.I)),
    ("years_in_business", re.compile(r"\b(since (19|20)\d{2}|(for|over) \d+\+? (years|decades)|\d+\+? years? (of )?(experience|in business|serving))\b", re.I)),
    ("statistic", re.compile(r"\b\d+(\.\d+)?\s?(%|percent)|\b\d{2,}[,\d]*\+?\s+(clients|customers|patients|projects|reviews|orders)\b", re.I)),
    ("price", re.compile(r"(\b(rs\.?|pkr|usd|gbp|eur|aed|inr)\s?\d|[$£€₹]\s?\d|\b\d+\s?(rupees|dollars)\b)", re.I)),
    ("superlative", re.compile(r"\b(best|no\.? ?1|#1|number one|leading|top[- ]rated|guarantee[ds]?|world[- ]class|unbeatable)\b", re.I)),
    ("phone", re.compile(r"(\+?\d[\d\s().-]{7,}\d)")),
    ("email", re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")),
    ("staff", re.compile(r"\b(dr\.|doctor|our team of \d+|founded by|ceo|director)\b", re.I)),
]  # fmt: skip
INJECTION = re.compile(
    r"(ignore (all |any )?(previous|prior|above) instructions|system prompt|you are now|disregard .{0,30}(rules|instructions)|<\/?(system|instructions?)>)",
    re.I,
)


@dataclass(frozen=True)
class Issue:
    code: str
    location: str
    detail: str


def _texts(brief: DesignBrief) -> Iterator[tuple[str, str]]:
    yield "business_summary", brief.business_summary
    for i, a in enumerate(brief.assumptions):
        yield f"assumptions[{i}]", a.statement
    for i, h in enumerate(brief.audience_hypotheses):
        yield f"audience_hypotheses[{i}]", h
    yield "design_direction.positioning", brief.design_direction.positioning
    for p in brief.pages:
        yield f"pages.{p.slug}.title", p.title
        yield f"pages.{p.slug}.goal", p.goal
        for j, s in enumerate(p.sections):
            loc = f"pages.{p.slug}.sections[{j}]"
            for field_name, value in (
                ("heading", s.heading),
                ("body", s.body),
                ("cta_label", s.cta_label),
            ):
                yield f"{loc}.{field_name}", value
            for k, item in enumerate(s.items):
                yield f"{loc}.items[{k}]", f"{item.title} {item.text}"
    for i, img in enumerate(brief.image_briefs):
        yield f"image_briefs[{i}]", f"{img.description} {img.alt_text}"


def contrast_ratio(fg: str, bg: str) -> float:
    """WCAG 2.x contrast ratio between two #RRGGBB colours."""

    def lum(hex_colour: str) -> float:
        channels = [int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]

    hi, lo = sorted((lum(fg), lum(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


CONTRAST_PAIRS = (
    ("text", "background", 4.5),
    ("text", "surface", 4.5),
    ("muted_text", "background", 4.5),
)


def check_brief(brief: DesignBrief, facts: dict[str, str]) -> list[Issue]:
    """Return integrity issues (empty = passes). `facts` maps fact ID -> verified value."""
    issues: list[Issue] = []
    slugs = [p.slug for p in brief.pages]
    if sorted(slugs) != sorted(PAGE_SLUGS):
        issues.append(
            Issue("pages", "pages", f"Need exactly one of each page {PAGE_SLUGS}; got {slugs}")
        )
    for fg, bg, minimum in CONTRAST_PAIRS:
        ratio = contrast_ratio(getattr(brief.palette, fg), getattr(brief.palette, bg))
        if ratio < minimum:
            issues.append(
                Issue(
                    "contrast", f"palette.{fg}", f"{fg} on {bg} is {ratio:.2f}:1; need {minimum}:1"
                )
            )
    known = set(facts)
    for fid in brief.facts_used:
        if fid not in known:
            issues.append(Issue("unknown_fact", "facts_used", f"{fid} is not a provided fact"))
    for p in brief.pages:
        for j, s in enumerate(p.sections):
            loc = f"pages.{p.slug}.sections[{j}]"
            unknown = [f for f in s.fact_ids if f not in known]
            if unknown:
                issues.append(Issue("unknown_fact", loc, f"Unknown fact IDs {unknown}"))
            if s.content_kind == "verified_fact" and not s.fact_ids:
                issues.append(
                    Issue("fact_without_source", loc, "verified_fact sections must cite fact_ids")
                )
            if s.block == "inquiry_demo" and p.slug != "inquiry":
                issues.append(
                    Issue(
                        "misplaced_form", loc, "Inquiry demo forms belong on the inquiry page only"
                    )
                )
    verified_values = [v.lower() for v in facts.values()]
    for loc, text in _texts(brief):
        for code, pattern in PROHIBITED:
            for m in pattern.finditer(text):
                hit = m.group(0)
                # A value that is itself a verified fact (e.g. the business's own name) is fine.
                if any(hit.lower().strip() in v for v in verified_values):
                    continue
                issues.append(
                    Issue(f"prohibited_{code}", loc, f"Unsupported claim or detail: {hit[:60]!r}")
                )
        if INJECTION.search(text):
            issues.append(Issue("instruction_text", loc, "Output contains instruction-like text"))
    return issues


def looks_like_injection(text: str) -> bool:
    return bool(INJECTION.search(text))
