# WEBFORGE AI — Complete Claude Code Handoff

**Purpose:** Product blueprint and implementation contract for building WEBFORGE AI from an empty repository through a tested, monitored VPS deployment.

**Owner:** Muhammad Aqib — Website Developer  
**Portfolio:** https://aqibkhn.space  
**GitHub:** https://github.com/10-aqib  
**Target markets:** Pakistan and international markets  
**Operating goal:** 24/7 VPS-hosted business discovery, website audits, custom redesign concepts, proposals, compliant outreach, and pipeline tracking.

> **Important:** This ZIP is a detailed specification and Claude Code instruction set. It is not a finished or deployed application. It contains no API keys, passwords, domain ownership claims, or working credentials. Claude Code must implement the application phase by phase, run tests, report evidence, and stop at each approval gate.

## Start here

1. Extract the ZIP into a new folder named `webforge-ai`.
2. Open that folder in a terminal or VS Code.
3. Read `CLAUDE.md` and this README.
4. Follow `13_DEVELOPMENT_SETUP.md`.
5. Start Claude Code from the project root using `claude`.
6. Paste `PHASE_PROMPTS/PHASE_00_FOUNDATION.md`.
7. Do not jump ahead. Complete the tests and review each phase report before continuing.

## Package contents

| File/folder | Purpose |
|---|---|
| `CLAUDE.md` | Persistent Claude Code project instructions |
| `00_PROJECT_OVERVIEW.md` | Vision, goals, scope and owner profile |
| `01_PRODUCT_REQUIREMENTS.md` | Features, user stories and non-functional requirements |
| `02_SYSTEM_ARCHITECTURE.md` | Components, data flow, boundaries and reliability |
| `03_TECH_STACK.md` | Stack recommendations and architecture decisions |
| `04_REPOSITORY_LAYOUT.md` | Suggested monorepo layout |
| `05_DATA_MODEL.md` | Database entities, lifecycle, indexes and retention |
| `06_DISCOVERY_AND_DATA_GOVERNANCE.md` | Lead sources, Places restrictions, provenance and dedupe |
| `07_WEBSITE_AUDIT.md` | Browser audit rules, evidence and safety |
| `08_AI_DESIGN_ENGINE.md` | AI brief, six-screen design generation and content integrity |
| `09_PROPOSALS_AND_PREVIEWS.md` | Screenshots, PDF and secure preview |
| `10_EMAIL_COMPLIANCE.md` | Country eligibility, provider, suppression, unsubscribe and replies |
| `11_SECURITY.md` | Threat model, SSRF, isolation, secrets and privacy |
| `12_API_AND_JOBS.md` | API boundaries, queues, retries and idempotency |
| `13_DEVELOPMENT_SETUP.md` | Windows/WSL setup instructions |
| `14_ENVIRONMENT_VARIABLES.md` | Environment configuration reference |
| `15_TESTING_QA.md` | Unit, integration, E2E, security and operational tests |
| `16_DEPLOYMENT.md` | VPS, Docker Compose, DNS, TLS and release |
| `17_OPERATIONS_RUNBOOK.md` | Daily operation, incidents and recovery |
| `18_COSTS_AND_LIMITS.md` | Provider budgets, limits and capacity |
| `19_ACCEPTANCE_CRITERIA.md` | Definition of done and release gates |
| `20_IMPLEMENTATION_ROADMAP.md` | 12 phased implementation plan |
| `21_OFFICIAL_REFERENCES.md` | Technical and legal sources to re-check |
| `PHASE_PROMPTS/` | Exact Claude Code prompts for Phases 00–11 |
| `CHECKLISTS/` | Owner inputs, launch, daily operations and incident checklists |
| `REFERENCE_TEMPLATES/` | Example JSON schemas and an outreach draft template |
| `.env.example` | Safe placeholder configuration |
| `.gitignore` | Prevent secrets, local data and generated artifacts entering Git |

## End-to-end workflow

`Campaign → Discover candidates → Independently verify facts and sources → Deduplicate → Qualify → Audit current website → Create evidence-based redesign brief → Generate six-page concept → Validate responsive behavior → Capture screenshots → Build PDF + expiring preview → Assess legal eligibility → Send only when permitted → Process delivery/bounce/reply/opt-out events → Update dashboard and metrics`

## Non-negotiable rules

- Never scrape Google Maps or turn Google Maps Content into a persistent prospect database. Retain only permitted identifiers such as Place IDs unless a current written license or policy exception allows more. Independently verify facts retained in the prospect database.
- A publicly visible email address is not, by itself, consent or automatic legal permission to market.
- Unknown jurisdiction, recipient type, legal basis, or provider permission means **HOLD**, not send.
- Never send to opted-out, suppressed, hard-bounced, complained, or do-not-contact recipients.
- Never bypass provider limits with rotating domains, inboxes, identities, or deceptive headers.
- Never invent testimonials, awards, staff, certifications, history, prices, opening hours, claims or contact details.
- Never run generated code with access to production secrets, database, Redis, Docker socket, host filesystem, cloud metadata or private networks.
- Keep API keys out of frontend code, logs, Git, screenshots, generated sites and PDFs.
- External sending is disabled by default. Automation can be enabled only after supervised testing and explicit owner approval for reviewed jurisdictions/categories.

## Initial Claude Code task

Claude must inspect this handoff, summarize the architecture and constraints, then implement **Phase 00 only**. It must not silently implement multiple phases.
