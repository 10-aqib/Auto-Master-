# Implementation Status

| Phase | Name | Status | Email |
|---|---|---|---|
| 00 | Foundation | Complete | Disabled (rejected by config) |
| 01 | Database + auth | Complete | Disabled (rejected by config) |
| 02 | Source adapters | Complete | Disabled (rejected by config) |
| 03 | Discovery | Complete | Disabled (rejected by config) |
| 04 | Website audit | Complete | Disabled (rejected by config) |
| 05 | AI intelligence | Complete (mock provider; live Claude calls not run) | Disabled (rejected by config) |
| 06 | Design generation | Complete | Disabled (rejected by config) |
| 07 | Validation | Complete | Disabled (rejected by config) |
| 08 | Proposals | Complete (no email) | Disabled (rejected by config) |
| 09 | Email/compliance | Complete (mock provider only) | Live sending rejected by config; no approved provider |
| 10 | Dashboard/orchestration | Complete | Live sending rejected by config; email pause seeded ON |
| 11 | Production | **Release artifacts complete; VPS/DNS/provider steps NOT RUN** | NO-GO for live email (see release report) |

## Phase 11 — Production artifacts, security review and release report (2026-11-27)

### Delivered
- Production Compose override + Caddyfile (TLS, HSTS, three hostnames, API host limited to webhooks/unsubscribe/
  liveness, no other host ports), release tags for rollback, resource limits, log rotation, `ops` alert service.
- Every base image pinned by digest (Dockerfiles, Compose, test Compose, CI). Runtime hardening (OS updates; pip,
  npm, virtualenv and caches removed).
- Encrypted backups (`backup.sh`), automated restore test (`restore-test.sh`), `backup_runs` (migration `0009`),
  backup status in Operations; `python -m webforge_api.backup`.
- Operational alerts (`python -m webforge_api.ops_alerts`): DB/Redis, workers, queue age, dead letters, budgets,
  provider errors, failed sign-ins, webhook signature failures, pause changes, bounce/complaint rates, backups,
  restore tests, disk, memory, TLS expiry; optional `ALERT_WEBHOOK_URL`. Webhook signature failures now recorded.
- Security tooling: `.gitleaks.toml`, `make scan-secrets|scan-deps|scan-images`, CI `security` job.
- Fixes found by this phase: pypdf 6.1.3 → 7.2.0 (97 advisories); validator form interaction could hang/crash when a
  bad form navigates; `ops` service healthcheck.
- Docs: `docs/operations/runbook.md`, `docs/release/RELEASE_REPORT.md`, ADR 0012.

### Verification evidence (local run, 2026-11-27)

| Check | Result |
|---|---|
| API tests (real PostgreSQL + Redis) | PASS — 500 passed (10 new: backup format sizes/tamper/truncation/wrong key/plaintext, key validation, alerts for backups/logins/failures, backup status, TLS skip) |
| Browser sandbox tests | PASS — 22 passed (validator stable over 3 repeated runs after the fix) |
| Lint / strict types (API 149 files, sandbox 6, dashboard) / dashboard 51 tests / build | PASS |
| Docker stack (dev, hardened images) / smoke / isolation / E2E | PASS — 19/19, 8/8, 30/30, 0 error log lines |
| gitleaks (history) / pip-audit (API, sandbox) / npm audit | 0 / 0 / 0 |
| Trivy HIGH/CRITICAL fixable (api, browser, dashboard) | 0 / 0 / 0 (unfixed upstream listed in the release report) |
| Backup → restore test → tampered backup | PASS → PASS (head 0009, 37 tables) → correctly FAILED + `backup_failed` alert |
| Production-mode rehearsal (Caddy internal TLS) | config checks pass; routing/HSTS/redirect/port exposure verified; isolation 8/8; backup + restore; deploy r2 30 s; rollback r1 29 s with data and pauses intact |

NOT RUN: VPS hardening, DNS, real certificates, off-site backup upload, real provider/API calls, supervised pilot.
Recommendation: GO for a mail-free internal pilot once owner inputs exist; **NO-GO for live email**.

## Phase 10 — Owner dashboard and orchestration (2026-11-27)

### Delivered
- **Overview**: cumulative pipeline funnel, holds/exits, outcomes (sent, delivered, bounced, complaints, replied,
  opted out, interested, clients), hold reasons, per-campaign and per-country views (country filter), monthly
  spend, budget warnings (80%) and stops (100% / limit 0), review-queue counts, live API health.
- **Review queues** page (seven queues, oldest first, linked to the item).
- **Operations** page: worker heartbeats, queue depth/age, dead letters, failures and provider errors (24 h),
  quotas, pause switches, backup status.
- **Pause banner** on every page (state + last actor + time); scoped pause labels in Settings.
- **Index pages**: Designs (with business names), Outreach (status filters); nav reorganised.
- Drafts carry the prospect's campaign so campaign pauses hold sends. Skip link; Card overflow fix.
- Docs: ADR 0011, API docs.

### Verification evidence (local run, 2026-11-27)

| Check | Result |
|---|---|
| API tests (real PostgreSQL + Redis) | PASS — 490 passed (6 new: cumulative funnel + filters, budget warning/stop, review queues, operations RBAC/queues/dead letters/backups, worker heartbeat TTL against real Redis, campaign link) |
| Lint / strict types / dashboard tests and build | PASS — 51 dashboard tests |
| Docker stack 9 services / smoke / isolation | PASS — 19/19, 8/8 |
| Browser E2E (full fixture pipeline through proposal, compliance HOLD→eligible, mock send, overview/banner/queues/operations/index pages, skip link, no overflow at 390 px on ten pages) | PASS — 30/30 |
| Error log lines | 0 |

## Phase 09 — Email compliance engine, mock provider, replies (2026-11-27)

### Delivered
- **Provider review**: Resend and Postmark prohibit unsolicited/cold email → no live adapter; mock only
  (`docs/compliance/email-providers.md`).
- **Policy registry** (country × recipient type × category, versioned, reviewed-only activation, owner-only),
  inactive research drafts via `cli seed-policy-drafts`.
- **Contacts** only from the verified official domain or provided by the business (no guessed addresses);
  encrypted + keyed hash; consent records.
- **17-check eligibility engine** run at draft, approval and immediately before sending; HOLD/INELIGIBLE with
  reason codes; full checklist stored on each assessment (migration `0008`).
- **One owner-approved initial message** (`outreach-1` template, truthful-content checks), send job with recipient
  lock, durable send intent, stable idempotency key, ambiguous-send reconciliation, all pause switches (global,
  email, campaign, country, provider) holding queued mail.
- **Unsubscribe** (token hash, RFC 8058 one-click, GET-safe page, GLOBAL suppression + cancel in one transaction),
  **signed webhooks** (freshness window, dedupe), hard bounce/complaint suppression, **inbound replies** stored
  encrypted and classified by fixed rules with opt-out priority.
- **UI**: Compliance page (sending status, policy registry, review/activation, suppression, country pause),
  Outreach card on prospects (contacts, draft, 17-check list, approve/cancel, dev simulator), Replies inbox.
- Docs: ADR 0010, provider review, `.env.example`, API docs.

### Verification evidence (local run, 2026-11-27)

| Check | Result |
|---|---|
| API tests (real PostgreSQL + Redis) | PASS — 484 passed (33 new: no-policy HOLD, public-address-is-not-consent, eligible draft + approval, official-source contacts, zero budget and production-mock fail closed, idempotent send with preview/unsubscribe, transient retry + ambiguous reconcile without duplicates, every pause switch, suppression cancelling queued mail, one-click unsubscribe, webhook signature/replay/dedupe, bounce/complaint/soft bounce, reply classification and opt-out priority, classifier and content-check cases, policy registry rules and owner-only activation, seeded drafts inactive, provider/live-sending rejection) |
| Lint / strict types (API 142 files, dashboard) / dashboard tests and build | PASS — 49 tests |
| Docker stack 9 services / smoke / isolation | PASS — 19/19, 8/8 |
| Browser E2E (policy review + activation, email resume, contact, 17/17 checks, owner approval, worker mock send, preview + unsubscribe links in body, simulated reply classified, recipient one-click unsubscribe → suppressed) | PASS — 28/28 |
| Error log lines | 0 |

Not done (owner decisions): any live provider, legal review of real country policies, sender domain, postal
address and mailbox. Live sending remains impossible by configuration.

## Phase 08 — Proposal PDF and secure preview (2026-11-26)

### Delivered
- **Proposal PDF (`proposal-1`)**: cover with independent-concept/non-endorsement notice, dated audit
  observations, design direction, six page previews (desktop + mobile), information architecture, cautious
  opportunities ("not guaranteed"), developer introduction (Muhammad Aqib, Website Developer, aqibkhn.space,
  github.com/10-aqib) and a next step that shows `PROPOSAL_CONTACT_EMAIL` only when supplied. Built only from the
  active APPROVED concept with a READY validation; screenshots hash-checked against the render version.
- **Offline PDF rendering** in the browser sandbox (`POST /pdf`, JS off, network blocked) and **pypdf checks**
  (opens, ≥ 10 pages, no blank pages, ≥ 12 images, business/notice/developer present, no internal IDs, no
  debug/placeholder text). Pass → `READY` + prospect `PROPOSAL_READY`; fail → `DRAFT` + `HUMAN_REVIEW`.
- **Preview gateway** (`webforge_api.preview`, container `preview`, `PREVIEW_BASE_URL`, port 4000): 256-bit tokens,
  only keyed hash stored, link shown once; 30-day default expiry; immediate revoke; uniform 404; per-IP rate
  limit; strict sandbox CSP and security headers; no cookies/docs/API; hash-verified pages; access counting.
  Production config requires an https preview origin separate from app/API.
- **Lifecycle**: download, regenerate (new version), create/revoke previews, delete (PDF removed, previews
  revoked, metadata kept), `cli purge-artifacts` retention (migration `0007`).
- **UI**: "Proposal and preview" card on the design page. Docs: ADR 0009, API docs, `.env.example`.
- Nothing is emailed.

### Verification evidence (local run, 2026-11-26)

| Check | Result |
|---|---|
| API tests (real PostgreSQL + Redis) | PASS — 451 passed (12 new: generation and checks, failed checks hold, approved concept required, screenshot version mismatch, preview lifecycle on separate origin incl. headers / uniform 404 / 405 / access count / revocation, expiry, delete + retention purge, rate limit, token uniqueness and roles, escaping and contact-email rule, production origin rules) |
| Browser sandbox tests | PASS — 22 passed (3 new: real Chromium PDF with page count and blocked remote image, endpoint validation) |
| Real stack PDF | PASS — 11 pages, 1.5 MB, text extraction confirms notice, developer identity, no invented contact |
| Migration 0007 round trip | PASS |
| Lint / strict types (API 134 files, sandbox, dashboard) / dashboard tests and build | PASS — 48 tests |
| Docker stack 9 services / smoke / isolation | PASS — healthy, 19/19, 8/8 |
| Browser E2E (proposal READY, PDF download, preview opened from a fresh context on the preview origin, headers, demo form, PDF via token, wrong token 404, revoke → 404) | PASS — 27/27 |
| Error log lines | 0 |

Not run: preview on a real public subdomain with TLS (needs the owner's domain and VPS; Phase 11 Caddy config).

## Phase 07 — Responsive validation and screenshots (2026-11-26)

### Delivered
- **Offline validator** in the browser sandbox (`POST /validate`, `apps/browser/.../validator.py`): pages served
  from memory at `https://concept.invalid/`, all other requests aborted and reported, DNS disabled; desktop
  1440 / tablet 768 / mobile 390; measures overflow, console errors, blocked requests, images, notice, links,
  headings, accessible names, labels, alt text, computed-colour contrast, keyboard focus, tokens/fonts, and
  demo-form behaviour (fill, Enter, click; no navigation or requests allowed). Screenshots at device scale 2,
  taken before interaction.
- **Rules `validator-1`** (`design/validation_rules.py`): pass / fail / unknown checks with critical / major /
  minor severity and evidence; `READY` only with zero critical failures; HTML hash and screenshot hash checks
  catch version mismatches.
- **Job `design.validate`** (audit queue, isolation self-test gated), queued automatically after each render;
  18 screenshots + report stored per run in `design_validations` (migration `0006`); desktop shots linked to
  `design_pages`; prospect → `VALIDATING`, or `HUMAN_REVIEW` when revision is needed.
- **Bounded repair**: contrast/focus failures trigger one safe-mode deterministic re-render per brief version.
- **Approval gate**: a concept can be approved only if its latest validation is `READY`.
- **API/UI**: re-run validation, screenshot endpoint; validation panel with summary, failing checks + evidence,
  18 screenshot thumbnails (hash shown), approve disabled until ready. Docs: ADR 0008, API docs, isolation doc.

### Verification evidence (local run, 2026-11-26)

| Check | Result |
|---|---|
| API tests (real PostgreSQL + Redis) | PASS — 439 passed (18 new: ready path with 18 screenshots, approval gate, 10 critical fixtures incl. overflow / console error / external font / broken image / broken route / submitting form / missing notice / HTML version mismatch / screenshot hash mismatch / load failure, warnings not blocking, repair once, repair bounded, isolation gate, tampered page) |
| Browser sandbox tests | PASS — 19 passed (7 new against real Chromium: clean page at 2x, inert form, submitting form detected, CSP blocks implicit submit, overflow/contrast/headings/names/alt/blocked fetch/console error fixtures, missing notice) |
| Real renderer × real Chromium, all four industry variants | PASS — 293/293 checks each; low-contrast palette: 15 contrast failures, safe-mode repair: 0 |
| Migration 0006 round trip | PASS |
| Lint / strict types (API 128 files, sandbox, dashboard) | PASS |
| Dashboard unit tests / build | PASS — 48 passed / build OK |
| Docker stack 8 services / smoke / isolation | PASS — healthy, 15/15, 8/8 |
| Browser E2E (incl. live validation READY 293/293, 18 screenshots, 2x mobile image, approve) | PASS — 26/26 |
| Error log lines | 0 |

## Phase 06 — Six-screen concept renderer (2026-11-26)

### Delivered
- **Deterministic renderer `renderer-1`** (`design/renderer.py`, `design/templates.py`): sandboxed autoescaping
  Jinja, fixed component vocabulary, CSS from validated palette values and system font stacks, industry variants
  (warm / clinical / solid / professional), mobile-first layout, semantic headings, skip link, labelled fields,
  visible focus, 44px targets, reduced motion. Notice "Independent redesign concept — not the official website"
  on every page (banner and footer). Assumptions are marked "To be confirmed by the business"; contact panel
  shows verified contact facts only; no testimonial/rating/award/statistic components exist.
- **Safety scan** before storage: no scripts, event handlers, external or protocol-relative URLs, frames,
  objects, links, CSS fetches, form actions, named fields or submit buttons; notice required; 200 KB cap.
- **Inert demo form**: no action/method, unnamed fields, `type="button"`, `form-action 'none'` CSP.
- **Assets**: one original generated SVG per render, recorded in `assets` (`original-generated`); no downloads.
- **Versioning**: `design_renders` (migration `0005`) with manifest (keys, SHA-256, sizes), scan results and one
  active render per project; approve → active; re-activate any approved render (rollback). Pages also recorded in
  `design_pages`; integrity verified on every read.
- **Job / API**: `design.render` on queue `design`; `POST /designs/{id}/render`,
  `GET /designs/renders/{id}/pages/{slug}` (sandbox CSP), `POST /designs/renders/{id}/review|activate`.
- **UI**: concepts card on the design page with six page tabs, desktop/tablet/mobile widths, sandboxed iframe
  preview, approve/reject, rollback. Docs: ADR 0007, `.env.example` (`CONCEPT_AUTHOR_*`), API docs.

### Verification evidence (local run, 2026-11-26)

| Check | Result |
|---|---|
| API tests (real PostgreSQL + Redis) | PASS — 421 passed (23 new: six pages, determinism, inert form, escaping/injection, 11 scan rules, notice, labels, contrast-safe buttons, variants, store/preview/review/rollback, tamper detection, roles, locked prospects) |
| Migration 0005 upgrade/downgrade round trip; model/migration drift check | PASS / no differences |
| Lint / strict types (API 122 files, dashboard) | PASS |
| Dashboard unit tests / production build | PASS — 47 passed / build OK |
| Docker stack — 8 services healthy | PASS |
| Smoke / isolation proof | PASS — 15/15, 8/8 |
| Browser E2E (render, sandboxed preview, in-frame navigation, demo form cannot submit, no overflow at 390px, CSP header, approve) | PASS — 25/25 |
| Error log lines | 0 |

### Notes
- The dashboard frame uses `sandbox allow-same-origin` so in-frame links keep the session cookie; scripts, forms,
  popups and top navigation stay blocked (ADR 0007 §4).
- Phase 07 adds automated responsive validation and stored screenshots for every page.

## Phase 05 — Structured AI design briefs (2026-11-26)

### Delivered
- **Brief schema `brief-1`** (`design/brief_schema.py`): strict Pydantic models (no extra fields) for summary,
  facts used, assumptions, audience hypotheses, direction, hex palette, allowed font stacks, industry trust-page
  label, exactly six pages (home, services, about, trust, inquiry, contact) with typed blocks, image briefs and
  accessibility notes. Each section is labelled `verified_fact` (must cite fact IDs), `proposed_copy` or
  `assumption`. The API schema sent to Claude is generated from the same models.
- **Integrity checks** (`design/integrity.py`): unknown fact IDs, uncited facts, invented testimonials/quotes,
  awards, certifications, years in business, statistics, prices, superlatives, phone numbers, emails, staff
  names, misplaced forms, WCAG 4.5:1 text contrast, instruction-like text.
- **Providers** (`services/ai.py`): official `anthropic` SDK with strict JSON output, no tools, server-side
  refusal fallbacks and mapped errors (retryable vs permanent); offline mock provider (default; refused in
  production).
- **Generation job** `design.brief` on queue `design` (`services/briefs.py`): minimal fenced context (independent
  facts + audit finding titles), worst-case budget reservation under an advisory lock, input-token cap, bounded
  repair loop, versioned `design_briefs` rows (migration `0004`) with facts snapshot, issues, attempts, tokens and
  cost; failures go to `NEEDS_REVIEW` and the prospect to `HUMAN_REVIEW`.
- **API**: `POST /prospects/{id}/brief`, `GET /designs`, `GET /designs/{id}`, `POST /designs/briefs/{id}/review`.
- **UI**: "Design brief" card on prospects; brief page with six screens, content labels, sources, palette,
  failed checks, cost and approve/reject. Docs: ADR 0006, `.env.example`, `docs/api/README.md`, `docs/versions.md`.

### Verification evidence (local run, 2026-11-26)

| Check | Result |
|---|---|
| API tests (real PostgreSQL + Redis) | PASS — 398 passed (33 new: schema, integrity, injection, repair, budget 0 / exhausted, cost accounting, 429/500/529/401/400/unreachable via a local fake Messages API server, mock refused in production, roles) |
| Migration 0004 upgrade/downgrade round trip | PASS |
| Lint / strict types (API 117 files, dashboard) | PASS |
| Dashboard unit tests / production build | PASS — 45 passed / build OK |
| Docker stack — 8 services healthy | PASS |
| Smoke / isolation proof | PASS — 15/15, 8/8 |
| Browser E2E (incl. generate and approve a mock brief) | PASS — 24/24 |
| Error log lines | 0 |

Not run: a real Claude API call (no API key supplied, and paid calls need owner authorization). To enable:
set `AI_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` (server-side only) and a non-zero `AI_DAILY_BUDGET_MINOR`.

### Notes
- The `anthropic` 2.x SDK installs `httpx2`, which Starlette's TestClient now uses; three cookie-replacement tests
  were updated to use a `Harness.set_cookie` helper (behaviour under test unchanged).

## Phase 04 — Isolated website audit engine (2026-11-26)

### Delivered
- **Browser sandbox** (`apps/browser`, Playwright 1.63 image): evidence collection only (desktop 1440×1000 and
  mobile 390×844 screenshots, DOM metrics, console errors, failed requests, bounded same-site crawl). No clicks,
  typing or form submission; downloads, service workers, non-http(s)/media/websocket requests blocked; fresh
  Chromium per audit.
- **Egress proxy** (`webforge_api.egress_proxy`): the sandbox's only route out; DNS resolved and vetted at the
  proxy, private/loopback/link-local/metadata/IPv6-local refused, ports 80/443, byte/time caps.
- **Topology**: `sandbox` network is internal (no internet, no DB/Redis/API); `worker-audit` bridges backend and
  sandbox; sandbox has no secrets, runs non-root with a read-only filesystem and CPU/memory/pid limits.
- **Runtime isolation gate**: the worker calls the sandbox `/selftest` before auditing; audits fail with
  `isolation_unproven` if any internal target is reachable. `make isolation` runs the same proof from inside the
  running container (also in CI).
- **Deterministic audit rules v1**: findings with code, severity, viewport, evidence, confidence and reproduction
  steps; category scores (branding NOT_TESTED); bot-blocked/erroring sites recorded as FAILED with no scores.
- **Storage adapters**: private local volume and S3-compatible (SSE) with traversal-safe keys; screenshots served
  only to signed-in staff.
- **Pipeline**: qualification without audit evidence queues an audit; finished audits trigger re-qualification;
  failed audits go to manual review (no retry loop).
- **UI**: audit section on prospects (run audit, history) and an audit page (categories, findings, strengths,
  caveats, screenshots). Docs: `docs/security/browser-isolation.md`, ADR 0005.

### Verification evidence (local run, 2026-11-26)

| Check | Result |
|---|---|
| API tests (real PostgreSQL + Redis) | PASS — 365 passed |
| Browser sandbox tests (12 fixture sites incl. fixed-width, broken images, 404 nav, missing CTA, slow, oversized media, cookie overlay, bot-blocked, non-http schemes) | PASS — 12 passed |
| Egress proxy SSRF tests (loopback, metadata, mixed DNS, private IPs, ports, redirects, byte cap) | PASS — 11 passed |
| Lint / strict types (API 109 files, sandbox 4 files, dashboard) | PASS |
| Docker stack — 9 services | PASS — all healthy |
| Smoke | PASS — 15/15 |
| Isolation proof from inside the sandbox (`make isolation`) | PASS — 8/8: no direct TCP to postgres/redis/api/dashboard/metadata/internet, proxy refuses internal targets, no secrets, cannot resolve `postgres`, no published ports, non-root, read-only FS |
| Live chain worker → sandbox → proxy → internet | PASS (chain); the target page itself failed because this build environment intercepts TLS — Chromium correctly rejected the intercepted certificate and the audit was recorded as FAILED |
| Browser E2E | PASS — 23/23 |
| Error log lines (api, workers, browser, proxy) | 0 |

Not run here: a successful audit of a real public website (needs normal internet egress; run `make dev` on the
VPS and audit any verified prospect).

## Phase 03 — Campaigns, discovery, dedupe and qualification (2026-11-26)

Owner instruction on 2026-11-26: "all phases approved" — phases 03–11 run back to back, each still tested,
documented and committed separately. Live email, paid API calls and cloud resources remain off.

### Delivered
- **Durable PostgreSQL job queue** (transactional enqueue, idempotency keys, `SKIP LOCKED` claims, leases and
  crash recovery, exponential backoff, DEAD/FAILED dead-letter, manual retry/cancel, correlation IDs) and a
  **worker** service (`webforge_api.worker`, heartbeat health check). ADR 0004.
- **Durable pause switches** (`system_controls`, seeded paused; admins pause, only the owner resumes;
  env emergency override). Paused work is deferred without using retry attempts.
- **Campaigns**: CRUD with per-field validation, readiness checks, lifecycle (draft/active/paused/completed/
  archived), candidate cap, campaign budget, idempotent daily discovery runs; closing a campaign cancels queued work.
- **Discovery pipeline**: search → per-Place-ID website verification → qualification, using only Phase 02
  approved, enabled connectors; rediscovery in another campaign links and re-qualifies without re-verifying.
- **Dedupe**: domain + branch key; language paths ignored; possible same-name duplicates flagged; manual merge
  with history; do-not-contact survives merges.
- **Qualification rubric v1** (`docs/compliance/qualification.md`): evidence-only scoring with coverage,
  outcomes STRONG/POTENTIAL/INVESTIGATE/REJECTED/MANUAL_REVIEW with reason codes; industry from the site's own
  schema.org data.
- **Prospect lifecycle** state machine with logged transitions; review tools (approve/hold/reject/do-not-contact/
  reopen with role rules).
- **Dashboard**: Campaigns (list, create, detail with readiness/progress/actions/edit), Prospects (filters,
  pagination, evidence page with provenance, checks, qualification components, review), Jobs, Settings (pause).
- Migration 0003, OpenAPI contract, docs (ADR 0004, rubric, schema, API, migrations).

### Verification evidence (local run, 2026-11-26)

| Check | Result |
|---|---|
| `make lint`, `make typecheck` (102 Python files strict; tsc) | PASS |
| API tests on real PostgreSQL + Redis | PASS — 339 passed, 0 skipped |
| Dashboard unit tests / build | PASS — 43 tests; 16 routes build |
| Migration 0003 round trip (0003↔0002) | PASS |
| Docker stack (now 6 services incl. worker) | PASS — all healthy, migrate exited 0 |
| Smoke | PASS — 15/15 (new: worker healthy) |
| Browser E2E | PASS — 23/23 (new: resume pause, create/activate/run mock campaign, worker processes jobs) |
| API/worker error log lines | 0 |

Required Phase 03 tests: duplicate domain ✔, branch separation ✔, unknown facts don't score ✔, policy failure
blocks ingestion ✔, budget/campaign caps ✔, idempotent retries ✔, reject/suppression persists across campaigns ✔.

### Notes
- Mock places point at non-resolvable `*.example.test` sites, so in the live dev stack they are held at
  verification (by design); the full verify→prospect→qualify path is exercised in tests with local fake sites.
- Qualification stays INVESTIGATE (`awaiting_audit_evidence`) until Phase 04 audits supply evidence.

## Phase 02 — Source adapters and data governance (2026-11-26)

### Delivered
- **Policy re-check** of Google Places API (New) docs on 2026-11-26, recorded with URLs and open legal questions in
  `docs/compliance/source-policies.md` (Service Specific Terms page could not be read automatically: owner must read it).
- **Source terms/permission registry** (`source_registrations`, migration 0002): `google_places`, `official_website`,
  `mock_places`, all DISABLED by default. Enabling needs an owner terms review (DB CHECK + service rule). Mock is
  blocked in production.
- **Places connector** (Text Search + Place Details, New API) with fixed minimal field masks, no wildcard, SKU derived
  from the highest field tier, key only in a server-side header.
- **Place IDs only** are persisted (`external_place_identifiers`); all other Maps content is returned transiently and
  shown with "Google Maps" attribution (self-hosted Roboto, `translate="no"`, no wrap) and a link to `googleMapsUri`.
- **Independent verification**: SSRF-safe fetcher (DNS pinned, public IPs only, redirects re-validated, size/time
  limits, TLS verified) and an official-website verifier (robots.txt, parked/off-site/structured-data checks, name
  matching). Prospects are created only from VERIFIED checks, named with the site's own text, with field-level
  provenance (source URL, time, terms version, confidence, method). Domains are never guessed.
- **Provenance rules**: only independent sources can back a stored fact (service rule + DB CHECK).
- **Cost accounting and budgets**: per-SKU owner-configured prices (unpriced = refused), daily budget, daily request cap,
  per-campaign cap, per-minute rate limit, reservation under an advisory lock, SUCCESS/ERROR outcome, 80% warning.
- **Transient cache** limited to registry `cache_rules` (Places: `location` ≤ 30 days), encrypted, with purge.
- **Maintenance CLI**: `refresh-place-ids` (IDs-only, marks obsolete), `purge-transient`.
- **Mocks for CI**: `MockPlacesConnector` and an httpx mock transport for the real connector; CI makes no external calls.
- **Dashboard**: Sources page (registry, review, enable/disable, blockers, budget meters, owner URL check) and Places
  discovery (search, attribution, verify website, stored IDs, recent checks).
- **Docs**: source policies, SSRF defences, ADR 0003, schema/API/migration/version updates, `.env.example`.

### Verification evidence (local run, 2026-11-26)

| Check | Command | Result |
|---|---|---|
| Lint / format | `make lint` | PASS |
| Types | `make typecheck` (mypy strict, 89 files; tsc) | PASS — 0 issues |
| API tests (real PostgreSQL + Redis) | `make test-integration` | PASS — 321 passed, 0 skipped |
| Dashboard tests | `npm test` | PASS — 43 passed (6 files) |
| API tests without a database | `make test` | 184 passed, 137 **skipped** (reported) |
| Dashboard build | `npm run build` | PASS |
| Migrations | upgrade/downgrade 0002↔0001↔base round trip; models = migrations | PASS |
| Compose | `docker compose up --build --wait` | PASS — migrate exited 0, 4 services healthy |
| Smoke | `make smoke` | PASS — 14/14 |
| Browser E2E | `make e2e` | PASS — 20/20 (5 new Phase 02 steps) |
| No Maps-style content persisted | scan of all 30 tables after E2E search + verify | 0 matches |
| API error log lines | grep | 0 |
| Real Google Places call | — | **NOT RUN**: no key or approved budget (by design; mock transport used) |
| CI | GitHub Actions | NOT RUN here — runs on push |

Required Phase 02 tests: field mask required/no wildcard ✔, Place ID persistence ✔, restricted fields not persisted
(whole-database scan) ✔, provenance required ✔, budget/rate limits ✔, key not in frontend/logs/responses ✔,
connectors disabled by default ✔. Plus 55 SSRF/fetcher tests and 21 verifier tests.

### Known issues / notes
- Open legal questions (transient use of `websiteUri`/`displayName` for verification; retention for unverified
  candidate IDs; overall use-case fit) are listed in `docs/compliance/source-policies.md`.
- Website verification runs in the API process for now (homepage + robots.txt only); moves to a queued worker in
  Phase 03 and to an isolated network in Phase 04.
- Minimal dedupe only (reuse a prospect with the same verified domain); full dedupe/branches in Phase 03.
- `make e2e` needs a fresh database (it bootstraps the owner).

### Owner actions before using Google Places for real
1. Read the Service Specific Terms and confirm the use case (see open questions).
2. Create a restricted API key (Places API (New) only, server IP), set budgets/alerts in Google Cloud.
3. Fill `GOOGLE_MAPS_API_KEY`, `GOOGLE_PLACES_SKU_PRICES_MINOR_PER_1000` (current prices), daily budget, caps,
   then `GOOGLE_PLACES_API_ENABLED=true`.
4. Record the terms review in Sources and enable the source.

### Next phase
Phase 03 — Discovery, campaigns, dedupe, qualification and jobs (`docs/spec/PHASE_PROMPTS/PHASE_03_DISCOVERY.md`).
Requires owner approval to start.

## Phase 01 — Database, migrations and secure authentication (2026-11-26)

### Delivered
- **Schema:** migration `0001` creates all 24 spec tables plus `user_sessions` and `mfa_recovery_codes`
  (UUID keys, UTC `timestamptz`, FKs with deliberate delete rules, CHECK/unique constraints, indexes).
  Business tables are staged for later phases. See `docs/architecture/schema.md` and `docs/migrations.md`.
- **Append-only activity log** enforced by database triggers (UPDATE, DELETE and TRUNCATE blocked).
- **Owner bootstrap:** one-time CLI (`make owner`), no default password, single-OWNER DB constraint.
- **Auth:** Argon2id, password policy, signed 15-minute access tokens, rotating hashed refresh tokens with
  reuse detection, 30-day absolute session limit, logout / logout-all / per-session revoke, forced
  password change for admin-created accounts.
- **MFA:** TOTP enrolment with QR, replay protection, 10 single-use recovery codes, required for
  OWNER/ADMIN, owner can reset another user's MFA.
- **RBAC:** OWNER, ADMIN, REVIEWER, READ_ONLY with tested allow/deny for every route; session-state gating.
- **Web security:** HttpOnly SameSite=Lax cookies (`__Host-` + Secure in production), session-bound CSRF
  token, Origin allow-list, login rate limits per IP and per account (Redis, fail closed), account lockout,
  generic errors that never echo input.
- **Encryption utility:** AES-256-GCM with column-bound associated data and key fingerprints for rotation;
  keyed lookup hashes for emails/IPs.
- **Retention interfaces:** session purge, contact deletion and prospect erasure that never remove suppressions.
- **Dashboard:** login, MFA verify and enrolment, forced password change, account security (password, MFA,
  recovery codes, sessions), user administration and activity log; same-origin API proxy and automatic
  token refresh. Every control performs a real action.
- **Contract:** `packages/contracts/openapi.json` (test fails if stale). API reference: `docs/api/README.md`.
- **Ops:** Compose `migrate` one-shot service; `make env` generates real secrets; `make test-integration`
  with throwaway Postgres/Redis; browser E2E test (`make e2e`); CI runs DB tests (required) and the E2E flow.
- **Docs:** `docs/security/authentication.md`, `docs/compliance/retention.md`, ADR 0002, updated
  `.env.example`, versions and architecture.

### Verification evidence (local run, 2026-11-26)

| Check | Command | Result |
|---|---|---|
| Install | `make install` | PASS |
| Lint / format | `make lint` (ruff, eslint, prettier) | PASS |
| Types | `make typecheck` (mypy strict, 66 files; tsc strict) | PASS — 0 issues |
| API tests (real PostgreSQL 18 + Redis 8) | `make test-integration` | PASS — 193 passed, 0 skipped |
| Dashboard tests | `npm test` | PASS — 37 passed (5 files) |
| API tests without a database | `make test` | 85 passed, 108 **skipped** (reported, not counted as passed) |
| Dashboard production build | `npm run build` | PASS — 10 routes + proxy |
| Compose | `make compose-config`, `docker compose up --build --wait` | PASS — migrate exited 0, 4 services healthy |
| Smoke | `make smoke` | PASS — 14/14 |
| Browser E2E | `make e2e` (Chromium) | PASS — 15/15 steps |
| Log hygiene | grep API logs for test passwords/emails; error lines | 0 matches; 0 errors |
| CI | GitHub Actions | NOT RUN here — runs on push |

Test coverage by area: migrations (empty DB upgrade, downgrade/upgrade round trip, models = migrations),
password hashing/policy, login/logout/revocation, refresh rotation/reuse/grace/expiry/absolute limit, MFA
enrolment/verify/replay/recovery/expiry/disable rules, RBAC matrix (28 role×route cases) and forged/`alg:none`
tokens, CSRF and Origin, rate limiting (IP, account, MFA, limiter outage), lockout, activity-log redaction and
append-only triggers, FK/unique/check constraints, UTC handling, encryption/rotation, retention, bootstrap CLI,
client-IP trust, dashboard redirect safety, proxy path/header filtering.

### Known issues / notes
- Migration `0001` was regenerated during this phase (never applied outside development). From now on,
  schema changes must be new revisions.
- CSP still allows inline scripts; nonce-based CSP is planned for Phase 10 (ADR 0002).
- Per-IP login limiting sees the dashboard as the client until Caddy supplies a trusted
  `X-Forwarded-For` (Phase 11). Per-account limits and lockout are fully effective now.
- Starlette's `httpx` test-client deprecation warning remains (harmless).

### Security observations
- No secrets, real customer data or default credentials in the repository.
- Tokens, recovery codes and MFA secrets are stored only as HMACs or ciphertext.
- `LOOKUP_HASH_KEY` must never be rotated without re-hashing; documented in the auth design.

### Next phase
Phase 02 — Source adapters and data governance (`docs/spec/PHASE_PROMPTS/PHASE_02_SOURCE_ADAPTERS.md`).
Requires owner approval to start.

## Phase 00 — Foundation (2026-11-26)

### Delivered
- Monorepo: `apps/api` (FastAPI), `apps/dashboard` (Next.js), `infrastructure/`, `docs/`. Deviations: ADR 0001.
- Validated settings module covering every variable in `.env.example`; production fail-fast; risky
  capabilities rejected until implemented.
- Structured JSON logging with request/correlation IDs and secret/PII redaction.
- `GET /health/live` and `GET /health/ready` (real PostgreSQL `SELECT 1` and Redis `PING`, bounded timeouts,
  503 when not ready, error class only — no driver messages).
- Dashboard system-status page showing live API readiness, `/health` route, security headers.
- Docker Compose: PostgreSQL 18, Redis 8 (password), API, dashboard; healthchecks; named volumes;
  internal backend network; no DB/Redis host ports; API/dashboard bound to 127.0.0.1; non-root,
  read-only containers with all capabilities dropped and `no-new-privileges`.
- GitHub Actions CI: API lint/format/types/tests; dashboard lint/format/types/tests/build; Docker stack
  smoke test. Actions pinned by SHA; read-only token permissions.
- Makefile: `help env install dev up down logs ps smoke lint format typecheck test build compose-config clean`.
- Docs: versions, architecture overview, ADR 0001, this status file.

### Verification evidence (local run, 2026-11-26)

| Check | Command | Result |
|---|---|---|
| API deps | `uv sync --frozen` | PASS |
| API format | `uv run ruff format --check .` | PASS |
| API lint | `uv run ruff check .` | PASS |
| API types | `uv run mypy` (strict) | PASS — 13 files, 0 issues |
| API tests | `uv run pytest` | PASS — 44 passed |
| Dashboard deps | `npm ci` | PASS |
| Dashboard lint | `npm run lint` / `npm run format:check` | PASS |
| Dashboard types | `npm run typecheck` | PASS |
| Dashboard tests | `npm test` | PASS — 13 passed (3 files) |
| Dashboard build | `npm run build` | PASS (`/` partial prerender, `/health` dynamic) |
| Compose config | `docker compose config --quiet` | PASS |
| Images | `docker compose build` | PASS (see known issues for sandbox proxy note) |
| Stack start | `docker compose up -d --wait` | PASS — all 4 services healthy |
| Smoke | `infrastructure/scripts/smoke.sh` | PASS — 9/9 |
| Degraded state | stop redis → dashboard | PASS — shows "Degraded", Redis "Failed (ConnectionError)", API 503 |
| Browser check | Playwright, 1280px and 390px | PASS — no console errors, no horizontal overflow |
| Shutdown | `docker compose down` | PASS |
| CI workflow | GitHub Actions | NOT RUN here — runs on push |

### Known issues / notes
- The verification sandbox reaches registries through a TLS-intercepting proxy, so images were built
  there with a local, uncommitted override that adds the proxy CA. The committed Dockerfiles are
  unchanged and need no override on a normal machine or in CI.
- Starlette prints a deprecation warning about `httpx` in its test client; harmless, tracked for upgrade.
- CSP allows inline scripts until nonce-based CSP lands with auth (Phase 01). See ADR 0001.

### Security observations
- No secrets in the repository; `.env` is Git-ignored and created with mode 600.
- PostgreSQL and Redis are unreachable from the host and have no internet route.
- Readiness and error responses never include driver messages, hostnames or credentials.
- Request IDs from callers are validated before being logged or echoed (no header/log injection).

### Next phase
Phase 01 — Database, migrations and secure authentication (`docs/spec/PHASE_PROMPTS/PHASE_01_DATABASE_AUTH.md`).
Requires owner approval to start.
