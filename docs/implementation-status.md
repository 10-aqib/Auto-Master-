# Implementation Status

| Phase | Name | Status | Email |
|---|---|---|---|
| 00 | Foundation | **Complete — awaiting owner review** | Disabled (rejected by config) |
| 01 | Database + auth | Not started | Disabled |
| 02 | Source adapters | Not started | Disabled |
| 03 | Discovery | Not started | Disabled |
| 04 | Website audit | Not started | Disabled |
| 05 | AI intelligence | Not started | Disabled |
| 06 | Design generation | Not started | Disabled |
| 07 | Validation | Not started | Disabled |
| 08 | Proposals | Not started | Disabled |
| 09 | Email/compliance | Not started | Sandbox only |
| 10 | Dashboard/orchestration | Not started | Paused |
| 11 | Production | Not started | Only approved category |

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
