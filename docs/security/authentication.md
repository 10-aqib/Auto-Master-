# Authentication and Session Security

## Owner bootstrap

There are no default credentials. The single OWNER account is created once from the server shell:

```bash
make owner EMAIL=you@yourdomain NAME="Muhammad Aqib"
```

The CLI prompts for the password twice (never via arguments or environment), refuses if any user already
exists (advisory lock + partial unique index), and records `owner.bootstrapped` in the activity log. The
owner must enrol two-factor authentication at first sign-in.

## Passwords

Argon2id (`time_cost=3`, `memory_cost=64 MiB`, `parallelism=1`), rehashed automatically if parameters change.
Policy: 12–128 characters, no leading/trailing spaces, not trivially repetitive, not a common password, not the
email. Unknown accounts are verified against a dummy hash so timing does not reveal which emails exist.

## Tokens and cookies

| Cookie | Content | Lifetime | Flags |
|---|---|---|---|
| `wf_at` | HS256 access token (`sid`, `sub`, `exp`) signed with `JWT_SIGNING_KEY` | 15 min | HttpOnly, SameSite=Lax |
| `wf_rt` | 256-bit opaque refresh token; DB stores an HMAC of it only | 7 days sliding, 30 days absolute | HttpOnly, SameSite=Lax |
| `wf_csrf` | HMAC(session id, `APP_SECRET_KEY`) | session | readable by JS (double submit) |

With `COOKIE_SECURE=true` (required in production) the names carry the `__Host-` prefix, which forces
`Secure`, `Path=/` and no `Domain`. Every request re-reads the session row, so revocation is immediate even
though the access token has not expired.

**Refresh rotation:** each refresh issues a new refresh token and remembers the previous hash. Presenting the
previous token within 30 seconds (parallel tabs) returns a new access token without rotating again; after
that it is treated as theft and the whole session is revoked (`auth.refresh.reuse_detected`).

**Revocation triggers:** logout, logout-all, password change (all other sessions), MFA enable, role change,
deactivation, owner MFA reset, refresh-token reuse.

## CSRF and origin

State-changing requests with cookie auth must send `X-CSRF-Token` matching the session-bound token. Browser
requests carrying an `Origin` header must come from `APP_URL` or `CORS_ALLOWED_ORIGINS`. The dashboard
proxies `/api/v1/*` on its own origin, so cookies are first-party and never shared cross-site.

## Two-factor authentication

TOTP (RFC 6238, 30 s, ±1 step) with replay protection (a used time step is never accepted again). Secrets are
AES-256-GCM encrypted with `ENCRYPTION_KEY` and bound to their column as associated data. Ten single-use
recovery codes are shown once and stored as HMACs. Required for OWNER and ADMIN
(`MFA_REQUIRED_FOR_OWNER=true`, enforced in production). Completing MFA replaces the pending session with a
new one (no session fixation). Verification attempts are rate-limited per user.

## Brute-force protection

- Per-IP: `LOGIN_RATE_LIMIT_PER_IP_PER_MINUTE` (default 10).
- Per-account: `LOGIN_RATE_LIMIT_PER_ACCOUNT_PER_HOUR` (default 20), keyed by a hash of the email.
- Lockout: `ACCOUNT_LOCKOUT_THRESHOLD` failures lock the account for `ACCOUNT_LOCKOUT_MINUTES`; the response
  stays generic.
- Counters live in Redis. If Redis is unavailable, sign-in fails closed with `503`.
- The client IP is taken from `X-Forwarded-For` only when the direct peer is in `TRUSTED_PROXY_CIDRS`
  (the dashboard network). The dashboard forwards the browser's `X-Forwarded-For` only when
  `DASHBOARD_TRUST_FORWARDED_FOR=true`, which must be set only behind a proxy that overwrites it (Caddy,
  Phase 11). Until then, per-IP limits see the dashboard as the client; per-account limits still apply.

## Encryption at rest (application level)

`Crypto` (AES-256-GCM, random 96-bit nonce, column context as AAD). Ciphertexts carry a 4-byte key
fingerprint, so after setting a new `ENCRYPTION_KEY` and moving the old one to `ENCRYPTION_KEY_PREVIOUS`,
existing data stays readable and can be re-encrypted (`Crypto.reencrypt`). Lookup hashes (emails, IPs) use
HMAC-SHA256 with `LOOKUP_HASH_KEY`, which must not rotate without re-hashing suppressions.

## Secret rotation summary

| Secret | Effect of rotation |
|---|---|
| `JWT_SIGNING_KEY` | Every session ends (tokens and refresh hashes no longer verify) |
| `APP_SECRET_KEY` | CSRF tokens change; users re-load the page or sign in again |
| `ENCRYPTION_KEY` | Use `ENCRYPTION_KEY_PREVIOUS` during re-encryption, then clear it |
| `LOOKUP_HASH_KEY` | Do not rotate without a migration that re-hashes suppressions and contacts |

## Activity log

Append-only (database triggers). Records actor, action, outcome, entity, request ID, keyed IP hash, truncated
user agent and redacted metadata. Passwords, tokens, codes and email addresses are never written.
