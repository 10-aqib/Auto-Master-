# Email Provider Review (Phase 09)

Engineering record, not legal advice. Reviewed 2026-11-26/27 from the providers' public pages.

| Provider | Source | What it says | Decision |
|---|---|---|---|
| Resend | resend.com/legal/acceptable-use (page updated 2026-10-13) | "You are prohibited from sending unsolicited messages of any kind … including cold outreach, purchased lists, or scraped contact data." "All mail must be sent to recipients who have explicitly opted in." No B2B exception. | **Not usable** for this product's first-contact outreach. No adapter built. |
| Postmark | postmarkapp.com/terms-of-service (new customers effective 2024-12-10) | "All email lists … must be permission-based subscriptions." Purchased/rented lists prohibited. Sender must have a lawful basis and meet notice/consent obligations. | **Not usable** for unsolicited first contact. No adapter built. |

## Consequences

- Only the **mock provider** exists (`services/email/provider.py`). It sends nothing; it supports idempotency,
  scripted failures (transient, permanent, ambiguous), signed webhooks and inbound replies for testing.
- `EMAIL_SENDING_ENABLED=true` is rejected at startup. `EMAIL_PROVIDER` accepts only `mock`.
- Production refuses the mock as a "provider that permits this traffic" (check 12) and requires
  `EMAIL_PROVIDER_POLICY_APPROVED=true`, `EMAIL_PROVIDER_APPROVAL_REF` and `EMAIL_DOMAIN_AUTHENTICATED=true`.

## Before any live adapter (owner actions)

1. Choose a provider whose written policy (or written account approval) permits this exact traffic: one initial,
   personalised, non-bulk business message per prospect, with the recipient categories you intend to contact.
2. Store that written approval and reference it in `EMAIL_PROVIDER_APPROVAL_REF`.
3. Use a domain you own; publish the provider's SPF/DKIM/DMARC records and confirm alignment, then set
   `EMAIL_DOMAIN_AUTHENTICATED=true`.
4. Have qualified counsel review and activate a policy for each country + recipient type you will contact.
5. Implement the adapter against the `EmailProvider` interface with tests, and a small supervised pilot.
