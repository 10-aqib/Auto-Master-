# ADR 0012 — Phase 11 Production Topology, Backups, Alerts and Release Gates

- Status: Accepted
- Date: 2026-11-27

1. **Override, not a second stack.** `infrastructure/production/docker-compose.prod.yml` layers on the hardened base
   Compose file: adds Caddy (the only public entry, 80/443), removes every other host port with `!reset`, tags app
   images with `RELEASE_TAG` (rollback = previous tag), adds memory/PID limits, log rotation and the `ops` service.
2. **Three hostnames.** `app.` → dashboard; `api.` → only `/webhooks/email/*`, `/u/*`, `/health/live` (the staff
   API is reachable only through the dashboard); `preview.` → preview service. Caddy adds HSTS and strips `Server`.
   Production config refuses http URLs and a preview origin equal to the app/API host.
3. **Digest pinning** for every base image (tag + sha256) in Dockerfiles, Compose, the test Compose file and CI.
4. **Runtime hardening** found by image scanning: OS security updates at build; pip, npm/npx/corepack, virtualenv
   and the base image's pip cache removed from runtime images (none are used at runtime). Result: 0 fixable
   HIGH/CRITICAL; unfixed upstream advisories are tracked in the release report.
5. **Backups** are encrypted by our own code (AES-256-GCM chunked `WFB1`, authenticated chunk index + final flag) with
   a dedicated `BACKUP_ENCRYPTION_KEY`, so storage providers never see plaintext and a restore needs only that key.
   A weekly automated **restore test** proves restorability; results are stored in `backup_runs` (migration `0009`)
   and shown in Operations.
6. **Alerts** run in-process every 5 minutes (`ops` service) and post to an owner-controlled HTTPS webhook; email is
   not used for alerts because outbound email is disabled.
7. **Release gates.** Live email remains impossible by configuration until every launch gate in the runbook is met;
   the release report gives a GO only for a mail-free internal pilot once owner inputs exist.
