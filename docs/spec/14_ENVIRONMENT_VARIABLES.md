# 14 — Environment Configuration

Validate all settings at startup and fail fast when required production configuration is missing. Keep `.env.example` synchronized with code. All values below are examples/placeholders.

## Application

```dotenv
APP_ENV=development
APP_NAME=WEBFORGE_AI
APP_URL=http://localhost:3000
API_URL=http://localhost:8000
PREVIEW_BASE_URL=http://localhost:4000
TIMEZONE=Asia/Karachi
LOG_LEVEL=INFO
```

## Database / queue

```dotenv
DATABASE_URL=postgresql+psycopg://webforge:CHANGE_ME@postgres:5432/webforge
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/1
CELERY_RESULT_BACKEND=redis://redis:6379/2
```

Do not expose DB or Redis publicly. Use least-privilege DB roles as appropriate.

## Auth / encryption

```dotenv
APP_SECRET_KEY=GENERATE_A_LONG_RANDOM_SECRET
JWT_SIGNING_KEY=GENERATE_A_DIFFERENT_LONG_RANDOM_SECRET
ENCRYPTION_KEY=USE_SUPPORTED_32_BYTE_KEY_FORMAT
ACCESS_TOKEN_MINUTES=15
REFRESH_TOKEN_DAYS=7
MFA_REQUIRED_FOR_OWNER=true
```

Generate cryptographically secure secrets; never reuse keys between purposes. Document rotation.

## AI

```dotenv
AI_PROVIDER=anthropic
ANTHROPIC_API_KEY=
ANTHROPIC_MODEL=
AI_MAX_INPUT_TOKENS_PER_JOB=
AI_MAX_OUTPUT_TOKENS_PER_JOB=
AI_DAILY_BUDGET_MINOR=0
```

Choose a current model ID from official Anthropic docs at implementation time. Server-side only.

## Google Places

```dotenv
GOOGLE_MAPS_API_KEY=
GOOGLE_PLACES_API_ENABLED=false
GOOGLE_PLACES_DAILY_BUDGET_MINOR=0
GOOGLE_PLACES_MAX_REQUESTS_PER_CAMPAIGN=0
```

Restrict key by API and server IP where possible. Use explicit field masks. Avoid persisting restricted Places fields.

## Email

```dotenv
EMAIL_PROVIDER=mock
EMAIL_API_KEY=
EMAIL_FROM_NAME=Muhammad Aqib
EMAIL_FROM_ADDRESS=
EMAIL_REPLY_TO=
EMAIL_SENDING_ENABLED=false
EMAIL_DAILY_MAX=0
EMAIL_HOURLY_MAX=0
EMAIL_MONTHLY_BUDGET_MINOR=0
EMAIL_WEBHOOK_SECRET=
EMAIL_INBOUND_SIGNING_SECRET=
EMAIL_PROVIDER_POLICY_APPROVED=false
```

Do not populate sending values until account approval, legal review and compliance setup are complete. Change from `mock` only to a provider whose current policies allow this use.

## Storage

```dotenv
S3_ENDPOINT=
S3_REGION=
S3_BUCKET=
S3_ACCESS_KEY=
S3_SECRET_KEY=
S3_FORCE_PATH_STYLE=false
ARTIFACT_RETENTION_DAYS=90
PREVIEW_RETENTION_DAYS=30
```

## Limits / worker runtime

```dotenv
BROWSER_MAX_PAGES=10
BROWSER_MAX_DEPTH=2
BROWSER_PAGE_TIMEOUT_SECONDS=30
BROWSER_MAX_RESPONSE_BYTES=5242880
BROWSER_JOB_TIMEOUT_SECONDS=300
DISCOVERY_WORKER_CONCURRENCY=2
AUDIT_WORKER_CONCURRENCY=1
DESIGN_WORKER_CONCURRENCY=1
RENDER_WORKER_CONCURRENCY=1
OUTREACH_WORKER_CONCURRENCY=1
GLOBAL_PAUSE=true
EMAIL_PAUSE=true
```

Production pause flags should be stored in durable app configuration so the owner can pause without redeploying; environment defaults fail closed.

## Monitoring / backup

```dotenv
SENTRY_DSN=
OTEL_EXPORTER_OTLP_ENDPOINT=
BACKUP_BUCKET=
BACKUP_ENCRYPTION_KEY_REF=
ALERT_EMAIL_TO=
```

Do not emit secrets or full PII in logs/traces.
