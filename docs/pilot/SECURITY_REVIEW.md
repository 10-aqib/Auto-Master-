# Security Review — Internal Pilot

Date: 2026-11-27. Reviewer: engineering (automated and manual checks in the development sandbox).
This review does **not** replace an independent penetration test, which is listed in `DEPLOYMENT_BLOCKERS.md`.

## 1. Outbound email cannot reach a real provider

Requirement: no scheduled job, worker, API endpoint, dashboard action or retry can trigger a real email
provider request.

| Layer | Control | Proof |
|---|---|---|
| Code | No live provider adapter exists. `EmailProvider` enum = `{mock}`; `build_provider` raises for any other name. | `test_configuration_cannot_select_or_enable_a_live_provider` |
| Config | `Settings` rejects `EMAIL_SENDING_ENABLED=true` and any non-mock `EMAIL_PROVIDER` at startup. | same test |
| Call graph | Exactly **one** `provider.send(` call in the source tree (`services/outreach.py`). `outreach.send` is called only from `services/job_handlers.py` (the `email.send` job). No API router, CLI, ops loop, preview app or backup tool calls it. | `test_exactly_one_provider_send_call_site`, `test_send_is_reached_only_from_the_worker_job` (AST scan) |
| Jobs | Only `email.send` and `email.reconcile` touch email. Dashboard actions call the API, which only *queues* jobs. | `test_only_job_types_touching_email_are_send_and_reconcile` |
| Network | The email package imports no network modules; nothing uses `smtplib`. | `test_email_package_has_no_network_code` |
| Hard guard (new) | At the top of `outreach.send()`, before the message is loaded or changed: a non-mock provider fails `live_email_disabled` while sending is disabled; the mock provider fails `mock_provider_in_production` in production. Independent of compliance checks and pauses. | `test_a_live_provider_is_never_called_even_with_every_approval_flag` (a recording provider, every approval flag set, retried: **0 calls**, message stays SCHEDULED) and `test_test_provider_cannot_send_in_production` |
| Kill switch | `email_pause` and `global_pause` are seeded ON. `EMAIL_PAUSE`/`GLOBAL_PAUSE` env overrides beat the dashboard. A pause after approval holds queued mail (job deferred, not sent). | `test_environment_kill_switch_overrides_the_dashboard`, `test_pause_applied_after_approval_holds_queued_mail`, existing outreach tests |
| Runtime sentinel | `socket.connect` patched to refuse any non-loopback address around the whole mock flow: send, transient failure, retry, ambiguous result, reconcile, signed webhooks, inbound reply, unsubscribe. **0 attempts**; exactly one mock message despite the failure and the ambiguous result. | `test_no_network_connection_during_the_whole_mock_email_flow` |

Test email isolation: `MockEmailProvider` records messages in memory only. It cannot run in production (hard
guard), and its webhooks need HMAC signatures within a 300 s tolerance.

Conclusion: in this codebase, no path makes a real provider request. Adding a real adapter would need a code
change, a config enum change and removal of the startup validator, all of which these tests would flag.

## 2. SSRF and untrusted URLs

`net/safe_fetch.py` already had broad coverage (`test_safe_fetch.py`, 7 egress-proxy tests): private, loopback,
link-local, CGNAT and metadata ranges; IPv6-mapped and 6to4 forms; mixed DNS answers; DNS-rebinding pinning;
redirect revalidation; port allow-list (80/443); userinfo; TLS verification; size and time caps.

New for the pilot: `tests/test_pilot_ssrf.py` with 17 attacker-style encodings (decimal, hex and octal IPs,
`127.1`, `0`, long-form and hex-mapped IPv6, link-local with a zone id, `localhost.`, `LOCALHOST`,
`metadata.google.internal`, userinfo and backslash confusion, ports 0 and 65536).

**Finding fixed:** `http://host:0/` was treated as port 80 (`parts.port or default`), so a URL that should have
been rejected was rewritten. The target was still a public host on an allowed port, so this was **not** an
internal-access bypass, but it is now blocked (`blocked_port`). All 17 cases now pass.

## 3. Browser sandbox and generated-site isolation

`make isolation`: **8/8 PASS**.
1. The sandbox reports itself as isolated.
2. No direct TCP to db, redis, api, cloud metadata or the internet.
3. The egress proxy refuses internal targets.
4. No secrets in the sandbox environment.
5. The sandbox cannot resolve `postgres`.
6. No published ports.
7. Runs as non-root.
8. Read-only root filesystem.

Generated concepts and previews:
- Previews are served by a separate app on a separate origin; production requires an HTTPS origin different
  from the dashboard (`test_production_requires_separate_https_preview_origin`).
- The preview app has no API routes (smoke check) and mounts artifacts read-only.
- Headers: `frame-ancestors 'none'`, a sandbox CSP, `X-Frame-Options: DENY`, `X-Robots-Tag: noindex`,
  `Referrer-Policy: no-referrer`, `Cache-Control: private, no-store`, no cookies.
- Forms in concepts have no `name` fields, so nothing can be submitted.
- Untrusted business text is HTML-escaped (`test_untrusted_text_is_escaped_and_cannot_inject_markup`).
- Concept validation runs in the browser sandbox only, with interactions bounded.

## 4. Preview expiration and access control

From `tests/test_proposals.py` (all passing):
- Tokens are 32 random bytes; only a hash is stored; the token never appears in DB rows.
- Unknown or garbled tokens give 404, and POST gives 405.
- A revoked preview gives 404 immediately.
- A preview gives 404 after the retention window. The retention job expires proposals and deletes their PDFs;
  deleted proposals give 404 for both the preview and the staff PDF.
- Rate limit: 10 requests then 429 in the test configuration (`PREVIEW_RATE_LIMIT_PER_MINUTE`).
- Roles: REVIEWER cannot create previews or delete proposals.
- Access count and last-access time are recorded.

## 5. Budgets and hard stops

| Budget | Behaviour | Test |
|---|---|---|
| Google Places daily request cap, daily spend, per-campaign cap, provider rate limit | Requests refused before the provider is called; defaults are 0 (= blocked) | `test_daily_request_cap_and_budget`, `test_daily_budget_exhausted`, `test_campaign_request_cap`, `test_provider_rate_limit` |
| Discovery candidate cap | Search stops at the cap | `test_candidate_cap_limits_and_stops_search` |
| AI daily budget | 0 blocks paid calls; exhaustion stops *before* calling | `test_paid_calls_blocked_without_budget`, `test_budget_exhaustion_stops_before_calling` |
| Email daily/hourly maximum | 0 fails closed | `test_zero_budget_and_production_mock_fail_closed` |
| Overview warnings | Warning at ≥ 80 %, stopped at the limit; ops alert fires | `test_budgets_warn_at_80_percent_and_stop_at_limit`, ops alert tests |
| Rate limiter outage | Fails closed (login, Place ID refresh) | `test_rate_limiter_outage_fails_closed`, `test_refresh_cli_fails_closed_when_rate_limiter_down` |

## 6. Backup, restore and emergency recovery

- `make backup` makes an encrypted DB dump and artifacts archive with SHA-256 checksums.
- `make restore-test` restores into a throwaway database and verifies it: **passed** (head 0010, 37 tables,
  33 artifact entries).
- New: `infrastructure/scripts/recover.sh` (`make recover`), the runbook's full-restore steps as one guarded
  script. It verifies checksums, refuses a non-empty database or artifacts volume (exit 3, tested), restores,
  migrates forward, and then turns the global and email pauses **ON** through the new `emergency-pause` CLI
  (audited as a system action), so a recovered system does not resume work by itself.
- Drill: all volumes destroyed (`docker compose down -v`), then recovered in 13 s. Row counts identical in
  36/37 tables; `activity_logs` +2 (the two pause records). Artifacts byte-identical (26 files, same hash).
  Smoke 19/19, isolation 8/8, provenance audit passed.

Not yet proven: off-site backup copies and restore onto a different host (needs the VPS). See blockers.

## 7. Other controls (unchanged, tested in earlier phases)

- Authentication: Argon2id, TOTP MFA, CSRF, session rotation, per-IP and per-account login limits.
- Authorization: RBAC (OWNER/ADMIN/REVIEWER) on every privileged route.
- Secrets: encryption at rest with key rotation (`ENCRYPTION_KEY_PREVIOUS`); structured logs redact secrets and
  personal data; gitleaks passes on the repository.
- PostgreSQL and Redis have no published ports (smoke). API path traversal blocked (smoke).
- AI output: strict Pydantic schemas; no tools given to the model; output is rendered as escaped text only.

## 8. Residual risks

| Risk | Severity | Mitigation / owner action |
|---|---|---|
| No independent penetration test | High for production, acceptable for a closed internal pilot | Commission one before any public exposure |
| Images built in this sandbox used a local CA override (TLS-intercepting proxy) | Low | CI builds the committed Dockerfiles; rebuild on the VPS |
| Image vulnerability scan findings (Phase 11 trivy report) | Medium | Re-scan on the VPS build; patch base images before production |
| Single-host deployment | Medium | Off-site backups plus the recovery script; documented RTO |
| Legal questions (Places use, email law) | High for production | `DATA_SOURCE_COMPLIANCE_REVIEW.md` §5 |
