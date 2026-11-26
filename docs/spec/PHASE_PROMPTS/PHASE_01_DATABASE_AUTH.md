# PHASE 01 — Database, Migrations and Secure Authentication

Read `CLAUDE.md`, `05_DATA_MODEL.md`, `11_SECURITY.md`, `12_API_AND_JOBS.md`, `15_TESTING_QA.md` and Phase 00 status.

## Objective
Implement schema, migrations, secure owner authentication and RBAC. Do not implement discovery or email sends.

## Work
1. Create SQLAlchemy models/Alembic migrations for users, campaigns, prospects, prospect_campaigns, prospect_sources, external_place_identifiers, email_contacts, website_audits, audit_findings, design_projects, design_pages, assets, proposals, preview_deployments, compliance_assessments, consent_records, suppressions, outreach_messages, email_events, replies, jobs, activity_logs, api_usage and policy_configs. Stage tables if needed, but document omissions/deviations.
2. Use UUIDs, UTC timestamps, foreign keys, constraints, indexes and privacy-safe fields.
3. Test migrations from empty DB and prior phase state; add downgrade where safe.
4. Secure one-time owner bootstrap; no seeded default password.
5. Argon2id or maintained password hashing; short-lived sessions; refresh rotation/revocation; MFA/TOTP path.
6. RBAC: OWNER, ADMIN, REVIEWER, READ_ONLY; test positive and negative route access.
7. CSRF protections for cookie auth, secure HttpOnly/SameSite cookies, login rate limits and safe errors.
8. Append-only activity log for privileged actions; redact sensitive data.
9. Application-level encryption utility for contact data and strict key configuration.
10. Retention/deletion interfaces; do not accidentally delete required suppression records.

## Tests
Migration upgrades, password handling, login/logout/revocation, MFA path, RBAC, CSRF/session, rate limiting, activity-log redaction, FK/unique constraints and UTC handling.

## Deliverable
Working database/auth, migrations, API docs, updated `.env.example`, schema diagram and test evidence. **Stop after Phase 01.**
