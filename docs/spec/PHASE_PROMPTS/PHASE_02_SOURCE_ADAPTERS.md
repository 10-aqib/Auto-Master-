# PHASE 02 — Source Connectors and Data Governance

Read `06_DISCOVERY_AND_DATA_GOVERNANCE.md`, `10_EMAIL_COMPLIANCE.md`, `11_SECURITY.md` and `21_OFFICIAL_REFERENCES.md`.

## Objective
Create policy-aware source adapters and limited approved data retrieval. Do not build a Maps scraper or email sender.

## Work
1. Re-check current Places API (New) docs, field masks, billing, attribution, caching/storage restrictions and service-specific terms. Record checked date/URLs.
2. Implement server-side API adapter with minimal explicit field mask, quota and budget controls. Never use wildcard fields in production.
3. Store only Place ID from Maps unless a current policy/license explicitly permits additional data retention. Treat other response fields as transient. Never export Maps names, addresses, phones, ratings, reviews, photos or website data into a persistent prospect dataset by default.
4. Independently verify stored business facts from business-owned websites or licensed providers. Save field-level source URL, timestamp, terms/license note, source type and confidence.
5. Require domain association evidence. Never guess domains or email addresses.
6. Create source terms/permission registry. Connectors without reviewed terms remain disabled.
7. Show required attribution wherever Places content is displayed.
8. Track API usage/cost and campaign budget.
9. Create mock connectors for CI; CI makes no external calls.
10. Add policy-based deletion/refresh for transient values.

## Tests
Field mask required/no wildcard; Place ID persistence; restricted fields not persisted; provenance required; budget/rate limits; secret not in frontend/logs; source connectors disabled by default.

## Deliverable
Source adapter interface, Places connector with policy protections, independent source provenance, mocks, cost accounting and policy notes. **Stop after Phase 02.**
