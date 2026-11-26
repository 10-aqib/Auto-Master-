# API Reference (v1)

The machine-readable contract is [`packages/contracts/openapi.json`](../../packages/contracts/openapi.json)
(regenerate with `make contracts`; CI fails if it is stale). Interactive docs: `http://127.0.0.1:8000/docs`
in non-production environments only.

## Conventions

- Prefix `/api/v1`. JSON only. Unknown request fields are rejected (`422`).
- Errors always use `{code, message, correlation_id, field_errors}`. Submitted values are never echoed.
- `correlation_id` equals the `X-Request-ID` response header; quote it when reporting a problem.
- Cookie authentication. State-changing requests must send `X-CSRF-Token` (value of the `wf_csrf` cookie)
  and, from browsers, an allowed `Origin`.
- Timestamps are UTC ISO 8601.

## Endpoints

| Method | Path | Who | Notes |
|---|---|---|---|
| POST | `/auth/login` | anyone | Rate-limited per IP and per account; generic failure message; lockout after repeated failures |
| POST | `/auth/mfa/verify` | session pending MFA | `{code, method: "totp"\|"recovery"}`; replaces the pending session |
| POST | `/auth/refresh` | refresh cookie | Rotates the refresh token; reuse after 30 s revokes the session |
| POST | `/auth/logout` | any session | Revokes the current session |
| POST | `/auth/logout-all` | any session | Revokes every session of the user |
| GET | `/auth/me` | any session | User + session state |
| POST | `/auth/mfa/setup` | signed in, MFA off | Returns secret, `otpauth://` URI and QR (SVG data URI) once |
| POST | `/auth/mfa/enable` | signed in, setup started | Returns 10 recovery codes once; revokes other sessions |
| POST | `/auth/mfa/disable` | active session | Password + code; refused for OWNER/ADMIN when MFA is required |
| POST | `/auth/mfa/recovery-codes` | active session | Replaces recovery codes (needs a TOTP code) |
| POST | `/auth/password` | active or must-change session | Revokes all other sessions |
| GET | `/auth/sessions` | active session | Own active sessions |
| DELETE | `/auth/sessions/{id}` | active session | Revoke one of your own sessions |
| GET | `/users` | OWNER, ADMIN | |
| POST | `/users` | OWNER (ADMIN/REVIEWER/READ_ONLY), ADMIN (REVIEWER/READ_ONLY) | New users must change their password |
| PATCH | `/users/{id}` | OWNER, ADMIN | Role changes: OWNER only. Deactivation/role change revokes sessions |
| POST | `/users/{id}/revoke-sessions` | OWNER, ADMIN | Within the roles they manage |
| POST | `/users/{id}/reset-mfa` | OWNER | For a lost authenticator |
| GET | `/activity` | OWNER, ADMIN | Cursor pagination (`limit`, `cursor`, `action`) |
| GET | `/sources` | OWNER, ADMIN | Registry with blockers and usage |
| POST | `/sources/{key}/review` | OWNER | Record terms review (https URL, version, notes) |
| POST | `/sources/{key}/enable` | OWNER | Requires a terms review (except mock, which is blocked in production) |
| POST | `/sources/{key}/disable` | OWNER, ADMIN | Always allowed |
| GET | `/usage/{provider}` | OWNER, ADMIN | Today/month usage, budget ratios, daily series |
| POST | `/places/search` | OWNER, ADMIN | Transient results + attribution; stores Place IDs only |
| GET | `/places/identifiers` | OWNER, ADMIN | Stored Place IDs |
| POST | `/places/identifiers/{id}/verify-website` | OWNER, ADMIN | Place Details (Enterprise SKU) → official-website check |
| POST | `/verification/website` | OWNER, ADMIN | Check an owner-supplied URL + expected name |
| GET | `/verification/recent` | OWNER, ADMIN | Recent website checks |
| GET/POST | `/campaigns`, `/campaigns/{id}` (GET/PUT) | read: all roles; write: OWNER, ADMIN | Validation errors per field; edits only in DRAFT/PAUSED |
| POST | `/campaigns/{id}/activate|pause|resume|complete|archive` | OWNER, ADMIN | Activation requires all readiness checks |
| POST | `/campaigns/{id}/discover` | OWNER, ADMIN | Queues one search per query per UTC day (idempotent); refused while paused |
| GET | `/prospects`, `/prospects/{id}` | all roles | Filters, pagination, field-level evidence, qualification history |
| POST | `/prospects/{id}/review` | OWNER, ADMIN, REVIEWER | approve / hold / reject / do_not_contact; reopen: OWNER/ADMIN (DNC: OWNER only) |
| POST | `/prospects/{id}/qualify`, `/prospects/merge` | OWNER, ADMIN | Re-score; manual merge with history |
| GET/POST | `/jobs`, `/jobs/{id}/retry|cancel` | OWNER, ADMIN | Dead-letter visibility and manual recovery |
| GET/PUT | `/controls`, `/controls/{key}` | read: all; pause: OWNER/ADMIN; resume: OWNER | Durable pause switches |
| POST | `/prospects/{id}/brief` | OWNER, ADMIN | Queue an AI design brief (needs a successful audit; refused for locked prospects) |
| GET | `/designs`, `/designs/{id}` | all roles | Design projects with every brief version, issues, tokens and cost |
| POST | `/designs/briefs/{id}/review` | OWNER, ADMIN, REVIEWER | Approve (valid drafts only) or reject a brief version |
| POST | `/designs/{id}/render` | OWNER, ADMIN | Queue a deterministic six-page render of the latest approved brief |
| GET | `/designs/renders/{id}/pages/{slug}` | all roles | Concept page HTML, served with a `sandbox` CSP and integrity-checked |
| POST | `/designs/renders/{id}/review` | OWNER, ADMIN, REVIEWER | Approve (becomes active) or reject a new render |
| POST | `/designs/renders/{id}/activate` | OWNER, ADMIN | Re-activate an earlier approved render (rollback) |
| POST | `/designs/renders/{id}/validate` | OWNER, ADMIN | Re-run offline validation (runs automatically after each render) |
| GET | `/designs/validations/{id}/screenshots/{slug}/{viewport}` | all roles | Validation screenshot PNG (hash-verified) |
| POST | `/designs/{id}/proposal` | OWNER, ADMIN | Queue a proposal PDF for the active, validated concept |
| GET | `/proposals?design_id=&prospect_id=` | all roles | Proposals with checks and preview links (metadata only) |
| GET | `/proposals/{id}/pdf` | all roles | Download the PDF (hash-verified) |
| POST | `/proposals/{id}/previews` | OWNER, ADMIN | Create a preview link; the URL is returned once, only its hash is stored |
| POST | `/previews/{id}/revoke` | OWNER, ADMIN | Revoke a preview link immediately |
| POST | `/proposals/{id}/delete` | OWNER, ADMIN | Delete the PDF and revoke all previews (metadata kept) |
| GET | `/industries` | all roles | Industry vocabulary |
| GET | `/health/live`, `/health/ready` | anyone | Liveness / dependency readiness |

## Session states

A signed-in session is in one state; endpoints outside the allowed set return `403` with the state as `code`.

| State | Meaning | Allowed |
|---|---|---|
| `mfa_pending` | Password OK, second factor needed (5-minute window) | `me`, `mfa/verify`, `logout` |
| `mfa_enrollment_required` | OWNER/ADMIN without MFA | `me`, `mfa/setup`, `mfa/enable`, `logout` |
| `password_change_required` | Temporary password | `me`, `password`, MFA setup, `logout` |
| `active` | Fully authenticated | Everything the role allows |

## Preview origin (separate service)

`PREVIEW_BASE_URL` (container `preview`) serves only `GET /p/<token>/<page>` and `GET /p/<token>/proposal.pdf`.
Everything else, and any unknown, expired or revoked token, returns a plain `404`. See ADR 0009.
