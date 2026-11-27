# WEBFORGE AI — Internal Pilot Readiness

Date: 2026-11-27 · Branch: `claude/gifted-meitner-ozj5y9` · Migration head: `0010`

## Verdict

**The software is ready for a closed internal pilot with email OFF, once the pilot entry conditions in
`DEPLOYMENT_BLOCKERS.md` §E are met.** It is **not** production-ready, and it is not ready for any real
outbound email. Passing tests show that the code does what it was designed to do. They do not answer the
legal, infrastructure or operational questions listed as blockers.

## Pilot scope

| In scope | Out of scope |
|---|---|
| Owner-only access (OWNER account with MFA) | Other users and clients |
| Prospects added from URLs the owner supplies, verified on the business's own website | Google Places discovery (stays DISABLED until COUNSEL-1 is answered) |
| Website audits in the isolated browser sandbox | Any real email (provider adapter not built; sending blocked by config, code and pauses) |
| Mock AI briefs (real AI only after COUNSEL-2 and a small budget) | Paid APIs without explicit approval |
| Six-screen concepts, PDF proposals and token previews, labelled as independent redesign concepts | Public marketing of previews |
| Backups, restore tests, recovery drills | Multi-host or high-availability setup |

## Summary of this review

| Area | Outcome | Document |
|---|---|---|
| Email cannot reach a real provider | Proven by static, runtime and network tests; hard guards added | `SECURITY_REVIEW.md` §1 |
| Google Places terms | Reviewed against the current ToS and Service Specific Terms; one retention defect fixed; one legal question open | `DATA_SOURCE_COMPLIANCE_REVIEW.md` |
| Provenance | New independent audit; live data 14/14 | same, §4 |
| SSRF and sandbox | 17 new encodings; one low-severity fix; isolation 8/8 | `SECURITY_REVIEW.md` §2–3 |
| Previews | Expiry, revoke, hashing, roles, rate limit, headers all tested | `SECURITY_REVIEW.md` §4 |
| Budgets | Warnings at 80 %, hard stops at the limit, fail closed at 0 and on limiter outage | `SECURITY_REVIEW.md` §5 |
| Backup and recovery | Restore test and full volume-loss drill passed; `make recover` added | `INTERNAL_PILOT_TEST_RESULTS.md` §5 |
| Clean checkout | 531 API, 22 sandbox and 51 dashboard tests; build passes | `INTERNAL_PILOT_TEST_RESULTS.md` §1 |
| Remaining blockers | 7 owner inputs, 5 legal items, 9 engineering items | `DEPLOYMENT_BLOCKERS.md` |

## Changes made for the pilot

- `services/outreach.py`: hard guards before any message change (`live_email_disabled`,
  `mock_provider_in_production`).
- `services/places.py` and migration `0010`: unverified Google-supplied URLs are not kept.
- `provenance_audit.py`: read-only audit, `python -m webforge_api.provenance_audit`.
- `net/safe_fetch.py`: explicit port 0 rejected.
- `cli.py emergency-pause` and `infrastructure/scripts/recover.sh` (`make recover`).
- Tests: `test_email_kill_switch.py`, `test_pilot_ssrf.py`, `test_provenance_audit.py`, plus new cases in
  `test_sources_api.py` and `test_cli_sources.py`.

## Pilot operating rules

1. Keep `EMAIL_SENDING_ENABLED=false`, `EMAIL_PROVIDER=mock` and `EMAIL_PAUSE=true` in the VPS `.env`.
2. Keep `google_places` DISABLED. Add prospects from owner-supplied URLs.
3. Run the provenance audit weekly and before any export; any failure means pause and investigate.
4. Daily backup, weekly restore test (systemd timers in the runbook); copy backups off-site.
5. After any incident or recovery, the pauses stay ON until the owner has reviewed Operations and Activity.
6. Every preview and proposal stays labelled "Independent redesign concept"; no real business is contacted.

## Exit criteria for the pilot

- Two weeks of daily backups and two passing weekly restore tests on the VPS.
- No provenance audit failures, no dead-letter jobs left unexplained, no sandbox isolation failures.
- The owner has reviewed at least 10 audited prospects and their concepts for accuracy and labelling.
- Written answers to COUNSEL-1 to COUNSEL-4 before any decision on Places or email.

## Approvals required (not given)

- Deploying to a VPS.
- Enabling any paid API.
- Building or enabling a real email provider.
