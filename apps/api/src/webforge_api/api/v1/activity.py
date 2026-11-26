"""/api/v1/activity — read-only, cursor-paginated activity log (OWNER, ADMIN)."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import select, tuple_

from webforge_api.api.deps import DbDep, OwnerOrAdmin
from webforge_api.api.v1.schemas import ActivityOut, ActivityPage
from webforge_api.models import ActivityLog
from webforge_api.services.errors import ServiceError

router = APIRouter(prefix="/activity", tags=["activity"])


def _encode(entry: ActivityLog) -> str:
    raw = f"{entry.occurred_at.isoformat()}|{entry.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def _decode(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        ts, ident = base64.urlsafe_b64decode(cursor.encode()).decode().split("|", 1)
        return datetime.fromisoformat(ts), uuid.UUID(ident)
    except (ValueError, UnicodeDecodeError) as exc:
        raise ServiceError("invalid_cursor", "Invalid pagination cursor.") from exc


@router.get("", response_model=ActivityPage)
def list_activity(
    _principal: OwnerOrAdmin,
    db: DbDep,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(max_length=200)] = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
) -> ActivityPage:
    stmt = select(ActivityLog).order_by(ActivityLog.occurred_at.desc(), ActivityLog.id.desc())
    if action:
        stmt = stmt.where(ActivityLog.action == action)
    if cursor:
        ts, ident = _decode(cursor)
        stmt = stmt.where(tuple_(ActivityLog.occurred_at, ActivityLog.id) < tuple_(ts, ident))
    rows = list(db.scalars(stmt.limit(limit + 1)))
    page, more = rows[:limit], len(rows) > limit
    return ActivityPage(
        items=[ActivityOut.model_validate(r) for r in page],
        next_cursor=_encode(page[-1]) if more and page else None,
    )
