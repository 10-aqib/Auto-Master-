# WEBFORGE AI — Browser sandbox

Disposable Chromium (Playwright) service used for website audits, concept screenshots and PDFs.
It holds no secrets, has no database/Redis access, and reaches the internet only through the
SSRF-filtering egress proxy. See `docs/security/browser-isolation.md`.
