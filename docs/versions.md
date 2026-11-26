# Pinned Versions

Recorded 2026-11-26 (Phase 00). Versions are pinned exactly in lockfiles, `pyproject.toml`,
`package.json`, Dockerfiles, Compose and CI. Never use floating `latest` tags. Review security
advisories before upgrading and update this file in the same change.

## Runtimes and images

| Component | Version | Pinned in |
|---|---|---|
| Python | 3.13.18 (`python:3.13.18-slim-trixie`) | `infrastructure/docker/api.Dockerfile`, `pyproject.toml` (`>=3.13,<3.14`) |
| uv | 0.11.32 (`ghcr.io/astral-sh/uv:0.11.32`) | API Dockerfile, CI |
| Node.js | 22.23.5 LTS (`node:22.23.5-bookworm-slim`) | dashboard Dockerfile, CI, `package.json` engines |
| PostgreSQL | 18.7 (`postgres:18.7-alpine3.24`) | `docker-compose.yml` |
| Redis | 8.12.0 (`redis:8.12.0-alpine3.23`) | `docker-compose.yml` |
| Docker Engine / Compose (dev host used for verification) | 29.9.3 / v5.7.1 | not pinned |

Image digests are not pinned yet; digest pinning is a Phase 11 production-hardening task.

## API (Python) — `apps/api/uv.lock`

| Package | Version |
|---|---|
| fastapi | 0.165.0 |
| starlette (transitive) | 1.10.0 |
| uvicorn[standard] | 0.54.0 |
| pydantic | 2.14.4 |
| pydantic-settings | 2.16.3 |
| structlog | 26.1.0 |
| psycopg[binary] | 3.3.9 |
| redis | 8.2.0 |
| pytest / pytest-asyncio | 9.2.0 / 1.5.0 |
| httpx (test client) | 0.28.1 |
| ruff | 0.17.6 |
| mypy | 2.4.1 |

## Dashboard (Node) — `apps/dashboard/package-lock.json`

| Package | Version |
|---|---|
| next | 16.4.6 |
| react / react-dom | 19.3.1 |
| typescript | 5.9.3 |
| tailwindcss / @tailwindcss/turbopack | 4.3.5 |
| eslint / eslint-config-next | 9.39.5 / 16.4.6 |
| vitest | 5.1.2 |
| @testing-library/react | 16.3.3 |
| jsdom | 31.0.1 |
| prettier | 3.10.1 |

TypeScript 7 (native port) was available but not chosen: Next.js tooling targets 5.x.
ESLint 9 is used because `eslint-config-next` 16.4.6 is generated against it.

## CI actions (pinned by commit SHA)

| Action | Version | SHA |
|---|---|---|
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/setup-node | v6.5.0 | `249970729cb0ef3589644e2896645e5dc5ba9c38` |
| astral-sh/setup-uv | v8.3.2 | `11f9893b081a58869d3b5fccaea48c9e9e46f990` |
