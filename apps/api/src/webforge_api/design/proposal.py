"""Proposal document (proposal-1): self-contained HTML rendered to PDF offline in the browser sandbox.

All text is autoescaped; screenshots are embedded as data: URIs from hash-verified validation evidence. The
document states only verified facts, dated audit observations, the approved brief and the owner's identity
from settings. It never invents contact details, experience, clients, testimonials or outcomes.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field
from typing import Any

from jinja2 import DictLoader, StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment

TEMPLATE_VERSION = "proposal-1"
NOTICE = "Independent website redesign concept — not the official website of {business}."
FOOTER_NOTICE = "Independent redesign concept — not affiliated with or endorsed by the business"

# Cautious, non-guaranteed framing per audit category (no conversion/SEO/revenue promises).
OPPORTUNITIES = {
    "mobile_usability": "A phone-first layout may make the site easier to read and navigate on small screens.",
    "conversion": "Clearer calls to action and a simple inquiry page may make it easier for visitors to get in touch.",
    "content_trust": "Plain, factual page structure may help visitors find the information they look for.",
    "navigation": "A short, consistent menu across six pages may help visitors find their way.",
    "technical": "Lighter, static pages may load more predictably; real-world speed depends on hosting.",
    "visual_structure": "A clear heading hierarchy and consistent spacing may make pages easier to scan.",
}
GENERAL_OPPORTUNITIES = [
    "Consistent colours and typography across every page.",
    "Accessible contrast, visible keyboard focus and readable text sizes were checked automatically.",
]

PAGE_PURPOSE = {
    "home": "First impression and the main paths into the site.",
    "services": "What the business offers, without invented prices or availability.",
    "about": "Who the business is, using verified information only.",
    "trust": "Industry-specific page that explains the process or offering.",
    "inquiry": "A demonstration inquiry form; it does not send or store anything.",
    "contact": "Verified contact routes only; missing details are left for the business to confirm.",
}

TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:">
<title>Website Redesign Concept for {{ business }}</title>
<style>
@page { size: A4; }
* { box-sizing: border-box; }
body { margin: 0; font: 10.5pt/1.5 system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #1a1a1a; }
h1 { font-size: 26pt; line-height: 1.15; margin: 0 0 6mm; }
h2 { font-size: 16pt; margin: 0 0 4mm; color: {{ primary }}; }
h3 { font-size: 11.5pt; margin: 4mm 0 1.5mm; }
p { margin: 0 0 3mm; }
section { page-break-after: always; }
section:last-of-type { page-break-after: auto; }
.cover { padding-top: 30mm; }
.eyebrow { text-transform: uppercase; letter-spacing: .12em; font-size: 9pt; color: #555; }
.notice { border: 1.5px solid #1a1a1a; padding: 3mm 4mm; font-weight: 600; margin: 8mm 0; }
.muted { color: #555; }
.meta { font-size: 9pt; color: #555; }
table { width: 100%; border-collapse: collapse; font-size: 9.5pt; }
th, td { text-align: left; vertical-align: top; padding: 2mm; border-bottom: 1px solid #ddd; }
.sev { font-weight: 600; white-space: nowrap; }
.swatches { display: flex; flex-wrap: wrap; gap: 3mm; margin: 2mm 0 4mm; }
.swatch { display: flex; align-items: center; gap: 2mm; font-size: 9pt; }
.chip { width: 9mm; height: 9mm; border: 1px solid #ccc; border-radius: 1.5mm; }
.shotpage { display: flex; gap: 5mm; align-items: flex-start; }
.desk { flex: 3; max-height: 190mm; overflow: hidden; border: 1px solid #ccc; border-radius: 2mm; }
.mob { flex: 1; max-height: 190mm; overflow: hidden; border: 1px solid #ccc; border-radius: 2mm; }
.desk img, .mob img { width: 100%; display: block; }
ul { margin: 0 0 3mm; padding-left: 5mm; }
.ia li { margin-bottom: 1.5mm; }
.links a { color: {{ primary }}; }
</style></head>
<body>
<section class="cover">
  <p class="eyebrow">Redesign concept · {{ prepared_on }}</p>
  <h1>Website Redesign Concept for {{ business }}</h1>
  <p>An independent concept prepared by {{ author.name }}, {{ author.title }}.</p>
  <p class="notice">{{ notice }} It is a design proposal only and is not affiliated with, endorsed or authorised by {{ business }}.</p>
  <p class="meta">Concept version {{ render_version }} · validated at desktop, tablet and mobile widths on {{ validated_on }} ({{ checks_passed }} automated checks passed).</p>
</section>

<section>
  <h2>Current website observations</h2>
  {% if findings %}
  <p class="muted">Observed on {{ audit_date }} at {{ audit_url }} by an automated, single-run check of public pages. Results are indicative and limited to what was measured.</p>
  <table><thead><tr><th>Priority</th><th>Observation</th><th>Where</th></tr></thead><tbody>
  {% for f in findings %}<tr><td class="sev">{{ f.severity }}</td><td>{{ f.description }}</td><td>{{ f.viewport or 'all' }}</td></tr>{% endfor %}
  </tbody></table>
  {% else %}
  <p>No specific issues were recorded by the automated check{% if audit_date %} on {{ audit_date }}{% endif %}. This concept focuses on presentation and structure.</p>
  {% endif %}
</section>

<section>
  <h2>Proposed design direction</h2>
  <p>{{ direction.positioning }}</p>
  <p class="muted">Tone: {{ direction.tone }}.</p>
  {% if direction.visual_principles %}<ul>{% for v in direction.visual_principles %}<li>{{ v }}</li>{% endfor %}</ul>{% endif %}
  <h3>Colour palette</h3>
  <div class="swatches">{% for name, hex in palette %}<div class="swatch"><span class="chip" style="background: {{ hex }}"></span>{{ name }} {{ hex }}</div>{% endfor %}</div>
  <h3>Typography</h3>
  <p>Headings: {{ fonts.heading }}. Body text: {{ fonts.body }}. System fonts only, so nothing is downloaded or licensed separately.</p>
  <h3>Visitor journey</h3>
  <p>Home introduces the business and points to the inquiry page; Services, About and {{ trust_label }} answer common questions; Contact shows verified details only.</p>
</section>

{% for p in pages %}
<section>
  <h2>{{ loop.index }}. {{ p.title }}</h2>
  <p class="muted">{{ p.purpose }}</p>
  <div class="shotpage">
    <div class="desk"><img src="{{ p.desktop }}" alt="{{ p.title }} page, desktop"></div>
    <div class="mob"><img src="{{ p.mobile }}" alt="{{ p.title }} page, mobile"></div>
  </div>
</section>
{% endfor %}

<section>
  <h2>Proposed information architecture</h2>
  <ul class="ia">{% for p in pages %}<li><strong>{{ p.title }}</strong>{% if p.sections %} — {{ p.sections | join(", ") }}{% endif %}</li>{% endfor %}</ul>
  <h2>Potential improvements</h2>
  <p class="muted">These are design opportunities, not guaranteed results. Effects on enquiries, search ranking or revenue cannot be promised.</p>
  <ul>{% for o in opportunities %}<li>{{ o }}</li>{% endfor %}</ul>
</section>

<section>
  <h2>About the developer</h2>
  <p><strong>{{ author.name }}</strong>, {{ author.title }}.</p>
  <p class="links">Portfolio: <a href="{{ author.url }}">{{ author.url }}</a>{% if author.github %}<br>GitHub: <a href="{{ author.github }}">{{ author.github }}</a>{% endif %}</p>
  <h2>Next step</h2>
  <p>If this direction is useful, reply to the message this proposal came with{% if contact_email %} or write to {{ contact_email }}{% endif %}. Content marked "to be confirmed" in the concept would be replaced with details supplied by {{ business }}.</p>
  <p class="notice">{{ notice }}</p>
</section>
</body></html>
"""

_env = ImmutableSandboxedEnvironment(
    loader=DictLoader({"proposal": TEMPLATE}), autoescape=True, undefined=StrictUndefined
)
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
LEAK_RE = re.compile(
    r"\b(undefined|None|null|TODO|FIXME|lorem ipsum|placeholder|traceback|/data/artifacts|designs/)\b",
    re.I,
)


@dataclass
class ProposalInput:
    business: str
    prepared_on: str
    render_version: int
    validated_on: str
    checks_passed: int
    audit_date: str | None
    audit_url: str | None
    findings: list[dict[str, Any]]
    brief: dict[str, Any]
    shots: dict[str, dict[str, str]]  # slug -> {"desktop": data URI, "mobile": data URI}
    author: dict[str, str]
    contact_email: str
    opportunities: list[str] = field(default_factory=list)


def build_html(inp: ProposalInput) -> str:
    brief = inp.brief
    pages = []
    for page in brief["pages"]:
        pages.append({
            "slug": page["slug"], "title": page["title"], "purpose": PAGE_PURPOSE.get(page["slug"], page["goal"]),
            "desktop": inp.shots[page["slug"]]["desktop"], "mobile": inp.shots[page["slug"]]["mobile"],
            "sections": [s["heading"] for s in page["sections"]][:6],
        })  # fmt: skip
    pal = brief["palette"]
    return _env.get_template("proposal").render(
        business=inp.business, prepared_on=inp.prepared_on, render_version=inp.render_version,
        validated_on=inp.validated_on, checks_passed=inp.checks_passed, audit_date=inp.audit_date,
        audit_url=inp.audit_url, findings=inp.findings, direction=brief["design_direction"],
        palette=[(k.replace("_", " "), v) for k, v in pal.items()], fonts=brief["typography"],
        trust_label=brief["trust_page_label"], pages=pages, opportunities=inp.opportunities, author=inp.author,
        contact_email=inp.contact_email, notice=NOTICE.format(business=inp.business), primary=pal["primary"],
    )  # fmt: skip


def opportunities_for(categories: list[str]) -> list[str]:
    seen = [OPPORTUNITIES[c] for c in dict.fromkeys(categories) if c in OPPORTUNITIES]
    return (seen + GENERAL_OPPORTUNITIES)[:6]


def check_pdf(
    pdf: bytes, *, business: str, author: dict[str, str], min_pages: int, min_images: int
) -> list[dict[str, Any]]:
    """Open the PDF and verify structure and content. Returns check results (all must pass)."""
    from pypdf import PdfReader

    checks: list[dict[str, Any]] = []

    def add(code: str, ok: bool, detail: str = "") -> None:
        checks.append({"code": code, "ok": bool(ok), "detail": detail[:300]})

    add("pdf_header", pdf.startswith(b"%PDF-"))
    try:
        reader = PdfReader(io.BytesIO(pdf))
        texts = [(pg.extract_text() or "") for pg in reader.pages]
        images = sum(len(pg.images) for pg in reader.pages)
    except Exception as exc:  # any parse failure is a failed proposal, never a crash
        add("pdf_opens", False, type(exc).__name__)
        return checks
    add("pdf_opens", True)
    full = "\n".join(texts)
    flat = re.sub(r"\s+", " ", full)
    add("page_count", len(texts) >= min_pages, f"{len(texts)} pages")
    add(
        "no_blank_pages",
        all(t.strip() for t in texts),
        f"blank: {[i + 1 for i, t in enumerate(texts) if not t.strip()]}",
    )
    add("screenshots_embedded", images >= min_images, f"{images} images")
    add("business_named", business in flat)
    add(
        "concept_notice",
        "Independent website redesign concept" in flat and "not affiliated with" in flat,
    )
    add(
        "developer_identity",
        all(v in flat for v in (author["name"], author["title"], author["url"]))
        and (not author.get("github") or author["github"] in flat),
    )
    add("no_internal_ids", not UUID_RE.search(full), "UUID found" if UUID_RE.search(full) else "")
    leak = LEAK_RE.search(full)
    add("no_debug_or_placeholders", leak is None, leak.group(0) if leak else "")
    checks.append({"code": "page_count_value", "ok": True, "detail": str(len(texts))})
    return checks
