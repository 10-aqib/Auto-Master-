# WEBFORGE AI — Release Report (Phases 00–11)

- Date: 2026-11-27
- Branch: `claude/gifted-meitner-ozj5y9`
- Scope: everything that can be built and verified without the owner's VPS, domain, provider accounts or legal
  review. Steps that need those are listed as **NOT RUN** with the reason.

## Recommendation

| Decision | Verdict | Why |
|---|---|---|
| Deploy to a VPS for an **internal, mail-free pilot** (discovery with budgets, audits, briefs, concepts, validation, proposals, previews) | **GO, once the owner supplies the inputs in §6** | All automated gates pass; production topology, TLS routing, isolation, backups + restore and deploy/rollback were rehearsed locally in production mode. |
| **Live email outreach** | **NO-GO** | No provider permits this traffic (Resend and Postmark prohibit unsolicited email); no live adapter exists; no legally reviewed country policy is active; sender domain, mailbox and postal address are not supplied. Live sending is rejected by configuration. |
| Claim "production-ready" | **No** | The production environment itself (VPS, DNS, real TLS, off-site storage, real APIs) has not been exercised. |

## 1. Versions

Runtimes and libraries: `docs/versions.md`. Base images are pinned by tag **and digest**:

| Image | Digest |
|---|---|
| postgres:18.7-alpine3.24 | sha256:0115267ab5a509022df9319c77be365cef335adb71556c75f60f5360ee247e71 |
| redis:8.12.0-alpine3.23 | sha256:5af80107c1eeecb484a2269b80a26d12bfa6521787da4663bd9f19f60a163483 |
| python:3.13.18-slim-trixie | sha256:7249d5587b78209a006dc4a3b5340678f84ea729239193aa559962cd8c1fce50 |
| node:22.23.5-bookworm-slim | sha256:be979e5523c76fa4d5ca4ebd3099078f220aa47ec39c48ad5b5df9314debd6eb |
| mcr.microsoft.com/playwright/python:v1.63.0-noble | sha256:72bd171a9ffc2b4b59532aaa6210e21014d07093120dc25528870c0b840da1f0 |
| ghcr.io/astral-sh/uv:0.11.32 | sha256:df4cae8f3a96d175e2e5f992e597550000edbe78fdc2594d5cd8de1a217f504c |
| caddy:2.11.9-alpine | sha256:003a97808e781aa9f7e75cc2f43d34d461099031faf5e20faefb9f61126836f0 |

Database migrations: `0001`–`0009`, each upgrade/downgrade round-trip tested; model/migration drift check clean.

## 2. Test evidence (local runs, 2026-11-27)

| Suite | Result |
|---|---|
| API (pytest, real PostgreSQL 18 + Redis 8) | PASS — 500 passed |
| Browser sandbox (real Chromium) | PASS — 22 passed |
| Dashboard (Vitest, ESLint, `tsc --noEmit`, production build) | PASS — 51 tests, lint/types clean, build OK |
| Docker stack (9 services, dev) | all healthy |
| Smoke (`make smoke`) | PASS 19/19 |
| Isolation proof from inside the sandbox (`make isolation`) | PASS 8/8 (dev and production mode) |
| Browser E2E (`tests/e2e/console-flow.mjs`) — sign-in/MFA, users, sources, campaigns, discovery, brief, render, validation (293 checks × real Chromium), proposal PDF, preview on separate origin, compliance gate with mock send, reply, unsubscribe, dashboard, keyboard, 390 px layout | PASS 30/30 |
| Error-level log lines across all services after E2E | 0 |

One defect was found and fixed in the final run: the sandbox validator could hang when a bad demo form navigated on
Enter (the follow-up button click waited for a form that was gone). Interactions are now bounded; the validator
tests passed three times in a row afterwards.

## 3. Security review

| Check | Tool / method | Result |
|---|---|---|
| Secrets in Git history | gitleaks 8.30.1 (`.gitleaks.toml`) | 0 findings. 6 raw hits were fake test-fixture passwords and one spec sentence; allowlisted by path only. |
| Secrets in working tree | gitleaks `dir` | Only the git-ignored local `.env` and Next.js per-build server-only keys under `.next/server` (not shipped to browsers; the app uses neither preview mode nor server actions). |
| Client bundle | grep of `.next/static` for secret names, internal hosts, test credentials; source maps | none found; no source maps emitted |
| Python dependencies | pip-audit 2.10.0 (API + sandbox lockfiles) | 0 known vulnerabilities after upgrading **pypdf 6.1.3 → 7.2.0** (the earlier pin had 97 advisories) |
| npm dependencies | `npm audit` (dashboard prod + all, E2E) | 0 vulnerabilities |
| Container images | Trivy 0.69.1, HIGH/CRITICAL | **0 fixable** in all three images after hardening (OS security updates at build; pip/npm/virtualenv and the base image's pip cache removed from runtimes). Remaining **unfixed upstream**: API 53 HIGH (util-linux family, Debian `affected`/`fix_deferred`), sandbox 2 HIGH (gstreamer plugins), dashboard 34 HIGH + 1 CRITICAL (`zlib1g` CVE-2023-45853, minizip, Debian `will_not_fix`; not used by the app). Re-scan monthly and on every base-image update. |
| SSRF / network isolation | `make isolation` (8 probes from inside the sandbox) + SSRF unit tests | PASS |
| Preview isolation | separate origin and service, sandbox CSP, token hash only, uniform 404, rate limit | PASS (tests + E2E + production-mode curl checks) |
| Production routing | curl through Caddy (`tls internal`, `*.webforge.localhost`) | app 200 + HSTS; HTTP→HTTPS 308; API host serves only webhooks/unsubscribe/liveness (staff API and docs 404); unsigned webhook 403; Postgres/Redis/API/dashboard/preview ports closed on the host; only 80/443 published |
| AI output | strict schema + integrity checks; mock provider refused in production | PASS (tests) |

## 4. Backup and restore evidence

| Step | Result |
|---|---|
| `backup.sh` (dev stack with E2E data) | encrypted DB + artifacts, 4.2 MB, `WFB1` header, no plaintext visible, recorded in `backup_runs` |
| `restore-test.sh` | checksums OK; restored into `restore_check`; migration head `0009`, 37 tables, 2 users, 33 artifact entries; dropped; recorded `ok` |
| Tampered backup | decryption failed authentication; restore test exited 1 and recorded `failed`; ops alert `backup_failed` (critical) fired |
| Production mode | backup + restore test passed again under the production Compose files |
| Off-site copy | **NOT RUN** — `BACKUP_S3_*` not supplied (script warns and records `local:`) |

## 5. Deploy / rollback rehearsal (production mode, local)

`APP_ENV=production` with all production config checks active; Caddy with internal TLS; images tagged `r1`/`r2`.
Bootstrap owner OK; `RELEASE_TAG=r2 up -d --wait` → healthy in 30 s; rollback `RELEASE_TAG=r1` → healthy in 29 s;
users and pause switches (global + email ON) preserved; `ops` alerts ran (only expected local TLS-resolution
warnings). One defect found and fixed during rehearsal: the `ops` service inherited the API's HTTP healthcheck.

## 6. Missing owner inputs (blocking production)

From `docs/spec/CHECKLISTS/OWNER_INPUTS_BEFORE_PRODUCTION.md`: domain + DNS access; VPS (provider, region, IP,
budget), SSH key and non-root user; off-site backup bucket and credentials; alert webhook; Anthropic API key and
daily budget (until then the mock brief model is used in development only); Google Places key, SKU prices and
budgets if discovery uses Places; professional mailbox, sender domain with SPF/DKIM/DMARC, postal address,
**an email provider that permits this traffic**, qualified legal review per target country and recipient type,
privacy notice and retention approval.

## 7. NOT RUN (needs the owner's environment)

Ubuntu/firewall/SSH hardening on the VPS; DNS and real ACME certificates; real Places calls; real Claude calls;
real public-website audits (TLS interception in this build environment blocks them); off-site backup upload;
external uptime monitoring; provider sandbox/webhooks; supervised pilot with real recipients; automatic mode.

## 8. Unresolved risks

1. **Outreach legality and provider permission** — the core business risk; live email stays disabled by design.
2. Unfixed upstream OS advisories in base images (§3) — monitor; rebuild on base-image releases.
3. Single-VPS deployment: no high availability; recovery depends on off-site backups (not yet configured).
4. Browser sandbox resource limits are estimates; measure under real audits before raising concurrency.
5. Next.js embeds per-build server-side keys in the image; acceptable while preview mode and server actions are
   unused — treat images as confidential and do not publish them.
