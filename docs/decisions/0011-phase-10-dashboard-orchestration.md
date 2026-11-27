# ADR 0011 — Phase 10 Owner Dashboard and Orchestration

- Status: Accepted
- Date: 2026-11-27

1. **Read-only aggregation, no new state.** `/overview`, `/review-queues` and `/operations` are computed from
   existing tables on request. No open or click tracking exists, so none is shown.
2. **Funnel** counts prospects that reached each pipeline stage (cumulative), plus holds/exits, message and reply
   outcomes, top compliance hold reasons (30 days), per campaign, per country (filterable) and month-to-date
   spend per provider.
3. **Budgets** report today's use against every hard limit (Places spend and requests, AI spend, email volume):
   `warning` at 80%, `stopped` at 100% or when the limit is 0. Enforcement stays where it already was (each
   spend-causing service reserves before calling and stops at 100%); the dashboard only reports.
4. **Review queues** gather everything automation refused to decide: human-review prospects (source conflicts,
   weak evidence, failed audits), compliance holds, messages awaiting owner approval, briefs with claim issues,
   concepts needing revision, proposals that failed checks and uncertain replies.
5. **Operations** (owner/admin) shows worker heartbeats (Redis keys with a 60 s TTL written every 10 s by each
   worker), queue depth and oldest age, dead letters, failures and provider errors (24 h), quotas, pause switches
   and backup status (honestly "unknown" until Phase 11 records backups).
6. **Pause visibility.** A banner on every page shows system and email pause state with who changed it and when;
   scoped country/provider pauses are listed in Settings and Operations.
7. **Scheduling.** Sends are scheduled at owner approval (UTC storage) and held by the job queue while any pause or
   inactive campaign applies; drafts now carry the prospect's campaign so campaign pauses take effect.
8. **Accessibility.** Skip link, labelled controls, keyboard-reachable actions, no horizontal overflow at 390 px
   (verified by E2E on ten pages; this found and fixed a Card `min-width` overflow).
