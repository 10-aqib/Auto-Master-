# PHASE 00 — Foundation and Repository Setup

Paste this entire prompt into Claude Code from the project root.

You are implementing Phase 00 of WEBFORGE AI. First read `CLAUDE.md`, `README.md`, `00_PROJECT_OVERVIEW.md`, `02_SYSTEM_ARCHITECTURE.md`, `03_TECH_STACK.md`, `04_REPOSITORY_LAYOUT.md`, `13_DEVELOPMENT_SETUP.md`, `14_ENVIRONMENT_VARIABLES.md` and `19_ACCEPTANCE_CRITERIA.md`.

## Objective
Create a clean, runnable development foundation. Do not implement prospect discovery, AI generation, live email, external provider calls or business workflows in this phase.

## Required work
1. Inspect current files and Git status before modifying anything.
2. Create monorepo per `04_REPOSITORY_LAYOUT.md`; record justified deviations in an ADR.
3. Set up Next.js + strict TypeScript dashboard skeleton and FastAPI API skeleton using currently supported stable versions. Pin dependencies/containers and record actual versions in `docs/versions.md`.
4. Configure Python formatter/linter/type-check/test tools and frontend lint/type-check/test/build scripts.
5. Add local Docker Compose with PostgreSQL, Redis, API and dashboard; add healthchecks and named volumes; DB/Redis must not be publicly exposed.
6. Add `/health/live` and `/health/ready`; readiness checks only real dependencies that exist.
7. Add structured logging with request/correlation IDs and redaction. Never log secrets or PII.
8. Add validated settings module and complete `.env.example`; production must fail fast on missing required settings.
9. Add `.gitignore` for `.env`, virtualenvs, node_modules, build outputs, Playwright traces, private generated artifacts, keys and local DB files.
10. Add CI workflow for dependency install, lint, type checks, tests and build, with lockfiles.
11. Add Makefile or scripts for help/dev/down/lint/typecheck/test/build/logs/clean.
12. Create `docs/implementation-status.md`, `docs/versions.md`, initial architecture diagram and Phase 00 ADR.
13. Add health smoke test and configuration tests.

## Constraints
- No live API calls, no emails, no secrets and no production resources.
- No fake integration or placeholder page that looks functional.
- No public PostgreSQL/Redis ports.
- Keep the foundation understandable and maintainable.

## Verification
Run and report exact results for dependency installation, lint, type-check, tests, frontend production build, Compose config validation, service start, health checks and shutdown. If Docker is unavailable, mark the checks NOT RUN and provide commands; do not claim success.

## Deliverable
Working Phase 00 foundation, actual versions, commands/results, known issues, security observations and next phase. **Stop after Phase 00. Do not start Phase 01.**
