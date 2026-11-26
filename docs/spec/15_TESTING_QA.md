# 15 — Testing and Quality Assurance Strategy

## Testing pyramid

- Unit: validators, scoring, state machine, jurisdiction rules, suppression, URL validation and cost calculation.
- Integration: migrations/transactions, Redis jobs, source adapters, AI mocks, storage, email mock and webhook verification.
- E2E: dashboard flows using fixture businesses and mock external services.
- Browser security: SSRF, DNS, redirect, metadata and private-IP cases.
- Acceptance: fake prospect → audit → concept → proposal → compliance HOLD/eligible.
- Operational: backup restore, pause switch, provider outage, worker restart, disk alert and rollback.

## Mandatory fixture websites

1. Clean responsive service business.
2. Fixed-width desktop-only site.
3. Broken image paths.
4. Navigation links to 404.
5. Missing/unclear CTA.
6. Unsupported claims that AI must not repeat as verified facts.
7. Redirect loop and redirect to private IP.
8. DNS rebinding/mixed-IP simulation.
9. Localhost and metadata targets.
10. Slow page and oversized media.
11. Consent/cookie overlay.
12. Bot-blocked or unavailable website.

## Email tests — never send real messages

- Mock provider/sandbox only.
- Unknown country returns HOLD.
- UK individual/sole-trader and corporate categories are not conflated.
- Canada needs a configured qualifying consent basis; public email is not blanket permission.
- Suppressed email cannot be scheduled or sent.
- Opt-out racing a queued job wins.
- Hard bounce and complaint suppress the contact.
- Invalid webhook signature rejected.
- Duplicate provider event processed once.
- Ambiguous send result reconciled, avoiding duplicate.
- Global/email pause stops queued sends.
- Sender/subject/header mismatch rejected.

## AI/content tests

Invalid JSON/schema rejected; extra fields rejected; prompt injection cannot execute tools or override policy; no invented testimonials/awards/prices/locations; unknown facts omitted or flagged; six-page content consistency; regeneration preserves prior version; no shell/tool execution from model output.

## Design checks

Screenshot all six pages at desktop/mobile; no horizontal overflow; contrast/focus checks; working navigation; forms inert; asset provenance; independent concept banner; no broken images/fonts, console errors or source-map leakage.

## Data/jobs tests

Migrations from empty and previous state; idempotent duplicate jobs; worker crash/lease recovery; bounded retries; dead-letter visibility; transactional outbox; retention/deletion respects suppression.

## Security tests

Login rate limiting; RBAC; CSRF/XSS; SSRF/open redirect; preview-token expiry and entropy; webhook replay/signature; secret/dependency scans; DB/Redis not public; browser worker cannot reach internal services/metadata.

## Required evidence

Every phase report lists exact commands, tests/counts, failure and skip reasons, manual checks and remaining risks. Never describe skipped tests as passed.
