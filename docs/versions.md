# Pinned Versions

Recorded 2026-11-26 (Phase 00), updated for Phases 01–02. Versions are pinned exactly in lockfiles, `pyproject.toml`,
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
| Playwright (browser sandbox) | 1.63.0 (`mcr.microsoft.com/playwright/python:v1.63.0-noble`, Chromium build 1243) | `infrastructure/docker/browser.Dockerfile`, `apps/browser/pyproject.toml` |
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
| anthropic (Claude API SDK, Phase 05) | 2.14.0 |
| httpx2 (transitive via anthropic; also used by Starlette TestClient) | 2.16.2 |
| psycopg[binary] | 3.3.9 |
| redis | 8.2.0 |
| sqlalchemy | 2.1.9 |
| alembic | 1.20.1 |
| argon2-cffi | 25.1.0 |
| pyjwt | 2.15.1 |
| pyotp | 2.12.1 |
| cryptography | 50.0.2 |
| segno (QR codes) | 1.6.6 |
| httpx (runtime: Places connector) | 0.28.1 |
| httpcore (SSRF-safe fetcher) | 1.0.9 |
| idna | 3.20 |
| boto3 (S3 storage) | 1.44.12 |
| moto (dev, S3 tests) | 5.2.6 |
| pytest / pytest-asyncio | 9.2.0 / 1.5.0 |
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
| @fontsource/roboto (attribution font, self-hosted) | 5.3.0 |

TypeScript 7 (native port) was available but not chosen: Next.js tooling targets 5.x.
ESLint 9 is used because `eslint-config-next` 16.4.6 is generated against it.

## End-to-end tests — `tests/e2e/package-lock.json`

| Package | Version |
|---|---|
| playwright | 1.63.0 |

## CI actions (pinned by commit SHA)

| Action | Version | SHA |
|---|---|---|
| actions/checkout | v7.0.1 | `3d3c42e5aac5ba805825da76410c181273ba90b1` |
| actions/setup-node | v6.5.0 | `249970729cb0ef3589644e2896645e5dc5ba9c38` |
| astral-sh/setup-uv | v8.3.2 | `11f9893b081a58869d3b5fccaea48c9e9e46f990` |

## AI model (Phase 05)

Default model and prices checked 2026-11-26: `DEFAULT_MODEL` and `PRICES_MINOR_PER_MTOK` in
`apps/api/src/webforge_api/services/ai.py` (input/output USD per million tokens). Unknown models are priced at
the highest listed rate. Override the model with `ANTHROPIC_MODEL`; re-check prices before raising budgets.
