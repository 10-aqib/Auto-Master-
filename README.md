# WEBFORGE AI

Internal platform for Muhammad Aqib (Website Developer) to discover business prospects, audit their
public websites, create independent redesign concepts, prepare proposals and run legally eligible
outreach. It is being built in 12 controlled phases.

**Current state: Phase 02 (source adapters and data governance) complete.** Accounts, MFA, roles, the
activity log, a data-source registry, a policy-safe Google Places connector (Place IDs only) and independent
website verification work end to end. All sources start disabled; email sending does not exist yet. See
[`docs/implementation-status.md`](docs/implementation-status.md).

## Stack

Next.js + TypeScript dashboard · FastAPI + Pydantic API · PostgreSQL · Redis · Docker Compose.
Pinned versions: [`docs/versions.md`](docs/versions.md).

## Quick start

Requirements: Docker Engine with Compose v2, Node.js 22, Python 3.13, [uv](https://docs.astral.sh/uv/), GNU Make.

```bash
make env        # creates .env with fresh random secrets (mode 600)
make install    # API + dashboard dependencies from lockfiles
make dev        # build, migrate and start the stack; waits until healthy
make smoke      # verify health, readiness, auth gating and closed ports
make owner EMAIL=you@yourdomain NAME="Muhammad Aqib"   # one-time; prompts for a password
```

Open the dashboard, sign in and set up two-factor authentication (required for the owner).

- Dashboard: http://127.0.0.1:3000
- API health: http://127.0.0.1:8000/health/ready
- API docs (non-production only): http://127.0.0.1:8000/docs

Stop with `make down`. Run `make help` for every command.

## Quality checks

```bash
make lint && make typecheck
make test-integration   # starts throwaway Postgres/Redis; runs every API and dashboard test
make e2e                # browser end-to-end console flow against `make dev` (fresh database)
```

`make test` runs without a database and reports the database tests as skipped. CI runs everything,
including a production build, the Docker smoke test and the browser end-to-end flow.

## Repository layout

```text
apps/api/             FastAPI service (src/webforge_api, tests)
apps/dashboard/       Next.js dashboard
packages/contracts/   generated OpenAPI contract (make contracts)
infrastructure/       Dockerfiles, test services and scripts
tests/e2e/            browser end-to-end tests
docs/                 status, versions, architecture, API, security, ADRs
docs/spec/            product handoff: specs, phase prompts, checklists
.github/workflows/    CI
```

## Safety defaults

External email sending and Google Places discovery are rejected by configuration until their phases
implement the required safeguards. Global and email pause default to on. See `CLAUDE.md` and
`docs/spec/` for the full rules.
