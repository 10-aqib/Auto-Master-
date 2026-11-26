# PHASE 04 — Isolated Website Audit Engine

Read `07_WEBSITE_AUDIT.md`, `11_SECURITY.md`, `12_API_AND_JOBS.md` and `15_TESTING_QA.md`.

## Work
1. Separate browser worker image/service using Playwright. No production secrets or browser-context access to DB/Redis.
2. Strict URL parsing, DNS resolution and validation of every IP/redirect/final target.
3. Block loopback, private, link-local, reserved, multicast, IPv6 local, cloud metadata and internal service ranges. Defend against DNS rebinding using network egress proxy/firewall.
4. Apply page/depth/time/bytes/redirect/download limits from audit spec.
5. Use disposable browser context/workspace; destroy after artifact extraction.
6. Capture desktop/mobile screenshots and collect DOM/console/network evidence without submitting forms.
7. Audit navigation, broken links/images, headings, CTA, overflow, mobile layout, accessibility basics and optionally verified performance tool.
8. Store findings with code/severity/evidence/time/viewport/confidence; unknown = NOT_TESTED/UNKNOWN.
9. Implement explainable scoring; avoid unsupported subjective claims.
10. Owner UI for audit status, screenshots and evidence.

## Tests
Use all fixture sites including localhost, metadata, malicious redirects, mixed DNS and oversized resources. Prove private targets are unreachable from inside worker. If isolation cannot be proven, disable real crawling.

## Deliverable
Hardened worker, evidence model, UI, security report and fixture tests. **Stop after Phase 04.**
