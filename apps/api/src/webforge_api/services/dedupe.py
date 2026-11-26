"""Cautious de-duplication.

- Identity = normalised verified domain + branch key. Never merged on a fuzzy name alone.
- Branch key: a location-specific path on a shared site (e.g. /locations/lahore). Language-only
  paths (/en, /ur-pk) and the home page map to "" (the main site).
- Possible duplicates (same normalised name, different domain) are flagged for manual review.
- Manual merges keep the merged prospect (state MERGED) and a full history row.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from webforge_api.models import (
    DomainVerification,
    ExternalPlaceIdentifier,
    Prospect,
    ProspectCampaign,
    ProspectMerge,
    ProspectSource,
)
from webforge_api.models.enums import ProspectState
from webforge_api.security.crypto import Crypto
from webforge_api.services import activity
from webforge_api.services.auth import Principal
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import ConflictError, NotFoundError
from webforge_api.sources.names import normalize_name

_LANG_SEGMENT = re.compile(r"^[a-z]{2}(-[a-z]{2})?$")
_GENERIC_PAGES = {"index.html", "index.php", "home", "default.aspx"}


def branch_key_for(url: str) -> str:
    from urllib.parse import urlsplit

    segments = [s for s in urlsplit(url).path.lower().split("/") if s]
    segments = [s for s in segments if not _LANG_SEGMENT.fullmatch(s) and s not in _GENERIC_PAGES]
    return "/" + "/".join(segments)[:250] if segments else ""


def follow_merges(db: Session, prospect: Prospect | None) -> Prospect | None:
    seen: set[uuid.UUID] = set()
    while prospect is not None and prospect.state is ProspectState.MERGED:
        if prospect.id in seen:
            break
        seen.add(prospect.id)
        merge = db.scalar(
            select(ProspectMerge)
            .where(ProspectMerge.from_prospect_id == prospect.id)
            .order_by(ProspectMerge.merged_at.desc())
        )
        prospect = db.get(Prospect, merge.into_prospect_id) if merge else None
    return prospect


def possible_duplicates(db: Session, prospect: Prospect) -> list[Prospect]:
    """Same normalised name, different domain. Flag only; never auto-merge."""
    key = normalize_name(prospect.business_name)
    if not key:
        return []
    rows = db.scalars(
        select(Prospect).where(
            Prospect.id != prospect.id,
            Prospect.state != ProspectState.MERGED,
            func.lower(Prospect.business_name).contains(key.split()[0]),
        )
    )
    return [
        p
        for p in rows
        if normalize_name(p.business_name) == key and p.verified_domain != prospect.verified_domain
    ]


def merge_prospects(
    db: Session,
    crypto: Crypto,
    actor: Principal,
    *,
    from_id: uuid.UUID,
    into_id: uuid.UUID,
    reason: str,
    now: datetime,
    meta: RequestMeta,
) -> ProspectMerge:
    if from_id == into_id:
        raise ConflictError("same_prospect", "Choose two different prospects.")
    source = db.get(Prospect, from_id, with_for_update=True)
    target = db.get(Prospect, into_id, with_for_update=True)
    if source is None or target is None:
        raise NotFoundError("not_found", "Prospect not found.")
    if ProspectState.MERGED in (source.state, target.state):
        raise ConflictError("already_merged", "One of these prospects was already merged.")
    snapshot: dict[str, Any] = {
        "business_name": source.business_name,
        "verified_domain": source.verified_domain,
        "branch_key": source.branch_key,
        "state": source.state.value,
        "do_not_contact": source.do_not_contact,
    }
    for model in (ProspectSource, ExternalPlaceIdentifier, DomainVerification):
        db.execute(update(model).where(model.prospect_id == from_id).values(prospect_id=into_id))
    for link in db.scalars(select(ProspectCampaign).where(ProspectCampaign.prospect_id == from_id)):
        exists = db.scalar(
            select(ProspectCampaign.id).where(
                ProspectCampaign.prospect_id == into_id,
                ProspectCampaign.campaign_id == link.campaign_id,
            )
        )
        if exists:
            db.delete(link)
        else:
            link.prospect_id = into_id
    # Do-not-contact always survives a merge.
    target.do_not_contact = target.do_not_contact or source.do_not_contact
    source.state = ProspectState.MERGED
    source.state_changed_at = now
    merge = ProspectMerge(
        from_prospect_id=from_id,
        into_prospect_id=into_id,
        reason=reason[:500],
        snapshot=snapshot,
        merged_by_user_id=actor.user.id,
        merged_at=now,
    )
    db.add(merge)
    activity.record(
        db,
        crypto,
        action="prospect.merged",
        actor_user_id=actor.user.id,
        meta=meta,
        entity_type="prospect",
        entity_id=into_id,
        metadata={"from": str(from_id)},
    )
    db.commit()
    return merge
