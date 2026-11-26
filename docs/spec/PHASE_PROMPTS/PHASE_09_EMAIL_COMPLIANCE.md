# PHASE 09 — Email Provider, Compliance Engine and Reply Events

Read `10_EMAIL_COMPLIANCE.md`, `05_DATA_MODEL.md`, `11_SECURITY.md`, `12_API_AND_JOBS.md`, `21_OFFICIAL_REFERENCES.md`.

## Objective
Build email infrastructure in mock/sandbox mode. Live external sends stay disabled until owner finishes legal/provider review and explicitly authorizes them.

## Work
1. Research current provider acceptable-use policy for intended business outreach. Never assume Resend/Postmark or other provider permits cold marketing. Record account approval/evidence. If unsupported, leave live adapter disabled and explain.
2. Implement EmailProvider interface with mock first; real adapter only if permitted.
3. Policy registry by country + recipient type + message category. Unknown/unreviewed = HOLD. Store source, version, reviewer, review date and next review.
4. Eligibility engine applies every condition in `10_EMAIL_COMPLIANCE.md`: source permission, basis/consent, disclosures, unsubscribe, provider approval, suppression, budget and pause flags.
5. Public email address is contact data, not proof of consent.
6. Secure unsubscribe token + immediate GLOBAL suppression; cancel queued mail transactionally and recheck before send.
7. Hard bounce/complaint suppression; signed webhook and replay protection; dedupe events.
8. One-time send intent/idempotency; reconcile ambiguous provider responses.
9. Inbound replies via supported provider feature or authorized least-privilege mailbox access; never scrape webmail UI.
10. Classify replies; uncertain to human review; opt-out has deterministic priority.
11. Global/email/campaign/country/provider pause controls; queued sends must stop.
12. Truthful message templates and content checks. No automatic follow-up sequence in v1.
13. Keep `EMAIL_SENDING_ENABLED=false`, `GLOBAL_PAUSE=true`, provider mock in dev/CI.

## Tests
Mock/sandbox only. Unknown country HOLD; country examples remain disabled until legal-reviewed policy is configured. Test opt-out race, suppression, complaint, bounce, replay, idempotency, pause, provider disabled and ambiguous send.

## Deliverable
Compliance engine, mock/approved adapter, webhook/reply ingestion, suppression, UI and test evidence. Do not enable live mail. **Stop after Phase 09.**
