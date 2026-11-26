# 12 — API Modules, Job Orchestration and State Changes

## API modules

- `auth`: sessions, MFA and authorization.
- `campaigns`: campaign CRUD, policy readiness and pause/resume.
- `discovery`: source connectors and candidate jobs.
- `prospects`: verified records, notes, dedupe/merge, suppression.
- `audits`: status, screenshots and findings.
- `designs`: briefs, versions, page plans, approvals.
- `proposals`: PDF/preview, expiry/revocation.
- `compliance`: policy configs, assessments, evidence and review.
- `outreach`: drafts, scheduling, sends and event status.
- `replies`: inbound replies and classification.
- `analytics`: pipeline and cost aggregates.
- `admin`: global pause, settings, retention and health.
- `webhooks`: provider signature validation and event ingestion.

## API conventions

Version prefix `/api/v1`; Pydantic request/response models; stable pagination; consistent error `{code,message,correlation_id,field_errors}`; UTC ISO timestamps; idempotency keys for actions that create jobs/messages; auth on owner endpoints; narrow rate-limited public preview/unsubscribe endpoints; generated/versioned OpenAPI.

## Candidate endpoints

- `POST/GET /api/v1/campaigns`
- `POST /api/v1/campaigns/{id}/validate`
- `POST /api/v1/campaigns/{id}/discover`
- `POST /api/v1/campaigns/{id}/pause`
- `GET /api/v1/prospects` and `GET /api/v1/prospects/{id}`
- `POST /api/v1/prospects/{id}/audit`
- `POST /api/v1/prospects/{id}/qualify`
- `POST /api/v1/designs/{id}/generate`
- `POST /api/v1/designs/{id}/pages/{page_id}/regenerate`
- `POST /api/v1/proposals/{id}/generate`
- `POST /api/v1/proposals/{id}/revoke-preview`
- `POST /api/v1/compliance/assessments`
- `POST /api/v1/outreach/{id}/schedule`
- `POST /api/v1/admin/pause-all`
- `POST /api/v1/admin/resume`
- `POST /api/v1/webhooks/email/{provider}`
- isolated `GET /preview/{token}`
- `GET /unsubscribe/{token}` and provider-supported confirmation route

This is a candidate map; build only in the relevant phase and finalize schemas in OpenAPI.

## Job contract

Each task has stable name/payload schema version, entity/version, idempotency key, correlation ID, available time, attempt/max attempts, timeout, retry classification, lease/heartbeat and terminal safe error. Jobs are durable in DB/outbox; Redis is queue transport.

## Idempotency

- Discovery: repeated campaign/source window does not duplicate prospects.
- Audit: prospect+URL+audit version may reuse recent successful audit unless forced.
- Design: same brief/version cannot duplicate; regenerate creates version.
- Proposal: design + template version is idempotent.
- Outreach: one send intent per contact/proposal/campaign/message version unless owner creates a new reviewed message.
- Email: use provider idempotency where supported; reconcile ambiguous result before retry.
- Webhooks: unique provider event ID.

## State transitions

Only service functions change state. Validate allowed transitions in transactions, write audit event, enqueue via transactional outbox/equivalent. Avoid lost messages between DB commit and queue publication.

## Recovery

Display queued/running/retrying/failed jobs. Retry only transient/idempotent failures. Email sends and other externally billable/non-idempotent work require provider reconciliation and explicit reason before retry. Show sanitized failure/request IDs.
