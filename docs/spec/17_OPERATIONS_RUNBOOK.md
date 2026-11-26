# 17 — Operations Runbook

## Daily checks

- Dashboard/API/DB/Redis/worker health.
- Queue depth, oldest job and dead-letter count.
- Provider errors, bounces, complaints and inbound events.
- Global and email pause state.
- Daily/monthly provider spend.
- Disk, memory, CPU, storage and backup result.
- Certificate expiry and DNS/provider status.

## Emergency: unexpected email sending

1. Activate global and email-only pause.
2. Disable provider credential/route if pause is uncertain.
3. Cancel queued outreach jobs.
4. Preserve relevant logs/events securely.
5. Rotate keys if compromised.
6. Investigate eligibility, suppression, queue race and webhook paths.
7. Notify provider/counsel and affected parties as required.
8. Resume only after root cause is fixed and retested.

## Provider complaint/bounce spike

Pause affected campaign/provider/country. Check source validity, legal eligibility, sender authentication and provider notices. Suppress complaints/hard bounces. Do not resume or increase volume until reviewed and permitted.

## Database/worker outage

Pause discovery and all mail. Inspect health/disk/logs. Do not manually edit job rows. Restore service or backup using documented procedure. Reconcile outbox and provider events before resuming.

## Suspected secret leak

Pause integration, revoke/rotate key in provider console, update secret store, redeploy, scan Git/logs/artifacts, preserve evidence and assess notification duties with counsel.

## Job recovery

Retry only transient/idempotent work. Reconcile provider status before retrying email. Use dead-letter reason codes. Log operator, time and reason.

## Maintenance

Apply OS updates; review dependency upgrades; check provider/API policy/version changes; rotate keys; renew jurisdiction policy reviews; test backup restore quarterly and after backup changes; expire preview/artifacts per retention.

## Alerts

API/DB/Redis outage; queue age; worker crash loop; repeated failures; budget cap; unexpected pause change; complaint/bounce threshold; backup failure; disk threshold; certificate expiry; login spike; webhook signature failures.
