# ADR 0005 — Phase 04 Isolated Audit Engine

- Status: Accepted
- Date: 2026-11-26

1. **Separate browser service** (`apps/browser`, Playwright 1.63 official image) that only collects evidence.
   All judgement (findings, scores) is deterministic code in the API (`services/audit_rules.py`, rules v1), so
   it is testable without a browser and versioned.
2. **Network isolation by topology plus an SSRF egress proxy** (`webforge_api.egress_proxy`), rather than
   relying on Chromium flags alone. Runtime self-test gates every audit batch (fail closed).
3. **Evidence over opinion**: findings state what was measured, at which viewport, with reproduction steps
   and confidence. Branding is not auto-scored. Bot-blocked or erroring sites are recorded as FAILED with no
   scores. Timing is labelled "single run, indicative only".
4. **Artifact storage adapter** (`storage/`): private local volume by default, S3-compatible with SSE for
   production; keys validated against traversal; screenshots served only through authenticated endpoints.
5. **Pipeline**: qualification without audit evidence queues an audit; a finished audit queues re-qualification
   so website-quality components gain evidence.
