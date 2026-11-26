# 18 — Cost, Quotas and Capacity Controls

## Cost categories

VPS compute/storage/backup/egress; Anthropic input/output tokens; Google Places SKUs/requests; licensed data/contact enrichment; email provider; object storage/egress; monitoring/logging; domain/mailbox. Prices and free credits change: get current quotes before purchase.

## Hard budget controls

Configure daily/monthly budgets per provider and campaign: AI spend; Places requests/spend; candidate count; audit pages/bytes/time; design generations; artifact size/retention; email volume/spend based on approved provider limits. Warn at 80%; stop new spend-causing jobs at 100%; emergency override requires owner action and audit record.

## Cost accounting

Every provider call records provider, operation, campaign, job, request ID, units/tokens, estimated cost/currency and time. Reconcile with provider invoices where possible.

## Capacity

Begin browser/render concurrency at one per pool and measure peak memory/CPU. Scale queues independently; do not increase parallelism solely to raise outreach volume. Separate queues prevent browser jobs from starving email/event jobs.

## Per-prospect cost guard

Reserve/estimate audit + AI + render + storage costs before design. Stop and ask owner for review when a prospect exceeds its ceiling. Prevent repeated regeneration loops.
