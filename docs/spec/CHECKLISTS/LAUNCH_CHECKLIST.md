# Launch Checklist

## Technical
- [ ] CI green; dependencies/container versions pinned.
- [ ] No secrets in Git, bundles, logs or artifacts.
- [ ] Authentication/MFA/RBAC tested.
- [ ] DB migration and recovery plan tested.
- [ ] Browser/render network isolation verified.
- [ ] SSRF, redirects, DNS rebinding and metadata tests pass.
- [ ] Health/alerts configured for dashboard/API/workers.
- [ ] Preview token expiry/revocation verified.
- [ ] Backup restoration proven.
- [ ] Monitoring and cost budgets configured.

## Product
- [ ] Source provenance visible.
- [ ] Google Places terms and attribution complied with.
- [ ] Audit evidence is truthful/repeatable.
- [ ] Six screens coherent and responsive.
- [ ] No false proof or unlicensed assets.
- [ ] Proposal/preview clearly identifies independent concept.
- [ ] Demo forms are inert.

## Outreach
- [ ] Provider allows intended email category and account approval documented.
- [ ] Every country/recipient policy is reviewed and explicitly enabled.
- [ ] Sender identity and legally required disclosures correct.
- [ ] SPF/DKIM/DMARC verified.
- [ ] Unsubscribe tested externally.
- [ ] Opt-outs, bounces and complaints suppress globally.
- [ ] Webhook signature/replay tests pass.
- [ ] Provider event dedupe and ambiguous-send reconciliation work.
- [ ] Global and email pauses stop queued jobs.
- [ ] Supervised initial pilot; automatic mode remains off until owner approval.
