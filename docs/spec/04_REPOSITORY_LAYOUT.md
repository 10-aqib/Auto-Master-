# 04 — Target Repository Layout

```text
webforge-ai/
├── CLAUDE.md
├── README.md
├── .gitignore
├── .env.example
├── docker-compose.yml
├── Makefile
├── docs/
│   ├── implementation-status.md
│   ├── versions.md
│   ├── architecture/
│   ├── decisions/
│   ├── operations/
│   ├── security/
│   └── compliance/
├── apps/
│   ├── dashboard/       # Next.js + TypeScript
│   ├── api/              # FastAPI, auth, business logic, webhooks
│   └── preview/          # optional hardened read-only preview gateway
├── workers/
│   ├── discovery/
│   ├── audit/
│   ├── design/
│   ├── render/
│   ├── proposal/
│   ├── outreach/
│   └── shared/
├── packages/
│   ├── contracts/       # generated API contracts
│   ├── ui/              # shared UI if useful
│   └── design-schema/   # JSON schemas for briefs/page blocks
├── infrastructure/
│   ├── docker/
│   ├── caddy/
│   ├── scripts/
│   ├── monitoring/
│   └── backup/
└── tests/
    ├── fixtures/
    ├── integration/
    ├── e2e/
    ├── security/
    └── acceptance/
```

Rules:
- Follow the actual repository state. Record justified deviations in an ADR.
- Never put secrets or customer data in docs, tests or fixtures.
- Generated websites are untrusted build inputs/artifacts, not trusted application source.
- Commit database migrations.
- Keep `CLAUDE.md` concise; put detailed specs and operating procedures under `docs/`.
