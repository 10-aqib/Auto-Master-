# 06 — Lead Discovery, Source Governance and Qualification

## Approved source strategy

Use only sources under current terms and permitted APIs:
- Google Places API (New) for discovery and permitted place identifiers, with required attribution and policy-aware fields.
- Business-owned official websites for independently verified identity, website content and contact routes.
- Government/company registries and public directories only where automated access and reuse are permitted.
- Licensed business-data providers with documented contractual rights for prospecting.
- Owner-provided CSV only after confirming rights to use it for this purpose.

Do not scrape search-result pages, Google Maps UI, social platforms, gated directories or sources that prohibit automated access. `robots.txt` is not legal authorization; review terms and policy too.

## Google Places guardrails

- Use Places API (New), never browser scraping.
- Use explicit field masks; do not request `*` in production.
- Display required attribution.
- Do not create a persistent prospect database from Maps Content. Place IDs may be stored as the documented exception; refresh transient Places fields when needed.
- Do not persist Google-provided names, addresses, phone numbers, ratings, reviews, photos or website URLs unless a current policy/license expressly permits that field and use.
- Safer design: store Place ID separately, then independently verify retained facts through the business-owned website or a separately licensed source.
- A Places API field is still Maps Content even if fetched server-side.
- Budget requests and account for SKU-level cost.

## Independent verification

For each stored business fact, record field name, source URL/provider, observation time, business-owned/licensed status, terms/license version where relevant, confidence and method. Prefer official business domains. Do not assume a similar-looking domain belongs to the business.

## Website crawl limits

Only public pages. Never log in, bypass access controls, solve CAPTCHAs, submit forms or perform destructive actions. Suggested starting limits: 10 same-site pages, depth 2, 30 seconds/page, 5 MB/response, 50 MB/prospect. Respect rate limits and back off on 429/503. Allow HTTP/HTTPS only; block other schemes and dangerous downloads. Keep crawl scope to verified domain and approved redirects.

## Dedupe

1. Normalize verified domain (lowercase, punycode, remove default port/path; treat `www` carefully).
2. Normalize name for matching, but never auto-merge on fuzzy name alone.
3. Compare country/region/city and official domain.
4. Keep separate branches/franchises when evidence supports separate locations.
5. Retain merge history and source trail.
6. Check suppression independently from prospect dedupe.

## Initial qualification score (configurable; not buying intent)

- Website presence/accessibility: 10.
- Mobile experience: 20.
- Visual hierarchy/readability: 15.
- Navigation/information clarity: 15.
- Conversion path: 15.
- Business fit: 15.
- Verified contact route/source quality: 10.

Suggested bands: 75–100 STRONG; 60–74 POTENTIAL; 40–59 INVESTIGATE; 0–39 REJECT/LOW PRIORITY. Only score where evidence exists; unknown stays unknown. Every component needs reason/evidence. A high score never grants permission to email.

## Discovery algorithm

1. Validate campaign target, source configuration and policies.
2. Fetch candidate identifiers within budget.
3. Normalize/dedupe.
4. Independently resolve website/business facts.
5. Verify domain association.
6. Record field-level provenance and timestamp.
7. Qualify on observed evidence.
8. Hold conflicts/weak evidence; reject irrelevant candidates.
9. Queue audit only for qualified, safe, public websites.
10. Record request counts/cost; stop at caps.

Hold or reject parked, malicious, unrelated or mismatched domains. Never guess missing contact details.
