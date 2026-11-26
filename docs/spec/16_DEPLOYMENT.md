# 16 — VPS Deployment and Production Release

## Initial VPS recommendation

A small supervised pilot could start around 4 vCPU, 8 GB RAM and 160 GB SSD/NVMe. This is a planning estimate, not a guarantee. Browser/render workers are resource-intensive; measure and scale or separate them before increasing concurrency.

Choose provider/region based on latency, data residency, backup, support, price and terms (Hetzner, DigitalOcean or an equivalent provider are candidates). Owner purchases the instance; do not create cloud resources without explicit approval.

## Server baseline

Supported Ubuntu LTS, patched OS, non-root deploy user, SSH keys, password/root SSH disabled after validating non-root access, firewall only needed ports (normally restricted SSH + 80/443), automatic security updates, time sync and encrypted off-server backups.

## DNS

Owner must own/control the domain. Example hostnames: `app.<domain>`, `api.<domain>`, `preview.<domain>`. Optional sending subdomain follows the actual provider instructions. Never invent DNS/IP/SPF/DKIM/DMARC records; copy values from provider/VPS console and verify propagation.

## Production services

Caddy, Next.js dashboard, FastAPI API, PostgreSQL, Redis, worker services (discovery/audit/design/render/proposal/outreach) and optional preview gateway. Requirements: pinned images/digests, health checks, restart policies, resource limits, non-root processes, named volumes, restricted secrets, no public DB/Redis ports and strict browser/render isolation. Never mount Docker socket into untrusted workers.

## Deploy procedure

1. Confirm release tag and green CI.
2. Back up database and verify artifact.
3. SSH using non-root user.
4. Pull approved commit/tag from private repo.
5. Update secrets securely, not in Git.
6. Build pinned images.
7. Run reviewed migration as a one-off task.
8. Start/update services.
9. Verify health/readiness and service status.
10. Smoke-test dashboard, API and preview.
11. Confirm global/email pause enabled and email mock/sandbox configured.
12. Check logs, CPU, memory, disk, queues and errors.
13. Keep previous release for rollback.

Example commands once Compose file exists:

```bash
docker compose config
docker compose pull
docker compose build --pull
docker compose up -d
docker compose ps
docker compose logs --tail=200 api
```

Use actual migration/service commands documented by Claude; do not guess service names.

## Rollback

Use tags and migration notes. Prefer backward-compatible migrations. Do not blindly revert schema after writes; use a tested forward fix or restore plan. Pause outbound jobs before rollback. Reconcile outbox/queue/provider events after rollback.

## Enablement order

Internal dashboard → mock data/fixture sites → real source API with budgets → real audit/design/proposals without mail → provider sandbox/webhooks → legal/provider review for one jurisdiction/category → supervised manual pilot → automatic mode only for explicitly approved categories.
