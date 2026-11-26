# Migration Notes

Migrations live in `apps/api/src/webforge_api/migrations/versions/` and ship inside the API image.

| Revision | Phase | Summary | Downgrade |
|---|---|---|---|
| 0001 | 01 | Initial schema (26 tables), append-only trigger on `activity_logs` | Drops everything (development only) |

Apply: `make migrate` (Compose runs the one-shot `migrate` service automatically before the API starts).
Create a new revision after changing models:

```bash
cd apps/api && uv run python -c "from alembic import command; from webforge_api.db.migrate import alembic_config; command.revision(alembic_config('postgresql+psycopg://...'), message='describe change', autogenerate=True)"
```

Review the generated file, keep it free of application imports, and run `make test-integration`:
`test_models_match_migrations` fails if models and migrations drift. Never edit an applied revision.
Production upgrades: back up first (Phase 11 runbook), then apply; downgrades in production are not supported.
