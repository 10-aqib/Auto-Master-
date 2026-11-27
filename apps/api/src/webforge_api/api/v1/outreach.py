"""/api/v1 compliance policies, contacts, suppression, outreach messages and replies (Phase 09)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from webforge_api.api.deps import (
    AnyStaff,
    CryptoDep,
    DbDep,
    MetaDep,
    NowDep,
    OwnerOnly,
    OwnerOrAdmin,
    SettingsDep,
)
from webforge_api.models import (
    ComplianceAssessment,
    EmailContact,
    OutreachMessage,
    PolicyConfig,
    Reply,
    Suppression,
)
from webforge_api.models.enums import RecipientType, SuppressionReason
from webforge_api.security.crypto import normalize_email
from webforge_api.services import compliance, outreach
from webforge_api.services.email.provider import EmailProvider
from webforge_api.services.errors import ConflictError, NotFoundError

router = APIRouter(tags=["outreach"])


def get_provider(request: Request) -> EmailProvider:
    provider: EmailProvider = request.app.state.email_provider
    return provider


ProviderDep = Annotated[EmailProvider, Depends(get_provider)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ----------------------------------------------------------------------------- policies


class PolicyIn(Strict):
    country_code: str = Field(pattern=r"^[A-Z]{2}$")
    recipient_type: RecipientType
    message_category: str = Field(max_length=64)
    version: str = Field(min_length=1, max_length=32)
    rules: dict[str, Any]
    source_references: list[str] = Field(min_length=1, max_length=20)


class ActivateIn(Strict):
    reviewer_name: str = Field(min_length=3, max_length=200)
    reviewer_qualification: str = Field(min_length=3, max_length=200)
    reviewed_on: date
    effective_from: date


class PolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    country_code: str
    recipient_type: str
    message_category: str
    version: str
    status: str
    rules: dict[str, Any]
    reviewer_name: str | None
    reviewer_qualification: str | None
    reviewed_at: datetime | None
    effective_from: date | None
    effective_to: date | None
    source_references: list[str]


@router.get("/outreach/config")
def outreach_config(_p: AnyStaff, settings: SettingsDep, provider: ProviderDep) -> dict[str, Any]:
    """What the UI may offer. No secrets."""
    return {"provider": provider.name, "is_mock": provider.is_mock, "live_sending_enabled": settings.email_sending_enabled,
            "simulate_available": provider.is_mock and not settings.is_production,
            "sender_configured": bool(settings.email_from_address and settings.email_reply_to),
            "physical_address_configured": bool(settings.email_physical_address),
            "daily_max": settings.email_daily_max, "hourly_max": settings.email_hourly_max}  # fmt: skip


@router.get("/compliance/categories")
def categories(_p: AnyStaff) -> dict[str, Any]:
    return {"message_categories": compliance.MESSAGE_CATEGORIES, "legal_bases": sorted(compliance.LEGAL_BASES),
            "verification_methods": sorted(compliance.VERIFICATION_METHODS), "rule_keys": sorted(compliance.REQUIRED_RULE_KEYS)}  # fmt: skip


@router.get("/compliance/policies", response_model=list[PolicyOut])
def list_policies(_p: AnyStaff, db: DbDep) -> list[PolicyOut]:
    rows = db.scalars(
        select(PolicyConfig).order_by(
            PolicyConfig.country_code, PolicyConfig.recipient_type, PolicyConfig.version
        )
    )
    return [PolicyOut.model_validate(r) for r in rows]


@router.post("/compliance/policies", response_model=PolicyOut)
def create_policy(
    body: PolicyIn, principal: OwnerOrAdmin, db: DbDep, crypto: CryptoDep, meta: MetaDep
) -> PolicyOut:
    return PolicyOut.model_validate(
        compliance.create_policy(
            db, crypto, data=body.model_dump(), actor_user_id=principal.user.id, meta=meta
        )
    )


@router.post("/compliance/policies/{policy_id}/activate", response_model=PolicyOut)
def activate_policy(
    policy_id: uuid.UUID,
    body: ActivateIn,
    principal: OwnerOnly,
    db: DbDep,
    crypto: CryptoDep,
    meta: MetaDep,
) -> PolicyOut:
    row = compliance.activate_policy(db, crypto, policy_id=policy_id, reviewer_name=body.reviewer_name,
                                     reviewer_qualification=body.reviewer_qualification,
                                     reviewed_at=datetime.combine(body.reviewed_on, datetime.min.time()).astimezone(),
                                     effective_from=body.effective_from, actor_user_id=principal.user.id, meta=meta)  # fmt: skip
    return PolicyOut.model_validate(row)


@router.post("/compliance/policies/{policy_id}/retire", response_model=PolicyOut)
def retire_policy(
    policy_id: uuid.UUID, principal: OwnerOrAdmin, db: DbDep, crypto: CryptoDep, meta: MetaDep
) -> PolicyOut:
    return PolicyOut.model_validate(
        compliance.retire_policy(
            db, crypto, policy_id=policy_id, actor_user_id=principal.user.id, meta=meta
        )
    )


# ----------------------------------------------------------------------------- contacts and consent


class ContactIn(Strict):
    email: str = Field(min_length=3, max_length=254)
    recipient_type: RecipientType
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    source_url: str = Field(min_length=8, max_length=2048, pattern=r"^https?://")
    verification_method: str
    contact_name: str | None = Field(default=None, max_length=200)
    role_function: str | None = Field(default=None, max_length=120)


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID | None
    email_masked: str = ""
    contact_name: str | None
    recipient_type: str
    role_function: str | None
    source_url: str | None
    country_code: str | None
    verification_state: str
    verification_method: str | None
    suppressed: bool = False


class ConsentIn(Strict):
    consent_type: str = Field(min_length=3, max_length=64)
    scope: str = Field(min_length=3, max_length=200)
    source: str = Field(min_length=3, max_length=200)
    evidence: str = Field(min_length=10, max_length=4000)
    captured_at: datetime
    expires_at: datetime | None = None


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return (local[:1] + "•••" if local else "") + "@" + domain


def _contact_out(db: DbDep, crypto: CryptoDep, c: EmailContact) -> ContactOut:
    out = ContactOut.model_validate(c)
    out.email_masked = _mask(compliance.contact_email(crypto, c))
    out.suppressed = compliance.is_suppressed(db, c.email_hash)
    return out


@router.get("/prospects/{prospect_id}/contacts", response_model=list[ContactOut])
def list_contacts(
    prospect_id: uuid.UUID, _p: AnyStaff, db: DbDep, crypto: CryptoDep
) -> list[ContactOut]:
    return [
        _contact_out(db, crypto, c)
        for c in db.scalars(select(EmailContact).where(EmailContact.prospect_id == prospect_id))
    ]


@router.post("/prospects/{prospect_id}/contacts", response_model=ContactOut)
def add_contact(
    prospect_id: uuid.UUID,
    body: ContactIn,
    principal: OwnerOrAdmin,
    db: DbDep,
    crypto: CryptoDep,
    now: NowDep,
    meta: MetaDep,
) -> ContactOut:
    c = compliance.add_contact(db, crypto, prospect_id=prospect_id, email=body.email, recipient_type=body.recipient_type,
                               country_code=body.country_code, source_url=body.source_url, verification_method=body.verification_method,
                               contact_name=body.contact_name, role_function=body.role_function, actor_user_id=principal.user.id,
                               now=now, meta=meta)  # fmt: skip
    return _contact_out(db, crypto, c)


@router.post("/contacts/{contact_id}/consent")
def add_consent(
    contact_id: uuid.UUID,
    body: ConsentIn,
    principal: OwnerOrAdmin,
    db: DbDep,
    crypto: CryptoDep,
    meta: MetaDep,
) -> dict[str, str]:
    row = compliance.add_consent(
        db,
        crypto,
        contact_id=contact_id,
        actor_user_id=principal.user.id,
        meta=meta,
        **body.model_dump(),
    )
    return {"id": str(row.id)}


# ----------------------------------------------------------------------------- suppression


class SuppressIn(Strict):
    email: str = Field(min_length=3, max_length=254)
    reason: Literal["MANUAL", "LEGAL", "DO_NOT_CONTACT"] = "MANUAL"


@router.get("/compliance/suppressions")
def suppression_summary(_p: AnyStaff, db: DbDep) -> dict[str, Any]:
    by_reason = dict(
        db.execute(select(Suppression.reason, func.count()).group_by(Suppression.reason)).all()
    )
    recent = db.execute(
        select(Suppression.reason, Suppression.created_at, Suppression.scope)
        .order_by(Suppression.created_at.desc())
        .limit(20)
    ).all()
    return {"total": sum(by_reason.values()), "by_reason": {k.value: v for k, v in by_reason.items()},
            "recent": [{"reason": r.value, "created_at": c.isoformat(), "scope": s.value} for r, c, s in recent],
            "note": "Only keyed hashes are stored. Suppressions cannot be removed through the API."}  # fmt: skip


@router.post("/compliance/suppressions")
def add_suppression(
    body: SuppressIn,
    principal: OwnerOrAdmin,
    db: DbDep,
    crypto: CryptoDep,
    now: NowDep,
    meta: MetaDep,
) -> dict[str, int]:
    cancelled = compliance.suppress(db, crypto, email_hash=crypto.email_hash(normalize_email(body.email)), reason=SuppressionReason(body.reason),
                                    source_event="manual", now=now, actor_user_id=principal.user.id, meta=meta)  # fmt: skip
    db.commit()
    return {"cancelled_messages": cancelled}


# ----------------------------------------------------------------------------- outreach messages


class DraftIn(Strict):
    contact_id: uuid.UUID
    proposal_id: uuid.UUID
    legal_basis: str | None = Field(default=None, max_length=64)
    legal_basis_evidence: str | None = Field(default=None, max_length=4000)
    finding_id: uuid.UUID | None = None


class ReassessIn(Strict):
    legal_basis: str | None = Field(default=None, max_length=64)
    legal_basis_evidence: str | None = Field(default=None, max_length=4000)


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID
    email_contact_id: uuid.UUID | None
    proposal_id: uuid.UUID | None
    provider: str
    provider_message_id: str | None
    message_category: str
    subject: str | None
    status: str
    error_code: str | None
    cancelled_reason: str | None
    attempt_count: int
    approved_at: datetime | None
    accepted_at: datetime | None
    last_event_at: datetime | None
    created_at: datetime
    body: str | None = None
    assessment: dict[str, Any] | None = None


def _message_out(
    db: DbDep, crypto: CryptoDep, m: OutreachMessage, *, with_body: bool
) -> MessageOut:
    out = MessageOut.model_validate(m)
    if with_body and m.body_encrypted:
        out.body = crypto.decrypt_str(m.body_encrypted, context=outreach.BODY_CONTEXT)
    a = (
        db.get(ComplianceAssessment, m.compliance_assessment_id)
        if m.compliance_assessment_id
        else None
    )
    if a is not None:
        out.assessment = {"decision": a.decision.value, "reason_codes": a.reason_codes, "checks": a.checks, "assessed_at": a.assessed_at.isoformat(),
                          "policy_version": a.policy_version, "legal_basis": a.legal_basis}  # fmt: skip
    return out


@router.get("/outreach", response_model=list[MessageOut])
def list_messages(
    principal: AnyStaff, db: DbDep, crypto: CryptoDep, prospect_id: uuid.UUID | None = None
) -> list[MessageOut]:
    stmt = select(OutreachMessage).order_by(OutreachMessage.created_at.desc()).limit(200)
    if prospect_id:
        stmt = stmt.where(OutreachMessage.prospect_id == prospect_id)
    full = principal.user.role.value in ("OWNER", "ADMIN")
    return [_message_out(db, crypto, m, with_body=full) for m in db.scalars(stmt)]


@router.post("/prospects/{prospect_id}/outreach", response_model=MessageOut)
def create_draft(prospect_id: uuid.UUID, body: DraftIn, principal: OwnerOrAdmin, db: DbDep, settings: SettingsDep, crypto: CryptoDep,
                 provider: ProviderDep, now: NowDep, meta: MetaDep) -> MessageOut:  # fmt: skip
    m = outreach.create_draft(db, settings, crypto, provider, outreach.DraftInput(prospect_id=prospect_id, **body.model_dump()),
                              actor_user_id=principal.user.id, now=now, meta=meta)  # fmt: skip
    return _message_out(db, crypto, m, with_body=True)


@router.post("/outreach/{message_id}/reassess", response_model=MessageOut)
def reassess(message_id: uuid.UUID, body: ReassessIn, _p: OwnerOrAdmin, db: DbDep, settings: SettingsDep, crypto: CryptoDep,
             provider: ProviderDep, now: NowDep) -> MessageOut:  # fmt: skip
    m = outreach.reassess(
        db,
        settings,
        crypto,
        provider,
        message_id=message_id,
        now=now,
        legal_basis=body.legal_basis,
        evidence=body.legal_basis_evidence,
    )
    return _message_out(db, crypto, m, with_body=True)


@router.post("/outreach/{message_id}/approve", response_model=MessageOut)
def approve(message_id: uuid.UUID, principal: OwnerOnly, db: DbDep, settings: SettingsDep, crypto: CryptoDep, provider: ProviderDep,
            now: NowDep, meta: MetaDep) -> MessageOut:  # fmt: skip
    m = outreach.approve(
        db,
        settings,
        crypto,
        provider,
        message_id=message_id,
        actor_user_id=principal.user.id,
        now=now,
        meta=meta,
    )
    return _message_out(db, crypto, m, with_body=True)


@router.post("/outreach/{message_id}/cancel", response_model=MessageOut)
def cancel(
    message_id: uuid.UUID, principal: OwnerOrAdmin, db: DbDep, crypto: CryptoDep, meta: MetaDep
) -> MessageOut:
    return _message_out(
        db,
        crypto,
        outreach.cancel(
            db, crypto, message_id=message_id, actor_user_id=principal.user.id, meta=meta
        ),
        with_body=True,
    )


class SimulateIn(Strict):
    kind: Literal["delivered", "hard_bounce", "complaint", "reply"]
    text: str = Field(default="", max_length=2000)


@router.post("/outreach/{message_id}/simulate")
def simulate(message_id: uuid.UUID, body: SimulateIn, _p: OwnerOnly, db: DbDep, settings: SettingsDep, crypto: CryptoDep,
             provider: ProviderDep, now: NowDep) -> dict[str, Any]:  # fmt: skip
    """Development only: send a signed mock webhook through the real processing path."""
    if settings.is_production or not provider.is_mock:
        raise NotFoundError("not_found", "Not available.")
    m = db.get(OutreachMessage, message_id)
    contact = db.get(EmailContact, m.email_contact_id) if m and m.email_contact_id else None
    if m is None or contact is None or not m.provider_message_id:
        raise ConflictError("not_sent", "Only sent mock messages can receive simulated events.")
    kind, raw, headers = outreach.simulate(
        settings, body.kind, m, compliance.contact_email(crypto, contact), body.text
    )
    if kind == "inbound":
        reply = outreach.process_inbound(
            db, settings, crypto, provider, headers=headers, raw=raw, now=now
        )
        return {
            "reply_id": str(reply.id) if reply else None,
            "classification": reply.classification if reply else None,
        }
    return outreach.process_events(
        db, settings, crypto, provider, headers=headers, raw=raw, now=now
    )


# ----------------------------------------------------------------------------- replies


class ReplyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    prospect_id: uuid.UUID | None
    outreach_message_id: uuid.UUID | None
    received_at: datetime
    classification: str | None
    subject: str | None
    summary: str | None
    needs_human_review: bool
    handled_at: datetime | None


@router.get("/replies", response_model=list[ReplyOut])
def list_replies(_p: AnyStaff, db: DbDep, open_only: bool = False) -> list[ReplyOut]:
    stmt = select(Reply).order_by(Reply.received_at.desc()).limit(200)
    if open_only:
        stmt = stmt.where(Reply.needs_human_review.is_(True), Reply.handled_at.is_(None))
    return [ReplyOut.model_validate(r) for r in db.scalars(stmt)]


@router.post("/replies/{reply_id}/handled", response_model=ReplyOut)
def reply_handled(reply_id: uuid.UUID, principal: OwnerOrAdmin, db: DbDep, now: NowDep) -> ReplyOut:
    r = db.get(Reply, reply_id)
    if r is None:
        raise NotFoundError("not_found", "Reply not found.")
    r.handled_at, r.handled_by_user_id = now, principal.user.id
    db.commit()
    return ReplyOut.model_validate(r)
