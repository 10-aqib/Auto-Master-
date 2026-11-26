# PHASE 08 — PDF Proposal and Secure Preview

Read `09_PROPOSALS_AND_PREVIEWS.md`, `11_SECURITY.md`, `15_TESTING_QA.md`.

## Work
1. Create professional PDF from current design screenshots and evidence-based audit summary.
2. Include cover, observations, design direction, six screenshots, sitemap, cautious benefits and developer intro: Muhammad Aqib, Website Developer, `https://aqibkhn.space`, `https://github.com/10-aqib`.
3. Do not invent phone/address/company registration/years/client count/testimonials/certifications. Owner supplies missing facts.
4. Include independent-concept/non-endorsement notice in PDF and preview.
5. Static read-only preview with random high-entropy token; store hash; expiry default 30 days; immediate revocation.
6. Isolate preview host; strict CSP/security headers; no secrets/source maps/private metadata.
7. Demo forms inert; collect no real user data.
8. Artifact TTL, secure storage and deletion.
9. Owner can preview/download/regenerate/expire/revoke.

## Tests
PDF opens and has expected pages/screenshots; token entropy/expiry/revocation; only valid token opens externally; no leakage; screenshots match version; forms inert.

## Deliverable
PDF and secure preview pipeline. Do not email. **Stop after Phase 08.**
