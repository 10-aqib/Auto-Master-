"""Email compliance engine (Phase 09): policy registry, contacts, consent, suppression and eligibility.

Engineering controls, not legal advice. Unknown or unreviewed = HOLD. A public email address is contact data,
never consent. Suppression and unsubscribe cannot be bypassed by any role.
"""

from __future__ import annotations

import uuid
import zlib
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlsplit

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import (
    Campaign,
    ComplianceAssessment,
    ConsentRecord,
    EmailContact,
    OutreachMessage,
    PolicyConfig,
    Proposal,
    Prospect,
    Suppression,
)
from webforge_api.models.enums import (
    CampaignStatus,
    ComplianceDecision,
    ContactVerificationState,
    MessageStatus,
    PolicyStatus,
    ProposalStatus,
    ProspectState,
    RecipientType,
    SuppressionReason,
    SuppressionScope,
)
from webforge_api.security.crypto import Crypto, normalize_email
from webforge_api.services import activity, controls
from webforge_api.services.context import RequestMeta
from webforge_api.services.email.templates import Draft
from webforge_api.services.email.templates import check as check_content
from webforge_api.services.errors import ConflictError, NotFoundError, ValidationFailedError

MESSAGE_CATEGORIES = {
    "commercial_initial": "One initial commercial message offering a website redesign (no follow-ups)."
}
VERIFICATION_METHODS = {"published_on_official_website", "provided_by_business"}
LEGAL_BASES = {
    "consent",
    "legitimate_interest",
    "corporate_subscriber_exemption",
    "existing_relationship",
    "none_required_reviewed",
}
ACTIVE_SENDS = (
    MessageStatus.SENDING,
    MessageStatus.ACCEPTED,
    MessageStatus.SENT,
    MessageStatus.DELIVERED,
)
UNSENT = (MessageStatus.DRAFT, MessageStatus.PENDING_REVIEW, MessageStatus.SCHEDULED)
REQUIRED_RULE_KEYS = {
    "permitted",
    "legal_bases",
    "consent_required",
    "disclosures",
    "unsubscribe",
    "retention_days",
    "next_review",
}

Severity = Literal["hold", "ineligible"]


# ----------------------------------------------------------------------------- policies


def validate_rules(rules: dict[str, Any]) -> None:
    missing = REQUIRED_RULE_KEYS - set(rules)
    if missing:
        raise ValidationFailedError("invalid_rules", f"Policy rules are missing: {sorted(missing)}")
    if not isinstance(rules["legal_bases"], list) or not set(rules["legal_bases"]) <= LEGAL_BASES:
        raise ValidationFailedError(
            "invalid_rules", f"legal_bases must be a subset of {sorted(LEGAL_BASES)}"
        )
    if not isinstance(rules["disclosures"], list) or not set(rules["disclosures"]) <= {
        "sender_identity",
        "physical_address",
        "unsubscribe",
        "concept_notice",
    }:
        raise ValidationFailedError("invalid_rules", "disclosures contains an unknown item")
    try:
        date.fromisoformat(str(rules["next_review"]))
    except ValueError as exc:
        raise ValidationFailedError("invalid_rules", "next_review must be an ISO date") from exc


def create_policy(
    db: Session,
    crypto: Crypto,
    *,
    data: dict[str, Any],
    actor_user_id: uuid.UUID,
    meta: RequestMeta,
) -> PolicyConfig:
    if data["message_category"] not in MESSAGE_CATEGORIES:
        raise ValidationFailedError("unknown_category", "Unknown message category.")
    validate_rules(data["rules"])
    row = PolicyConfig(country_code=data["country_code"].upper(), recipient_type=data["recipient_type"],
                       message_category=data["message_category"], version=data["version"], status=PolicyStatus.DRAFT,
                       rules=data["rules"], source_references=data["source_references"])  # fmt: skip
    db.add(row)
    db.flush()
    activity.record(db, crypto, action="policy.created", actor_user_id=actor_user_id, meta=meta, entity_type="policy", entity_id=row.id,
                    metadata={"country": row.country_code, "type": row.recipient_type.value, "version": row.version})  # fmt: skip
    db.commit()
    return row


def activate_policy(db: Session, crypto: Crypto, *, policy_id: uuid.UUID, reviewer_name: str, reviewer_qualification: str,
                    reviewed_at: datetime, effective_from: date, actor_user_id: uuid.UUID, meta: RequestMeta) -> PolicyConfig:  # fmt: skip
    """Owner records the qualified legal review; the previous ACTIVE version for the same key is retired."""
    row = db.get(PolicyConfig, policy_id, with_for_update=True)
    if row is None:
        raise NotFoundError("not_found", "Policy not found.")
    if row.status not in (PolicyStatus.DRAFT, PolicyStatus.IN_REVIEW):
        raise ConflictError("not_activatable", f"Policy is {row.status.value}.")
    if not row.source_references:
        raise ValidationFailedError(
            "sources_required", "Add official source references before activation."
        )
    db.execute(update(PolicyConfig).where(PolicyConfig.country_code == row.country_code, PolicyConfig.recipient_type == row.recipient_type,
                                          PolicyConfig.message_category == row.message_category, PolicyConfig.status == PolicyStatus.ACTIVE)
               .values(status=PolicyStatus.RETIRED, effective_to=effective_from))  # fmt: skip
    db.flush()
    row.status, row.reviewer_name, row.reviewer_qualification = (
        PolicyStatus.ACTIVE,
        reviewer_name,
        reviewer_qualification,
    )
    row.reviewed_at, row.effective_from = reviewed_at, effective_from
    activity.record(db, crypto, action="policy.activated", actor_user_id=actor_user_id, meta=meta, entity_type="policy", entity_id=row.id,
                    metadata={"country": row.country_code, "reviewer": reviewer_name[:80], "version": row.version})  # fmt: skip
    db.commit()
    return row


def retire_policy(
    db: Session,
    crypto: Crypto,
    *,
    policy_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    meta: RequestMeta,
) -> PolicyConfig:
    row = db.get(PolicyConfig, policy_id, with_for_update=True)
    if row is None:
        raise NotFoundError("not_found", "Policy not found.")
    row.status = PolicyStatus.RETIRED
    activity.record(
        db,
        crypto,
        action="policy.retired",
        actor_user_id=actor_user_id,
        meta=meta,
        entity_type="policy",
        entity_id=row.id,
    )
    db.commit()
    return row


def active_policy(
    db: Session, country: str, recipient_type: RecipientType, category: str, today: date
) -> PolicyConfig | None:
    row = db.scalar(select(PolicyConfig).where(PolicyConfig.country_code == country, PolicyConfig.recipient_type == recipient_type,
                                               PolicyConfig.message_category == category, PolicyConfig.status == PolicyStatus.ACTIVE))  # fmt: skip
    if (
        row is None
        or row.effective_from is None
        or row.effective_from > today
        or (row.effective_to and row.effective_to <= today)
    ):
        return None
    return row


# ----------------------------------------------------------------------------- contacts and consent


def add_contact(db: Session, crypto: Crypto, *, prospect_id: uuid.UUID, email: str, recipient_type: RecipientType, country_code: str | None,
                source_url: str, verification_method: str, contact_name: str | None, role_function: str | None,
                actor_user_id: uuid.UUID, now: datetime, meta: RequestMeta) -> EmailContact:  # fmt: skip
    prospect = db.get(Prospect, prospect_id)
    if prospect is None:
        raise NotFoundError("not_found", "Prospect not found.")
    if verification_method not in VERIFICATION_METHODS:
        raise ValidationFailedError(
            "unverifiable_source",
            "Only addresses published on the official website or provided by the business are allowed (no guessed addresses).",
        )
    host = (urlsplit(source_url).hostname or "").lower()
    domain = (prospect.verified_domain or "").lower()
    if verification_method == "published_on_official_website" and (
        not domain or not (host == domain or host.endswith("." + domain))
    ):
        raise ValidationFailedError(
            "source_not_official", "The source page must be on the prospect's verified domain."
        )
    normalized = normalize_email(email)
    if "@" not in normalized:
        raise ValidationFailedError("invalid_email", "Invalid email address.")
    email_hash = crypto.email_hash(normalized)
    if db.scalar(
        select(EmailContact.id).where(
            EmailContact.prospect_id == prospect_id, EmailContact.email_hash == email_hash
        )
    ):
        raise ConflictError(
            "duplicate_contact", "This address is already recorded for the prospect."
        )
    row = EmailContact(prospect_id=prospect_id, email_encrypted=crypto.encrypt_str(normalized, context="email-contact"),
                       email_hash=email_hash, contact_name=contact_name, recipient_type=recipient_type,
                       role_function=role_function, source_url=source_url, source_retrieved_at=now,
                       country_code=(country_code or prospect.country_code), verification_state=ContactVerificationState.VERIFIED,
                       verification_method=verification_method)  # fmt: skip
    db.add(row)
    db.flush()
    activity.record(db, crypto, action="contact.added", actor_user_id=actor_user_id, meta=meta, entity_type="email_contact",
                    entity_id=row.id, metadata={"method": verification_method, "type": recipient_type.value})  # fmt: skip
    db.commit()
    return row


def contact_email(crypto: Crypto, contact: EmailContact) -> str:
    return crypto.decrypt_str(contact.email_encrypted, context="email-contact")


def add_consent(db: Session, crypto: Crypto, *, contact_id: uuid.UUID, consent_type: str, scope: str, source: str, evidence: str,
                captured_at: datetime, expires_at: datetime | None, actor_user_id: uuid.UUID, meta: RequestMeta) -> ConsentRecord:  # fmt: skip
    if db.get(EmailContact, contact_id) is None:
        raise NotFoundError("not_found", "Contact not found.")
    row = ConsentRecord(email_contact_id=contact_id, consent_type=consent_type, scope=scope, source=source, evidence=evidence,
                        captured_at=captured_at, expires_at=expires_at)  # fmt: skip
    db.add(row)
    db.flush()
    activity.record(
        db,
        crypto,
        action="consent.recorded",
        actor_user_id=actor_user_id,
        meta=meta,
        entity_type="consent",
        entity_id=row.id,
    )
    db.commit()
    return row


# ----------------------------------------------------------------------------- suppression


def lock_recipient(db: Session, email_hash: str) -> None:
    """Serialise opt-out and send pre-flight for one recipient (transaction-scoped advisory lock)."""
    db.execute(select(func.pg_advisory_xact_lock(zlib.crc32(("recipient:" + email_hash).encode()))))


def is_suppressed(db: Session, email_hash: str, campaign_id: uuid.UUID | None = None) -> bool:
    q = select(Suppression.id).where(
        Suppression.email_hash == email_hash, Suppression.scope == SuppressionScope.GLOBAL
    )
    if db.scalar(q.limit(1)):
        return True
    if campaign_id is not None:
        return db.scalar(select(Suppression.id).where(Suppression.email_hash == email_hash, Suppression.scope == SuppressionScope.CAMPAIGN,
                                                      Suppression.scope_ref == str(campaign_id)).limit(1)) is not None  # fmt: skip
    return False


def suppress(db: Session, crypto: Crypto, *, email_hash: str, reason: SuppressionReason, source_event: str | None, now: datetime,
             actor_user_id: uuid.UUID | None = None, meta: RequestMeta | None = None) -> int:  # fmt: skip
    """GLOBAL suppression + cancel every unsent message to this recipient, in the caller's transaction.
    Returns the number of cancelled messages. The caller commits."""
    lock_recipient(db, email_hash)
    if not db.scalar(
        select(Suppression.id).where(
            Suppression.email_hash == email_hash, Suppression.scope == SuppressionScope.GLOBAL
        )
    ):
        db.add(Suppression(email_hash=email_hash, scope=SuppressionScope.GLOBAL, scope_ref="", reason=reason,
                           source_event=(source_event or "")[:128] or None, created_at=now, created_by_user_id=actor_user_id))  # fmt: skip
    cancelled = db.execute(update(OutreachMessage).where(OutreachMessage.recipient_hash == email_hash, OutreachMessage.status.in_(UNSENT))
                           .values(status=MessageStatus.CANCELLED, cancelled_reason=f"suppressed_{reason.value.lower()}"[:64]))  # fmt: skip
    count = int(cancelled.rowcount or 0)  # type: ignore[attr-defined]
    activity.record(db, crypto, action="suppression.added", actor_user_id=actor_user_id, meta=meta, system=actor_user_id is None,
                    entity_type="suppression", entity_id=email_hash[:16], metadata={"reason": reason.value, "cancelled": count})  # fmt: skip
    return count


# ----------------------------------------------------------------------------- eligibility


@dataclass
class Assessment:
    decision: ComplianceDecision
    reasons: list[str]
    checks: list[dict[str, Any]]
    policy: PolicyConfig | None


def _paused_reasons(
    db: Session, settings: Settings, campaign: Campaign | None, country: str | None, provider: str
) -> list[str]:
    reasons = []
    if controls.is_paused(db, settings, "email_pause"):
        reasons.append("paused_email_or_global")
    if campaign is not None and campaign.status is not CampaignStatus.ACTIVE:
        reasons.append("campaign_not_active")
    if country and controls.is_scoped_paused(db, f"country_pause:{country}"):
        reasons.append("country_paused")
    if controls.is_scoped_paused(db, f"provider_pause:{provider}"):
        reasons.append("provider_paused")
    return reasons


def sends_since(db: Session, since: datetime) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(OutreachMessage)
            .where(
                OutreachMessage.status.in_(ACTIVE_SENDS), OutreachMessage.last_attempt_at >= since
            )
        )
        or 0
    )


def assess(db: Session, settings: Settings, crypto: Crypto, *, message: OutreachMessage, draft: Draft, legal_basis: str | None,
           legal_basis_evidence: str | None, now: datetime, provider_name: str, provider_is_mock: bool) -> Assessment:  # fmt: skip
    """Run every pre-send condition. Any failure -> INELIGIBLE (hard stops) or HOLD (missing review/evidence)."""
    checks: list[dict[str, Any]] = []

    def add(
        n: int, code: str, ok: bool, reason: str, severity: Severity = "hold", detail: str = ""
    ) -> None:
        checks.append(
            {
                "n": n,
                "code": code,
                "ok": bool(ok),
                "reason": None if ok else reason,
                "severity": severity,
                "detail": detail[:200],
            }
        )

    prospect = db.get(Prospect, message.prospect_id)
    contact = db.get(EmailContact, message.email_contact_id) if message.email_contact_id else None
    proposal = db.get(Proposal, message.proposal_id) if message.proposal_id else None
    campaign = db.get(Campaign, message.campaign_id) if message.campaign_id else None
    if prospect is None:
        raise NotFoundError("not_found", "Prospect not found.")
    country = (contact.country_code if contact else None) or prospect.country_code
    rtype = contact.recipient_type if contact else RecipientType.UNKNOWN
    today = now.date()
    add(1, "country_known", bool(country), "country_unknown")
    add(2, "recipient_type_known", rtype is not RecipientType.UNKNOWN, "recipient_type_unknown")
    add(
        3,
        "message_category_known",
        message.message_category in MESSAGE_CATEGORIES,
        "message_category_unknown",
    )
    policy = active_policy(db, country, rtype, message.message_category, today) if country else None
    rules: dict[str, Any] = policy.rules if policy else {}
    review_current = bool(policy) and str(rules.get("next_review", "")) >= today.isoformat()
    add(4, "reviewed_policy", bool(policy) and review_current, "no_reviewed_policy" if not policy else "policy_review_overdue",
        detail=f"{policy.country_code}/{policy.recipient_type.value} v{policy.version}" if policy else "")  # fmt: skip
    if policy and not rules.get("permitted", False):
        add(4, "policy_permits", False, "policy_prohibits", "ineligible")
    basis_ok = (
        bool(legal_basis)
        and legal_basis in rules.get("legal_bases", [])
        and bool((legal_basis_evidence or "").strip())
    )
    if rules.get("consent_required") and contact is not None:
        consent = db.scalar(select(ConsentRecord.id).where(ConsentRecord.email_contact_id == contact.id, ConsentRecord.withdrawn_at.is_(None),
                                                           (ConsentRecord.expires_at.is_(None)) | (ConsentRecord.expires_at > now)).limit(1))  # fmt: skip
        basis_ok = basis_ok and consent is not None
    add(
        5,
        "legal_basis_evidence",
        basis_ok,
        "legal_basis_missing" if not rules.get("consent_required") else "consent_missing",
    )
    add(6, "data_source_permitted", bool(contact and contact.source_url) and bool(rules.get("personal_data_reviewed", rtype in (RecipientType.CORPORATE, RecipientType.ROLE_ACCOUNT))),
        "personal_data_use_unreviewed")  # fmt: skip
    verified = (
        contact is not None
        and contact.verification_state is ContactVerificationState.VERIFIED
        and (contact.verification_method or "") in VERIFICATION_METHODS
    )
    add(7, "email_verified", verified, "email_unverified")
    suppressed = bool(message.recipient_hash) and is_suppressed(
        db, message.recipient_hash or "", message.campaign_id
    )
    add(8, "not_suppressed", not suppressed, "suppressed", "ineligible")
    blocked_state = prospect.do_not_contact or prospect.state in (
        ProspectState.UNSUBSCRIBED,
        ProspectState.BOUNCED,
        ProspectState.DO_NOT_CONTACT,
        ProspectState.REJECTED,
    )
    add(9, "no_opt_out_or_dnc", not blocked_state, "do_not_contact", "ineligible")
    need_address = "physical_address" in rules.get("disclosures", [])
    identity_ok = bool(
        settings.email_from_name and settings.email_from_address and settings.email_reply_to
    )
    add(10, "sender_identity_and_disclosures", identity_ok and (not need_address or bool(settings.email_physical_address)),
        "sender_identity_incomplete" if not identity_ok else "physical_address_missing")  # fmt: skip
    add(
        11,
        "unsubscribe_live",
        settings.api_url.startswith(("https://", "http://"))
        and (not settings.is_production or settings.api_url.startswith("https://")),
        "unsubscribe_unavailable",
    )
    provider_ok = (provider_is_mock and not settings.is_production) or (
        settings.email_provider_policy_approved and bool(settings.email_provider_approval_ref)
    )
    add(
        12,
        "provider_permits_traffic",
        provider_ok,
        "provider_not_approved",
        detail="mock sandbox" if provider_is_mock else provider_name,
    )
    add(
        13,
        "sender_domain_authenticated",
        (provider_is_mock and not settings.is_production) or settings.email_domain_authenticated,
        "sender_domain_unverified",
    )
    within = (settings.email_daily_max > 0 and settings.email_hourly_max > 0
              and sends_since(db, now - timedelta(days=1)) < settings.email_daily_max
              and sends_since(db, now - timedelta(hours=1)) < settings.email_hourly_max)  # fmt: skip
    add(
        14,
        "rate_and_budget",
        within,
        "rate_or_budget_exceeded",
        detail=f"daily max {settings.email_daily_max}, hourly max {settings.email_hourly_max}",
    )
    paused = _paused_reasons(db, settings, campaign, country, provider_name)
    add(15, "not_paused", not paused, paused[0] if paused else "", detail=",".join(paused))
    preview_ok = (
        proposal is not None
        and proposal.status is ProposalStatus.READY
        and proposal.deleted_at is None
        and bool(proposal.expires_at and proposal.expires_at > now + timedelta(days=7))
    )
    add(16, "preview_valid", preview_ok, "proposal_not_ready_or_expiring")
    content = check_content(
        draft,
        from_name=settings.email_from_name,
        physical_address_required=need_address,
        physical_address=settings.email_physical_address,
    )
    add(
        17, "message_truthful", not content, content[0] if content else "", detail=",".join(content)
    )
    failed = [c for c in checks if not c["ok"]]
    if any(c["severity"] == "ineligible" for c in failed):
        decision = ComplianceDecision.INELIGIBLE
    elif failed:
        decision = ComplianceDecision.HOLD
    else:
        decision = ComplianceDecision.ELIGIBLE
    return Assessment(decision, [c["reason"] for c in failed], checks, policy)


def record_assessment(db: Session, a: Assessment, *, message: OutreachMessage, legal_basis: str | None, evidence: str | None,
                      now: datetime, provider_version: str) -> ComplianceAssessment:  # fmt: skip
    contact = db.get(EmailContact, message.email_contact_id) if message.email_contact_id else None
    prospect = db.get(Prospect, message.prospect_id)
    row = ComplianceAssessment(prospect_id=message.prospect_id, email_contact_id=message.email_contact_id,
                               country_code=(contact.country_code if contact else None) or (prospect.country_code if prospect else None),
                               recipient_type=contact.recipient_type if contact else RecipientType.UNKNOWN,
                               message_category=message.message_category, legal_basis=legal_basis, legal_basis_evidence=evidence,
                               policy_config_id=a.policy.id if a.policy else None, policy_version=a.policy.version if a.policy else None,
                               provider_policy_version=provider_version, decision=a.decision, reason_codes=a.reasons,
                               assessed_at=now, expires_at=now + timedelta(days=7), checks=a.checks)  # fmt: skip
    db.add(row)
    db.flush()
    return row


# Research starting points only (DRAFT, never active): counsel must review, complete and activate them.
POLICY_DRAFTS: list[dict[str, Any]] = [
    {"country_code": "US", "recipient_type": RecipientType.CORPORATE, "notes": "CAN-SPAM applies to commercial email including B2B.",
     "sources": ["https://www.ftc.gov/business-guidance/resources/can-spam-act-compliance-guide-business"],
     "disclosures": ["sender_identity", "physical_address", "unsubscribe", "concept_notice"]},
    {"country_code": "GB", "recipient_type": RecipientType.CORPORATE, "notes": "PECR differs for corporate subscribers vs individuals/sole traders.",
     "sources": ["https://ico.org.uk/for-organisations/direct-marketing-and-privacy-and-electronic-communications/guide-to-pecr/electronic-and-telephone-marketing/electronic-mail-marketing/"],
     "disclosures": ["sender_identity", "unsubscribe", "concept_notice"]},
    {"country_code": "CA", "recipient_type": RecipientType.CORPORATE, "notes": "CASL generally requires express or qualifying implied consent.",
     "sources": ["https://crtc.gc.ca/eng/com500/guide.htm"], "disclosures": ["sender_identity", "physical_address", "unsubscribe", "concept_notice"]},
    {"country_code": "PK", "recipient_type": RecipientType.CORPORATE, "notes": "No rule assumed. Obtain current official sources and local counsel review.",
     "sources": [], "disclosures": ["sender_identity", "unsubscribe", "concept_notice"]},
]  # fmt: skip


def seed_policy_drafts(db: Session, today: date) -> int:
    """Create DRAFT (inactive, not permitted) research entries. Idempotent. Never activates anything."""
    created = 0
    for d in POLICY_DRAFTS:
        exists = db.scalar(select(PolicyConfig.id).where(PolicyConfig.country_code == d["country_code"], PolicyConfig.recipient_type == d["recipient_type"],
                                                         PolicyConfig.message_category == "commercial_initial", PolicyConfig.version == "draft-0"))  # fmt: skip
        if exists:
            continue
        rules = {"permitted": False, "legal_bases": [], "consent_required": True, "disclosures": d["disclosures"],
                 "unsubscribe": "visible link + RFC 8058 one-click; honour immediately", "retention_days": 365,
                 "next_review": today.isoformat(), "research_notes": d["notes"] + " NOT LEGAL ADVICE; counsel must review."}  # fmt: skip
        db.add(PolicyConfig(country_code=d["country_code"], recipient_type=d["recipient_type"], message_category="commercial_initial",
                            version="draft-0", status=PolicyStatus.DRAFT, rules=rules, source_references=d["sources"]))  # fmt: skip
        created += 1
    db.commit()
    return created
