"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from webforge_api import __version__
from webforge_api.api import health
from webforge_api.config import AppEnv, Settings, get_settings
from webforge_api.logging_config import configure_logging, get_logger
from webforge_api.middleware import RequestContextMiddleware

log = get_logger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level.value, json_output=settings.app_env is not AppEnv.TEST)

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

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Content-Type", "X-Request-ID", "X-CSRF-Token"],
    )
    # Added last so it wraps everything, including CORS responses.
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)
        log.error("unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "internal_error", "request_id": request_id}},
        )

    app.include_router(health.router)
    return app
