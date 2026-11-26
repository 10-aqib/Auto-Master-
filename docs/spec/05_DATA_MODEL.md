# 05 — Data Model and Lifecycle

Use PostgreSQL, UUID primary keys, UTC timestamps, foreign keys, explicit retention rules and application-level encryption for sensitive contact fields where practical. Passwords must be hashed, never stored in plaintext.

## Core tables and key fields

- **`users`** — `id`, normalized email, password hash, display name, role, active flag, MFA flag, created/updated/last-login timestamps. Roles: OWNER, ADMIN, REVIEWER, READ_ONLY. Secure one-time owner bootstrap; no default password.
- **`campaigns`** — name, status, target ISO country codes/regions, industries, filter JSON, candidate cap, daily/monthly budget, sending mode, policy version, creator and timestamps. Modes: DISABLED, MANUAL_REVIEW, AUTOMATIC_ELIGIBLE_ONLY.
- **`prospects`** — verified business name/domain, industry, country/region/city/timezone, business type, lifecycle state, qualification score/band, owner notes, first-seen/last-verified timestamps.
- **`prospect_campaigns`** — many-to-many campaign association, unique prospect/campaign pair.
- **`prospect_sources`** — source type/name/URL/record ID, fact field, safe value or value hash, retrieval/observation timestamps, terms/license version, independent-source flag and evidence note. Keep field-level provenance. Never copy restricted Maps fields here.
- **`external_place_identifiers`** — provider and Place ID only (plus last-checked timestamp). Confirm current policy before adding fields.
- **`email_contacts`** — encrypted email, normalized hash, contact name only if lawfully sourced, recipient type, role/function, source URL/time, country, verification state/method. Do not store inferred consent here.
- **`website_audits`** — prospect, URL, start/end, status, version, desktop/mobile screenshot keys, performance source, scores JSON, browser version and error summary.
- **`audit_findings`** — audit, category, severity, code, description, evidence URL/text, screenshot, viewport, confidence, observation time and reproduction steps.
- **`design_projects`** — prospect/audit, status, brief JSON/schema version, design tokens, page plan, model, prompt/renderer versions and current version.
- **`design_pages`** — design project, slug/title/page type/content JSON/render status/screenshot/sort order/version. Unique project+slug+version.
- **`assets`** — storage key, type/MIME/size/hash, provider/source, license ID/URL, attribution requirements/text, timestamps/expiry.
- **`proposals`** — prospect/design, PDF key, preview ID, proposal version/status/generated/expiry.
- **`preview_deployments`** — proposal, token hash, route, status, created/expiry/revocation, optional aggregate access count. Store token hash, not raw token.
- **`compliance_assessments`** — prospect/contact, country, recipient/message type, legal basis/evidence, policy/provider version, decision/reason codes, reviewer/time and expiry. Decisions: ELIGIBLE, INELIGIBLE, HOLD, HUMAN_REVIEW.
- **`consent_records`** — contact, consent type/scope/source/evidence, capture/expiry/withdrawal. Only when actual consent exists and is relevant.
- **`suppressions`** — normalized email hash, GLOBAL or scoped suppression, reason, source event, created time/actor. Global by default.
- **`outreach_messages`** — prospect/contact/proposal, provider/message ID, message category, subject/body version, encrypted body or storage key, status, schedule/attempt/accept/send/event times, compliance assessment, idempotency key and error code.
- **`email_events`** — provider, unique provider event ID, message, event type/time, payload hash, processing state. Unique provider+event ID.
- **`replies`** — prospect/contact, provider thread ID, received time, classification, summary, encrypted body key, human-review flag and handled time.
- **`jobs`** — type/entity/status/queue/idempotency/attempts/availability/start/finish/heartbeat/error/correlation ID. Enforce unique idempotency.
- **`activity_logs`** — actor, action, entity, redacted metadata, timestamp and safe request metadata. Append-only.
- **`api_usage`** — provider/operation/campaign/job, units/tokens, estimated cost/currency/time/provider request ID.
- **`policy_configs`** — country, recipient type, message category, version/status/rules, reviewer, review/effective dates and source references. Cannot be ACTIVE without documented qualified legal review.

## Prospect lifecycle

`DISCOVERED → SOURCE_VERIFYING → VERIFIED → DEDUPLICATED → QUALIFYING → QUALIFIED → AUDITING → AUDITED → GENERATING_DESIGN → VALIDATING → PROPOSAL_READY → COMPLIANCE_CHECK → HUMAN_REVIEW / SCHEDULED → SENT → DELIVERED → REPLIED → INTERESTED → CLIENT`

Hold/terminal states include `REJECTED`, `FAILED`, `BOUNCED`, `UNSUBSCRIBED`, `DO_NOT_CONTACT`, `POLICY_HOLD`, `EXPIRED`. State transitions require allowed-from/allowed-to rules, actor/job, reason and timestamp.

## Constraints and indexes

- Unique normalized suppression hash per scope.
- Unique provider event IDs.
- Unique idempotency keys for jobs/messages.
- Index status+created_at for queues; campaign/status/country for dashboard; verified domain for dedupe.
- Avoid globally unique domain if branches share a site.
- Choose FK delete behavior deliberately. Prospect deletion must not silently delete suppression/audit history.

## Retention and migrations

Define configurable retention by data type/jurisdiction. Provide correction/deletion workflows. Keep only minimum suppression data needed to avoid re-contact, subject to counsel review. Expire previews/artifacts automatically. All schema changes require Alembic migrations and tests; never alter production tables manually.
