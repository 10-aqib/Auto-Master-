# WEBFORGE AI

Internal platform for Muhammad Aqib (Website Developer) to discover business prospects, audit their
public websites, create independent redesign concepts, prepare proposals and run legally eligible
outreach. It is being built in 12 controlled phases.

**Current state: Phase 00 (foundation) complete.** No business features, external API calls or email
sending exist yet. See [`docs/implementation-status.md`](docs/implementation-status.md).

## Stack

Next.js + TypeScript dashboard · FastAPI + Pydantic API · PostgreSQL · Redis · Docker Compose.
Pinned versions: [`docs/versions.md`](docs/versions.md).

## Quick start

Requirements: Docker Engine with Compose v2, Node.js 22, Python 3.13, [uv](https://docs.astral.sh/uv/), GNU Make.

```bash
make env        # creates .env from .env.example (mode 600)
```

Edit `.env` and replace every `CHANGE_ME` (Postgres and Redis passwords must match their URLs).

```bash
make install    # API + dashboard dependencies from lockfiles
make dev        # build and start the stack; waits until healthy
make smoke      # verify health, readiness and closed ports
```

- Dashboard: http://127.0.0.1:3000
- API health: http://127.0.0.1:8000/health/ready
- API docs (non-production only): http://127.0.0.1:8000/docs

Stop with `make down`. Run `make help` for every command.

## Quality checks

```bash
make lint && make typecheck && make test
```

CI runs the same checks plus a production build and a full Docker stack smoke test.

## Repository layout

```text
apps/api/             FastAPI service (src/webforge_api, tests)
apps/dashboard/       Next.js dashboard
infrastructure/       Dockerfiles and scripts
docs/                 status, versions, architecture, ADRs
docs/spec/            product handoff: specs, phase prompts, checklists
.github/workflows/    CI
```

## Safety defaults

External email sending and Google Places discovery are rejected by configuration until their phases
implement the required safeguards. Global and email pause default to on. See `CLAUDE.md` and
`docs/spec/` for the full rules.
