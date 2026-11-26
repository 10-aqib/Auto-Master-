"""Import every model so Base.metadata is complete for Alembic and tests."""

from webforge_api.models.audits import AuditFinding, WebsiteAudit
from webforge_api.models.campaigns import Campaign
from webforge_api.models.compliance import (
    ComplianceAssessment,
    ConsentRecord,
    PolicyConfig,
    Suppression,
)
from webforge_api.models.designs import Asset, DesignPage, DesignProject
from webforge_api.models.identity import ActivityLog, MfaRecoveryCode, User, UserSession
from webforge_api.models.ops import ApiUsage, Job
from webforge_api.models.outreach import EmailEvent, OutreachMessage, Reply
from webforge_api.models.proposals import PreviewDeployment, Proposal
from webforge_api.models.prospects import (
    EmailContact,
    ExternalPlaceIdentifier,
    Prospect,
    ProspectCampaign,
    ProspectSource,
)
from webforge_api.models.sources import DomainVerification, SourceRegistration, TransientSourceValue

__all__ = [
    "ActivityLog",
    "ApiUsage",
    "Asset",
    "AuditFinding",
    "Campaign",
    "ComplianceAssessment",
    "ConsentRecord",
    "DesignPage",
    "DesignProject",
    "DomainVerification",
    "EmailContact",
    "EmailEvent",
    "ExternalPlaceIdentifier",
    "Job",
    "MfaRecoveryCode",
    "OutreachMessage",
    "PolicyConfig",
    "PreviewDeployment",
    "Proposal",
    "Prospect",
    "ProspectCampaign",
    "ProspectSource",
    "Reply",
    "SourceRegistration",
    "Suppression",
    "TransientSourceValue",
    "User",
    "UserSession",
    "WebsiteAudit",
]
