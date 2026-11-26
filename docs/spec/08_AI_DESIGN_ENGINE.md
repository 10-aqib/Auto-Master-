# 08 — AI Brief and Six-Screen Design Engine

## Design goal

Generate a tailored, professional concept that suits the prospect's industry. Prioritize usability, clarity, mobile-first behavior, strong hierarchy and credible content. Avoid generic six-page template spam.

## Two-stage generation

### Stage A — Structured brief

Provide only necessary context: independently verified business name/industry, verified facts and their sources, current-site audit findings, owner's service positioning and lawfully usable brand assets. AI returns strict JSON matching a versioned schema:
- observed business summary;
- unknowns/assumptions;
- clearly labelled audience hypotheses;
- design direction and visual principles;
- color palette with contrast goals;
- typography roles using licensed/system fonts;
- navigation and sitemap;
- six page plans, goals, sections, CTA labels/content blocks;
- image briefs;
- accessibility/responsive decisions;
- factual claim allowlist with source references.

### Stage B — Deterministic renderer

Map validated JSON into safe, approved blocks: hero, feature grid, service cards, process steps, gallery, product cards, fact-backed statistics only, authorized testimonials only, factual FAQ, inert inquiry demo, contact panel and footer. Never execute arbitrary AI-generated shell commands or scripts. If code generation is unavoidable, build in a disposable no-secrets sandbox and scan output.

## Default six screens

1. Home — positioning, CTA, offerings, evidence-backed trust.
2. Services/Products — verified offerings; no invented pricing/availability.
3. About — verified story and approach only.
4. Industry-specific trust/process — clinic treatments, hotel rooms, restaurant menu, studio portfolio, manufacturer capabilities, etc.
5. Inquiry/Booking — non-submitting demo form; no data collection.
6. Contact — verified contact channels only; missing values omitted or clearly marked for owner review.

Page labels can adapt; restaurant version might be Home/Menu/About/Gallery/Reservations Demo/Contact.

## Brand/assets

Use prospect logo only when legitimate; otherwise use a neutral text wordmark. Do not copy competitors pixel-for-pixel. Do not use unlicensed stock photography, copyrighted product images, third-party logos or fonts. Record source/license/attribution. Avoid hotlinks. Optimize assets, alt text and fallbacks. Keep motion restrained and respect reduced-motion preferences.

## Content integrity

Separate `verified_fact`, `proposed_copy`, and `assumption`. Never fabricate reviews, client logos, years in business, certifications, awards, staff bios, addresses, hours, prices, warranties, results or success percentages. Empty testimonial area is preferable to a fake quote. Unsupported “best/number one/guaranteed” claims are prohibited.

## Visual quality

Consistent tokens, clear type hierarchy, mobile navigation, touch targets, spacing, contrast, no horizontal overflow, correct image sizes/alt text, focus/hover states and minimal JavaScript.

## Versioning and failure

Store brief, model, schema, prompt and renderer versions. Regeneration creates a new version; preserve rollback. If facts change, mark dependent content/proposals stale. Validate schema, reject executable/unknown fields, bounded format retry; then HUMAN_REVIEW. AI output never overrides compliance or security gates.
