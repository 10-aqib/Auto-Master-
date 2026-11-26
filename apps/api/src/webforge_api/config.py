"""Validated application settings.

All configuration is read from environment variables (or a local, Git-ignored `.env`).
Validation runs at startup. In production any missing, placeholder or weak secret
fails fast. Risky capabilities that later phases implement (live email, Google Places)
are rejected outright until the code that makes them safe exists.
"""

from __future__ import annotations

import base64
import binascii
import ipaddress
import json
from enum import StrEnum
from functools import lru_cache
from typing import Annotated, Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_MARKERS = ("CHANGE_ME", "GENERATE_", "USE_SUPPORTED", "REPLACE_ME", "EXAMPLE")
MIN_SECRET_LENGTH = 32

NonNegativeInt = Annotated[int, Field(ge=0)]
PositiveInt = Annotated[int, Field(gt=0)]


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class EmailProvider(StrEnum):
    MOCK = "mock"


class AIProvider(StrEnum):
    ANTHROPIC = "anthropic"


class ConfigurationError(RuntimeError):
    """Raised when settings are unsafe for the selected environment."""


def _is_placeholder(value: str) -> bool:
    upper = value.upper()
    return any(marker in upper for marker in PLACEHOLDER_MARKERS)


def parse_sku_prices(raw: str) -> dict[str, int]:
    """Parse GOOGLE_PLACES_SKU_PRICES_MINOR_PER_1000 (JSON object of non-negative ints)."""
    try:
        data = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("GOOGLE_PLACES_SKU_PRICES_MINOR_PER_1000 must be a JSON object") from exc
    if not isinstance(data, dict) or not all(
        isinstance(k, str) and isinstance(v, int) and not isinstance(v, bool) and v >= 0
        for k, v in data.items()
    ):
        raise ValueError(
            "GOOGLE_PLACES_SKU_PRICES_MINOR_PER_1000 must map SKU names to non-negative integers"
        )
    return dict(data)


def is_valid_encryption_key(value: str) -> bool:
    decoded = _decode_key(value)
    return decoded is not None and len(decoded) == 32


def _decode_key(value: str) -> bytes | None:
    padded = value + "=" * (-len(value) % 4)
    try:
        return base64.urlsafe_b64decode(padded.encode())
    except (binascii.Error, ValueError):
        return None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_name: str = "WEBFORGE_AI"
    app_url: str = "http://localhost:3000"
    api_url: str = "http://localhost:8000"
    preview_base_url: str = "http://localhost:4000"
    timezone: str = "Asia/Karachi"
    log_level: LogLevel = LogLevel.INFO
    cors_allowed_origins: str = "http://localhost:3000"

    # Database / queue
    database_url: SecretStr = SecretStr(
        "postgresql+psycopg://webforge:CHANGE_ME@postgres:5432/webforge"
    )
    redis_url: SecretStr = SecretStr("redis://redis:6379/0")
    celery_broker_url: SecretStr = SecretStr("redis://redis:6379/1")
    celery_result_backend: SecretStr = SecretStr("redis://redis:6379/2")
    readiness_timeout_seconds: Annotated[float, Field(gt=0, le=10)] = 2.0

    # Auth / encryption
    app_secret_key: SecretStr = SecretStr("")
    jwt_signing_key: SecretStr = SecretStr("")
    encryption_key: SecretStr = SecretStr("")
    # Previous ENCRYPTION_KEY, accepted for decryption only during key rotation.
    encryption_key_previous: SecretStr = SecretStr("")
    # Keyed hash for lookups (email/suppression hashes). Never rotate without re-hashing.
    lookup_hash_key: SecretStr = SecretStr("")
    access_token_minutes: Annotated[int, Field(gt=0, le=60)] = 15
    refresh_token_days: Annotated[int, Field(gt=0, le=30)] = 7
    session_max_days: Annotated[int, Field(gt=0, le=90)] = 30
    mfa_pending_minutes: Annotated[int, Field(gt=0, le=15)] = 5
    # Applies to OWNER and ADMIN accounts.
    mfa_required_for_owner: bool = True
    cookie_secure: bool = True
    # CIDRs of reverse proxies (the dashboard container) whose X-Forwarded-For is trusted.
    trusted_proxy_cidrs: str = "127.0.0.1/32"
    login_rate_limit_per_ip_per_minute: PositiveInt = 10
    login_rate_limit_per_account_per_hour: PositiveInt = 20
    account_lockout_threshold: PositiveInt = 10
    account_lockout_minutes: PositiveInt = 15

    # AI
    ai_provider: AIProvider = AIProvider.ANTHROPIC
    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = ""
    ai_max_input_tokens_per_job: NonNegativeInt = 0
    ai_max_output_tokens_per_job: NonNegativeInt = 0
    ai_daily_budget_minor: NonNegativeInt = 0

    # Google Places
    google_maps_api_key: SecretStr = SecretStr("")
    google_places_api_enabled: bool = False
    google_places_daily_budget_minor: NonNegativeInt = 0
    google_places_max_requests_per_campaign: NonNegativeInt = 0
    # Requests per UTC day across all campaigns (0 = none allowed).
    google_places_daily_request_cap: NonNegativeInt = 0
    google_places_rate_limit_per_minute: Annotated[int, Field(gt=0, le=600)] = 30
    # JSON map of SKU -> price in minor units per 1000 requests, copied from Google's current
    # price list by the owner. A SKU without a price is refused (fail closed).
    google_places_sku_prices_minor_per_1000: str = "{}"
    google_places_price_currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    google_places_language_code: str = Field(
        default="en", pattern=r"^[a-zA-Z]{2,3}(-[A-Za-z0-9]{2,8})?$"
    )

    # Email
    email_provider: EmailProvider = EmailProvider.MOCK
    email_api_key: SecretStr = SecretStr("")
    email_from_name: str = "Muhammad Aqib"
    email_from_address: str = ""
    email_reply_to: str = ""
    email_sending_enabled: bool = False
    email_daily_max: NonNegativeInt = 0
    email_hourly_max: NonNegativeInt = 0
    email_monthly_budget_minor: NonNegativeInt = 0
    email_webhook_secret: SecretStr = SecretStr("")
    email_inbound_signing_secret: SecretStr = SecretStr("")
    email_provider_policy_approved: bool = False

    # Storage
    storage_backend: Literal["local", "s3"] = "local"
    storage_local_root: str = "/data/artifacts"
    s3_endpoint: str = ""
    s3_region: str = ""
    s3_bucket: str = ""
    s3_access_key: SecretStr = SecretStr("")
    s3_secret_key: SecretStr = SecretStr("")
    s3_force_path_style: bool = False
    artifact_retention_days: PositiveInt = 90
    preview_retention_days: PositiveInt = 30

    # Browser sandbox (Phase 04): internal URL of the isolated browser service.
    browser_service_url: str = "http://browser:9000"
    audit_version: str = "1"

    # Official-website verification (independent source)
    website_fetch_user_agent: str = Field(
        default="WEBFORGE-AI-Verifier/0.2 (website verification; respects robots.txt)",
        min_length=8,
        max_length=200,
    )

    # Limits / worker runtime
    browser_max_pages: PositiveInt = 10
    browser_max_depth: NonNegativeInt = 2
    browser_page_timeout_seconds: PositiveInt = 30
    browser_max_response_bytes: PositiveInt = 5_242_880
    browser_job_timeout_seconds: PositiveInt = 300
    discovery_worker_concurrency: PositiveInt = 2
    audit_worker_concurrency: PositiveInt = 1
    design_worker_concurrency: PositiveInt = 1
    render_worker_concurrency: PositiveInt = 1
    outreach_worker_concurrency: PositiveInt = 1
    # Emergency overrides: true forces the pause regardless of the dashboard switch.
    # The normal switches live in the database (system_controls) and start paused.
    global_pause: bool = False
    email_pause: bool = False

    # Monitoring / backup
    sentry_dsn: SecretStr = SecretStr("")
    otel_exporter_otlp_endpoint: str = ""
    backup_bucket: str = ""
    backup_encryption_key_ref: str = ""
    alert_email_to: str = ""

    @field_validator("timezone")
    @classmethod
    def _valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"unknown IANA timezone: {value!r}") from exc
        return value

    @field_validator("trusted_proxy_cidrs")
    @classmethod
    def _valid_cidrs(cls, value: str) -> str:
        for cidr in (c.strip() for c in value.split(",")):
            if cidr:
                try:
                    ipaddress.ip_network(cidr, strict=False)
                except ValueError as exc:
                    raise ValueError(f"invalid CIDR in TRUSTED_PROXY_CIDRS: {cidr!r}") from exc
        return value

    @field_validator("database_url")
    @classmethod
    def _postgres_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("postgresql://", "postgresql+psycopg://")):
            raise ValueError("DATABASE_URL must be a postgresql:// or postgresql+psycopg:// URL")
        return value

    @field_validator("redis_url", "celery_broker_url", "celery_result_backend")
    @classmethod
    def _redis_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith(("redis://", "rediss://")):
            raise ValueError("Redis URLs must use redis:// or rediss://")
        return value

    @model_validator(mode="after")
    def _guard_unimplemented_capabilities(self) -> Self:
        # Fail closed: these switches stay off until their phase implements the safeguards.
        if self.email_sending_enabled:
            raise ValueError(
                "EMAIL_SENDING_ENABLED=true is rejected: compliant sending is not implemented "
                "(Phase 09) and requires owner approval."
            )
        return self

    @field_validator("google_places_sku_prices_minor_per_1000")
    @classmethod
    def _valid_prices(cls, value: str) -> str:
        parse_sku_prices(value)
        return value

    @property
    def is_production(self) -> bool:
        return self.app_env is AppEnv.PRODUCTION

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def places_sku_prices(self) -> dict[str, int]:
        return parse_sku_prices(self.google_places_sku_prices_minor_per_1000)

    @property
    def trusted_proxies(self) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        return [
            ipaddress.ip_network(c.strip(), strict=False)
            for c in self.trusted_proxy_cidrs.split(",")
            if c.strip()
        ]

    @property
    def sqlalchemy_url(self) -> str:
        """DATABASE_URL with the psycopg (v3) driver selected."""
        return self.database_url.get_secret_value().replace(
            "postgresql://", "postgresql+psycopg://", 1
        )

    @property
    def psycopg_conninfo(self) -> str:
        """DATABASE_URL in the libpq form psycopg expects (no SQLAlchemy driver suffix)."""
        return self.database_url.get_secret_value().replace(
            "postgresql+psycopg://", "postgresql://", 1
        )

    def production_problems(self) -> list[str]:
        """Return reasons these settings are unsafe for production (empty when safe)."""
        problems: list[str] = []
        secrets = {
            "APP_SECRET_KEY": self.app_secret_key.get_secret_value(),
            "JWT_SIGNING_KEY": self.jwt_signing_key.get_secret_value(),
            "ENCRYPTION_KEY": self.encryption_key.get_secret_value(),
            "LOOKUP_HASH_KEY": self.lookup_hash_key.get_secret_value(),
        }
        for name, value in secrets.items():
            if not value:
                problems.append(f"{name} is required")
            elif _is_placeholder(value):
                problems.append(f"{name} still holds a placeholder value")
            elif name != "ENCRYPTION_KEY" and len(value) < MIN_SECRET_LENGTH:
                problems.append(f"{name} must be at least {MIN_SECRET_LENGTH} characters")

        enc = secrets["ENCRYPTION_KEY"]
        if enc and not _is_placeholder(enc) and not is_valid_encryption_key(enc):
            problems.append("ENCRYPTION_KEY must be 32 random bytes, URL-safe base64 encoded")
        prev = self.encryption_key_previous.get_secret_value()
        if prev and not is_valid_encryption_key(prev):
            problems.append("ENCRYPTION_KEY_PREVIOUS must be 32 random bytes, URL-safe base64")

        filled = [v for v in secrets.values() if v]
        if len(set(filled)) != len(filled):
            problems.append(
                "APP_SECRET_KEY, JWT_SIGNING_KEY, ENCRYPTION_KEY and LOOKUP_HASH_KEY "
                "must all differ"
            )
        if not self.cookie_secure:
            problems.append("COOKIE_SECURE must be true in production")
        if self.google_places_api_enabled and not self.google_maps_api_key.get_secret_value():
            problems.append("GOOGLE_PLACES_API_ENABLED=true requires GOOGLE_MAPS_API_KEY")
        if self.storage_backend == "s3" and not (self.s3_bucket and self.s3_region):
            problems.append("STORAGE_BACKEND=s3 requires S3_BUCKET and S3_REGION")
        if not self.mfa_required_for_owner:
            problems.append("MFA_REQUIRED_FOR_OWNER must be true in production")

        urls = {
            "DATABASE_URL": self.database_url,
            "REDIS_URL": self.redis_url,
            "CELERY_BROKER_URL": self.celery_broker_url,
            "CELERY_RESULT_BACKEND": self.celery_result_backend,
        }
        for name, url in urls.items():
            if _is_placeholder(url.get_secret_value()):
                problems.append(f"{name} still holds a placeholder password")
        if self.log_level is LogLevel.DEBUG:
            problems.append("LOG_LEVEL=DEBUG is not allowed in production")
        if not self.app_url.startswith("https://") or not self.api_url.startswith("https://"):
            problems.append("APP_URL and API_URL must use https:// in production")
        return problems


def load_settings() -> Settings:
    """Build settings and enforce production requirements. Raises ConfigurationError."""
    try:
        settings = Settings()
    except ValueError as exc:  # pydantic ValidationError subclasses ValueError
        raise ConfigurationError(f"Invalid configuration: {exc}") from exc
    if settings.is_production:
        problems = settings.production_problems()
        if problems:
            raise ConfigurationError("Refusing to start in production: " + "; ".join(problems))
    return settings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()
