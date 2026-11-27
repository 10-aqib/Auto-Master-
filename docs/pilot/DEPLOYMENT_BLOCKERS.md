# Deployment Blockers

Date: 2026-11-27. Passing automated tests does **not** make WEBFORGE AI production-ready. Each item below must
be closed, with evidence, before the stage named in its "Blocks" column.

Stages: **P** = internal real-data pilot (owner only, email OFF) · **E** = any real outbound email ·
**X** = production / external users.

## A. Owner decisions and inputs (not supplied; must not be invented)

| # | Blocker | Blocks | Owner action |
|---|---|---|---|
| A1 | VPS not provisioned (supported Ubuntu LTS) | P | Provision a server; share the host details out of band |
| A2 | Domains not supplied: dashboard, API, preview (the preview must be a separate origin) | P | Register the domains and point DNS at the VPS |
| A3 | Professional sender mailbox and domain not supplied | E | Provide the mailbox; set up SPF, DKIM and DMARC; then `EMAIL_DOMAIN_AUTHENTICATED=true` |
| A4 | Postal address for email footers (`EMAIL_PHYSICAL_ADDRESS`) not supplied | E | Provide a real address |
| A5 | Legal entity, phone and other business identity details not supplied | E, X | Provide them or confirm none are needed |
| A6 | Off-site backup destination not chosen | P | Choose S3-compatible storage; set the backup remote and key; keep `BACKUP_ENCRYPTION_KEY` offline as well |
| A7 | Alert channel (`ALERT_WEBHOOK_URL` / `ALERT_EMAIL_TO`) not set | P | Choose a channel |

## B. Legal and compliance (counsel required)

| # | Blocker | Blocks | Detail |
|---|---|---|---|
| B1 | Is Places-based prospect discovery a permitted use (ToS §3.2.3(a),(d)(iii))? | Enabling `google_places` | Keep it DISABLED; use owner-provided URLs. `DATA_SOURCE_COMPLIANCE_REVIEW.md` COUNSEL-1 |
| B2 | Country email policies are inactive DRAFTs | E | A reviewed policy and legal basis per country and recipient type (Pakistan and each international market) |
| B3 | Retention periods not signed off | X | `docs/compliance/retention.md` |
| B4 | AI provider data processing terms for business facts | P (if AI briefs are used) | COUNSEL-2; use the mock AI provider until confirmed |
| B5 | Privacy notice and data subject request process | E, X | Draft and publish; the deletion tooling exists (retention jobs, suppression) |

## C. Engineering work not done (by design or out of scope)

| # | Blocker | Blocks | Detail |
|---|---|---|---|
| C1 | **No real email provider adapter exists.** Only the mock provider. | E | Build the adapter behind the existing interface, then relax the config validator with owner approval. The kill-switch tests (`test_email_kill_switch.py`) must be updated deliberately; their failure is the alarm. |
| C2 | Provider policy approval (`EMAIL_PROVIDER_POLICY_APPROVED`, `EMAIL_PROVIDER_APPROVAL_REF`) | E | The chosen provider must accept cold B2B outreach in writing |
| C3 | Live bounce and complaint webhooks never tested against a real provider | E | Sandbox account test after C1 |
| C4 | Independent penetration test | X | Before any external exposure |
| C5 | Restore onto a *different* host never drilled | P (before real data accumulates) | Repeat `make recover` on the VPS from an off-site copy |
| C6 | Image vulnerability findings from the Phase 11 scan not re-checked on a clean build | P | Rebuild on the VPS, run `make scan-images`, patch criticals |
| C7 | CI on GitHub Actions not observed for this commit | P | Check the workflow result after push |
| C8 | Paid API keys (Google Places, Anthropic) and budgets are unset, so every budget is 0 (blocked) | Enabling those sources | Set small daily budgets; check that the 80 % warning reaches the alert channel |
| C9 | External uptime monitoring not configured | X | Owner's choice of provider |

## D. Already closed in this review

- Unverified Google website URLs retained → fixed and redacted (migration 0010).
- Explicit port `0` rewritten to 80 → now blocked.
- No guard independent of pauses against a non-mock provider → hard guards added.
- Full recovery existed only as runbook prose → `make recover`, drilled.
- No independent provenance check → `python -m webforge_api.provenance_audit`.

## E. Pilot entry conditions (all required)

1. A1, A2, A6, A7, C5, C6 and C7 closed.
2. `EMAIL_SENDING_ENABLED=false`, `EMAIL_PROVIDER=mock`, and `EMAIL_PAUSE=true` set in the VPS `.env`
   (belt and braces).
3. `google_places` DISABLED unless B1 is answered in writing.
4. `make smoke`, `make isolation`, `make restore-test` and the provenance audit all pass on the VPS.
5. Owner approval recorded.
