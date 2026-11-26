"""Liveness and readiness endpoints.

Liveness only proves the process serves requests. Readiness checks the real
dependencies that exist in this phase: PostgreSQL and Redis.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

import psycopg
import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel

from webforge_api.config import Settings
from webforge_api.logging_config import get_logger

log = get_logger(__name__)
router = APIRouter(prefix="/health", tags=["health"])

CheckStatus = Literal["ok", "fail"]


class LiveResponse(BaseModel):
    status: Literal["ok"]


class DependencyCheck(BaseModel):
    status: CheckStatus
    latency_ms: float | None = None
    error: str | None = None


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, DependencyCheck]


async def check_postgres(settings: Settings) -> None:
    timeout = settings.readiness_timeout_seconds
    async with await psycopg.AsyncConnection.connect(
        settings.psycopg_conninfo, connect_timeout=max(1, int(timeout))
    ) as conn:
        await conn.execute("SELECT 1")


async def check_redis(settings: Settings) -> None:
    timeout = settings.readiness_timeout_seconds
    client = aioredis.from_url(
        settings.redis_url.get_secret_value(),
        socket_connect_timeout=timeout,
        socket_timeout=timeout,
    )
    try:
        await client.ping()
    finally:
        await client.aclose()


Checker = Callable[[Settings], Awaitable[None]]


def get_app_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_dependency_checks() -> dict[str, Checker]:
    return {"postgres": check_postgres, "redis": check_redis}


async def _run_check(name: str, checker: Checker, settings: Settings) -> DependencyCheck:
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        await asyncio.wait_for(checker(settings), timeout=settings.readiness_timeout_seconds)
    except Exception as exc:
        # Error class only: driver messages can include hostnames or credentials.
        log.warning("readiness_check_failed", dependency=name, error_type=type(exc).__name__)
        return DependencyCheck(status="fail", error=type(exc).__name__)
    return DependencyCheck(status="ok", latency_ms=round((loop.time() - started) * 1000, 2))


@router.get("/live", response_model=LiveResponse)
async def live() -> LiveResponse:
    return LiveResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready(
    response: Response,
    settings: Annotated[Settings, Depends(get_app_settings)],
    checks: Annotated[dict[str, Checker], Depends(get_dependency_checks)],
) -> ReadyResponse:
    names = list(checks)
    results = await asyncio.gather(*(_run_check(n, checks[n], settings) for n in names))
    by_name = dict(zip(names, results, strict=True))
    is_ready = all(r.status == "ok" for r in results)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    response.headers["Cache-Control"] = "no-store"
    return ReadyResponse(status="ready" if is_ready else "not_ready", checks=by_name)
