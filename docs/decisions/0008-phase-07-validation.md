# ADR 0008 — Phase 07 Offline Concept Validation and Screenshots

- Status: Accepted
- Date: 2026-11-26

1. **Measure in the sandbox, judge in the API.** The browser sandbox (`POST /validate`, `validator.py`) loads
   the six pages from the request body at `https://concept.invalid/<slug>` and returns measurements and PNGs.
   `design/validation_rules.py` (`validator-1`) turns them into pass / fail / unknown checks with severities.
2. **Fully offline.** Pages are fulfilled from memory; every other request is aborted and reported; Chromium
   runs with DNS disabled (`--host-resolver-rules=MAP * ~NOTFOUND`) and a dead proxy, and the egress proxy is
   not used. A missing image or font therefore shows up as a blocked request (critical), never as a fetch.
3. **What is checked** at desktop 1440, tablet 768 and mobile 390 for every page: loads, HTML hash matches the
   stored render (screenshot/version mismatch), screenshot captured and hash-verified, no horizontal overflow,
   no console errors, no external requests, images load, concept notice visible at top, every link resolves to
   one of the six pages, demo form neither navigates nor sends requests and has no named fields (critical);
   one h1, heading order, accessible names, alt text, WCAG AA text contrast measured on computed colours,
   visible keyboard focus, design tokens and fonts identical on all pages (major); `lang` (minor). Six pages
   present is a site-level critical check.
4. **Ready rule.** `READY` only when no critical check fails; majors are shown as warnings. A render can be
   approved only if its latest validation is `READY` (enforced by the API).
5. **Clean, high-resolution screenshots.** Device scale 2, animations disabled, caret hidden, captured before
   any keyboard or form interaction; nothing is injected into the page. 18 PNGs per render are stored under the
   render's prefix with SHA-256 and the HTML hash they depict, and served only to signed-in staff.
6. **Bounded repair.** Contrast or focus failures trigger one deterministic re-render in safe mode
   (high-contrast neutrals, explicit focus outlines) per brief version, which is then validated again. There is
   no AI regeneration in this loop. If the result still has critical failures the prospect goes to
   `HUMAN_REVIEW`.
7. **Pipeline.** A successful render queues `design.validate` on the `audit` queue (the only worker that can
   reach the sandbox). The isolation self-test gates validation like audits. The prospect moves to `VALIDATING`.
