# ADR 0004 — Phase 03 Job Queue, Discovery Pipeline and Qualification

- Status: Accepted
- Date: 2026-11-26

## Decisions

1. **PostgreSQL job queue instead of Celery.** Jobs are rows in `jobs`, inserted in the same transaction as the
   business change that causes them (transactional outbox without a relay). Workers claim with
   `SELECT … FOR UPDATE SKIP LOCKED` and a lease; expired leases are reclaimed (crash recovery). Retryable
   failures back off exponentially and end in `DEAD`; non-retryable ones end in `FAILED`; both are visible and
   manually retryable (non-idempotent types such as email sends require reconciliation first). Redis stays for
   rate limits. This deviates from the "Redis + Celery" suggestion because it removes the commit/publish gap,
   needs no extra broker, and is easy to observe. Revisit if throughput needs exceed one database.
2. **Worker pools by queue.** `python -m webforge_api.worker --queues …`; scale with container replicas.
   A heartbeat file backs the container health check.
3. **Durable pause switches** (`system_controls`), seeded **paused**. Admins can pause; only the owner can resume.
   `GLOBAL_PAUSE`/`EMAIL_PAUSE` environment variables are emergency overrides that force the pause on.
   Paused work is deferred without consuming retry attempts.
4. **Discovery pipeline:** campaign → `discovery.search` (one per query per UTC day, idempotent) →
   `discovery.verify` per new Place ID → `prospect.qualify`. Rediscovery of an already-verified place links the
   prospect to the new campaign and re-qualifies it without re-verifying.
5. **Dedupe:** identity = verified domain + branch key (location-specific path; language-only paths ignored).
   Never merged on fuzzy names; same-name/different-domain is flagged `possible_duplicate` for review. Manual merges
   keep the merged prospect (`MERGED`) and a history row with a snapshot; do-not-contact always survives a merge.
6. **Qualification rubric v1** (see `docs/compliance/qualification.md`): only components with evidence count;
   pre-audit prospects are `INVESTIGATE / awaiting_audit_evidence`. Industry comes only from the business's own
   schema.org data.
7. **Owner decisions persist across campaigns:** reject and do-not-contact live on the prospect, not the campaign.
   Do-not-contact can only be lifted by the owner; suppression of email addresses (Phase 09) is separate and global.
