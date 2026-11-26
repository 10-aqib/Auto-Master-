from __future__ import annotations

import base64
import secrets

import pytest

from webforge_api.config import AppEnv, ConfigurationError, Settings, load_settings


def _key32() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def _production_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_URL", "https://app.test.invalid")
    monkeypatch.setenv("API_URL", "https://api.test.invalid")
    monkeypatch.setenv("APP_SECRET_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("JWT_SIGNING_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv("ENCRYPTION_KEY", _key32())
    monkeypatch.setenv("LOOKUP_HASH_KEY", secrets.token_urlsafe(48))
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://webforge:s3cure-test-pw@postgres:5432/webforge"
    )


def test_safe_defaults_fail_closed() -> None:
    s = Settings()
    assert s.app_env is AppEnv.TEST
    assert s.email_sending_enabled is False
    assert s.email_provider.value == "mock"
    assert s.email_provider_policy_approved is False
    assert s.google_places_api_enabled is False
    assert s.global_pause is False  # emergency override off; the DB switch starts paused
    assert s.email_pause is False
    assert s.mfa_required_for_owner is True


def test_development_allows_placeholders() -> None:
    settings = load_settings()
    assert settings.app_env is AppEnv.TEST


def test_valid_production_settings_load(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    assert load_settings().is_production


@pytest.mark.parametrize(
    "name", ["APP_SECRET_KEY", "JWT_SIGNING_KEY", "ENCRYPTION_KEY", "LOOKUP_HASH_KEY"]
)
def test_production_requires_secret(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    _production_env(monkeypatch)
    monkeypatch.delenv(name)
    with pytest.raises(ConfigurationError, match=f"{name} is required"):
        load_settings()


def test_production_rejects_placeholder_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("APP_SECRET_KEY", "GENERATE_A_LONG_RANDOM_SECRET_PLEASE_XXXXXXXXXX")
    with pytest.raises(ConfigurationError, match="placeholder"):
        load_settings()


def test_production_rejects_short_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("JWT_SIGNING_KEY", "too-short")
    with pytest.raises(ConfigurationError, match="at least 32"):
        load_settings()


def test_production_rejects_reused_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    shared = secrets.token_urlsafe(48)
    monkeypatch.setenv("APP_SECRET_KEY", shared)
    monkeypatch.setenv("JWT_SIGNING_KEY", shared)
    with pytest.raises(ConfigurationError, match="must all differ"):
        load_settings()


@pytest.mark.parametrize("bad", ["not-base64-!!!", base64.urlsafe_b64encode(b"x" * 16).decode()])
def test_production_rejects_bad_encryption_key(monkeypatch: pytest.MonkeyPatch, bad: str) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("ENCRYPTION_KEY", bad)
    with pytest.raises(ConfigurationError, match="32 random bytes"):
        load_settings()


def test_production_rejects_placeholder_db_password(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv(
        "DATABASE_URL", "postgresql+psycopg://webforge:CHANGE_ME@postgres:5432/webforge"
    )
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        load_settings()


def test_production_requires_https(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("API_URL", "http://api.test.invalid")
    with pytest.raises(ConfigurationError, match="https"):
        load_settings()


def test_production_rejects_debug_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    with pytest.raises(ConfigurationError, match="DEBUG"):
        load_settings()


def test_email_sending_cannot_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_SENDING_ENABLED", "true")
    with pytest.raises(ConfigurationError, match="rejected"):
        load_settings()


def test_unknown_email_provider_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "smtp")
    with pytest.raises(ConfigurationError):
        load_settings()


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("TIMEZONE", "Mars/Olympus"),
        ("DATABASE_URL", "mysql://u:p@h/db"),
        ("REDIS_URL", "http://redis:6379"),
        ("EMAIL_DAILY_MAX", "-1"),
        ("BROWSER_MAX_PAGES", "0"),
    ],
)
def test_invalid_values_rejected(monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError):
        load_settings()


def test_configuration_error_does_not_leak_secret_values(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    secret = "short-but-very-identifiable"
    monkeypatch.setenv("JWT_SIGNING_KEY", secret)
    with pytest.raises(ConfigurationError) as info:
        load_settings()
    assert secret not in str(info.value)


def test_secrets_hidden_in_repr(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    settings = load_settings()
    assert settings.app_secret_key.get_secret_value() not in repr(settings)
    assert "s3cure-test-pw" not in repr(settings)


def test_psycopg_conninfo_strips_driver_suffix() -> None:
    s = Settings(database_url="postgresql+psycopg://u:p@db:5432/x")
    assert s.psycopg_conninfo == "postgresql://u:p@db:5432/x"


def test_env_example_covers_every_setting() -> None:
    from pathlib import Path

    example = Path(__file__).resolve().parents[3] / ".env.example"
    keys = {
        line.split("=", 1)[0].strip().lower()
        for line in example.read_text().splitlines()
        if "=" in line and not line.lstrip().startswith("#")
    }
    missing = set(Settings.model_fields) - keys
    assert not missing, f".env.example is missing: {sorted(missing)}"


def test_production_rejects_placeholder_redis_password(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("REDIS_URL", "redis://:CHANGE_ME@redis:6379/0")
    with pytest.raises(ConfigurationError, match="REDIS_URL"):
        load_settings()


@pytest.mark.parametrize(
    ("name", "value"), [("COOKIE_SECURE", "false"), ("MFA_REQUIRED_FOR_OWNER", "false")]
)
def test_production_requires_secure_auth_settings(
    monkeypatch: pytest.MonkeyPatch, name: str, value: str
) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigurationError, match=name):
        load_settings()


def test_production_rejects_bad_previous_encryption_key(monkeypatch: pytest.MonkeyPatch) -> None:
    _production_env(monkeypatch)
    monkeypatch.setenv("ENCRYPTION_KEY_PREVIOUS", "short")
    with pytest.raises(ConfigurationError, match="ENCRYPTION_KEY_PREVIOUS"):
        load_settings()


def test_invalid_trusted_proxy_cidr_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "10.0.0.0/8,not-a-cidr")
    with pytest.raises(ConfigurationError):
        load_settings()


def test_sqlalchemy_url_selects_psycopg_driver() -> None:
    s = Settings(database_url="postgresql://u:p@db:5432/x")
    assert s.sqlalchemy_url == "postgresql+psycopg://u:p@db:5432/x"


def test_places_disabled_by_default_and_enabled_needs_key_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert Settings().google_places_api_enabled is False
    assert Settings().google_places_daily_request_cap == 0
    _production_env(monkeypatch)
    monkeypatch.setenv("GOOGLE_PLACES_API_ENABLED", "true")
    with pytest.raises(ConfigurationError, match="GOOGLE_MAPS_API_KEY"):
        load_settings()


@pytest.mark.parametrize("raw", ["not json", "[1]", '{"sku": -1}', '{"sku": 1.5}', '{"sku": true}'])
def test_invalid_sku_prices_rejected(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("GOOGLE_PLACES_SKU_PRICES_MINOR_PER_1000", raw)
    with pytest.raises(ConfigurationError):
        load_settings()


def test_sku_prices_parsed() -> None:
    s = Settings(google_places_sku_prices_minor_per_1000='{"TEXT_SEARCH_PRO": 3200}')
    assert s.places_sku_prices == {"TEXT_SEARCH_PRO": 3200}
