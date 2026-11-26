# ADR 0006 — Phase 05 Structured AI Design Briefs

- Status: Accepted
- Date: 2026-11-26

1. **One structured call, no tools.** Briefs come from a single Claude Messages API call through the official
   Python SDK (`anthropic` 2.14) with `output_config.format` set to a strict JSON schema generated from the
   Pydantic model (`design/brief_schema.py`, `brief-1`). No tool use, no agent loop, no network or shell access
   for the model. Constraints the API schema cannot express (lengths, patterns, six distinct pages) are still
   enforced by Pydantic after the call.
2. **Output is untrusted.** Every response is parsed with `extra="forbid"` models, then checked by
   deterministic integrity rules (`design/integrity.py`): known fact IDs only, `verified_fact` sections must
   cite facts, no testimonials/quotes, awards, certifications, years in business, statistics, prices,
   superlatives, phone numbers, emails or staff names unless the text matches a verified fact, inquiry form
   only on the inquiry page, WCAG 4.5:1 text contrast, and no instruction-like text.
3. **Context is minimal and fenced.** Only independently verified facts (`prospect_sources`,
   `is_independent = true`) and audit finding titles are sent, inside `<untrusted_context>`; the system prompt
   says that block is data only. Facts that look like instructions are flagged and force `NEEDS_REVIEW`.
   Maps content never reaches the prompt because it is never stored.
4. **Bounded repair.** On schema or integrity failure the job regenerates up to `AI_MAX_REPAIR_ATTEMPTS`
   times, sending only the list of problems (never the rejected output). If it still fails, the version is
   stored as `NEEDS_REVIEW`, the prospect moves to `HUMAN_REVIEW`, and the brief cannot be approved.
5. **Costs fail closed.** Each call reserves its worst-case cost (estimated input + max output tokens at the
   model's price, unknown models priced at the highest rate) in `api_usage` under an advisory lock, against
   `AI_DAILY_BUDGET_MINOR`. Budget 0 blocks all paid calls. Actual tokens and cost replace the reservation;
   provider errors are recorded at zero cost. Input over `AI_MAX_INPUT_TOKENS_PER_JOB` is refused.
6. **Mock provider for development and CI** (`AI_PROVIDER=mock`, the default). It builds a conservative,
   valid brief from the same context, is labelled `mock-brief-model-1`, costs nothing, and is refused in
   production (`build_model` raises; design jobs fail with `ai_not_configured`).
7. **Versioned and reviewed.** Each run stores a new `design_briefs` version with schema and prompt versions,
   model, facts snapshot, validation issues, attempts, tokens and cost. Owner/admin/reviewer approves or
   rejects; only approved briefs are copied to the design project for Phase 06.
8. **Provider failures.** Rate limits, timeouts, connection errors and 5xx/529 are retryable job failures;
   authentication and bad-request errors are permanent. Refusals use server-side fallbacks
   (`fallbacks: "default"`), and a remaining refusal is stored for review, not retried.
