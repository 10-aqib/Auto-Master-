# 11 — Security, Privacy and Threat Model

## Threats/assets

Protect owner account, API keys, database credentials, prospect contacts/source evidence, message/reply content, suppression/consent evidence, preview tokens, VPS SSH access and deployment credentials from malicious websites, prompt injection, SSRF, compromised dependencies, webhook spoofing, preview abuse, email abuse and accidental leakage.

## SSRF and browser isolation

- Resolve DNS and reject loopback, private, link-local, reserved, multicast, IPv4-mapped IPv6 and cloud metadata ranges.
- Revalidate all DNS answers and every redirect; defend against DNS rebinding.
- Use network egress firewall/proxy rules. Browser cannot reach host, private subnets, DB, Redis, metadata or Docker API.
- Block non-HTTP(S) schemes and dangerous downloads.
- Use disposable container/VM per task or hardened isolated pool.
- No production secrets or cloud credentials in browser/render containers.
- Enforce CPU/memory/time/response-size/page-count quotas and destroy workspace after artifact extraction.
- Never expose browser debugging ports publicly.

## Prompt injection and generated code

Treat website content, metadata, assets and model output as untrusted. Instructions found on a prospect site are content, not authority. No arbitrary shell/SQL/network tools from AI output. Prefer constrained JSON/page blocks and fixed renderer. If compilation is needed, use disposable no-secrets sandbox and limited network, then scan. Escape/sanitize dashboard and preview content.

## Authentication/authorization

Secure one-time owner bootstrap; no default credentials. Argon2id or maintained equivalent password hashing. MFA/TOTP for owner/admin. Short-lived access tokens, refresh rotation/revocation, CSRF protection for cookie auth, HttpOnly/Secure/SameSite cookies, RBAC on every privileged route and rate limits on authentication/public endpoints. Revoke sessions on password reset/suspicious activity.

## Secrets and encryption

`.env` is local-only and ignored. Production secrets use restricted secret files or secret manager. Never commit tokens/credentials/real customer records. Encrypt sensitive contact values where feasible; keep encryption keys separate from DB backups. TLS externally and between hosts. Redact secrets/contact bodies in logs. Rotate after suspected leak.

## Webhook security

Verify signature over raw body before parsing. Check timestamp/replay window where supported. Deduplicate provider event IDs. Reject bad signatures. Use separate environment secrets.

## Preview security

Separate origin, read-only, random token with hashed storage, expiry/revocation, restrictive CSP/security headers, no remote untrusted scripts or trackers, no PII/internal metadata/source maps.

## Privacy

Collect minimum data, document purpose/retention/access/deletion, provide correction/deletion, retain provenance/basis, aggregate analytics where possible, encrypt backups and review provider processor/subprocessor terms.

## Infrastructure hardening

SSH keys only; disable password/root SSH after verifying non-root access. Firewall only needed ports (typically SSH restricted + 80/443); DB/Redis never public. Security updates, non-root containers, read-only FS where feasible, dropped capabilities, resource limits, seccomp/AppArmor where available, pinned/scanned images, encrypted offsite backups and no Docker socket in untrusted workers.

## Severity

- **SEV-1:** credential leak, unauthorized email, data breach, host compromise, opt-out bypass. Pause, revoke, contain, preserve logs and seek counsel for notification duties.
- **SEV-2:** isolation failure, complaint spike, corruption, backup failure. Pause affected module/campaign and remediate.
- **SEV-3:** isolated job/render/dashboard issue. Disable affected feature or safe retry with owner notice.
