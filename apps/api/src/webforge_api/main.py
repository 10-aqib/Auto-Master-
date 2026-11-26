"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from webforge_api import __version__
from webforge_api.api import health
from webforge_api.api import v1 as api_v1
from webforge_api.api.errors import install_error_handlers
from webforge_api.config import AppEnv, Settings, get_settings
from webforge_api.db.base import utcnow
from webforge_api.db.session import build_engine, build_sessionmaker
from webforge_api.logging_config import configure_logging, get_logger
from webforge_api.middleware import RequestContextMiddleware
from webforge_api.security.crypto import Crypto
from webforge_api.security.rate_limit import RateLimiter, RedisRateLimiter

log = get_logger(__name__)


def create_app(
    settings: Settings | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
    clock: Callable[[], datetime] = utcnow,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level.value, json_output=settings.app_env is not AppEnv.TEST)
    crypto = Crypto.from_settings(settings)  # fails fast on invalid keys
    engine = build_engine(settings)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        log.info(
            "api_starting",
            app_env=settings.app_env.value,
            version=__version__,
            global_pause=settings.global_pause,
            email_pause=settings.email_pause,
            email_sending_enabled=settings.email_sending_enabled,
        )
        yield
        engine.dispose()
        log.info("api_stopping")

    docs_enabled = not settings.is_production
    app = FastAPI(
        title="WEBFORGE AI API",
        version=__version__,
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = settings
    app.state.crypto = crypto
    app.state.engine = engine
    app.state.sessionmaker = build_sessionmaker(engine)
    app.state.clock = clock
    app.state.rate_limiter = rate_limiter or RedisRateLimiter(
        redis.Redis.from_url(
            settings.redis_url.get_secret_value(), socket_timeout=2, socket_connect_timeout=2
        )
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token"],
    )
    # Added last so it wraps everything, including CORS responses.
    app.add_middleware(RequestContextMiddleware)

    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(api_v1.router)
    return app
