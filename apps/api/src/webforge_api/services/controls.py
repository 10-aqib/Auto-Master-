"""Durable system controls (pause switches). Every spend-causing or outbound job checks them.

The database row is the switch the owner uses. The GLOBAL_PAUSE environment variable is an
emergency override: when true, the system is paused regardless of the database.
"""

from __future__ import annotations

import re
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import SystemControl
from webforge_api.security.crypto import Crypto
from webforge_api.services import activity
from webforge_api.services.auth import Principal
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import NotFoundError

KNOWN_CONTROLS = {
    "global_pause": "Stops all discovery, audits, generation and outbound activity.",
    "email_pause": "Stops all email sending (queued messages are held).",
}
# Scoped email pauses, e.g. "country_pause:PK" or "provider_pause:mock". Absent row = not paused
# (global and email pauses still apply); enabled=true holds every send for that country/provider.
SCOPED_PREFIXES = {
    "country_pause": re.compile(r"^[A-Z]{2}$"),
    "provider_pause": re.compile(r"^[a-z0-9_-]{2,32}$"),
}


def is_known(key: str) -> bool:
    if key in KNOWN_CONTROLS:
        return True
    prefix, _, ref = key.partition(":")
    pattern = SCOPED_PREFIXES.get(prefix)
    return bool(pattern and pattern.match(ref))


def describe(key: str) -> str:
    prefix, _, ref = key.partition(":")
    if prefix == "country_pause":
        return f"Holds all email to recipients in {ref}."
    if prefix == "provider_pause":
        return f"Holds all email through the {ref} provider."
    return KNOWN_CONTROLS.get(key, "")


def is_scoped_paused(db: Session, key: str) -> bool:
    row = db.get(SystemControl, key)
    return bool(row and row.enabled)


def is_paused(db: Session, settings: Settings, key: str = "global_pause") -> bool:
    """True when `key` (or the global pause it depends on) is on. Missing rows count as paused."""
    if settings.global_pause:
        return True  # environment emergency override
    if key == "email_pause" and settings.email_pause:
        return True
    keys = ["global_pause"] if key == "global_pause" else ["global_pause", key]
    for k in keys:
        row = db.get(SystemControl, k)
        if row is None or row.enabled:
            return True
    return False


def list_controls(db: Session) -> list[SystemControl]:
    return list(db.scalars(select(SystemControl).order_by(SystemControl.key)))


def set_control(
    db: Session,
    crypto: Crypto,
    actor: Principal,
    key: str,
    enabled: bool,
    reason: str,
    now: datetime,
    meta: RequestMeta,
) -> SystemControl:
    if not is_known(key):
        raise NotFoundError("not_found", "Unknown control.")
    row = db.get(SystemControl, key, with_for_update=True)
    if row is None:
        row = SystemControl(key=key, enabled=enabled)
        db.add(row)
    row.enabled = enabled
    row.reason = reason[:500]
    row.updated_at = now
    row.updated_by_user_id = actor.user.id
    activity.record(
        db,
        crypto,
        action="control.paused" if enabled else "control.resumed",
        actor_user_id=actor.user.id,
        meta=meta,
        entity_type="control",
        entity_id=key,
        metadata={"reason": reason[:200]},
    )
    db.commit()
    return row


EMERGENCY_KEYS = ("global_pause", "email_pause")


def emergency_pause(db: Session, crypto: Crypto, reason: str, now: datetime) -> list[str]:
    """Turn the global and email pauses ON as the system (operator CLI, recovery). Never resumes."""
    for key in EMERGENCY_KEYS:
        row = db.get(SystemControl, key, with_for_update=True)
        if row is None:
            row = SystemControl(key=key, enabled=True)
            db.add(row)
        row.enabled = True
        row.reason = reason[:500]
        row.updated_at = now
        row.updated_by_user_id = None
        activity.record(
            db,
            crypto,
            action="control.paused",
            actor_user_id=None,
            system=True,
            entity_type="control",
            entity_id=key,
            metadata={"reason": reason[:200]},
        )
    db.commit()
    return list(EMERGENCY_KEYS)
