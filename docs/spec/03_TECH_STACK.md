# 03 — Technology Stack and Architecture Decisions

## Recommended stack

| Layer | Recommendation | Purpose |
|---|---|---|
| Dashboard | Next.js, React, TypeScript | Owner-facing web UI |
| Styling | Tailwind CSS + accessible components | Consistent design system |
| API | Python + FastAPI + Pydantic | Typed API and validation |
| Database | PostgreSQL + SQLAlchemy + Alembic | Durable relational state and migrations |
| Queue | Redis + Celery | Background workers |
| Browser | Playwright | Responsive screenshots and site audits |
| AI | Anthropic API via adapter | Structured brief generation |
| PDF | Controlled Chromium HTML-to-PDF or maintained library | Branded proposal |
| Storage | S3-compatible object storage / Cloudflare R2 candidate | Screenshots and preview artifacts |
| Reverse proxy | Caddy | Routing and TLS |
| Runtime | Docker Compose | Reproducible initial deployment |
| OS | Supported Ubuntu LTS | VPS |
| Tests | Pytest, Playwright, Vitest/Jest as appropriate | Automated quality gates |

## Important distinction

Claude Code is the development tool. It writes and tests the product. The deployed 24/7 application calls the Anthropic API (or another configured adapter) using a server-side key. Do not keep a Claude Code terminal open as the production process and do not automate/scrape its UI.

## Architecture decisions

1. **Modular monolith + worker pools:** simpler deployment initially; split services only when operationally justified.
2. **Structured AI before rendering:** AI returns schema-validated JSON (design tokens, page map, content blocks); a deterministic renderer maps it to approved components. Avoid arbitrary executable output.
3. **Provider adapters:** isolate LLM, discovery, email, storage, PDF and inbound reply providers.
4. **PostgreSQL is source of truth:** Redis is not permanent business storage.
5. **Compliance-first email:** disabled by default; check eligibility when scheduling and immediately before provider call.

## Version policy

Do not hard-code guessed version numbers into this handoff. At implementation time, choose currently supported stable versions from official sources, pin them in lockfiles/container images, and record actual versions in `docs/versions.md`. Avoid floating `latest` images. Review security advisories before upgrades.

Suggested packages (add only when needed; verify current support): frontend `lucide-react`, `zod`, `react-hook-form`, `@hookform/resolvers`; backend `fastapi`, `uvicorn[standard]`, `sqlalchemy`, `alembic`, `psycopg`, `pydantic-settings`, `celery`, `redis`, `httpx`, `anthropic`, `playwright`, `structlog`, `pytest`, `pytest-asyncio`, `ruff`, and a Python type checker.
