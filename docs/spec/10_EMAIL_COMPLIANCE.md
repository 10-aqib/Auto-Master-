# 10 — Outreach, Deliverability and Legal Eligibility

> Engineering specification, not legal advice. Requirements vary by country, recipient type, message and facts. Obtain qualified legal review for every target category. Until reviewed and configured, hold recipients and do not send.

## Core rule and default

A publicly visible email address is not proof of consent or automatic permission to market. “B2B” is not a universal exemption.

- `OUTREACH_ENABLED=false` by default.
- `SENDING_MODE=MANUAL_REVIEW` by default.
- No external sends during development, tests or CI.
- Unknown jurisdiction, recipient category, basis, provider permission or sender requirement = HOLD.
- First release sends one initial message only. No automated follow-up sequence initially.
- Owner explicitly enables reviewed country/recipient categories after legal/provider review.

## Mandatory checks immediately before sending

1. Country/jurisdiction known.
2. Recipient type classified (corporation, sole trader, partnership, individual, role mailbox, personal mailbox, etc.).
3. Message category correctly identified.
4. Current qualified-reviewed policy configuration exists for that exact category.
5. Required legal basis/consent evidence recorded.
6. Source and use of personal data permitted; privacy obligations addressed.
7. Email verified from an allowed source; no guessed addresses.
8. Not globally/campaign suppressed.
9. No opt-out, hard bounce, complaint or manual do-not-contact.
10. Accurate sender identity/reply-to and required physical address/disclosures supplied.
11. Required unsubscribe mechanism is live.
12. Provider policy permits this exact traffic and account approval is documented.
13. Sender-domain authentication ready.
14. Rate and cost budgets not exceeded.
15. Global/email/campaign pause off.
16. Preview link is valid, unexpired and labelled independent concept.
17. Message is truthful, personalized and non-deceptive.

Any failed condition returns INELIGIBLE or HOLD with reason codes. Admin cannot silently bypass suppression or unsubscribe.

## Country policy registry

Version the policy by country + recipient type + message category. Store official source URLs, review date, qualified reviewer, permitted message type, legal basis, disclosures, unsubscribe requirements, recordkeeping/retention and next review date. Do not enable any jurisdiction without this record.

Research examples requiring counsel validation:
- **United States:** CAN-SPAM applies to commercial email, including B2B; accurate headers/subject, sender/address disclosures, opt-out and honoring opt-outs are key controls.
- **United Kingdom:** PECR treatment differs for corporate subscribers vs individuals including sole traders/some partnerships; personal-data obligations can still apply.
- **Canada:** CASL generally requires express or qualifying implied consent, identification and unsubscribe; public details are not blanket permission.
- **Pakistan:** do not assume unrestricted cold email. Obtain current local legal review of electronic marketing/privacy/cyber/telecom rules before enabling.
- **Other countries:** disabled until researched and reviewed; do not extrapolate.

## Provider architecture

Implement `EmailProvider` adapter methods: `send(message, idempotency_key)`, `verify_webhook(headers, raw_body)`, `parse_event(payload)`, `get_message_status(id)` if supported, and inbound reply parsing if supported. Start with mock provider. Resend/Postmark are only candidates; do not assume they allow cold marketing. Check current acceptable-use policy, account approval, API/webhook support and geography before selecting.

## Domain and deliverability

Use a domain the owner owns. Configure exact provider-supplied SPF/DKIM/DMARC records and verify alignment. Keep personal mailbox separate from automated marketing stream where provider guidance recommends it. Accurate from/reply-to/subject. Monitor bounce, complaint, blocks and reputation. No rotating domains/inboxes, spoofing, misleading lookalikes or evasion. Tracking pixels off by default; click tracking requires privacy review.

## Unsubscribe and suppression

- Functional, easy opt-out; implement RFC 8058 one-click headers where applicable and supported, plus visible link.
- Token unguessable, scoped and never includes raw email address.
- Public opt-out endpoint works without login.
- Opt-out transactionally creates GLOBAL suppression, cancels queued messages and updates contact; recheck immediately before provider call.
- Hard bounces and complaints suppress automatically.
- Keep minimum suppression record if needed to prevent accidental re-contact; review retention with counsel.

## Pilot and limits

Start with internal mock tests. Then a small supervised pilot (e.g. up to 10 reviewed real records, only if lawful/provider-approved). Previously suggested 3–5/day is merely a cautious operational starting point, not a legal limit or deliverability guarantee. Do not infer safe volume from low message counts. Use provider limits/reputation and measured bounce/complaint rates.

## Message quality

Identify sender, state one real observation/date, say the preview is an independent concept, give a relevant next step and include required disclosures/opt-out. No fake familiarity, prior contact, urgency, deceptive subject or unsupported results.

## Replies

Use provider inbound routing or authorized least-privilege mailbox integration. Never scrape webmail or store mailbox password. Verify webhook signature and dedupe. Classify INTERESTED, NOT_INTERESTED, QUESTION, OPT_OUT, AUTO_REPLY, UNCERTAIN. Opt-out has deterministic priority even if model uncertain; uncertain commercial messages go to owner. Do not auto-negotiate pricing/delivery.

## Kill switches

Global pause, email-only pause, campaign pause, country disable and provider disable. Check them before queueing and immediately before provider call. Pause cancels/holds unsent queue jobs.
