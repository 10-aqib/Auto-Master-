# PHASE 11 — VPS Deployment, Security Review and Supervised Pilot

Read the full handoff, especially email compliance, security, QA, deployment, operations, costs and acceptance criteria.

## Work
1. Verify current supported Ubuntu LTS, Docker/Compose, firewall, Caddy and provider setup; pin images/digests.
2. Create production Compose topology for dashboard/API/Postgres/Redis/workers/Caddy/preview. DB/Redis not public. Prove browser/render isolation.
3. Configure domains/DNS/TLS only using owner-provided domain/IP values.
4. Configure secrets securely; scan Git, images, logs, frontend bundles, previews and PDFs.
5. Configure encrypted offsite backups and automated restore test. Test restore, not just backup creation.
6. Configure alerts for uptime, queue, worker crashes, spend, provider failure, disk, memory, TLS, login anomalies and backups.
7. Run unit/integration/E2E/security suites plus dependency/container scans. Review critical/high issues.
8. Verify SSRF and network isolation from inside browser/render worker.
9. Rehearse deploy/rollback with mail paused.
10. Confirm provider account approval and qualified country-specific legal review before live campaigns.
11. Run mock campaign, then small owner-reviewed real sample only if allowed. Inspect every concept and message during pilot.
12. Enable automatic mode only for explicitly reviewed countries/recipient types and after owner approval. Unknown cases remain held.
13. Write actual operational runbook: hostnames, service names, backup/restore, alerts and rollback, without credentials.

## Stop conditions
Do not enable live mail if source legality unclear, country policy unreviewed, provider approval absent, sender details incomplete, unsubscribe untested, webhooks failing, preview isolation unproven, backups not restorable, critical security issues unresolved or pause switch unable to stop queued messages.

## Deliverable
Release report with versions, smoke/security tests, backup restore evidence, unresolved risks, missing owner inputs and go/no-go recommendation. Do not claim production-ready while critical gates fail. **Stop after Phase 11.**
