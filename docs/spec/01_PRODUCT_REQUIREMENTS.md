# 01 — Product Requirements Specification

## Modules

### A. Campaign manager
Create/edit/pause/archive campaigns. Fields: name, countries, cities/regions, industries/categories, include/exclude terms, maximum prospects, schedule, budget ceiling, allowed sources, permitted recipient types and notes. Activation is blocked if source policy, jurisdiction policy, budget or sending mode is missing. States: DRAFT, READY, ACTIVE, PAUSED, COMPLETED, ARCHIVED.

### B. Discovery and prospect manager
Search approved sources, independently verify domain and business facts, record provenance/timestamps, deduplicate and review candidates. Place ID may be retained according to current Google policy; Maps-derived content must not be stored as a shadow prospect database. Branches/franchises must not be merged without evidence.

### C. Qualification
Score only known evidence: public website accessibility, mobile experience, navigation, visual hierarchy, conversion path, business fit and verified source quality. Every score component must show evidence, source, timestamp and confidence. Do not infer revenue, budget or purchase intent. Outcomes: STRONG, POTENTIAL, INVESTIGATE, REJECTED, MANUAL_REVIEW.

### D. Website audit
Use isolated browser workers on public sites. Capture desktop/mobile; inspect reachability, responsive layout, navigation, links, forms/CTAs, broken images, accessibility basics and measurable performance. Bound crawl depth, pages, time and bytes. Never log in, submit forms, purchase, bypass bot protection or run intrusive tests. Every finding contains evidence, severity, viewport, URL, timestamp and reproduction notes.

### E. AI analysis
Generate a structured brief from verified facts and observed audit evidence. Separate verified facts, assumptions and proposed copy. Validate output against a versioned schema. Record provider/model/version, prompt version and cost.

### F. Six-screen concept website
Default screens: Home; Services/Products; About; Industry-specific trust/process; Inquiry/Booking demo; Contact. Adapt by business category. Independent concept only. Use factual content and licensed/original assets. Demo forms must not submit or collect real data.

### G. Validation
Build in an isolated worker. Test desktop/tablet/mobile, links, assets, console errors, accessibility basics, load behavior and consistency. Preserve versions. Capture six clean screenshots.

### H. Proposal and preview
Create a branded PDF with cover, evidence-based observations, design direction, page map, six screenshots, cautious benefits wording and developer introduction. Preview URL is unguessable, read-only, labelled independent concept, revocable and time-limited (default 30 days). No tracking pixels by default.

### I. Outreach and mailbox events
One-to-one, evidence-based outreach only when all legal/provider gates pass. Truthful sender identity, relevant observation, concept link and required disclosures/opt-out. Initial release sends at most one first message; automated follow-ups are out of scope until separately approved. Replies classify as positive, negative, question, opt-out, auto-reply or uncertain; uncertain goes to human review.

### J. Dashboard and metrics
Track discovered, verified, deduped, audited, qualified, generated, proposal ready, compliance held, scheduled, sent, delivered, bounced, complained, replied, opted out, interested, converted, failed, spend and cost per stage. Show why leads were held/rejected. Provide global pause button.

## Core user stories

1. Owner can create a campaign by country/industry.
2. Owner can inspect each fact's source and verification date.
3. Owner can reject a prospect globally.
4. Owner can inspect audit evidence and screenshots.
5. Owner can preview all six screens.
6. Owner can regenerate one screen without losing prior versions.
7. Owner can create a PDF and expiring preview.
8. Owner can inspect compliance reason codes before scheduling.
9. Owner can pause outbound mail immediately.
10. Recipient can opt out easily and not be contacted again.
11. Owner can inspect replies, bounces and complaints.
12. Owner can enforce daily/monthly budgets.

## Non-functional requirements

Security, privacy, least privilege, SSRF protection, worker isolation, job idempotency, bounded retries, backups, health checks, migration discipline, pagination, accessibility, observability, UTC timestamps, localization, provider budgets and deletion/retention controls.

## Product rules

- External mail defaults to MANUAL_REVIEW or DISABLED.
- AUTOMATIC mode never overrides missing legal basis, source permission, provider approval or suppression.
- Opt-out is global across campaigns.
- Hard bounce/complaint automatically suppresses further marketing contact.
- Duplicate idempotency keys must not create duplicate designs or messages.
- If an audit cannot complete, record the failure; do not fabricate findings.
- Invalid AI output receives bounded retries, then HUMAN_REVIEW.
