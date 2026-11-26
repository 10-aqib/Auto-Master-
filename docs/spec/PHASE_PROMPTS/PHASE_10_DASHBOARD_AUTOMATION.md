# PHASE 10 — Complete Dashboard and Pipeline Orchestration

Read `01_PRODUCT_REQUIREMENTS.md`, `02_SYSTEM_ARCHITECTURE.md`, `12_API_AND_JOBS.md`, `17_OPERATIONS_RUNBOOK.md`, `18_COSTS_AND_LIMITS.md`.

## Work
1. Complete responsive owner dashboard: overview, campaigns, prospects/source evidence, audits, design projects/six-page previews, proposals, compliance queue, outreach drafts/events, replies, jobs and settings.
2. Connect every UI control to actual API behavior; no inert buttons/fake progress.
3. Prominent global/system pause and email-only pause, with state/last actor visible.
4. Manual queues for source conflicts, weak evidence, content claims, compliance holds and uncertain replies.
5. Pipeline/campaign/country/spend analytics. Avoid unsupported open tracking.
6. Health view for workers, queue depth, failures, quotas, provider errors and backups.
7. Audit history for privileged edits.
8. Pagination, filters, accessible error/loading/empty states and safe destructive confirmations.
9. Idempotent timezone-safe scheduling. No sends during global/campaign pause.
10. Hard stops and warnings for budget caps.

## Tests
Full E2E with fake fixtures through proposal and compliance HOLD; manual review; RBAC; pause; analytics; responsive UI and keyboard navigation.

## Deliverable
Complete owner dashboard/orchestration. Mail remains disabled. **Stop after Phase 10.**
