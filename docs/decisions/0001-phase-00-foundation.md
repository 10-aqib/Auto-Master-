# ADR 0001 — Phase 00 Foundation Layout and Tooling

- Status: Accepted
- Date: 2026-11-26

## Context

The handoff package (`docs/spec/`) defines a target monorepo (`04_REPOSITORY_LAYOUT.md`) and stack
(`03_TECH_STACK.md`). Phase 00 must produce a runnable, tested foundation without business features.

## Decisions

1. **Handoff specs live in `docs/spec/`.** The numbered specs, phase prompts, checklists and templates
   are kept verbatim there so the repository root stays a normal project root. `CLAUDE.md` stays at the root.
2. **Only directories with real content are created.** `workers/`, `packages/`, `apps/preview/`,
   `infrastructure/{caddy,monitoring,backup}` and `tests/{integration,e2e,security,acceptance}` are created
   by the phase that fills them. Empty placeholder folders would imply work that does not exist.
3. **Tests live next to each app** (`apps/api/tests`, `apps/dashboard/src/**/*.test.ts[x]`) for unit tests;
   the root `tests/` tree is reserved for cross-service suites from Phase 03 onward.
   `infrastructure/scripts/smoke.sh` is the stack-level smoke test.
4. **Python tooling:** uv (lockfile `uv.lock`), Ruff for format + lint, mypy `--strict`, pytest.
5. **Frontend tooling:** npm with `package-lock.json`, ESLint (`eslint-config-next`), Prettier, `tsc` strict
   via `next typegen && tsc --noEmit`, Vitest + Testing Library, Tailwind CSS 4.
6. **Fail-closed configuration.** `EMAIL_SENDING_ENABLED=true` and `GOOGLE_PLACES_API_ENABLED=true` are
   rejected at startup until Phases 09 and 02 implement their safeguards. Only the `mock` email provider
   value is accepted. Production refuses missing, placeholder, short or reused secrets, a non-32-byte
   `ENCRYPTION_KEY`, placeholder DB/Redis passwords, `LOG_LEVEL=DEBUG` and non-HTTPS public URLs.
   OpenAPI docs are disabled in production.
7. **Redis requires a password even in development**, so the same connection code works in every
   environment and an accidental exposure is not an open Redis.
8. **Dashboard calls the API server-side** using `API_INTERNAL_URL`; no `NEXT_PUBLIC_*` variables exist.
   The status panel uses `connection()` so it is never captured at build time.
9. **System font stack** instead of `next/font/google`, so builds need no font download and the CSP
   can restrict `font-src` to `'self'`.

## Consequences

- CSP still allows `'unsafe-inline'` scripts (needed by Next.js hydration without nonces). A nonce-based
  CSP is planned alongside authentication in Phase 01.
- Container images are pinned by tag, not digest. Digest pinning is a Phase 11 task.
- Redis runs without TLS and with a single password; ACLs and TLS are evaluated in Phase 11.
