"""Preview gateway (Phase 08): a separate, minimal ASGI app on its own origin.

Serves only `/p/<token>/<page>` and `/p/<token>/proposal.pdf` for active, unexpired, unrevoked previews. Every
other path — and every invalid, expired or revoked token — gets the same plain 404. No cookies, no API, no
dashboard, no docs, no source maps. Run with `uvicorn --factory webforge_api.preview:create_preview_app`.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from datetime import datetime

import redis
from fastapi import FastAPI, Request, Response
from fastapi.responses import PlainTextResponse, RedirectResponse
from sqlalchemy import update

from webforge_api import __version__
from webforge_api.api.deps import client_ip
from webforge_api.config import AppEnv, Settings, get_settings
from webforge_api.db.base import utcnow
from webforge_api.db.session import build_engine, build_sessionmaker
from webforge_api.design.brief_schema import PAGE_SLUGS
from webforge_api.logging_config import configure_logging, get_logger
from webforge_api.models import PreviewDeployment
from webforge_api.security.crypto import Crypto
from webforge_api.security.rate_limit import (
    RateLimiter,
    RateLimiterUnavailableError,
    RedisRateLimiter,
)
from webforge_api.services.proposals import resolve_token
from webforge_api.storage import Storage, StorageError, build_storage

log = get_logger("webforge_api.preview")

SECURITY_HEADERS = {
    "Content-Security-Policy": "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
    "form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "X-Robots-Tag": "noindex, nofollow, noarchive",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()",
    "Cache-Control": "private, no-store",
    "Strict-Transport-Security": "max-age=31536000",
}


def _not_found() -> Response:
    return PlainTextResponse("Not found", status_code=404)


def create_preview_app(
    settings: Settings | None = None,
    *,
    rate_limiter: RateLimiter | None = None,
    clock: Callable[[], datetime] = utcnow,
    storage: Storage | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level.value, json_output=settings.app_env is not AppEnv.TEST)
    engine = build_engine(settings)
    sessions = build_sessionmaker(engine)
    crypto = Crypto.from_settings(settings)
    store = storage or build_storage(settings)
    limiter = rate_limiter or RedisRateLimiter(
        redis.Redis.from_url(
            settings.redis_url.get_secret_value(), socket_timeout=2, socket_connect_timeout=2
        )
    )
    app = FastAPI(
        title="preview", version=__version__, docs_url=None, redoc_url=None, openapi_url=None
    )
    app.state.engine = engine

    @app.middleware("http")
    async def harden(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        if request.method not in ("GET", "HEAD"):
            response: Response = PlainTextResponse("Method not allowed", status_code=405)
        elif request.url.path.startswith("/p/"):
            try:
                allowed = limiter.hit(
                    f"preview:{client_ip(request, settings)}",
                    limit=settings.preview_rate_limit_per_minute,
                    window_seconds=60,
                )
            except RateLimiterUnavailableError:
                allowed = False
            response = (
                await call_next(request)
                if allowed
                else PlainTextResponse("Too many requests", status_code=429)
            )
        else:
            response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            response.headers[k] = v
        if "server" in response.headers:
            del response.headers["server"]
        return response

    @app.get("/health/live", include_in_schema=False)
    def live() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/p/{token}", include_in_schema=False)
    @app.get("/p/{token}/", include_in_schema=False)
    def root(token: str) -> Response:
        with sessions() as db:
            if resolve_token(db, crypto, token, clock()) is None:
                return _not_found()
        return RedirectResponse(f"/p/{token}/home", status_code=302)

    @app.get("/p/{token}/{name}", include_in_schema=False)
    def page(token: str, name: str) -> Response:
        if name not in PAGE_SLUGS and name != "proposal.pdf":
            return _not_found()
        now = clock()
        with sessions() as db:
            target = resolve_token(db, crypto, token, now)
            if target is None:
                return _not_found()
            if name == "proposal.pdf":
                key, digest, media = (
                    target.proposal.pdf_storage_key,
                    target.proposal.pdf_sha256,
                    "application/pdf",
                )
            else:
                entry = next(
                    (p for p in target.render.manifest.get("pages", []) if p["slug"] == name), None
                )
                key, digest, media = (
                    (entry["key"], entry["sha256"], "text/html; charset=utf-8")
                    if entry
                    else (None, None, "")
                )
            if not key:
                return _not_found()
            try:
                data = store.get(key)
            except StorageError:
                return _not_found()
            if hashlib.sha256(data).hexdigest() != digest:
                log.error("preview_integrity_mismatch", preview_id=str(target.preview.id))
                return _not_found()
            db.execute(update(PreviewDeployment).where(PreviewDeployment.id == target.preview.id)
                       .values(access_count=PreviewDeployment.access_count + 1, last_accessed_at=now))  # fmt: skip
            db.commit()
        headers = (
            {"Content-Disposition": 'inline; filename="website-redesign-concept.pdf"'}
            if media == "application/pdf"
            else {}
        )
        return Response(data, media_type=media, headers=headers)

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def anything(path: str) -> Response:
        return _not_found()

    return app
