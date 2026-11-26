# PHASE 03 — Campaigns, Discovery, Dedupe and Qualification

Read `01_PRODUCT_REQUIREMENTS.md`, `05_DATA_MODEL.md`, `06_DISCOVERY_AND_DATA_GOVERNANCE.md`, `12_API_AND_JOBS.md` and `18_COSTS_AND_LIMITS.md`.

## Work
1. Campaign CRUD, validation, pause/resume and lifecycle.
2. Target country/region/industry filters, campaign caps and budget reservations.
3. Discovery jobs use only Phase 02 approved connectors.
4. Normalize independently verified domains; dedupe cautiously; preserve branch/franchise distinctions and merge history.
5. Store provenance and last-verified timestamps.
6. Implement evidence-based qualification score. Unknown evidence stays unknown.
7. Outcomes: STRONG, POTENTIAL, INVESTIGATE, REJECTED, MANUAL_REVIEW with reason codes.
8. Owner review/reject/do-not-contact tools; suppression is global and separate.
9. Idempotent jobs, transactional outbox or equivalent, retries, dead-letter handling and correlation IDs.
10. Basic campaign/prospect screens showing source evidence.

## Tests
Duplicate domain handling; branch separation; unknown facts do not score; policy failure blocks ingestion; budget/campaign caps; idempotent retries; reject/suppression persists across campaigns.

## Deliverable
Working discovery flow with mock mode and documented live connector configuration. No email sends. **Stop after Phase 03.**
