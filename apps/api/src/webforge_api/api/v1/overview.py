"""/api/v1 overview analytics, review queues and operations health (Phase 10)."""

from __future__ import annotations

from typing import Any

import redis
from fastapi import APIRouter, Query, Request

from webforge_api.api.deps import AnyStaff, DbDep, NowDep, OwnerOrAdmin, SettingsDep
from webforge_api.services import overview as svc

router = APIRouter(tags=["overview"])


@router.get("/overview")
def get_overview(_p: AnyStaff, db: DbDep, settings: SettingsDep, now: NowDep,
                 campaign_id: str | None = Query(default=None, pattern=r"^[0-9a-f-]{36}$"),
                 country: str | None = Query(default=None, pattern=r"^[A-Z]{2}$")) -> dict[str, Any]:  # fmt: skip
    return svc.overview(db, settings, now, campaign_id=campaign_id, country=country)


@router.get("/review-queues")
def get_review_queues(_p: AnyStaff, db: DbDep) -> dict[str, Any]:
    queues = svc.review_queues(db)
    return {"counts": {k: len(v) for k, v in queues.items()}, "queues": queues}


@router.get("/operations")
def get_operations(
    request: Request, _p: OwnerOrAdmin, db: DbDep, settings: SettingsDep, now: NowDep
) -> dict[str, Any]:
    client: redis.Redis | None
    try:
        client = redis.Redis.from_url(
            settings.redis_url.get_secret_value(), socket_timeout=2, socket_connect_timeout=2
        )
    except (redis.RedisError, ValueError):
        client = None
    try:
        return svc.operations(db, settings, now, client)
    finally:
        if client is not None:
            client.close()
