from __future__ import annotations

import base64
import os
import secrets
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import psycopg
import pyotp
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from webforge_api.config import Settings, get_settings
from webforge_api.db.migrate import upgrade
from webforge_api.db.session import build_engine, build_sessionmaker
from webforge_api.main import create_app
from webforge_api.models import User
from webforge_api.models.enums import Role
from webforge_api.security import passwords
from webforge_api.security.crypto import Crypto
from webforge_api.security.rate_limit import MemoryRateLimiter
from webforge_api.services.auth import MFA_SECRET_CONTEXT

# Every variable Settings reads; cleared so the developer's shell/.env cannot leak into tests.
_ENV_PREFIXES = (
    "APP_", "API_", "PREVIEW_", "TIMEZONE", "LOG_", "CORS_", "DATABASE_", "REDIS_",
    "CELERY_", "READINESS_", "JWT_", "ENCRYPTION_", "ACCESS_", "REFRESH_", "MFA_", "AI_",
    "ANTHROPIC_", "GOOGLE_", "EMAIL_", "S3_", "ARTIFACT_", "BROWSER_", "DISCOVERY_",
    "AUDIT_", "DESIGN_", "RENDER_", "OUTREACH_", "GLOBAL_", "SENTRY_", "OTEL_", "BACKUP_",
    "ALERT_", "LOOKUP_", "SESSION_", "COOKIE_", "TRUSTED_", "LOGIN_", "ACCOUNT_",
)  # fmt: skip

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
REQUIRE_DB = os.environ.get("REQUIRE_DB_TESTS") == "1"
PASSWORD = "Correct-Horse-Battery-9"


@pytest.fixture(autouse=True)
def isolated_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> Iterator[None]:
    for key in list(os.environ):
        if key.upper().startswith(_ENV_PREFIXES):
            monkeypatch.delenv(key, raising=False)
    # Run from an empty directory so a local .env file is never read.
    monkeypatch.chdir(tmp_path_factory.mktemp("cwd"))
    monkeypatch.setenv("APP_ENV", "test")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def random_key32() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "app_secret_key": secrets.token_urlsafe(48),
        "jwt_signing_key": secrets.token_urlsafe(48),
        "encryption_key": random_key32(),
        "lookup_hash_key": secrets.token_urlsafe(48),
        "cookie_secure": False,
        "readiness_timeout_seconds": 0.5,
    }
    values.update(overrides)
    return Settings(**values)


# ----------------------------------------------------------------------------- database


def _admin_conninfo() -> str:
    return TEST_DATABASE_URL.replace("postgresql+psycopg://", "postgresql://", 1)


def _with_db(name: str) -> str:
    base, _, _ = _admin_conninfo().rpartition("/")
    return f"{base}/{name}"


def _sa(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _admin_exec(sql: str) -> None:
    with psycopg.connect(_admin_conninfo(), autocommit=True) as conn:
        conn.execute(sql.encode())


@pytest.fixture(scope="session")
def template_db() -> Iterator[str]:
    if not TEST_DATABASE_URL:
        if REQUIRE_DB:
            pytest.fail("REQUIRE_DB_TESTS=1 but TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL not set; database tests skipped")
    name = f"wf_tpl_{uuid.uuid4().hex[:10]}"
    _admin_exec(f'CREATE DATABASE "{name}"')
    upgrade(_sa(_with_db(name)))
    yield name
    _admin_exec(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def empty_db_url() -> Iterator[str]:
    """A brand-new database with no schema (for migration tests)."""
    if not TEST_DATABASE_URL:
        if REQUIRE_DB:
            pytest.fail("REQUIRE_DB_TESTS=1 but TEST_DATABASE_URL is not set")
        pytest.skip("TEST_DATABASE_URL not set; database tests skipped")
    name = f"wf_empty_{uuid.uuid4().hex[:10]}"
    _admin_exec(f'CREATE DATABASE "{name}"')
    yield _sa(_with_db(name))
    _admin_exec(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


@pytest.fixture
def db_url(template_db: str) -> Iterator[str]:
    """A migrated database cloned from the template, unique to this test."""
    name = f"wf_t_{uuid.uuid4().hex[:12]}"
    _admin_exec(f'CREATE DATABASE "{name}" TEMPLATE "{template_db}"')
    yield _sa(_with_db(name))
    _admin_exec(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


# ----------------------------------------------------------------------------- app


@dataclass
class FakeClock:
    current: datetime = field(default_factory=lambda: datetime.now(UTC).replace(microsecond=0))

    def __call__(self) -> datetime:
        return self.current

    def advance(self, **kwargs: float) -> None:
        self.current += timedelta(**kwargs)


@dataclass
class Harness:
    settings: Settings
    client: TestClient
    clock: FakeClock
    limiter: MemoryRateLimiter
    engine: Engine
    sessions: sessionmaker[Session]
    crypto: Crypto

    def db(self) -> Session:
        return self.sessions()

    # -- helpers ---------------------------------------------------------------

    def create_user(
        self,
        role: Role = Role.READ_ONLY,
        *,
        email: str | None = None,
        password: str = PASSWORD,
        mfa: bool = False,
        password_change_required: bool = False,
    ) -> tuple[User, str | None]:
        """Insert a user directly. Returns (user, totp_secret)."""
        secret = pyotp.random_base32(32) if mfa else None
        with self.db() as db:
            user = User(
                email=email or f"{role.value.lower()}-{uuid.uuid4().hex[:6]}@example.test",
                display_name=f"Test {role.value.title()}",
                role=role,
                password_hash=passwords.hash_password(password),
                mfa_enabled=mfa,
                mfa_secret_encrypted=(
                    self.crypto.encrypt_str(secret, context=MFA_SECRET_CONTEXT) if secret else None
                ),
                password_change_required=password_change_required,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
        return user, secret

    def totp(self, secret: str, *, steps_ahead: int = 0) -> str:
        return pyotp.TOTP(secret).at(self.clock() + timedelta(seconds=30 * steps_ahead))

    def login(self, email: str, password: str = PASSWORD) -> dict[str, Any]:
        r = self.client.post("/api/v1/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        body: dict[str, Any] = r.json()
        return body

    def login_active(self, user: User, secret: str | None) -> str:
        """Log in fully (MFA if enabled). Returns the CSRF token."""
        body = self.login(user.email)
        if secret:
            r = self.client.post(
                "/api/v1/auth/mfa/verify",
                json={"code": self.totp(secret)},
                headers={"X-CSRF-Token": body["csrf_token"]},
            )
            assert r.status_code == 200, r.text
            body = r.json()
        token: str = body["csrf_token"]
        return token

    def cookie(self, name: str) -> str | None:
        value: str | None = self.client.cookies.get(name)
        return value


@pytest.fixture
def harness(db_url: str) -> Iterator[Harness]:
    settings = make_settings(database_url=db_url, mfa_required_for_owner=True)
    yield from _harness(settings)


def _harness(settings: Settings, **app_kwargs: Any) -> Iterator[Harness]:
    clock = FakeClock()
    limiter = MemoryRateLimiter()
    app = create_app(settings, rate_limiter=limiter, clock=clock, **app_kwargs)
    engine = build_engine(settings)
    with TestClient(app) as client:
        yield Harness(
            settings=settings,
            client=client,
            clock=clock,
            limiter=limiter,
            engine=engine,
            sessions=build_sessionmaker(engine),
            crypto=Crypto.from_settings(settings),
        )
    engine.dispose()


@pytest.fixture
def harness_factory(db_url: str) -> Iterator[Any]:
    """Build a harness with custom settings overrides."""
    stack: list[Iterator[Harness]] = []

    def build(app_kwargs: dict[str, Any] | None = None, **overrides: Any) -> Harness:
        gen = _harness(make_settings(database_url=db_url, **overrides), **(app_kwargs or {}))
        stack.append(gen)
        return next(gen)

    yield build
    for gen in stack:
        for _ in gen:
            pass
