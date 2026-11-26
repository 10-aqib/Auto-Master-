# 07 — Website Audit Specification

## Objective

Generate fair, evidence-based observations that explain why a redesign concept may be useful. Do not label a site “bad” just because an AI model dislikes its style.

## Audit stages

1. Normalize and validate URL.
2. Resolve hostname and validate destination IP.
3. Open in isolated Chromium/Playwright worker with controlled egress.
4. Capture desktop (e.g. 1440×1000) and mobile (e.g. 390×844); optionally tablet.
5. Inspect homepage and selected same-origin public pages within bounded limits.
6. Collect navigation, links, images, headings, forms/CTAs, viewport overflow, accessibility basics and load failures.
7. Optionally use Lighthouse/PageSpeed when configured; save tool/version/test conditions.
8. Store evidence/screenshots and calculate scores from deterministic rules.
9. Summarize observations and potential improvements.

## Audit dimensions (initial weights)

- Visual structure/hierarchy: 20.
- Mobile usability: 20.
- Navigation/information architecture: 15.
- Branding/consistency: 10.
- Conversion path/CTA: 15.
- Content clarity/trust information: 10.
- Technical accessibility/performance evidence: 10.

Industry-specific rubrics matter; missing a feature is not always a defect.

## Finding schema

Each finding has a stable code, category, severity (INFO/LOW/MEDIUM/HIGH), title, factual description, observed URL/time, viewport/device, screenshot or DOM/console evidence, confidence and reproduction steps. Mention caveats such as consent overlays or bot blocks.

Good finding: “At 390px viewport width, the hero heading wraps to six lines and the primary action sits below the first viewport.” Avoid vague statements such as “the site looks old.”

## Safety limits

- Enforce SSRF controls before navigation and after every redirect.
- Re-resolve DNS and validate every A/AAAA answer. Defend against DNS rebinding and mixed public/private results.
- Block loopback, private, link-local, multicast, reserved, IPv6 local and metadata ranges.
- Block internal services, host ports, Docker socket, DB and Redis.
- Block `file://`, `data:`, `javascript:` and dangerous downloads.
- Limit response bytes, pages, redirects, CPU, memory and wall time.
- Browser has no secrets/cloud credentials and only disposable workspace.
- Never submit forms, purchase, authenticate, exploit or stress-test target sites.

## Output

JSON with schema version, per-category scores/evidence, screenshots, strengths, unknown/not-tested checks and no fabricated analytics, traffic, ranking, revenue or conversion figures.

## Fixture testing

Create deterministic sites for modern responsive, fixed-width, broken image, missing navigation, missing CTA, slow site, redirect chain, mixed public/private DNS, localhost, malicious redirect, cookie overlay and bot-blocked/unavailable cases.
