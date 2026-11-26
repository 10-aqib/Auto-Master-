# WEBFORGE AI — API

FastAPI service. Entry point: `webforge_api.asgi:app`.

```bash
uv sync               # install (dev included)
uv run pytest         # tests
uv run ruff check .   # lint
uv run mypy           # strict type check
uv run uvicorn webforge_api.asgi:app --reload   # local run (needs Postgres/Redis for readiness)
```

| Module | Purpose |
|---|---|
| `config.py` | Validated settings; production fail-fast |
| `logging_config.py` | JSON logs, redaction |
| `middleware.py` | Request IDs, access log |
| `api/health.py` | `/health/live`, `/health/ready` |
| `main.py` | App factory |
