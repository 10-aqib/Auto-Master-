# ADR 0003 — Phase 02 Source Adapters and Data Governance

- Status: Accepted
- Date: 2026-11-26

## Decisions

1. **Registry in the database** (`source_registrations`), seeded by migration 0002 with `google_places`,
   `official_website` and `mock_places`, all `DISABLED`. A CHECK constraint makes "enabled without terms review"
   impossible for non-mock sources. Enabling is OWNER-only; disabling is OWNER or ADMIN (fail-safe direction).
2. **Place IDs only.** `external_place_identifiers` keeps provider + ID + status + timestamps (+ optional campaign).
   `prospect_id` became nullable so candidates can exist before verification.
3. **Independent provenance enforced twice**: service rule (`record_fact`) and DB CHECK on `prospect_sources.source_type`.
4. **Fixed purpose-specific field masks** instead of caller-chosen fields; SKU derived from the highest-tier field.
5. **Fail-closed cost control**: every SKU needs an owner-configured price (IDs-only included, because Google's
   docs disagree on whether it is free); zero budget or cap blocks requests; usage is reserved before the call
   under a PostgreSQL advisory lock and marked SUCCESS/ERROR afterwards (errors cost 0). Costs are stored in
   thousandths of a minor unit for exact per-1000 pricing.
6. **SSRF-safe fetcher built on httpcore** with a custom network backend: resolve once, refuse if any answer is
   non-public, connect to the vetted IP, TLS verified against the original host name, no proxies, manual
   redirects re-validated. Reused by the Phase 04 audit worker.
7. **Website verification in the API process for now.** It fetches only one page plus robots.txt with strict
   limits. Phase 03 moves it into a queued worker; Phase 04 adds the isolated browser.
8. **Transient cache is opt-in per field** through `cache_rules`; with Google's rules only `location` (≤ 30 days)
   could be cached, and the current flows cache nothing.
9. **Prospects are created only from VERIFIED website checks**, named with the site's own text. Minimal dedupe:
   an existing prospect with the same verified domain is reused. Full dedupe/branch handling is Phase 03.
10. **Self-hosted Roboto** (`@fontsource/roboto`, latin 400) for the attribution text, keeping CSP `font-src 'self'`.

## Consequences

- Google Places cannot be exercised for real until the owner supplies a key, prices, budget and cap, records a
  terms review, and sets `GOOGLE_PLACES_API_ENABLED=true`. CI and local development use the mock connector and a
  mock HTTP transport; no external calls are made.
- Open legal questions are listed in `docs/compliance/source-policies.md`.
