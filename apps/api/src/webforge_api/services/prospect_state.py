"""Prospect lifecycle. Only this module changes `Prospect.state`; every change is logged."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from webforge_api.models import Prospect
from webforge_api.models.enums import ProspectState as S
from webforge_api.models.enums import Role
from webforge_api.security.crypto import Crypto
from webforge_api.services import activity
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import ConflictError, PermissionDeniedError

PIPELINE = [
    S.DISCOVERED, S.SOURCE_VERIFYING, S.VERIFIED, S.DEDUPLICATED, S.QUALIFYING, S.QUALIFIED,
    S.AUDITING, S.AUDITED, S.GENERATING_DESIGN, S.VALIDATING, S.PROPOSAL_READY,
    S.COMPLIANCE_CHECK, S.SCHEDULED, S.SENT, S.DELIVERED, S.REPLIED, S.INTERESTED, S.CLIENT,
]  # fmt: skip
HOLDS = {S.HUMAN_REVIEW, S.POLICY_HOLD, S.FAILED}
# Terminal or owner-only states: automation can never move a prospect out of these.
LOCKED = {S.REJECTED, S.DO_NOT_CONTACT, S.MERGED, S.CLIENT, S.UNSUBSCRIBED, S.BOUNCED, S.EXPIRED}
ACTIVE = set(PIPELINE) - {S.CLIENT}


def _allowed() -> dict[S, set[S]]:
    allowed: dict[S, set[S]] = {s: set() for s in S}
    for i, state in enumerate(PIPELINE[:-1]):
        allowed[state] |= set(PIPELINE[i + 1 :])  # forward moves (steps may be skipped)
    for state in ACTIVE | HOLDS:
        allowed[state] |= HOLDS | {S.REJECTED, S.DO_NOT_CONTACT, S.EXPIRED}
    for hold in HOLDS:
        allowed[hold] |= ACTIVE  # resume after review
    for state in (S.SCHEDULED, S.SENT, S.DELIVERED, S.REPLIED):
        allowed[state] |= {S.BOUNCED, S.UNSUBSCRIBED}
    for state in allowed:
        allowed[state].discard(state)
    return allowed


ALLOWED = _allowed()


def transition(
    db: Session,
    crypto: Crypto,
    prospect: Prospect,
    to: S,
    *,
    reason: str,
    now: datetime,
    actor_user_id: uuid.UUID | None = None,
    meta: RequestMeta | None = None,
) -> bool:
    """Apply an allowed transition (caller commits). Returns False when already in `to`."""
    if prospect.state is to:
        return False
    if to not in ALLOWED[prospect.state]:
        raise ConflictError(
            "invalid_transition", f"Cannot move a prospect from {prospect.state} to {to}."
        )
    previous = prospect.state
    prospect.state = to
    prospect.state_changed_at = now
    activity.record(
        db,
        crypto,
        action="prospect.state_changed",
        actor_user_id=actor_user_id,
        meta=meta,
        system=actor_user_id is None,
        entity_type="prospect",
        entity_id=prospect.id,
        metadata={"from": previous.value, "to": to.value, "reason": reason[:200]},
    )
    return True


def reopen(
    db: Session,
    crypto: Crypto,
    prospect: Prospect,
    *,
    role: Role,
    actor_user_id: uuid.UUID,
    reason: str,
    now: datetime,
    meta: RequestMeta,
) -> None:
    """Owner/admin reversal of a rejection. Do-not-contact can only be lifted by the owner;
    unsubscribes and bounces can never be reopened here (suppression is separate and global)."""
    if prospect.state is S.REJECTED:
        pass
    elif prospect.state is S.DO_NOT_CONTACT:
        if role is not Role.OWNER:
            raise PermissionDeniedError("forbidden", "Only the owner can lift do-not-contact.")
        prospect.do_not_contact = False
    else:
        raise ConflictError("not_reopenable", f"A {prospect.state} prospect cannot be reopened.")
    previous = prospect.state
    prospect.state = S.VERIFIED
    prospect.state_changed_at = now
    activity.record(
        db,
        crypto,
        action="prospect.reopened",
        actor_user_id=actor_user_id,
        meta=meta,
        entity_type="prospect",
        entity_id=prospect.id,
        metadata={"from": previous.value, "reason": reason[:200]},
    )
