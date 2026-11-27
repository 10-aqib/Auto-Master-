# Internal Pilot — Test Results

Date: 2026-11-27. Commit under test: `f515fdc` (code), plus this documentation commit.
Environment: development sandbox (Linux, Docker). No real email, no paid API calls, no cloud resources.
Legend: **PASS** = run here and passed · **NOT RUN** = not executed (reason given).

## 1. Clean checkout (requirement 11)

`git clone` of the committed branch into an empty directory with no `.env`. Steps run by
`make install`, `make lint`, `make typecheck`, then each suite. Throwaway Postgres/Redis came from
`infrastructure/docker/compose.test.yml`.

| Step | Command | Result |
|---|---|---|
| Install | `make install` (uv sync --frozen ×2, npm ci) | PASS |
| Lint | `make lint` (ruff format/check for API and browser, ESLint/Prettier for the dashboard) | PASS |
| Types | `make typecheck` (mypy strict ×2, tsc strict) | PASS |
| API tests | `REQUIRE_DB_TESTS=1 uv run pytest -q` | **PASS: 531 passed** (193.6 s), DB tests included, none skipped |
| Browser sandbox tests | `uv --directory apps/browser run pytest -q` | **PASS: 22 passed** |
| Dashboard tests | `npm test` | **PASS: 51 passed** (8 files) |
| Dashboard build | `npm run build` | PASS |

The API suite also ran in the working tree before the final changes: 530 passed. The extra test in the clean
run is the new `emergency-pause` CLI test.

## 2. Running stack (same commit, working tree)

Images were built with `docker compose build` using a local, uncommitted CA override that this sandbox's
TLS-intercepting proxy requires. The committed Dockerfiles are unchanged.

| Check | Command | Result |
|---|---|---|
| Stack health | `docker compose up -d --wait` | PASS: 9 services healthy |
| Migrations | `alembic_version` | PASS: head `0010` |
| End-to-end | `node tests/e2e/console-flow.mjs` | **PASS: 30/30** |
| Smoke | `make smoke` | **PASS: 19/19** |
| Isolation | `make isolation` | **PASS: 8/8** |
| Provenance audit (live data) | `python -m webforge_api.provenance_audit` | **PASS: 14/14** (the first run failed 3/14 because of the E2E fixture; fixed, see §4) |

## 3. Requirement-by-requirement

| # | Requirement | Evidence | Result |
|---|---|---|---|
| 1 | Real outbound email not enabled | `EMAIL_SENDING_ENABLED=false` enforced by the startup validator; only the mock provider exists | PASS |
| 2 | Kill switch not removed or bypassed | Pauses seeded ON; env override beats the dashboard; pause after approval holds queued mail | PASS (`test_email_kill_switch.py`, 10 tests) |
| 3 | No real provider request from any job, worker, endpoint, dashboard action or retry | AST call-graph tests, hard guard with a recording live provider (0 calls across a retry), network sentinel (0 non-loopback connections) | PASS |
| 4 | Test email isolated | Mock refused in production (`mock_provider_in_production`); signed webhooks | PASS |
| 5 | Google Places audit against current policies | ToS (Aug 26 2026) and Service Specific Terms (Nov 24 2026) reviewed; one retention defect fixed | PASS with open legal question (COUNSEL-1) |
| 6 | Independent provenance verification | New SQL audit; 2 tests (clean flow passes, 6 injected violation types detected); live 14/14 | PASS |
| 7 | SSRF and generated-site isolation | `test_safe_fetch.py`, `test_egress_proxy.py`, new `test_pilot_ssrf.py` (17), renders/validation tests, `make isolation` 8/8 | PASS after fixing port-0 handling |
| 8 | Preview expiration and access control | `test_proposals.py`: hashed tokens, revoke, expiry, retention purge, rate limit, roles, headers | PASS |
| 9 | Budget warnings and hard stops | Places (4 tests), discovery cap, AI (2), email (1), overview 80 %/100 % | PASS |
| 10 | Backup restore and emergency recovery | `make backup`, `make restore-test`, full `down -v` → `make recover` drill | PASS (single host; see blockers C5) |
| 11 | Full suite from a clean checkout | §1 | PASS |
| 12 | Remaining blockers documented | `DEPLOYMENT_BLOCKERS.md` | Done |

Subset run used for items 7–8 (working tree):
`pytest tests/test_pilot_ssrf.py tests/test_safe_fetch.py tests/test_egress_proxy.py tests/test_renders.py tests/test_validation.py tests/test_proposals.py`
→ **136 passed**.

## 4. Defects found and fixed during this review

| Defect | Severity | Fix | Test |
|---|---|---|---|
| Unverified website URLs supplied by Google (Maps Content) were stored | High (terms) | Redact unless VERIFIED; migration 0010 for old rows | `test_unverified_maps_website_is_not_retained` |
| Explicit port `0` silently became port 80 | Low (no internal access) | `parts.port is not None` | `test_pilot_ssrf.py` |
| Send path had no guard against a non-mock provider independent of pauses | Medium (defence in depth) | Hard guards at the top of `outreach.send` | `test_email_kill_switch.py` |
| E2E fixture created a prospect whose fields had no recorded facts | Test data only | Fixture records all four facts | live audit 14/14 |

## 5. Backup and recovery drill (detail)

1. `make backup`: encrypted DB dump and artifacts archive, plus SHA-256 checksums (≈ 4.2 MB).
2. `make restore-test`: passed (head 0010, 37 tables, 2 users, 33 artifact entries).
3. Fingerprint taken: exact row count of all 37 tables plus a SHA-256 over every artifact file.
4. Negative test: `recover.sh` against the live stack → **exit 3**, "Database webforge already has 37 tables".
5. `docker compose down -v`: all containers and volumes removed (0 `webforge_` volumes left).
6. `make recover`: completed in **13 s**.
7. Stack up, fingerprint again: 36/37 tables identical; `activity_logs` 53 → 55 (the two recovery pause
   records). Artifacts identical (26 files, same hash).
8. `global_pause` and `email_pause` are ON with the reason "Recovered from webforge-20261127T140309Z; review
   before resuming."
9. Smoke 19/19, isolation 8/8, provenance audit passed.

## 6. Not run

| Item | Reason |
|---|---|
| Real email provider, real bounce/complaint webhooks | Not permitted; no adapter exists |
| Google Places live API, Anthropic live API | Paid APIs not authorised; mocks and fakes used |
| Deployment to a VPS, TLS issuance, restore on a second host | No VPS or domain supplied; not authorised |
| GitHub Actions CI for this commit | Runs on push; result not observed here |
| Image vulnerability re-scan | Done in Phase 11 (see release report); not repeated for this commit |
| Load and soak testing | Out of scope for a single-user pilot |
| External penetration test | Requires a third party |
