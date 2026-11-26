# 02 — System Architecture

## Overview

Use a modular monolith for dashboard/API and separate worker processes for expensive or sensitive tasks.

```text
Owner Browser --HTTPS--> Caddy reverse proxy
                         |-- app.domain --> Next.js dashboard
                         `-- api.domain --> FastAPI API
                                            |--> PostgreSQL (source of truth)
                                            |--> Redis (queues/locks)
                                            |--> Discovery worker --> approved APIs
                                            |--> Audit worker --> isolated Playwright
                                            |--> Design/Render worker --> isolated build
                                            |--> Proposal worker --> PDF/screenshots
                                            |--> Outreach worker --> provider API/webhooks
                                            `--> S3-compatible object storage

preview.domain --> isolated, read-only preview gateway
```

## Components

- **Dashboard (Next.js):** campaign, prospect, audit, design, proposal, compliance, outreach and analytics UI. No secrets in browser code.
- **API (FastAPI):** authentication, validation, policy decisions, state transitions, audit logs and job creation. Long tasks run asynchronously.
- **PostgreSQL:** durable data source, migrations and relational constraints. Never public.
- **Redis + Celery:** queues, locks, counters and short-lived cache. Separate queues: discovery, audit, design, render, proposal, outreach and webhooks. Never treat Redis as permanent business state.
- **Workers:** discovery APIs; isolated browser audit; AI design brief; isolated render; PDF/proposal; outreach. Each has bounded time/resources and its own permissions.
- **Object storage:** private bucket for screenshots, PDFs, previews and assets; signed URLs/controlled gateway, lifecycle and deletion rules.
- **Email provider:** adapter interface, not hardwired. Verify current acceptable-use rules for the intended traffic. Webhook signatures and event dedupe are mandatory.

## Data flow

1. Owner creates campaign; API validates sources, budgets and policy readiness.
2. Discovery queries approved connectors within field/rate/cost limits.
3. Independent sources verify persisted business facts; provenance is stored.
4. Dedupe/qualification decides whether prospect proceeds.
5. Audit worker validates URL/DNS and runs in isolated browser context.
6. Evidence and screenshots are stored.
7. AI creates structured brief from minimal verified context.
8. Design worker creates concept; render worker builds in no-secrets sandbox.
9. Validation checks all pages/viewports.
10. Proposal worker builds PDF and preview.
11. Compliance engine classifies country, recipient type, legal basis and provider status.
12. Owner reviews. Just before sending, re-check pause, suppression, policy, provider, sender config and budgets.
13. Provider events update delivered/bounce/complaint; replies ingested via authorized integration; opt-out creates immediate global suppression.
14. Dashboard aggregates pipeline and cost data.

## Trust boundaries

Public internet inputs are untrusted. AI output is untrusted. Generated code is untrusted. Webhooks are untrusted until verified. Preview visitors are anonymous/read-only. Dashboard users require authentication, authorization and CSRF-safe sessions.

## Reliability

API creates durable jobs and returns job IDs. Use transactional outbox or equivalent. Workers use leases/locks and compare-and-set state transitions. Retry transient errors with bounded exponential backoff; never blindly retry an ambiguous email send. Use dead-letter handling and provider event deduplication. Health/readiness is separate for API, DB, Redis, workers and storage.

## Deployment

One VPS can host the initial low-concurrency pilot, but browser/render workers need strict isolation and resource limits. Scale those separately as measured. Suggested hostnames are `app.example.com`, `api.example.com`, `preview.example.com`; replace examples with a domain the owner actually controls. Optional sending subdomain must follow the selected provider's actual instructions.
