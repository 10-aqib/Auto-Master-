# 21 — Official References and Re-Verification Register

**Checked for package preparation:** 26 November 2026. Documentation, terms, APIs and law can change. Claude must revisit official sources before implementation/launch and record the checked date/version in `docs/versions.md` and compliance records.

## Claude Code / Anthropic
- Claude Code overview/installation: https://code.claude.com/docs/en/overview
- Claude Code best practices: https://www.anthropic.com/research/claude-code-best-practices
- Anthropic guidance on CLAUDE.md, skills, hooks, rules and subagents (June 2026): https://claude.com/resources/articles/steering-claude-code-skills-hooks-rules-subagents-and-more
- Anthropic API docs: https://docs.anthropic.com/

## Google Maps Platform / Places API
- Policies and attributions: https://developers.google.com/maps/documentation/places/web-service/policies
- Text Search (New): https://developers.google.com/maps/documentation/places/web-service/text-search
- Place data fields/SKUs: https://developers.google.com/maps/documentation/places/web-service/data-fields
- Field masks: https://developers.google.com/maps/documentation/places/web-service/choose-fields
- Usage and billing: https://developers.google.com/maps/documentation/places/web-service/usage-and-billing

Current reminder: Google documents caching/scraping restrictions and identifies Place IDs as an exception that can be stored. Do not use Maps content as a prospect database without an applicable permission/exception. Check the full service terms for actual project/use case.

## Email provider / standards
- Resend docs: https://resend.com/docs
- Postmark developer docs: https://postmarkapp.com/developer
- RFC 8058 one-click unsubscribe: https://www.rfc-editor.org/rfc/rfc8058
- SPF RFC 7208: https://www.rfc-editor.org/rfc/rfc7208
- DKIM RFC 6376: https://www.rfc-editor.org/rfc/rfc6376
- DMARC RFC 7489: https://www.rfc-editor.org/rfc/rfc7489

Some providers restrict unsolicited marketing or list-based sending. Confirm acceptable-use policy and account approval for this exact use case before selecting.

## Email/privacy legal sources
- US FTC CAN-SPAM guide: https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business
- UK ICO PECR electronic mail marketing guidance: https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/electronic-and-telephone-marketing/electronic-mail-marketing/
- Canada CRTC CASL implied-consent guidance: https://crtc.gc.ca/eng/com500/guide.htm
- Pakistan: research current official government/regulator sources and obtain qualified local counsel review. Do not infer a blanket rule from blogs/provider articles.

## Engineering docs
- Docker Engine Ubuntu: https://docs.docker.com/engine/install/ubuntu/
- Docker Compose: https://docs.docker.com/compose/
- FastAPI: https://fastapi.tiangolo.com/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Alembic: https://alembic.sqlalchemy.org/
- Playwright: https://playwright.dev/docs/intro
- PostgreSQL: https://www.postgresql.org/docs/
- Redis: https://redis.io/docs/latest/
- Caddy: https://caddyserver.com/docs/
- Next.js: https://nextjs.org/docs

## Research basis
Google Places requires explicit field masks for key endpoints and maps fields to billing SKUs; production requests should be minimal. Places policy restricts caching/scraping and identifies Place IDs as a storage exception. FTC outlines CAN-SPAM requirements for commercial email, including B2B. CRTC says CASL commercial electronic messages require consent (express or qualifying implied), identification and unsubscribe. Anthropic recommends repository `CLAUDE.md` instructions for coding conventions and project context.

This list is a starting register, not a substitute for reviewing all applicable current terms and laws.
