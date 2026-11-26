# PHASE 05 — AI Intelligence and Structured Design Briefs

Read `08_AI_DESIGN_ENGINE.md`, `11_SECURITY.md`, `18_COSTS_AND_LIMITS.md`, `21_OFFICIAL_REFERENCES.md`.

## Work
1. Verify current Anthropic API docs, SDK, model IDs, structured output behavior, data retention/privacy, rate limits and pricing. Record actual chosen model/version and checked date; do not guess model IDs.
2. Create server-side AI adapter and per-job token/cost caps.
3. Define versioned strict JSON/Pydantic schemas for business summary, facts, assumptions, design tokens, sitemap, six page plans, blocks, image briefs, sources and accessibility requirements.
4. Treat prospect website text as untrusted data; prompt injection cannot override policy or trigger tools.
5. Separate verified facts, proposed copy and assumptions. Every factual claim references source; unsupported claims omitted.
6. Structured output only; no shell, arbitrary URL fetch, DB access or executable tools.
7. Strict validation, reject extra fields, sanitize content, bounded schema-repair retries.
8. Store model/prompt/schema versions, usage and estimated cost.
9. Owner review UI for brief, facts and assumptions.

## Tests
Invalid JSON/schema, prompt injection, invented awards/testimonials/prices/addresses, missing fact sources, budget exhaustion and provider outage. Mock model in CI.

## Deliverable
Structured brief generator, owner review UI, schema tests and cost accounting. **Stop after Phase 05.**
