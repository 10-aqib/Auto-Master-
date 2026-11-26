"""Evidence-based qualification (rubric v1). A score is fit-for-outreach evidence, never buying
intent and never permission to email. Components without evidence are null and do not count.

Website-quality components score *opportunity*: clearer evidence of usability problems on the
current site means a redesign concept is more likely to be useful.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from webforge_api.models import (
    Campaign,
    DomainVerification,
    Prospect,
    ProspectSource,
    QualificationResult,
    WebsiteAudit,
)
from webforge_api.models.enums import (
    DomainVerificationStatus,
    ProspectState,
    QualificationOutcome,
    RunStatus,
)
from webforge_api.security.crypto import Crypto
from webforge_api.services.dedupe import possible_duplicates
from webforge_api.services.prospect_state import LOCKED, transition

RUBRIC_VERSION = "1"
WEIGHTS = {
    "website_presence": 10,
    "mobile_experience": 20,
    "visual_hierarchy": 15,
    "navigation_clarity": 15,
    "conversion_path": 15,
    "business_fit": 15,
    "source_quality": 10,
}
# Audit category (Phase 04) feeding each website-quality component.
AUDIT_CATEGORY = {
    "mobile_experience": "mobile_usability",
    "visual_hierarchy": "visual_structure",
    "navigation_clarity": "navigation",
    "conversion_path": "conversion",
}
MIN_COVERAGE = 0.5


@dataclass
class Component:
    weight: int
    score: float | None
    reason: str
    evidence: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "weight": self.weight,
            "score": self.score,
            "reason": self.reason,
            "evidence": self.evidence,
        }


def band_for(score: float) -> QualificationOutcome:
    if score >= 75:
        return QualificationOutcome.STRONG
    if score >= 60:
        return QualificationOutcome.POTENTIAL
    if score >= 40:
        return QualificationOutcome.INVESTIGATE
    return QualificationOutcome.REJECTED


def _components(db: Session, prospect: Prospect, campaign: Campaign | None) -> dict[str, Component]:
    c: dict[str, Component] = {}
    verification = db.scalar(
        select(DomainVerification)
        .where(DomainVerification.prospect_id == prospect.id)
        .order_by(DomainVerification.checked_at.desc())
    )
    if verification and verification.status is DomainVerificationStatus.VERIFIED:
        c["website_presence"] = Component(
            10, 10.0, "Official website reachable and verified",
            {"verification_id": str(verification.id), "domain": verification.domain},
        )  # fmt: skip
    else:
        c["website_presence"] = Component(10, None, "No verified website yet", {})

    audit = db.scalar(
        select(WebsiteAudit)
        .where(WebsiteAudit.prospect_id == prospect.id, WebsiteAudit.status == RunStatus.SUCCEEDED)
        .order_by(WebsiteAudit.finished_at.desc().nulls_last())
    )
    for name, category in AUDIT_CATEGORY.items():
        weight = WEIGHTS[name]
        cat = (audit.scores or {}).get("categories", {}).get(category) if audit else None
        if not audit:
            c[name] = Component(weight, None, "Not audited yet", {})
        elif not cat or cat.get("score") is None:
            c[name] = Component(
                weight, None, "Audit could not test this", {"audit_id": str(audit.id)}
            )
        else:
            quality = float(cat["score"])
            opportunity = round(weight * (1 - quality / 100), 2)
            c[name] = Component(
                weight, opportunity, f"Current site scores {quality:.0f}/100 for {category}",
                {"audit_id": str(audit.id), "category_score": quality},
            )  # fmt: skip

    industries = campaign.industries if campaign else []
    if not industries:
        c["business_fit"] = Component(15, None, "Campaign has no industry filter", {})
    elif not prospect.industry:
        c["business_fit"] = Component(15, None, "Industry not stated on the official website", {})
    elif prospect.industry in industries:
        c["business_fit"] = Component(15, 15.0, f"Industry {prospect.industry} is targeted", {})
    else:
        c["business_fit"] = Component(
            15, 0.0, f"Industry {prospect.industry} is not targeted", {"targets": industries}
        )

    best = db.scalar(
        select(ProspectSource.confidence)
        .where(
            ProspectSource.prospect_id == prospect.id, ProspectSource.fact_field == "business_name"
        )
        .order_by(ProspectSource.confidence.desc())
    )
    if best is None:
        c["source_quality"] = Component(10, None, "No independent name evidence", {})
    else:
        c["source_quality"] = Component(
            10, round(10 * float(best), 2), "Strength of independent name evidence",
            {"best_confidence": float(best)},
        )  # fmt: skip
    return c


def qualify(
    db: Session,
    crypto: Crypto,
    prospect_id: uuid.UUID,
    *,
    campaign_id: uuid.UUID | None,
    now: datetime,
    apply_state: bool = True,
) -> QualificationResult:
    """Score a prospect, store the result and move it along the pipeline (caller commits)."""
    prospect = db.get(Prospect, prospect_id, with_for_update=True)
    if prospect is None:
        raise ValueError("prospect not found")
    campaign = db.get(Campaign, campaign_id) if campaign_id else None
    comps = _components(db, prospect, campaign)
    known = {k: v for k, v in comps.items() if v.score is not None}
    known_weight = sum(v.weight for v in known.values())
    coverage = known_weight / sum(WEIGHTS.values())
    score = (
        round(sum(v.score or 0 for v in known.values()) / known_weight * 100, 2)
        if known_weight
        else None
    )
    reasons: list[str] = []
    audited = any(v.evidence.get("audit_id") for v in comps.values())

    if prospect.do_not_contact or prospect.state in (ProspectState.DO_NOT_CONTACT,):
        outcome, reasons = QualificationOutcome.REJECTED, ["do_not_contact"]
    elif prospect.state is ProspectState.REJECTED:
        outcome, reasons = QualificationOutcome.REJECTED, ["owner_rejected"]
    elif comps["business_fit"].score == 0:
        outcome, reasons = QualificationOutcome.REJECTED, ["industry_mismatch"]
    elif possible_duplicates(db, prospect):
        outcome, reasons = QualificationOutcome.MANUAL_REVIEW, ["possible_duplicate"]
    elif coverage < MIN_COVERAGE or score is None:
        outcome = QualificationOutcome.INVESTIGATE
        reasons = ["awaiting_audit_evidence" if not audited else "insufficient_evidence"]
    else:
        outcome = band_for(score)
        reasons = [f"score_band_{outcome.value.lower()}"]

    result = QualificationResult(
        prospect_id=prospect.id,
        campaign_id=campaign_id,
        rubric_version=RUBRIC_VERSION,
        outcome=outcome,
        score=score,
        evidence_coverage=round(coverage, 3),
        components={k: v.as_dict() for k, v in comps.items()},
        reason_codes=reasons,
        created_at=now,
    )
    db.add(result)
    prospect.qualification_score = score
    prospect.qualification_band = outcome.value

    if apply_state and prospect.state not in LOCKED:
        target = {
            QualificationOutcome.STRONG: ProspectState.QUALIFIED,
            QualificationOutcome.POTENTIAL: ProspectState.QUALIFIED,
            QualificationOutcome.MANUAL_REVIEW: ProspectState.HUMAN_REVIEW,
            QualificationOutcome.INVESTIGATE: (
                ProspectState.HUMAN_REVIEW if audited else ProspectState.QUALIFYING
            ),
            QualificationOutcome.REJECTED: (
                ProspectState.REJECTED
                if "industry_mismatch" in reasons
                else ProspectState.HUMAN_REVIEW
            ),
        }[outcome]
        if prospect.state is not target and target in _reachable(prospect.state):
            transition(db, crypto, prospect, target, reason=",".join(reasons), now=now)
    return result


def _reachable(state: ProspectState) -> set[ProspectState]:
    from webforge_api.services.prospect_state import ALLOWED

    return ALLOWED[state]
