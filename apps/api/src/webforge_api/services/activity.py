"""Append-only activity log writer. Metadata is redacted before it is stored."""

from __future__ import annotations

import uuid
from typing import Any, Literal

from sqlalchemy.orm import Session

from webforge_api.logging_config import redact_value
from webforge_api.models import ActivityLog
from webforge_api.security.crypto import Crypto
from webforge_api.services.context import RequestMeta

Outcome = Literal["success", "failure", "denied"]


def record(
    db: Session,
    crypto: Crypto,
    *,
    action: str,
    actor_user_id: uuid.UUID | None,
    meta: RequestMeta | None = None,
    outcome: Outcome = "success",
    entity_type: str | None = None,
    entity_id: str | uuid.UUID | None = None,
    metadata: dict[str, Any] | None = None,
    system: bool = False,
) -> ActivityLog:
    """Add an activity entry to the current transaction (caller commits)."""
    meta = meta or RequestMeta()
    actor_type = "system" if system else ("user" if actor_user_id else "anonymous")
    entry = ActivityLog(
        actor_user_id=actor_user_id,
        actor_type=actor_type,
        action=action,
        outcome=outcome,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        request_id=meta.request_id,
        ip_hash=crypto.lookup_hash(meta.ip, purpose="ip") if meta.ip else None,
        user_agent=meta.safe_user_agent,
        metadata_json=redact_value(None, metadata or {}),
    )
    db.add(entry)
    return entry
