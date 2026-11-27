"""Outreach (Phase 09): one initial message per prospect, owner-approved, sent only through an approved
provider (mock in development). Webhooks, replies and unsubscribe update suppression immediately."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import (
    AuditFinding,
    EmailContact,
    EmailEvent,
    OutreachMessage,
    Proposal,
    Prospect,
    Reply,
    WebsiteAudit,
)
from webforge_api.models.enums import (
    ComplianceDecision,
    EventProcessingState,
    MessageStatus,
    ProspectState,
    RunStatus,
    SuppressionReason,
)
from webforge_api.security.crypto import Crypto, normalize_email
from webforge_api.services import activity, compliance
from webforge_api.services.context import RequestMeta
from webforge_api.services.email.provider import EmailProvider, OutgoingEmail, signed_request
from webforge_api.services.email.templates import (
    PREVIEW_SLOT,
    TEMPLATE_VERSION,
    UNSUBSCRIBE_SLOT,
    Draft,
    render,
)
from webforge_api.services.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    UnavailableError,
)
from webforge_api.services.jobs import JobError, JobSpec, enqueue
from webforge_api.services.proposals import create_preview
from webforge_api.services.prospect_state import ALLOWED, transition

EMAIL_SEND = JobSpec("email.send", "outreach", max_attempts=5)
EMAIL_RECONCILE = JobSpec("email.reconcile", "outreach", max_attempts=6)
BODY_CONTEXT = "outreach-body"
REPLY_CONTEXT = "reply-body"
OPEN = (MessageStatus.DRAFT, MessageStatus.PENDING_REVIEW, MessageStatus.SCHEDULED, MessageStatus.SENDING,
        MessageStatus.AMBIGUOUS, MessageStatus.ACCEPTED, MessageStatus.SENT, MessageStatus.DELIVERED)  # fmt: skip


def _move(db: Session, crypto: Crypto, prospect: Prospect, to: ProspectState, reason: str, now: datetime,
          actor: uuid.UUID | None = None) -> None:  # fmt: skip
    if prospect.state is not to and to in ALLOWED[prospect.state]:
        transition(db, crypto, prospect, to, reason=reason, now=now, actor_user_id=actor)


def _draft_of(crypto: Crypto, m: OutreachMessage) -> Draft:
    return Draft(
        subject=m.subject or "",
        text=crypto.decrypt_str(m.body_encrypted or b"", context=BODY_CONTEXT),
    )


# ----------------------------------------------------------------------------- drafts


@dataclass
class DraftInput:
    prospect_id: uuid.UUID
    contact_id: uuid.UUID
    proposal_id: uuid.UUID
    legal_basis: str | None
    legal_basis_evidence: str | None
    finding_id: uuid.UUID | None


def create_draft(db: Session, settings: Settings, crypto: Crypto, provider: EmailProvider, inp: DraftInput, *,
                 actor_user_id: uuid.UUID, now: datetime, meta: RequestMeta) -> OutreachMessage:  # fmt: skip
    prospect = db.get(Prospect, inp.prospect_id, with_for_update=True)
    contact = db.get(EmailContact, inp.contact_id)
    proposal = db.get(Proposal, inp.proposal_id)
    if (
        prospect is None
        or contact is None
        or contact.prospect_id != prospect.id
        or proposal is None
        or proposal.prospect_id != prospect.id
    ):
        raise NotFoundError("not_found", "Prospect, contact or proposal not found.")
    existing = db.scalar(
        select(OutreachMessage.id)
        .where(OutreachMessage.prospect_id == prospect.id, OutreachMessage.status.in_(OPEN))
        .limit(1)
    )
    if existing:
        raise ConflictError(
            "one_message_only",
            "This prospect already has an outreach message. v1 sends one initial message only.",
        )
    audit = db.scalar(select(WebsiteAudit).where(WebsiteAudit.prospect_id == prospect.id, WebsiteAudit.status == RunStatus.SUCCEEDED)
                      .order_by(WebsiteAudit.finished_at.desc().nulls_last()).limit(1))  # fmt: skip
    finding = None
    if audit is not None:
        q = select(AuditFinding).where(AuditFinding.audit_id == audit.id)
        finding = (
            db.scalar(q.where(AuditFinding.id == inp.finding_id))
            if inp.finding_id
            else db.scalar(q.limit(1))
        )
    if audit is None or finding is None or audit.finished_at is None:
        raise ConflictError(
            "no_observation",
            "The message must state one real, dated observation from a successful audit.",
        )
    domain = prospect.verified_domain or urlsplit(audit.url).hostname or ""
    draft = render(business=prospect.business_name, domain=domain, observed_on=audit.finished_at.strftime("%d %B %Y"),
                   observation=finding.description.split(". ", 1)[0], from_name=settings.email_from_name,
                   author_title=settings.concept_author_title, author_url=settings.concept_author_url,
                   physical_address=settings.email_physical_address,
                   source_domain=(urlsplit(contact.source_url or "").hostname or domain),
                   preview_expires_on=(now + timedelta(days=settings.preview_retention_days)).strftime("%d %B %Y"),
                   contact_name=contact.contact_name)  # fmt: skip
    msg = OutreachMessage(prospect_id=prospect.id, email_contact_id=contact.id, proposal_id=proposal.id, provider=provider.name,
                          message_category="commercial_initial", subject_version=TEMPLATE_VERSION, body_version=TEMPLATE_VERSION,
                          subject=draft.subject, body_encrypted=crypto.encrypt_str(draft.text, context=BODY_CONTEXT),
                          status=MessageStatus.DRAFT, idempotency_key=f"outreach:{uuid.uuid4()}", recipient_hash=contact.email_hash)  # fmt: skip
    db.add(msg)
    db.flush()
    _assess_and_store(
        db, settings, crypto, provider, msg, inp.legal_basis, inp.legal_basis_evidence, now
    )
    _move(
        db,
        crypto,
        prospect,
        ProspectState.COMPLIANCE_CHECK,
        "outreach draft created",
        now,
        actor_user_id,
    )
    if msg.status is MessageStatus.DRAFT:
        _move(
            db, crypto, prospect, ProspectState.POLICY_HOLD, "compliance hold", now, actor_user_id
        )
    activity.record(db, crypto, action="outreach.draft_created", actor_user_id=actor_user_id, meta=meta, entity_type="outreach_message",
                    entity_id=msg.id, metadata={"status": msg.status.value})  # fmt: skip
    db.commit()
    return msg


def _assess_and_store(db: Session, settings: Settings, crypto: Crypto, provider: EmailProvider, msg: OutreachMessage,
                      legal_basis: str | None, evidence: str | None, now: datetime) -> compliance.Assessment:  # fmt: skip
    a = compliance.assess(db, settings, crypto, message=msg, draft=_draft_of(crypto, msg), legal_basis=legal_basis,
                          legal_basis_evidence=evidence, now=now, provider_name=provider.name, provider_is_mock=provider.is_mock)  # fmt: skip
    row = compliance.record_assessment(db, a, message=msg, legal_basis=legal_basis, evidence=evidence, now=now,
                                       provider_version=f"{provider.name}:{'sandbox' if provider.is_mock else settings.email_provider_approval_ref[:24]}")  # fmt: skip
    msg.compliance_assessment_id = row.id
    if msg.status in (MessageStatus.DRAFT, MessageStatus.PENDING_REVIEW):
        msg.status = (
            MessageStatus.PENDING_REVIEW
            if a.decision is ComplianceDecision.ELIGIBLE
            else MessageStatus.DRAFT
        )
        msg.error_code = (
            None
            if a.decision is ComplianceDecision.ELIGIBLE
            else (a.reasons[0] if a.reasons else "hold")[:64]
        )
    return a


def _latest_basis(db: Session, msg: OutreachMessage) -> tuple[str | None, str | None]:
    from webforge_api.models import ComplianceAssessment

    row = (
        db.get(ComplianceAssessment, msg.compliance_assessment_id)
        if msg.compliance_assessment_id
        else None
    )
    return (row.legal_basis, row.legal_basis_evidence) if row else (None, None)


def reassess(db: Session, settings: Settings, crypto: Crypto, provider: EmailProvider, *, message_id: uuid.UUID, now: datetime,
             legal_basis: str | None = None, evidence: str | None = None) -> OutreachMessage:  # fmt: skip
    msg = db.get(OutreachMessage, message_id, with_for_update=True)
    if msg is None:
        raise NotFoundError("not_found", "Message not found.")
    if msg.status not in (MessageStatus.DRAFT, MessageStatus.PENDING_REVIEW):
        raise ConflictError("not_editable", f"Message is {msg.status.value}.")
    old_basis, old_evidence = _latest_basis(db, msg)
    _assess_and_store(
        db, settings, crypto, provider, msg, legal_basis or old_basis, evidence or old_evidence, now
    )
    prospect = db.get(Prospect, msg.prospect_id)
    if prospect is not None and msg.status is MessageStatus.PENDING_REVIEW:
        _move(
            db, crypto, prospect, ProspectState.COMPLIANCE_CHECK, "compliance re-check passed", now
        )
    db.commit()
    return msg


def approve(db: Session, settings: Settings, crypto: Crypto, provider: EmailProvider, *, message_id: uuid.UUID, actor_user_id: uuid.UUID,
            now: datetime, meta: RequestMeta) -> OutreachMessage:  # fmt: skip
    """Owner approval (manual review mode). Re-runs every check; only ELIGIBLE messages are scheduled."""
    msg = db.get(OutreachMessage, message_id, with_for_update=True)
    if msg is None:
        raise NotFoundError("not_found", "Message not found.")
    if msg.status is not MessageStatus.PENDING_REVIEW:
        raise ConflictError(
            "not_pending_review",
            f"Message is {msg.status.value}; only eligible drafts can be approved.",
        )
    basis, evidence = _latest_basis(db, msg)
    a = _assess_and_store(db, settings, crypto, provider, msg, basis, evidence, now)
    if a.decision is not ComplianceDecision.ELIGIBLE:
        db.commit()
        raise ConflictError(
            "not_eligible", "Compliance checks no longer pass: " + ", ".join(a.reasons)
        )
    msg.status, msg.approved_by_user_id, msg.approved_at, msg.scheduled_at = (
        MessageStatus.SCHEDULED,
        actor_user_id,
        now,
        now,
    )
    enqueue(db, EMAIL_SEND, idempotency_key=f"send:{msg.id}", payload={"message_id": str(msg.id)}, now=now,
            entity_type="outreach_message", entity_id=msg.id, correlation_id=meta.request_id, created_by_user_id=actor_user_id)  # fmt: skip
    prospect = db.get(Prospect, msg.prospect_id)
    if prospect is not None:
        _move(
            db, crypto, prospect, ProspectState.SCHEDULED, "outreach approved", now, actor_user_id
        )
    activity.record(
        db,
        crypto,
        action="outreach.approved",
        actor_user_id=actor_user_id,
        meta=meta,
        entity_type="outreach_message",
        entity_id=msg.id,
    )
    db.commit()
    return msg


def cancel(
    db: Session,
    crypto: Crypto,
    *,
    message_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    meta: RequestMeta,
) -> OutreachMessage:
    msg = db.get(OutreachMessage, message_id, with_for_update=True)
    if msg is None:
        raise NotFoundError("not_found", "Message not found.")
    if msg.status not in compliance.UNSENT:
        raise ConflictError("not_cancellable", f"Message is {msg.status.value}.")
    msg.status, msg.cancelled_reason = MessageStatus.CANCELLED, "owner_cancelled"
    activity.record(
        db,
        crypto,
        action="outreach.cancelled",
        actor_user_id=actor_user_id,
        meta=meta,
        entity_type="outreach_message",
        entity_id=msg.id,
    )
    db.commit()
    return msg


# ----------------------------------------------------------------------------- sending


class SendDeferred(Exception):  # noqa: N818 - control-flow signal mapped to JobDeferred by the handler
    def __init__(self, reason: str, seconds: int = 300) -> None:
        super().__init__(reason)
        self.seconds = seconds


def send(
    db: Session,
    settings: Settings,
    crypto: Crypto,
    provider: EmailProvider,
    *,
    message_id: uuid.UUID,
    now: datetime,
) -> OutreachMessage:
    msg = db.get(OutreachMessage, message_id, with_for_update=True)
    if msg is None:
        raise JobError("not_found", "Message not found.")
    if msg.status is not MessageStatus.SCHEDULED:
        return msg  # cancelled, already sent, or reconciled: never send twice
    compliance.lock_recipient(db, msg.recipient_hash or "")
    db.refresh(msg)
    if msg.status is not MessageStatus.SCHEDULED:
        return msg
    basis, evidence = _latest_basis(db, msg)
    a = compliance.assess(db, settings, crypto, message=msg, draft=_draft_of(crypto, msg), legal_basis=basis, legal_basis_evidence=evidence,
                          now=now, provider_name=provider.name, provider_is_mock=provider.is_mock)  # fmt: skip
    if a.decision is not ComplianceDecision.ELIGIBLE:
        temporary = {
            "paused_email_or_global",
            "campaign_not_active",
            "country_paused",
            "provider_paused",
            "rate_or_budget_exceeded",
        }
        if set(a.reasons) <= temporary:
            db.rollback()
            raise SendDeferred(",".join(a.reasons))
        row = compliance.record_assessment(
            db,
            a,
            message=msg,
            legal_basis=basis,
            evidence=evidence,
            now=now,
            provider_version=provider.name,
        )
        msg.compliance_assessment_id, msg.status, msg.error_code = (
            row.id,
            MessageStatus.DRAFT,
            (a.reasons[0] if a.reasons else "hold")[:64],
        )
        prospect = db.get(Prospect, msg.prospect_id)
        if prospect is not None:
            _move(
                db,
                crypto,
                prospect,
                ProspectState.POLICY_HOLD,
                "pre-send compliance check failed",
                now,
            )
        db.commit()
        return msg
    contact = db.get(EmailContact, msg.email_contact_id) if msg.email_contact_id else None
    if contact is None or msg.proposal_id is None:
        raise JobError("not_found", "Contact or proposal missing.")
    preview, preview_url = create_preview(
        db,
        crypto,
        settings,
        proposal_id=msg.proposal_id,
        actor_user_id=None,
        now=now,
        meta=None,
        commit=False,
    )
    token = secrets.token_urlsafe(32)
    unsubscribe_url = f"{settings.api_url}/u/{token}"
    final = _draft_of(crypto, msg)
    text = final.text.replace(PREVIEW_SLOT, preview_url).replace(UNSUBSCRIBE_SLOT, unsubscribe_url)
    msg.body_encrypted = crypto.encrypt_str(text, context=BODY_CONTEXT)
    msg.unsubscribe_token_hash = crypto.lookup_hash(token, purpose="unsubscribe")
    msg.preview_id = preview.id
    msg.status, msg.attempt_count, msg.last_attempt_at = (
        MessageStatus.SENDING,
        msg.attempt_count + 1,
        now,
    )
    db.commit()  # the intent is durable before the provider call
    email = OutgoingEmail(to=compliance.contact_email(crypto, contact), from_name=settings.email_from_name,
                          from_address=settings.email_from_address, reply_to=settings.email_reply_to, subject=final.subject, text=text,
                          headers={"List-Unsubscribe": f"<{unsubscribe_url}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"})  # fmt: skip
    result = provider.send(email, msg.idempotency_key)
    msg = db.get(OutreachMessage, message_id, with_for_update=True) or msg
    prospect = db.get(Prospect, msg.prospect_id)
    if result.status == "accepted":
        msg.status, msg.provider_message_id, msg.accepted_at, msg.sent_at = (
            MessageStatus.ACCEPTED,
            result.provider_message_id,
            now,
            now,
        )
        if prospect is not None:
            _move(db, crypto, prospect, ProspectState.SENT, "message accepted by provider", now)
    elif result.status == "ambiguous":
        msg.status, msg.error_code = MessageStatus.AMBIGUOUS, "ambiguous_send"
        enqueue(db, EMAIL_RECONCILE, idempotency_key=f"reconcile:{msg.id}:{msg.attempt_count}", payload={"message_id": str(msg.id)},
                now=now, available_at=now + timedelta(minutes=2), entity_type="outreach_message", entity_id=msg.id)  # fmt: skip
    elif result.permanent:
        msg.status, msg.error_code = MessageStatus.FAILED, "provider_rejected"
    else:
        msg.status, msg.error_code = MessageStatus.SCHEDULED, "provider_transient_failure"
        db.commit()
        raise JobError(
            "provider_transient_failure", result.error or "Provider error.", retryable=True
        )
    activity.record(db, crypto, action="outreach.send_result", actor_user_id=None, system=True, entity_type="outreach_message",
                    entity_id=msg.id, metadata={"status": msg.status.value, "provider": provider.name})  # fmt: skip
    db.commit()
    return msg


def reconcile(
    db: Session, crypto: Crypto, provider: EmailProvider, *, message_id: uuid.UUID, now: datetime
) -> OutreachMessage:
    """Resolve an ambiguous send by asking the provider; never resend blindly."""
    msg = db.get(OutreachMessage, message_id, with_for_update=True)
    if msg is None:
        raise JobError("not_found", "Message not found.")
    if msg.status is not MessageStatus.AMBIGUOUS:
        return msg
    remote_id = provider.get_message_status(msg.idempotency_key)
    prospect = db.get(Prospect, msg.prospect_id)
    if remote_id:
        msg.status, msg.provider_message_id, msg.accepted_at, msg.sent_at, msg.error_code = (
            MessageStatus.ACCEPTED,
            remote_id,
            now,
            now,
            None,
        )
        if prospect is not None:
            _move(
                db,
                crypto,
                prospect,
                ProspectState.SENT,
                "ambiguous send confirmed by provider",
                now,
            )
    else:
        # Provider has no record: safe to retry with the same idempotency key (provider-side dedupe).
        msg.status, msg.error_code = MessageStatus.SCHEDULED, "ambiguous_not_found"
        enqueue(db, EMAIL_SEND, idempotency_key=f"send:{msg.id}:retry:{msg.attempt_count}", payload={"message_id": str(msg.id)}, now=now,
                entity_type="outreach_message", entity_id=msg.id)  # fmt: skip
    activity.record(db, crypto, action="outreach.reconciled", actor_user_id=None, system=True, entity_type="outreach_message",
                    entity_id=msg.id, metadata={"status": msg.status.value})  # fmt: skip
    db.commit()
    return msg


# ----------------------------------------------------------------------------- opt-out, events and replies


def _opt_out(db: Session, crypto: Crypto, *, email_hash: str, prospect_id: uuid.UUID | None, reason: SuppressionReason, source: str,
             now: datetime) -> int:  # fmt: skip
    cancelled = compliance.suppress(
        db, crypto, email_hash=email_hash, reason=reason, source_event=source, now=now
    )
    prospect = db.get(Prospect, prospect_id) if prospect_id else None
    if prospect is not None:
        prospect.do_not_contact = True
        target = (
            ProspectState.BOUNCED
            if reason is SuppressionReason.HARD_BOUNCE
            else ProspectState.UNSUBSCRIBED
        )
        if target in ALLOWED[prospect.state]:
            transition(
                db, crypto, prospect, target, reason=f"{reason.value.lower()} received", now=now
            )
        elif ProspectState.DO_NOT_CONTACT in ALLOWED[prospect.state]:
            transition(
                db,
                crypto,
                prospect,
                ProspectState.DO_NOT_CONTACT,
                reason=f"{reason.value.lower()} received",
                now=now,
            )
    return cancelled


def unsubscribe(db: Session, crypto: Crypto, *, token: str, now: datetime) -> bool:
    """Public, no login. Valid token -> GLOBAL suppression + cancel queued mail in one transaction."""
    if not (20 <= len(token) <= 100) or not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        return False
    msg = db.scalar(
        select(OutreachMessage).where(
            OutreachMessage.unsubscribe_token_hash
            == crypto.lookup_hash(token, purpose="unsubscribe")
        )
    )
    if msg is None or not msg.recipient_hash:
        return False
    _opt_out(db, crypto, email_hash=msg.recipient_hash, prospect_id=msg.prospect_id, reason=SuppressionReason.UNSUBSCRIBE,
             source=f"unsubscribe:{msg.id}", now=now)  # fmt: skip
    db.commit()
    return True


def _verify(provider: EmailProvider, headers: dict[str, str], raw: bytes, secret: str) -> None:
    if not secret:
        raise UnavailableError("webhook_not_configured", "Webhook secret is not configured.")
    if not provider.verify_webhook(
        {k.lower(): v for k, v in headers.items()}, raw, secret, time.time()
    ):
        raise PermissionDeniedError("invalid_signature", "Invalid or expired webhook signature.")


def process_events(db: Session, settings: Settings, crypto: Crypto, provider: EmailProvider, *, headers: dict[str, str], raw: bytes,
                   now: datetime) -> dict[str, int]:  # fmt: skip
    _verify(provider, headers, raw, settings.email_webhook_secret.get_secret_value())
    events = provider.parse_events(json.loads(raw))
    counts = {"processed": 0, "duplicates": 0, "ignored": 0}
    for e in events:
        msg = (
            db.scalar(
                select(OutreachMessage).where(
                    OutreachMessage.provider == provider.name,
                    OutreachMessage.provider_message_id == e.message_id,
                )
            )
            if e.message_id
            else None
        )
        inserted = db.execute(pg_insert(EmailEvent).values(
            id=uuid.uuid4(), provider=provider.name, provider_event_id=e.event_id, outreach_message_id=msg.id if msg else None,
            event_type=e.event_type, event_at=e.occurred_at, received_at=now, payload_sha256=hashlib.sha256(raw).hexdigest(),
            processing_state=EventProcessingState.RECEIVED).on_conflict_do_nothing(index_elements=["provider", "provider_event_id"])
            .returning(EmailEvent.id)).scalar()  # fmt: skip
        if inserted is None:
            counts["duplicates"] += 1
            continue
        state = EventProcessingState.PROCESSED
        prospect = db.get(Prospect, msg.prospect_id) if msg else None
        if msg is None:
            state = EventProcessingState.IGNORED
        elif e.event_type == "delivered":
            if msg.status in (MessageStatus.ACCEPTED, MessageStatus.SENT):
                msg.status = MessageStatus.DELIVERED
            if prospect is not None:
                _move(db, crypto, prospect, ProspectState.DELIVERED, "provider delivered", now)
        elif e.event_type == "bounced" and e.bounce_type == "hard":
            msg.status = MessageStatus.BOUNCED
            _opt_out(db, crypto, email_hash=msg.recipient_hash or "", prospect_id=msg.prospect_id, reason=SuppressionReason.HARD_BOUNCE,
                     source=f"event:{e.event_id}", now=now)  # fmt: skip
        elif e.event_type == "complained":
            msg.status = MessageStatus.COMPLAINED
            _opt_out(db, crypto, email_hash=msg.recipient_hash or "", prospect_id=msg.prospect_id, reason=SuppressionReason.COMPLAINT,
                     source=f"event:{e.event_id}", now=now)  # fmt: skip
        else:
            state = (
                EventProcessingState.IGNORED
            )  # soft bounce, deferral, opens (tracking is off) and unknown types
        if msg is not None:
            msg.last_event_at = now
        db.execute(
            update(EmailEvent).where(EmailEvent.id == inserted).values(processing_state=state)
        )
        counts["processed" if state is EventProcessingState.PROCESSED else "ignored"] += 1
    db.commit()
    return counts


OPT_OUT_RE = re.compile(
    r"\b(unsubscribe|opt[- ]?out|remove (me|us|this address)|take me off|stop (emailing|sending|contacting)|do not (contact|email)|don'?t (contact|email))\b|^\s*stop\s*$",
    re.I | re.M,
)
AUTO_RE = re.compile(
    r"\b(out of (the )?office|auto(matic)?[- ]?reply|on (annual )?leave|away until|vacation)\b",
    re.I,
)
NOT_INTERESTED_RE = re.compile(
    r"\b(not interested|no thanks|no,? thank you|we('| a)re (all )?set|not (looking|needed))\b",
    re.I,
)
INTERESTED_RE = re.compile(
    r"\b(interested|let'?s (talk|chat|discuss)|(can|could) we (talk|chat|meet|discuss)|looks (good|great)|call me|schedule|quote|how much|price|pricing|sounds good|tell me more)\b",
    re.I,
)


def classify(subject: str, text: str, auto_submitted: bool) -> tuple[str, bool]:
    """Deterministic: opt-out always wins; anything unclear goes to the owner."""
    body = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(">"))[:5000]
    blob = f"{subject}\n{body}"
    if OPT_OUT_RE.search(blob):
        return "OPT_OUT", False
    if auto_submitted or AUTO_RE.search(blob):
        return "AUTO_REPLY", False
    if NOT_INTERESTED_RE.search(blob):
        return "NOT_INTERESTED", True
    if INTERESTED_RE.search(blob):
        return "INTERESTED", True
    if "?" in body:
        return "QUESTION", True
    return "UNCERTAIN", True


def process_inbound(db: Session, settings: Settings, crypto: Crypto, provider: EmailProvider, *, headers: dict[str, str], raw: bytes,
                    now: datetime) -> Reply | None:  # fmt: skip
    _verify(provider, headers, raw, settings.email_inbound_signing_secret.get_secret_value())
    inbound = provider.parse_inbound(json.loads(raw))
    if db.scalar(
        select(Reply.id).where(
            Reply.provider == provider.name, Reply.provider_event_id == inbound.event_id
        )
    ):
        return None  # duplicate delivery
    from_hash = (
        crypto.email_hash(normalize_email(inbound.from_address))
        if "@" in inbound.from_address
        else None
    )
    msg = (
        db.scalar(
            select(OutreachMessage).where(
                OutreachMessage.provider == provider.name,
                OutreachMessage.provider_message_id == inbound.in_reply_to,
            )
        )
        if inbound.in_reply_to
        else None
    )
    if msg is None and from_hash:
        msg = db.scalar(
            select(OutreachMessage)
            .where(OutreachMessage.recipient_hash == from_hash)
            .order_by(OutreachMessage.created_at.desc())
            .limit(1)
        )
    label, review = classify(inbound.subject, inbound.text, inbound.auto_submitted)
    reply = Reply(prospect_id=msg.prospect_id if msg else None, email_contact_id=msg.email_contact_id if msg else None,
                  outreach_message_id=msg.id if msg else None, provider_thread_id=inbound.in_reply_to, received_at=inbound.received_at,
                  classification=label, summary=inbound.text.strip()[:280], needs_human_review=review or msg is None,
                  provider=provider.name, provider_event_id=inbound.event_id, from_hash=from_hash, subject=inbound.subject[:500],
                  body_encrypted=crypto.encrypt_str(inbound.text, context=REPLY_CONTEXT))  # fmt: skip
    db.add(reply)
    db.flush()
    prospect = db.get(Prospect, msg.prospect_id) if msg else None
    if label == "OPT_OUT":
        for h in {x for x in (from_hash, msg.recipient_hash if msg else None) if x}:
            _opt_out(db, crypto, email_hash=h, prospect_id=msg.prospect_id if msg else None, reason=SuppressionReason.UNSUBSCRIBE,
                     source=f"reply:{reply.id}", now=now)  # fmt: skip
    elif prospect is not None and label != "AUTO_REPLY":
        _move(db, crypto, prospect, ProspectState.REPLIED, f"reply classified {label}", now)
        if label == "INTERESTED":
            _move(
                db,
                crypto,
                prospect,
                ProspectState.INTERESTED,
                "reply looks interested (owner to confirm)",
                now,
            )
    activity.record(db, crypto, action="reply.received", actor_user_id=None, system=True, entity_type="reply", entity_id=reply.id,
                    metadata={"classification": label, "matched": msg is not None})  # fmt: skip
    db.commit()
    return reply


def simulate(
    settings: Settings, kind: str, msg: OutreachMessage, contact_email: str, text: str = ""
) -> tuple[str, bytes, dict[str, str]]:
    """Dev-only: build a signed mock webhook for a message (delivered / hard_bounce / complaint / reply)."""
    eid = f"sim-{uuid.uuid4()}"
    at = datetime.now().astimezone().isoformat()
    if kind == "reply":
        payload: dict[str, Any] = {"id": eid, "from": contact_email, "subject": f"Re: {msg.subject}", "text": text or "Thanks, tell me more.",
                                   "in_reply_to": msg.provider_message_id, "at": at, "headers": {}}  # fmt: skip
        raw, headers = signed_request(
            settings.email_inbound_signing_secret.get_secret_value(), payload
        )
        return "inbound", raw, headers
    event = {"delivered": {"type": "delivered"}, "hard_bounce": {"type": "bounced", "bounce_type": "hard"},
             "complaint": {"type": "complained"}}[kind]  # fmt: skip
    raw, headers = signed_request(settings.email_webhook_secret.get_secret_value(),
                                  {"events": [{"id": eid, "message_id": msg.provider_message_id, "at": at, **event}]})  # fmt: skip
    return "events", raw, headers
