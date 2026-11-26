"""Domain enumerations shared by models and API schemas."""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    REVIEWER = "REVIEWER"
    READ_ONLY = "READ_ONLY"


class CampaignStatus(StrEnum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class SendingMode(StrEnum):
    DISABLED = "DISABLED"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    AUTOMATIC_ELIGIBLE_ONLY = "AUTOMATIC_ELIGIBLE_ONLY"


class ProspectState(StrEnum):
    DISCOVERED = "DISCOVERED"
    SOURCE_VERIFYING = "SOURCE_VERIFYING"
    VERIFIED = "VERIFIED"
    DEDUPLICATED = "DEDUPLICATED"
    QUALIFYING = "QUALIFYING"
    QUALIFIED = "QUALIFIED"
    AUDITING = "AUDITING"
    AUDITED = "AUDITED"
    GENERATING_DESIGN = "GENERATING_DESIGN"
    VALIDATING = "VALIDATING"
    PROPOSAL_READY = "PROPOSAL_READY"
    COMPLIANCE_CHECK = "COMPLIANCE_CHECK"
    HUMAN_REVIEW = "HUMAN_REVIEW"
    SCHEDULED = "SCHEDULED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    REPLIED = "REPLIED"
    INTERESTED = "INTERESTED"
    CLIENT = "CLIENT"
    REJECTED = "REJECTED"
    FAILED = "FAILED"
    BOUNCED = "BOUNCED"
    UNSUBSCRIBED = "UNSUBSCRIBED"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"
    POLICY_HOLD = "POLICY_HOLD"
    EXPIRED = "EXPIRED"


class RecipientType(StrEnum):
    UNKNOWN = "UNKNOWN"
    CORPORATE = "CORPORATE"
    SOLE_TRADER = "SOLE_TRADER"
    INDIVIDUAL = "INDIVIDUAL"
    ROLE_ACCOUNT = "ROLE_ACCOUNT"


class ContactVerificationState(StrEnum):
    UNVERIFIED = "UNVERIFIED"
    VERIFIED = "VERIFIED"
    INVALID = "INVALID"


class RunStatus(StrEnum):
    """Generic status for audits, renders and generation runs."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Severity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ProposalStatus(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    SENT = "SENT"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class PreviewStatus(StrEnum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"


class ComplianceDecision(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    INELIGIBLE = "INELIGIBLE"
    HOLD = "HOLD"
    HUMAN_REVIEW = "HUMAN_REVIEW"


class SuppressionScope(StrEnum):
    GLOBAL = "GLOBAL"
    CAMPAIGN = "CAMPAIGN"


class SuppressionReason(StrEnum):
    UNSUBSCRIBE = "UNSUBSCRIBE"
    HARD_BOUNCE = "HARD_BOUNCE"
    COMPLAINT = "COMPLAINT"
    DO_NOT_CONTACT = "DO_NOT_CONTACT"
    MANUAL = "MANUAL"
    LEGAL = "LEGAL"


class MessageStatus(StrEnum):
    DRAFT = "DRAFT"
    PENDING_REVIEW = "PENDING_REVIEW"
    SCHEDULED = "SCHEDULED"
    SENDING = "SENDING"
    ACCEPTED = "ACCEPTED"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    BOUNCED = "BOUNCED"
    COMPLAINED = "COMPLAINED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    AMBIGUOUS = "AMBIGUOUS"


class EventProcessingState(StrEnum):
    RECEIVED = "RECEIVED"
    PROCESSED = "PROCESSED"
    IGNORED = "IGNORED"
    FAILED = "FAILED"


class JobStatus(StrEnum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    DEAD = "DEAD"
    CANCELLED = "CANCELLED"


class PolicyStatus(StrEnum):
    DRAFT = "DRAFT"
    IN_REVIEW = "IN_REVIEW"
    ACTIVE = "ACTIVE"
    RETIRED = "RETIRED"


class SourceType(StrEnum):
    """Kinds of data source in the registry."""

    MAPS_API = "MAPS_API"  # e.g. Google Places: identifiers only may be persisted
    OFFICIAL_WEBSITE = "OFFICIAL_WEBSITE"
    REGISTRY = "REGISTRY"
    LICENSED_PROVIDER = "LICENSED_PROVIDER"
    OWNER_UPLOAD = "OWNER_UPLOAD"
    MOCK = "MOCK"


class SourceStatus(StrEnum):
    DISABLED = "DISABLED"
    ENABLED = "ENABLED"


class ProvenanceSource(StrEnum):
    """Sources allowed to back a persisted business fact. Maps content is deliberately absent."""

    OFFICIAL_WEBSITE = "OFFICIAL_WEBSITE"
    REGISTRY = "REGISTRY"
    LICENSED_PROVIDER = "LICENSED_PROVIDER"
    OWNER_PROVIDED = "OWNER_PROVIDED"


class DomainVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    HOLD = "HOLD"
    REJECTED = "REJECTED"


class PlaceIdStatus(StrEnum):
    ACTIVE = "ACTIVE"
    OBSOLETE = "OBSOLETE"


class UsageOutcome(StrEnum):
    RESERVED = "RESERVED"
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
