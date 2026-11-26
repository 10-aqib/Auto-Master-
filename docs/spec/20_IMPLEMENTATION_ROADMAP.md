# 20 — Implementation Roadmap (12 Controlled Phases)

Complete one phase, execute tests, update `docs/implementation-status.md`, report evidence and get owner review before moving on.

| Phase | Name | Main output | Email |
|---|---|---|---|
| 00 | Foundation | Monorepo, tooling, Docker dev, CI, health/logging | Disabled |
| 01 | Database + auth | Schema, migrations, owner login, RBAC, audit logs | Disabled |
| 02 | Source adapters | Places policy-safe connector, provider interfaces, provenance | Disabled |
| 03 | Discovery | Campaigns, candidates, dedupe, scoring and jobs | Disabled |
| 04 | Website audit | Isolated Playwright, evidence and screenshots | Disabled |
| 05 | AI intelligence | Structured briefs and schema validation | Disabled |
| 06 | Design generation | Six-page renderer and asset provenance | Disabled |
| 07 | Validation | Responsive QA, screenshot pipeline | Disabled |
| 08 | Proposals | PDF, secure preview, expiration/revocation | Disabled |
| 09 | Email/compliance | Provider adapter, policies, unsubscribe, events | Sandbox only |
| 10 | Dashboard/orchestration | Full owner workflow, analytics, controls | Paused |
| 11 | Production | VPS, backup, hardening, supervised pilot | Only approved category |

## Detailed phases

### Phase 00 — Foundation
Monorepo, conventions, Docker dev services, API/dashboard skeleton, health endpoints, structured logging, CI, docs, environment validation and baseline tests. No paid integrations or external email.

### Phase 01 — Database and authentication
Models/migrations, secure owner bootstrap, Argon2id hashing, MFA, RBAC, session lifecycle and audit logs. Migration/unauthorized-access tests.

### Phase 02 — Sources and governance
Provider adapters; verify current Places API/terms; use field masks; retain Place IDs only as allowed; independent source verification and provenance. No Maps scraping.

### Phase 03 — Discovery/qualification
Campaigns, source queries, normalization, dedupe, evidence-based scores, manual review, rate/cost limits and job idempotency.

### Phase 04 — Audit
Hardened browser, SSRF/DNS/redirect controls, page/byte/time bounds, responsive screenshots, findings and fixtures.

### Phase 05 — AI intelligence
Anthropic adapter, current model selection, prompt/schema versions, structured output, source-grounded facts and cost limits.

### Phase 06 — Design generator
Component vocabulary, industry-aware page plans, design tokens, content integrity, asset licensing, versions and isolated render.

### Phase 07 — Validation
Desktop/tablet/mobile checks, accessibility basics, broken link/image, screenshot pipeline and bounded repair loop.

### Phase 08 — Proposal/preview
PDF, screenshot layout, concept notice, unguessable token, expiry/revocation and cleanup.

### Phase 09 — Email/compliance
Mock provider, policy registry, recipient classes, eligibility, suppression, unsubscribe, signatures, inbound replies, idempotency and pause controls. Live mail stays disabled.

### Phase 10 — Dashboard
All modules, review queues, jobs, analytics, cost alerts and working controls; orchestrate pipeline.

### Phase 11 — Production
VPS hardening, monitoring, backup/restore, security tests, provider/legal review and supervised pilot. Automatic mode only for explicitly reviewed categories.

## Every-phase rules

No inert controls, no fake business/send data outside tests, no deferring a security requirement when the feature creates that risk, tests alongside code, status docs updated, phase report with evidence.
