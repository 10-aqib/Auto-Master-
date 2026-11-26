# Implementation Status

| Phase | Name | Status | Email |
|---|---|---|---|
| 00 | Foundation | Complete | Disabled (rejected by config) |
| 01 | Database + auth | Complete | Disabled (rejected by config) |
| 02 | Source adapters | **Complete — awaiting owner review** | Disabled (rejected by config) |
| 03 | Discovery | Not started | Disabled |
| 04 | Website audit | Not started | Disabled |
| 05 | AI intelligence | Not started | Disabled |
| 06 | Design generation | Not started | Disabled |
| 07 | Validation | Not started | Disabled |
| 08 | Proposals | Not started | Disabled |
| 09 | Email/compliance | Not started | Sandbox only |
| 10 | Dashboard/orchestration | Not started | Paused |
| 11 | Production | Not started | Only approved category |

## Phase 02 — Source adapters and data governance (2026-11-26)

### Delivered
- **Policy re-check** of Google Places API (New) docs on 2026-11-26, recorded with URLs and open legal questions in
  `docs/compliance/source-policies.md` (Service Specific Terms page could not be read automatically: owner must read it).
- **Source terms/permission registry** (`source_registrations`, migration 0002): `google_places`, `official_website`,
  `mock_places`, all DISABLED by default. Enabling needs an owner terms review (DB CHECK + service rule). Mock is
  blocked in production.
- **Places connector** (Text Search + Place Details, New API) with fixed minimal field masks, no wildcard, SKU derived
  from the highest field tier, key only in a server-side header.
- **Place IDs only** are persisted (`external_place_identifiers`); all other Maps content is returned transiently and
  shown with "Google Maps" attribution (self-hosted Roboto, `translate="no"`, no wrap) and a link to `googleMapsUri`.
- **Independent verification**: SSRF-safe fetcher (DNS pinned, public IPs only, redirects re-validated, size/time
  limits, TLS verified) and an official-website verifier (robots.txt, parked/off-site/structured-data checks, name
  matching). Prospects are created only from VERIFIED checks, named with the site's own text, with field-level
  provenance (source URL, time, terms version, confidence, method). Domains are never guessed.
- **Provenance rules**: only independent sources can back a stored fact (service rule + DB CHECK).
- **Cost accounting and budgets**: per-SKU owner-configured prices (unpriced = refused), daily budget, daily request cap,
  per-campaign cap, per-minute rate limit, reservation under an advisory lock, SUCCESS/ERROR outcome, 80% warning.
- **Transient cache** limited to registry `cache_rules` (Places: `location` ≤ 30 days), encrypted, with purge.
- **Maintenance CLI**: `refresh-place-ids` (IDs-only, marks obsolete), `purge-transient`.
- **Mocks for CI**: `MockPlacesConnector` and an httpx mock transport for the real connector; CI makes no external calls.
- **Dashboard**: Sources page (registry, review, enable/disable, blockers, budget meters, owner URL check) and Places
  discovery (search, attribution, verify website, stored IDs, recent checks).
- **Docs**: source policies, SSRF defences, ADR 0003, schema/API/migration/version updates, `.env.example`.

### Verification evidence (local run, 2026-11-26)

| Check | Command | Result |
|---|---|---|
| Lint / format | `make lint` | PASS |
| Types | `make typecheck` (mypy strict, 89 files; tsc) | PASS — 0 issues |
| API tests (real PostgreSQL + Redis) | `make test-integration` | PASS — 321 passed, 0 skipped |
| Dashboard tests | `npm test` | PASS — 43 passed (6 files) |
| API tests without a database | `make test` | 184 passed, 137 **skipped** (reported) |
| Dashboard build | `npm run build` | PASS |
| Migrations | upgrade/downgrade 0002↔0001↔base round trip; models = migrations | PASS |
| Compose | `docker compose up --build --wait` | PASS — migrate exited 0, 4 services healthy |
| Smoke | `make smoke` | PASS — 14/14 |
| Browser E2E | `make e2e` | PASS — 20/20 (5 new Phase 02 steps) |
| No Maps-style content persisted | scan of all 30 tables after E2E search + verify | 0 matches |
| API error log lines | grep | 0 |
| Real Google Places call | — | **NOT RUN**: no key or approved budget (by design; mock transport used) |
| CI | GitHub Actions | NOT RUN here — runs on push |

Required Phase 02 tests: field mask required/no wildcard ✔, Place ID persistence ✔, restricted fields not persisted
(whole-database scan) ✔, provenance required ✔, budget/rate limits ✔, key not in frontend/logs/responses ✔,
connectors disabled by default ✔. Plus 55 SSRF/fetcher tests and 21 verifier tests.

### Known issues / notes
- Open legal questions (transient use of `websiteUri`/`displayName` for verification; retention for unverified
  candidate IDs; overall use-case fit) are listed in `docs/compliance/source-policies.md`.
- Website verification runs in the API process for now (homepage + robots.txt only); moves to a queued worker in
  Phase 03 and to an isolated network in Phase 04.
- Minimal dedupe only (reuse a prospect with the same verified domain); full dedupe/branches in Phase 03.
- `make e2e` needs a fresh database (it bootstraps the owner).

### Owner actions before using Google Places for real
1. Read the Service Specific Terms and confirm the use case (see open questions).
2. Create a restricted API key (Places API (New) only, server IP), set budgets/alerts in Google Cloud.
3. Fill `GOOGLE_MAPS_API_KEY`, `GOOGLE_PLACES_SKU_PRICES_MINOR_PER_1000` (current prices), daily budget, caps,
   then `GOOGLE_PLACES_API_ENABLED=true`.
4. Record the terms review in Sources and enable the source.

### Next phase
Phase 03 — Discovery, campaigns, dedupe, qualification and jobs (`docs/spec/PHASE_PROMPTS/PHASE_03_DISCOVERY.md`).
Requires owner approval to start.

## Phase 01 — Database, migrations and secure authentication (2026-11-26)

### Delivered
- **Schema:** migration `0001` creates all 24 spec tables plus `user_sessions` and `mfa_recovery_codes`
  (UUID keys, UTC `timestamptz`, FKs with deliberate delete rules, CHECK/unique constraints, indexes).
  Business tables are staged for later phases. See `docs/architecture/schema.md` and `docs/migrations.md`.
- **Append-only activity log** enforced by database triggers (UPDATE, DELETE and TRUNCATE blocked).
- **Owner bootstrap:** one-time CLI (`make owner`), no default password, single-OWNER DB constraint.
- **Auth:** Argon2id, password policy, signed 15-minute access tokens, rotating hashed refresh tokens with
  reuse detection, 30-day absolute session limit, logout / logout-all / per-session revoke, forced
  password change for admin-created accounts.
- **MFA:** TOTP enrolment with QR, replay protection, 10 single-use recovery codes, required for
  OWNER/ADMIN, owner can reset another user's MFA.
- **RBAC:** OWNER, ADMIN, REVIEWER, READ_ONLY with tested allow/deny for every route; session-state gating.
- **Web security:** HttpOnly SameSite=Lax cookies (`__Host-` + Secure in production), session-bound CSRF
  token, Origin allow-list, login rate limits per IP and per account (Redis, fail closed), account lockout,
  generic errors that never echo input.
- **Encryption utility:** AES-256-GCM with column-bound associated data and key fingerprints for rotation;
  keyed lookup hashes for emails/IPs.
- **Retention interfaces:** session purge, contact deletion and prospect erasure that never remove suppressions.
- **Dashboard:** login, MFA verify and enrolment, forced password change, account security (password, MFA,
  recovery codes, sessions), user administration and activity log; same-origin API proxy and automatic
  token refresh. Every control performs a real action.
- **Contract:** `packages/contracts/openapi.json` (test fails if stale). API reference: `docs/api/README.md`.
- **Ops:** Compose `migrate` one-shot service; `make env` generates real secrets; `make test-integration`
  with throwaway Postgres/Redis; browser E2E test (`make e2e`); CI runs DB tests (required) and the E2E flow.
- **Docs:** `docs/security/authentication.md`, `docs/compliance/retention.md`, ADR 0002, updated
  `.env.example`, versions and architecture.

### Verification evidence (local run, 2026-11-26)

| Check | Command | Result |
|---|---|---|
| Install | `make install` | PASS |
| Lint / format | `make lint` (ruff, eslint, prettier) | PASS |
| Types | `make typecheck` (mypy strict, 66 files; tsc strict) | PASS — 0 issues |
| API tests (real PostgreSQL 18 + Redis 8) | `make test-integration` | PASS — 193 passed, 0 skipped |
| Dashboard tests | `npm test` | PASS — 37 passed (5 files) |
| API tests without a database | `make test` | 85 passed, 108 **skipped** (reported, not counted as passed) |
| Dashboard production build | `npm run build` | PASS — 10 routes + proxy |
| Compose | `make compose-config`, `docker compose up --build --wait` | PASS — migrate exited 0, 4 services healthy |
| Smoke | `make smoke` | PASS — 14/14 |
| Browser E2E | `make e2e` (Chromium) | PASS — 15/15 steps |
| Log hygiene | grep API logs for test passwords/emails; error lines | 0 matches; 0 errors |
| CI | GitHub Actions | NOT RUN here — runs on push |

Test coverage by area: migrations (empty DB upgrade, downgrade/upgrade round trip, models = migrations),
password hashing/policy, login/logout/revocation, refresh rotation/reuse/grace/expiry/absolute limit, MFA
enrolment/verify/replay/recovery/expiry/disable rules, RBAC matrix (28 role×route cases) and forged/`alg:none`
tokens, CSRF and Origin, rate limiting (IP, account, MFA, limiter outage), lockout, activity-log redaction and
append-only triggers, FK/unique/check constraints, UTC handling, encryption/rotation, retention, bootstrap CLI,
client-IP trust, dashboard redirect safety, proxy path/header filtering.

### Known issues / notes
- Migration `0001` was regenerated during this phase (never applied outside development). From now on,
  schema changes must be new revisions.
- CSP still allows inline scripts; nonce-based CSP is planned for Phase 10 (ADR 0002).
- Per-IP login limiting sees the dashboard as the client until Caddy supplies a trusted
  `X-Forwarded-For` (Phase 11). Per-account limits and lockout are fully effective now.
- Starlette's `httpx` test-client deprecation warning remains (harmless).

### Security observations
- No secrets, real customer data or default credentials in the repository.
- Tokens, recovery codes and MFA secrets are stored only as HMACs or ciphertext.
- `LOOKUP_HASH_KEY` must never be rotated without re-hashing; documented in the auth design.

### Next phase
Phase 02 — Source adapters and data governance (`docs/spec/PHASE_PROMPTS/PHASE_02_SOURCE_ADAPTERS.md`).
Requires owner approval to start.

## Phase 00 — Foundation (2026-11-26)

### Delivered
- Monorepo: `apps/api` (FastAPI), `apps/dashboard` (Next.js), `infrastructure/`, `docs/`. Deviations: ADR 0001.
- Validated settings module covering every variable in `.env.example`; production fail-fast; risky
  capabilities rejected until implemented.
- Structured JSON logging with request/correlation IDs and secret/PII redaction.
- `GET /health/live` and `GET /health/ready` (real PostgreSQL `SELECT 1` and Redis `PING`, bounded timeouts,
  503 when not ready, error class only — no driver messages).
- Dashboard system-status page showing live API readiness, `/health` route, security headers.
- Docker Compose: PostgreSQL 18, Redis 8 (password), API, dashboard; healthchecks; named volumes;
  internal backend network; no DB/Redis host ports; API/dashboard bound to 127.0.0.1; non-root,
  read-only containers with all capabilities dropped and `no-new-privileges`.
- GitHub Actions CI: API lint/format/types/tests; dashboard lint/format/types/tests/build; Docker stack
  smoke test. Actions pinned by SHA; read-only token permissions.
- Makefile: `help env install dev up down logs ps smoke lint format typecheck test build compose-config clean`.
- Docs: versions, architecture overview, ADR 0001, this status file.

### Verification evidence (local run, 2026-11-26)

| Check | Command | Result |
|---|---|---|
| API deps | `uv sync --frozen` | PASS |
| API format | `uv run ruff format --check .` | PASS |
| API lint | `uv run ruff check .` | PASS |
| API types | `uv run mypy` (strict) | PASS — 13 files, 0 issues |
| API tests | `uv run pytest` | PASS — 44 passed |
| Dashboard deps | `npm ci` | PASS |
| Dashboard lint | `npm run lint` / `npm run format:check` | PASS |
| Dashboard types | `npm run typecheck` | PASS |
| Dashboard tests | `npm test` | PASS — 13 passed (3 files) |
| Dashboard build | `npm run build` | PASS (`/` partial prerender, `/health` dynamic) |
| Compose config | `docker compose config --quiet` | PASS |
| Images | `docker compose build` | PASS (see known issues for sandbox proxy note) |
| Stack start | `docker compose up -d --wait` | PASS — all 4 services healthy |
| Smoke | `infrastructure/scripts/smoke.sh` | PASS — 9/9 |
| Degraded state | stop redis → dashboard | PASS — shows "Degraded", Redis "Failed (ConnectionError)", API 503 |
| Browser check | Playwright, 1280px and 390px | PASS — no console errors, no horizontal overflow |
| Shutdown | `docker compose down` | PASS |
| CI workflow | GitHub Actions | NOT RUN here — runs on push |

### Known issues / notes
- The verification sandbox reaches registries through a TLS-intercepting proxy, so images were built
  there with a local, uncommitted override that adds the proxy CA. The committed Dockerfiles are
  unchanged and need no override on a normal machine or in CI.
- Starlette prints a deprecation warning about `httpx` in its test client; harmless, tracked for upgrade.
- CSP allows inline scripts until nonce-based CSP lands with auth (Phase 01). See ADR 0001.

### Security observations
- No secrets in the repository; `.env` is Git-ignored and created with mode 600.
- PostgreSQL and Redis are unreachable from the host and have no internet route.
- Readiness and error responses never include driver messages, hostnames or credentials.
- Request IDs from callers are validated before being logged or echoed (no header/log injection).

### Next phase
Phase 01 — Database, migrations and secure authentication (`docs/spec/PHASE_PROMPTS/PHASE_01_DATABASE_AUTH.md`).
Requires owner approval to start.
