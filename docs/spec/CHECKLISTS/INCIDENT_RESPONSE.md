# Incident Response Quick Card

## Unauthorized email / suspected spam incident
1. Activate global and email-only pause.
2. Disable provider credential/route if pause is uncertain.
3. Cancel unsent jobs; preserve provider events/logs.
4. Rotate exposed credentials.
5. Investigate eligibility, suppression, queue races, events and sender reputation.
6. Notify provider and seek legal advice for notification obligations.
7. Do not resume until root cause is fixed, tests pass and owner approves.

## Data leak / server compromise
1. Isolate affected host/service.
2. Revoke and rotate credentials.
3. Preserve forensic logs securely.
4. Restore from known-good release/backup after integrity review.
5. Assess breach duties with counsel.

## Provider outage or bounce/complaint spike
1. Pause affected campaign/country/provider.
2. Suppress complaints/hard bounces.
3. Inspect sender authentication, source quality and provider notices.
4. Resume only when approved and monitored.
