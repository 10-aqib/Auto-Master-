"""Field-level provenance for persisted business facts.

Only independent sources can back a stored fact. A Maps/Places source is rejected here and by a
database CHECK constraint, so Maps Content cannot be laundered into the prospect dataset.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from webforge_api.models import ProspectSource, SourceRegistration
from webforge_api.models.enums import ProvenanceSource, SourceStatus, SourceType
from webforge_api.services.errors import ServiceError

_SOURCE_TYPE_TO_PROVENANCE = {
    SourceType.OFFICIAL_WEBSITE: ProvenanceSource.OFFICIAL_WEBSITE,
    SourceType.REGISTRY: ProvenanceSource.REGISTRY,
    SourceType.LICENSED_PROVIDER: ProvenanceSource.LICENSED_PROVIDER,
    SourceType.OWNER_UPLOAD: ProvenanceSource.OWNER_PROVIDED,
}


class ProvenanceError(ServiceError):
    status_code = 422


@dataclass(frozen=True)
class FactEvidence:
    source: SourceRegistration
    source_url: str
    retrieved_at: datetime
    confidence: float
    method: str
    evidence_note: str | None = None


def record_fact(
    db: Session,
    *,
    prospect_id: uuid.UUID,
    field: str,
    value: str,
    evidence: FactEvidence,
    store_value: bool = True,
) -> ProspectSource:
    """Add one provenance row (caller commits)."""
    src = evidence.source
    provenance = _SOURCE_TYPE_TO_PROVENANCE.get(src.source_type)
    if provenance is None:
        raise ProvenanceError(
            "source_not_independent",
            f"{src.key} cannot back a stored fact (only independent sources can).",
        )
    if src.status is not SourceStatus.ENABLED:
        raise ProvenanceError("source_disabled", f"{src.key} is disabled.")
    if field not in src.persistable_fields:
        raise ProvenanceError("field_not_permitted", f"{src.key} may not supply {field}.")
    if not evidence.source_url:
        raise ProvenanceError("source_url_required", "A source URL is required.")
    if not 0 <= evidence.confidence <= 1:
        raise ProvenanceError("invalid_confidence", "Confidence must be between 0 and 1.")
    row = ProspectSource(
        prospect_id=prospect_id,
        source_type=provenance,
        source_name=src.display_name,
        source_key=src.key,
        source_url=evidence.source_url[:2048],
        fact_field=field,
        safe_value=value if store_value else None,
        value_hash=hashlib.sha256(value.encode()).hexdigest(),
        retrieved_at=evidence.retrieved_at,
        observed_at=evidence.retrieved_at,
        terms_version=src.terms_version,
        confidence=evidence.confidence,
        verification_method=evidence.method,
        is_independent=True,
        evidence_note=evidence.evidence_note,
    )
    db.add(row)
    return row
