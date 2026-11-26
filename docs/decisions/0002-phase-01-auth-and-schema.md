# ADR 0002 — Phase 01 Schema, Authentication and Dashboard Session Model

- Status: Accepted
- Date: 2026-11-26

## Decisions

1. **Full schema in one initial migration (0001).** All 24 spec tables plus `user_sessions` and
   `mfa_recovery_codes` are created now so later phases add columns rather than reshape relationships.
   Business tables are staged: no endpoints use them until their phase.
2. **Synchronous SQLAlchemy 2 + psycopg 3.** Route handlers are plain `def` (run in FastAPI's threadpool).
   Simpler transactions and testing than async ORM at this scale; health checks stay async.
3. **Enums as VARCHAR + CHECK**, with database defaults, instead of native PostgreSQL enums (painless migrations).
4. **Hybrid tokens.** Short signed access tokens (PyJWT, HS256) plus opaque, hashed, rotating refresh tokens
   stored in `user_sessions`. The session row is checked on every request, giving immediate revocation.
5. **Cookie auth through a same-origin dashboard proxy.** The browser only talks to the dashboard origin;
   `src/app/api/v1/[...path]` forwards an allow-list of headers to the API, and `src/proxy.ts` refreshes
   expired access tokens before pages render. This avoids cross-site cookies and CORS credentials.
6. **CSRF:** session-bound HMAC token (double submit) + Origin allow-list.
7. **Single OWNER, created by CLI only.** The API cannot create or assign OWNER.
8. **MFA required for OWNER and ADMIN** (setting name kept from the spec: `MFA_REQUIRED_FOR_OWNER`).
9. **Rate limits in Redis, fail closed.** Login returns 503 when the limiter is unavailable.
10. **Encryption key fingerprints** in ciphertext enable rotation without downtime.
11. **Next.js Cache Components disabled.** The console is fully per-user and dynamic; classic dynamic
    rendering with `cookies()` is simpler and avoids prerendering authenticated pages.
12. **Tests use a real PostgreSQL.** Each test gets its own database cloned from a migrated template.
    DB tests skip (and are reported as skipped) without `TEST_DATABASE_URL`; CI sets `REQUIRE_DB_TESTS=1`
    so a missing database fails the build.
13. **Phase 00's `/health/*` stays unversioned**; everything else lives under `/api/v1`.

## Consequences

- CSP still allows inline scripts (Next.js hydration). Nonce-based CSP needs per-request rendering of every
  page; deferred to Phase 10 with the full console (tracked in implementation status).
- Per-IP login limits are coarse until Caddy (Phase 11) supplies trustworthy `X-Forwarded-For`.
- Replacing migration 0001 was allowed only because no environment has applied it yet. From now on, schema
  changes are new migrations.
