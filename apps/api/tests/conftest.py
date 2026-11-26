from __future__ import annotations

from collections.abc import Iterator

import pytest

from webforge_api.config import get_settings

# Every variable Settings reads; cleared so the developer's shell/.env cannot leak into tests.
_ENV_PREFIXES = (
    "APP_",
    "API_",
    "PREVIEW_",
    "TIMEZONE",
    "LOG_",
    "CORS_",
    "DATABASE_",
    "REDIS_",
    "CELERY_",
    "READINESS_",
    "JWT_",
    "ENCRYPTION_",
    "ACCESS_",
    "REFRESH_",
    "MFA_",
    "AI_",
    "ANTHROPIC_",
    "GOOGLE_",
    "EMAIL_",
    "S3_",
    "ARTIFACT_",
    "BROWSER_",
    "DISCOVERY_",
    "AUDIT_",
    "DESIGN_",
    "RENDER_",
    "OUTREACH_",
    "GLOBAL_",
    "SENTRY_",
    "OTEL_",
    "BACKUP_",
    "ALERT_",
)


@pytest.fixture(autouse=True)
def isolated_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    import os

    for key in list(os.environ):
        if key.upper().startswith(_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    # Run from an empty directory so a local .env file is never read.
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
