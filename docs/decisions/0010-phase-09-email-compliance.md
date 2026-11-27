# ADR 0010 — Phase 09 Email Compliance Engine (mock only)

- Status: Accepted
- Date: 2026-11-27

1. **No live provider.** Resend and Postmark prohibit unsolicited email (docs/compliance/email-providers.md). Only
   the mock provider ships; live sending stays rejected by configuration.
2. **Policy registry.** `policy_configs` keyed by country + recipient type + message category, versioned, with
   rules (`permitted`, `legal_bases`, `consent_required`, `disclosures`, `unsubscribe`, `retention_days`,
   `next_review`), official sources and reviewer. ACTIVE requires recorded qualified review (DB constraint);
   activation is owner-only and retires the previous version. `cli seed-policy-drafts` creates inactive
   research drafts (US/GB/CA/PK) that permit nothing.
3. **Eligibility (17 checks)** run when drafting, again on owner approval, and again inside the send job
   immediately before the provider call: country, recipient type, category, active current policy (and that it
   permits), legal basis + evidence (and live consent record where required — a public address is never consent),
   personal-data review, verified non-guessed address on the verified domain, suppression, opt-out/DNC state,
   sender identity and required postal address, unsubscribe, provider permission, sender-domain authentication,
   daily/hourly limits (0 blocks), all pause switches, valid proposal/preview, and truthful content (no fake
   reply prefixes, urgency, familiarity, guarantees or implied endorsement; concept notice, observation date and
   opt-out present). Suppression/DNC → INELIGIBLE; anything else missing → HOLD. No role can bypass them.
4. **One message, owner-approved.** v1 sends a single initial message per prospect; no follow-ups. Approval is
   owner-only and moves the message to SCHEDULED; the send job holds (defers) while any pause is on: global,
   email, campaign, `country_pause:XX`, `provider_pause:<name>`.
5. **Send safety.** Advisory lock per recipient hash serialises opt-out and send pre-flight. The send intent
   (SENDING, fresh preview link, unsubscribe token hash, final encrypted body) is committed before the provider
   call; the provider idempotency key is stable across retries; ambiguous results are reconciled by asking the
   provider, never by resending blindly.
6. **Unsubscribe.** 256-bit token per message (hash only stored), `List-Unsubscribe` + RFC 8058 one-click
   header; public `GET /u/<token>` shows a button (no state change), `POST` creates GLOBAL suppression and cancels
   unsent mail in one transaction; prospect → UNSUBSCRIBED/DNC. Suppressions cannot be removed via the API.
7. **Webhooks and replies.** HMAC-SHA256 over `timestamp.body` with a 5-minute window, unique event IDs
   (duplicates ignored), rate limited, 1 MB cap. Hard bounce/complaint → suppression; soft bounces/opens are
   ignored (tracking off). Replies are matched by `In-Reply-To`, stored encrypted and classified by fixed rules:
   OPT_OUT (always wins, auto-suppresses), AUTO_REPLY, NOT_INTERESTED, INTERESTED, QUESTION, UNCERTAIN; all
   commercial/unclear replies wait for the owner. Nothing replies automatically. A dev-only simulator posts signed
   mock events through the same path.
