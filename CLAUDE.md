# Claude Code Instructions — WEBFORGE AI

You are the senior engineer implementing WEBFORGE AI. Treat the documents in this repository as the product contract. Read `README.md` and the relevant specifications before changing code.

## Repository map
- Specs from the handoff: `docs/spec/` (numbered docs, `PHASE_PROMPTS/`, `CHECKLISTS/`, `REFERENCE_TEMPLATES/`). References below to spec files such as `05_DATA_MODEL.md` mean `docs/spec/05_DATA_MODEL.md`.
- Status: `docs/implementation-status.md`. Versions: `docs/versions.md`. Decisions: `docs/decisions/`.
- Commands: `make help`.

## Mission
Build a secure, reliable internal platform for Muhammad Aqib to discover business prospects, audit their public websites, create six-screen independent redesign concepts, generate proposals/previews, perform legally eligible outreach, and manage replies/conversions.

## Mandatory workflow
1. At every session start, inspect `git status`, repository structure, current phase and `docs/implementation-status.md` (create it in Phase 00).
2. Read this file, `README.md`, and relevant specifications.
3. Work on **one phase only** unless the owner explicitly instructs otherwise.
4. Before coding, state objective, files, risks and test plan.
5. Implement a complete vertical slice. No fake integrations or placeholder buttons that appear functional.
6. Run formatters, linters, type checks, tests and builds relevant to the changes.
7. Update docs, `.env.example`, migration notes and implementation status.
8. Report exact commands and actual results. Distinguish passed, failed, skipped and not implemented. Never claim an unrun test passed.
9. Stop at the phase gate and wait for the owner's next instruction.

## Owner/product facts
- Owner: Muhammad Aqib, Website Developer.
- Portfolio: `https://aqibkhn.space`.
- GitHub: `https://github.com/10-aqib`.
- Target markets: Pakistan and international.
- Desired email identity: owner's professional domain email. Actual domain/mailbox is not supplied.
- Hosting: 24/7 VPS from the beginning.
- Development environment: Claude Code.
- Never invent phone, postal address, legal entity, domain, email address, years of experience, customer counts, credentials or project claims. Use placeholders until supplied.

## Architecture direction
Next.js + TypeScript dashboard; Python + FastAPI API; PostgreSQL; Redis + Celery workers; Playwright for browser tasks; Anthropic API for structured AI output; S3-compatible storage; Docker Compose; Caddy; supported Ubuntu LTS VPS. Start as a modular monolith with separated worker pools, not premature microservices.

## Safety and compliance invariants
- Google Places: no Maps UI scraping. Do not persist Maps Content outside current permitted exceptions. Place IDs may be stored according to policy. Any other retained business facts/contact details require independent source provenance or a documented license. Show required attribution.
- Email: never infer permission from public availability. Implement country + recipient-type policy checks, documented legal basis/consent where required, accurate sender identity, legally required disclosures, easy unsubscribe, immediate global suppression, bounce/complaint handling and retention controls. Uncertain records remain on HOLD.
- Generated sites are **independent redesign concepts**, not official business websites or endorsed work. Label previews/proposals. Use original or licensed assets.
- Public URLs are untrusted. Prevent SSRF, private-IP access, DNS rebinding, redirect bypass, cloud metadata access, internal service access and dangerous downloads. Isolate browser workers.
- AI output is untrusted. Validate strict schemas. Never provide unrestricted shell/network/database tools to generated content.
- Provide global, email-only, campaign, country and provider pause controls. Pausing must stop already queued but unsent mail.

## Engineering standards
- Strict TypeScript, Python type hints and Pydantic schemas.
- Validate settings at startup; `.env` is local-only and ignored by Git.
- UTC timestamps in storage; convert timezones at UI/scheduling boundaries.
- Database migrations are mandatory; never mutate production schema manually.
- Authenticate/authorize all privileged API calls; stable errors and suitable rate limits.
- Jobs are idempotent, observable, bounded and retried only when safe.
- Keep provenance for factual data, scores and AI-generated content.
- Structured logs with correlation/job IDs; redact secrets and personal data.
- PostgreSQL and Redis are never publicly exposed.
- No arbitrary shell execution from user/AI input.
- No silent production fallback to mock data.
- UI controls must perform real actions or be disabled with a reason.

## Quality gates
- No live email during development, tests or CI. Use mock/sandbox provider.
- Use fake businesses and test domains in automated tests.
- Sending is disabled by default until all manual gates and owner approvals are complete.
- Before release, test unsubscribe, bounce, complaint, duplicate jobs, pause switch, credential rotation, backup restore, SSRF defenses and preview isolation.
- Do not pass a phase with critical failed tests or unresolved security defects.

## Initial action
Read the handoff, summarize the architecture/constraints and propose the Phase 00 plan. Implement Phase 00 only. Do not send email, use paid APIs, or create cloud resources unless the owner explicitly authorizes that action.
