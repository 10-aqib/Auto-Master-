# WEBFORGE AI — Operations Runbook

No credentials, IPs or real hostnames are recorded here. `<domain>` is the owner's domain; replace it only on the
server, in `.env`. All commands run from the repository root on the VPS as the non-root deploy user.

## 1. Topology

| Service | Image | Networks | Public? | Notes |
|---|---|---|---|---|
| caddy | caddy:2.11.9-alpine (digest-pinned) | frontend | **80/443 only** | TLS (ACME), HSTS, routes 3 hostnames |
| dashboard | webforge/dashboard:`RELEASE_TAG` | frontend | via `app.<domain>` | Next.js; talks to the API internally |
| api | webforge/api:`RELEASE_TAG` | backend, frontend | `api.<domain>`: only `/webhooks/email/*`, `/u/*`, `/health/live` | staff API reachable only through the dashboard |
| preview | webforge/api:`RELEASE_TAG` | backend, frontend | via `preview.<domain>` | token previews, read-only artifacts |
| worker | webforge/api | backend, frontend | no | discovery, verification, qualification, design, outreach queues |
| worker-audit | webforge/api | backend, sandbox | no | audits, validation, proposal PDFs |
| browser | webforge/browser | sandbox (internal) | no | Chromium sandbox; no secrets, no DB/Redis/API |
| egress-proxy | webforge/api | sandbox, egress | no | the sandbox's only route out; SSRF policy |
| ops | webforge/api | backend, frontend | no | alert checks every 5 min |
| postgres / redis | digest-pinned | backend (internal) | **never** | named volumes `pgdata`, `redisdata` |
| migrate | webforge/api | backend | no | one-off `alembic upgrade head` before app services start |

Compose: `docker compose -f docker-compose.yml -f infrastructure/production/docker-compose.prod.yml` (the `make prod-*`
targets wrap it). Logs: `json-file`, 20 MB × 5 per container.

## 2. First-time server setup (owner + operator)

1. Supported Ubuntu LTS, patched; non-root deploy user with SSH keys; disable password and root SSH **after** the
   non-root login works; firewall: SSH (restricted source) + 80/443; unattended security updates; time sync.
2. Install Docker Engine + Compose plugin from Docker's official repository.
3. DNS: `A`/`AAAA` records for `app`, `api`, `preview` → the VPS IP (values from the VPS console only).
4. Clone the private repository; `python3 infrastructure/scripts/generate-env.py` creates `.env` with fresh secrets.
   Then set at least: `APP_ENV=production`, `APP_URL=https://app.<domain>`, `API_URL=https://api.<domain>`,
   `PREVIEW_BASE_URL=https://preview.<domain>`, `CORS_ALLOWED_ORIGINS=https://app.<domain>`, `COOKIE_SECURE=true`,
   `APP_DOMAIN`, `API_DOMAIN`, `PREVIEW_DOMAIN`, `BACKUP_DIR`, `BACKUP_S3_*`, `ALERT_WEBHOOK_URL`.
   **Copy `BACKUP_ENCRYPTION_KEY` to a password manager off the server** — backups cannot be restored without it.
5. `chmod 600 .env`. Never commit it.
6. `make prod-config` (must print `production compose OK`), then `RELEASE_TAG=$(git rev-parse --short HEAD) make prod-build prod-up`.
7. `docker compose exec -T api python -m webforge_api.cli bootstrap-owner --email <owner email> --name "<name>" --password-stdin`,
   sign in at `https://app.<domain>`, enrol MFA immediately.
8. Confirm the banner shows **System: PAUSED** and **Email: PAUSED** (seeded). Leave email paused.

## 3. Deploy a release

1. CI green for the commit; note the short SHA as `RELEASE_TAG`.
2. Pause outbound work: Settings → Global pause (reason "deploy").
3. `make backup` (with `COMPOSE_FILES="-f docker-compose.yml -f infrastructure/production/docker-compose.prod.yml"`)
   and confirm `Backup complete`.
4. `git fetch && git checkout <tag>`; read `docs/migrations.md` for new migrations.
5. `RELEASE_TAG=<sha> make prod-build` then `RELEASE_TAG=<sha> make prod-up` (migrations run first; `--wait` returns
   only when every service is healthy). Rehearsed: ~30 s.
6. Verify: `make prod-ps`; `curl -fsS https://api.<domain>/health/live`; sign in; Operations page shows workers,
   empty dead letters, backup OK.
7. Resume the global pause (owner). Email stays paused unless every launch gate below is met.

## 4. Roll back

1. Global pause on (and email pause, which should already be on).
2. `RELEASE_TAG=<previous sha> make prod-up` (images for previous tags stay on the host; do not prune them until the
   new release has run for a week). Rehearsed: ~29 s, data and pause state intact.
3. Migrations are forward-only by design. If the new release added a migration that the old code cannot run with,
   do **not** downgrade the schema after writes: either fix forward, or restore the pre-deploy backup (§6) into a
   fresh database after confirming what would be lost.
4. Reconcile: Outreach page (`AMBIGUOUS`/`SCHEDULED`), Jobs page (dead letters), then resume.

## 5. Backups (daily) and restore test (weekly)

- `infrastructure/scripts/backup.sh`: `pg_dump -Fc` + artifacts tar, each encrypted with AES-256-GCM (`WFB1` chunked
  format, `BACKUP_ENCRYPTION_KEY`), SHA-256 manifest, copied to `BACKUP_S3_BUCKET` when set, local retention
  `BACKUP_KEEP_DAYS`, run recorded in `backup_runs`.
- `infrastructure/scripts/restore-test.sh`: verifies checksums, decrypts, restores into a throwaway `restore_check`
  database, checks the migration head, table/user/control counts and the artifacts archive, drops it, records the
  result. A tampered file fails authentication and is recorded as failed (rehearsed).
- Suggested systemd timers (owner installs on the VPS):
  - `webforge-backup.timer`: daily 02:17 UTC → `COMPOSE_FILES=… infrastructure/scripts/backup.sh`
  - `webforge-restore-test.timer`: weekly Sunday 03:17 UTC → `COMPOSE_FILES=… infrastructure/scripts/restore-test.sh`
- Full restore onto a new server: set up per §2 with the same `BACKUP_ENCRYPTION_KEY`, start only `postgres`, create
  the database, `python -m webforge_api.backup decrypt < X.db.enc | docker compose exec -T postgres pg_restore -U … -d … --no-owner`,
  restore artifacts with `decrypt < X.artifacts.enc | tar -x` into the `artifacts` volume, then `make prod-up`.
  Scripted: `COMPOSE_FILES=… make recover [BACKUP=/path/webforge-<stamp>]` does these steps, refuses a non-empty
  database or artifacts volume, and leaves the global and email pauses ON. Then `make prod-up`, `make smoke`,
  `make isolation` and `docker compose … exec -T api python -m webforge_api.provenance_audit`, and resume from
  Settings only after review. Emergency stop from the host: `docker compose … exec -T api python -m
  webforge_api.cli emergency-pause --reason "…"`.

## 6. Alerts

The `ops` service runs every 5 minutes and posts to `ALERT_WEBHOOK_URL` (if set) when any warning/critical fires:
database or Redis unreachable; no live worker for a queue; oldest runnable job > 30 min; new dead letters; budget
≥ 80% / stopped; ≥ 5 provider errors/hour; ≥ 20 failed sign-ins/hour; ≥ 5 webhook signature failures/hour; pause
switch changed; bounce > 5% or complaints > 0.1% (≥ 10 sends/week); no backup in 26 h; no restore test in 8 days;
failed backup/restore; disk > 85%; memory < 10% free; TLS certificate < 14 days or unverifiable.
Manual run: `docker compose … exec -T ops python -m webforge_api.ops_alerts`. Container crashes: `restart:
unless-stopped` plus the "no live worker" alert; external uptime monitoring of `https://api.<domain>/health/live`
is recommended (owner's choice of provider).

## 7. Incidents

| Situation | First actions |
|---|---|
| Complaint/bounce spike, unexpected sends | Email pause (Settings). Inspect Outreach and Replies; suppressions apply immediately. |
| Spend spike | Global pause. Operations → Quotas; lower the budget in `.env`, redeploy. |
| Worker down / queue stale | `make prod-ps`; `docker compose … logs --tail=200 worker`; restart the service. Jobs resume from the queue. |
| Sandbox isolation doubt | Global pause; `make isolation` (must be 8/8) before resuming audits. |
| Suspected secret leak | Rotate in `.env` (`ENCRYPTION_KEY` rotation keeps the old key in `ENCRYPTION_KEY_PREVIOUS`; new JWT/app keys sign everyone out); redeploy; review Activity. |
| Data loss / corruption | Pause; restore per §5 into a new database; verify before switching. |

## 8. Launch gates for live email (all required; currently NOT met)

A provider whose written policy or account approval permits this exact traffic (Resend/Postmark do not); a live
adapter implemented and tested; sender domain with SPF/DKIM/DMARC verified; real postal address where required;
qualified legal review recorded and activated per country + recipient type; external unsubscribe test; webhook
delivery verified from the provider; backups restorable; isolation 8/8; no unresolved critical security findings;
owner approval. Until then `EMAIL_SENDING_ENABLED` stays rejected by configuration.
