# 19 — Definition of Done and Release Gates

## Foundation
Repo, formatting/lint/type/tests, local Docker workflow, health endpoints, complete `.env.example`, `.env` ignored, architecture/status docs, no production integrations.

## Database/auth
Migrations work from empty DB; owner login/MFA/RBAC/session revocation; activity logs; sensitive data protection and redacted logs.

## Discovery
Permitted source connectors; Places policy and attribution; independent provenance; dedupe tests; budget caps.

## Audit
Fixture tests; browser cannot reach private/metadata/internal services; evidence-backed findings; unknown checks explicitly labelled.

## AI/design
Structured brief validates; six industry-relevant pages; no false facts/testimonials/awards; licensed assets; concept label.

## Proposal/preview
Responsive checks; six screenshots; valid PDF; random/expiring/revocable/read-only isolated preview.

## Email/compliance
Provider policy and account approval documented; country/recipient policy reviewed by qualified person; unknown=HOLD; sender authentication; unsubscribe/suppression; bounce/complaint webhooks; pause stops queued jobs; no auto follow-ups initially.

## Production
CI green; security scans reviewed; secrets checked; backup restore proven; monitoring configured; firewall/isolation verified; rollback rehearsed; owner launch checklist completed; external sending remains paused until owner enables a reviewed category.

## Meaning of fully automated
Once approved, the permitted pipeline may run without per-record manual actions, but never bypass source terms, law, provider policy, suppression, budget, security or pause controls. Uncertain records remain in human review.
