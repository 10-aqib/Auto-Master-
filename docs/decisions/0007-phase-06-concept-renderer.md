# ADR 0007 — Phase 06 Deterministic Six-Screen Concept Renderer

- Status: Accepted
- Date: 2026-11-26

1. **Fixed renderer, no generated code.** Concepts are produced by `design/renderer.py` (`renderer-1`): Jinja in a
   sandboxed, autoescaping environment with `StrictUndefined`, a fixed component vocabulary (hero, feature grid,
   service cards, process steps, FAQ, text, CTA band, gallery placeholder, inert inquiry demo, contact panel) and
   CSS built only from schema-validated `#RRGGBB` values and system font stacks. The AI never writes HTML, CSS
   or scripts, so there is no generated code to execute; that is the sandboxing strategy for this phase. The
   renderer has no network access and needs no secrets.
2. **Output is scanned before it is stored.** Every page must contain the notice "Independent redesign concept —
   not the official website" and must not contain scripts, event handlers, `javascript:` or any absolute/
   protocol-relative URL, frames/objects/links/base, CSS fetches, form actions, named form fields or submit
   buttons, and must be under 200 KB. Any hit marks the render FAILED and nothing is written to storage.
3. **Inert demo forms, three ways.** No `action`/`method`, fields have no `name` (nothing would be sent), the only
   button is `type="button"`, and pages carry `form-action 'none'` in a meta CSP and in the HTTP CSP.
4. **Served sandboxed.** Concept pages are returned with `Content-Security-Policy: sandbox; default-src 'none';
   style-src 'unsafe-inline'; img-src data:; form-action 'none'; base-uri 'none'; frame-ancestors 'self'`,
   `no-store`, `nosniff` and `noindex` by the API. The dashboard serves them at `/api/concepts/...` inside an
   `<iframe sandbox="allow-same-origin">` with the same CSP plus `sandbox allow-same-origin`: the frame keeps the
   dashboard origin only so in-frame links send the SameSite session cookie (an opaque origin drops it and
   every link 401s). Scripts, forms, popups, plugins and top navigation remain blocked by the sandbox, and the
   CSP allows no script source, so same-origin grants the page nothing it can use. Stored pages are verified
   against their SHA-256 on every read.
5. **Content integrity carries through.** The stored brief is re-validated and re-checked before rendering;
   assumptions are visibly marked "To be confirmed by the business"; the contact panel shows only verified
   contact facts; there is no testimonial, rating, award or statistic component at all.
6. **Assets.** Fonts are system stacks (nothing downloaded or embedded). The only image is an original,
   deterministic abstract SVG in the brief palette, stored with an `assets` row (`license_id =
   original-generated`, provider `webforge-renderer`). No hotlinks, logos or stock photography.
7. **Versioning and rollback.** Each render is a `design_renders` version (migration `0005`) with brief version,
   renderer version, variant, page manifest (keys, hashes, sizes) and scan results; pages are also recorded in
   `design_pages`. Approval makes a render active; any approved render can be re-activated (rollback). A partial
   unique index guarantees one active render per project.
8. **Cost and cancellation.** Rendering makes no paid calls; jobs are bounded (size cap, two attempts), respect
   the global pause, refuse locked/do-not-contact prospects and can be cancelled while queued.
