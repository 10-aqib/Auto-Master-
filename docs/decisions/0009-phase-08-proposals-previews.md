# ADR 0009 — Phase 08 Proposal PDF and Secure Preview

- Status: Accepted
- Date: 2026-11-26

1. **Proposal content (`proposal-1`).** Cover ("Website Redesign Concept for [Business]", independent-concept and
   non-endorsement notice), dated and scoped audit observations, design direction (palette, typography, tone,
   journey), six page previews (desktop + mobile, labelled with purpose), information architecture, potential
   improvements framed as opportunities with an explicit "not guaranteed" statement, developer introduction
   (`CONCEPT_AUTHOR_*`: Muhammad Aqib, Website Developer, aqibkhn.space, github.com/10-aqib) and a next step that
   prints `PROPOSAL_CONTACT_EMAIL` only when the owner supplies it. No phone, address, registration, years,
   client counts, testimonials or certifications are ever generated.
2. **Built from verified evidence only.** The job requires the active concept to be APPROVED with a READY
   validation; every screenshot must match the render's HTML hash and its own stored SHA-256, or the job fails
   with `version_mismatch` / `integrity_mismatch`.
3. **Offline PDF.** The self-contained HTML (autoescaped, screenshots as data URIs, CSP `default-src 'none'`) is
   rendered by Chromium in the browser sandbox (`POST /pdf`, JavaScript disabled, all network blocked). Any
   blocked request fails the job.
4. **PDF checks (pypdf).** Opens; ≥ 10 pages; no blank pages; ≥ 12 embedded images; business name, concept notice
   and developer identity present; no UUIDs (internal IDs); no debug/placeholder words or storage paths. Any
   failure keeps the proposal DRAFT (no file stored, no preview possible) and moves the prospect to
   `HUMAN_REVIEW`. Success → `PROPOSAL_READY`.
5. **Preview tokens.** 256-bit `secrets.token_urlsafe(32)`; only a keyed HMAC (`lookup_hash`, purpose
   `preview-token`) is stored; the link is shown once. Default expiry `PREVIEW_RETENTION_DAYS` (30), capped by the
   proposal's own expiry; revocation and deletion take effect on the next request.
6. **Separate origin.** `webforge_api.preview` is its own ASGI app/container (`preview`, `PREVIEW_BASE_URL`): only
   `GET /p/<token>/<page>` and `/p/<token>/proposal.pdf`; every other path and every bad/expired/revoked token
   returns the same plain 404; no docs/OpenAPI, no cookies, no API routes; per-IP rate limit (fail closed);
   headers: `CSP sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; form-action 'none';
   base-uri 'none'; frame-ancestors 'none'`, `X-Frame-Options DENY`, `noindex`, `no-referrer`, COOP/CORP,
   Permissions-Policy, `no-store`, HSTS. Production config refuses a preview origin equal to the app/API host
   or without https. Pages are hash-verified on every read; access count and last access are recorded.
7. **Retention.** Proposal PDFs expire after `ARTIFACT_RETENTION_DAYS`; `cli purge-artifacts` expires previews and
   deletes PDFs past retention, keeping only metadata. Owners can delete a proposal at any time (PDF removed,
   all previews revoked). Nothing in this phase sends email.
