"""Policy-bound transient cache for third-party values.

A value may be cached only if the source registry lists the field in `cache_rules` and the TTL is
within the allowed maximum (e.g. Google allows latitude/longitude for up to 30 days; other Places
fields may not be cached at all). Values are encrypted and purged when expired.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from webforge_api.models import SourceRegistration, TransientSourceValue
from webforge_api.security.crypto import Crypto
from webforge_api.services.errors import ServiceError


class TransientPolicyError(ServiceError):
    status_code = 409


def _context(source_key: str, field: str) -> str:
    return f"transient:{source_key}:{field}"


class TransientStore:
    def __init__(self, db: Session, crypto: Crypto, now: datetime) -> None:
        self.db = db
        self.crypto = crypto
        self.now = now

    def max_ttl(self, source_key: str, field: str) -> int:
        reg = self.db.scalar(select(SourceRegistration).where(SourceRegistration.key == source_key))
        if reg is None:
            raise TransientPolicyError("unknown_source", "Unknown source.")
        value = reg.cache_rules.get(field)
        return int(value) if isinstance(value, int) and value > 0 else 0

    def put(
        self, source_key: str, external_ref: str, field: str, value: str, ttl_seconds: int
    ) -> None:
        allowed = self.max_ttl(source_key, field)
        if allowed == 0:
            raise TransientPolicyError(
                "caching_not_permitted", f"{source_key}.{field} may not be cached."
            )
        if ttl_seconds <= 0 or ttl_seconds > allowed:
            raise TransientPolicyError(
                "ttl_exceeds_policy", f"{source_key}.{field} may be cached for at most {allowed}s."
            )
        stmt = insert(TransientSourceValue).values(
            source_key=source_key,
            external_ref=external_ref,
            field=field,
            value_encrypted=self.crypto.encrypt_str(value, context=_context(source_key, field)),
            fetched_at=self.now,
            expires_at=self.now + timedelta(seconds=ttl_seconds),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["source_key", "external_ref", "field"],
            set_={
                "value_encrypted": stmt.excluded.value_encrypted,
                "fetched_at": stmt.excluded.fetched_at,
                "expires_at": stmt.excluded.expires_at,
            },
        )
        self.db.execute(stmt)
        self.db.commit()

    def get(self, source_key: str, external_ref: str, field: str) -> str | None:
        row = self.db.scalar(
            select(TransientSourceValue).where(
                TransientSourceValue.source_key == source_key,
                TransientSourceValue.external_ref == external_ref,
                TransientSourceValue.field == field,
                TransientSourceValue.expires_at > self.now,
            )
        )
        if row is None:
            return None
        return self.crypto.decrypt_str(row.value_encrypted, context=_context(source_key, field))

    def purge_expired(self) -> int:
        result = self.db.execute(
            delete(TransientSourceValue).where(TransientSourceValue.expires_at <= self.now)
        )
        self.db.commit()
        return int(getattr(result, "rowcount", 0) or 0)

    def purge_disallowed(self) -> int:
        """Delete cached values whose field is no longer permitted by the registry."""
        removed = 0
        for reg in self.db.scalars(select(SourceRegistration)):
            allowed = {k for k, v in reg.cache_rules.items() if isinstance(v, int) and v > 0}
            stmt = delete(TransientSourceValue).where(TransientSourceValue.source_key == reg.key)
            if allowed:
                stmt = stmt.where(TransientSourceValue.field.not_in(allowed))
            result = self.db.execute(stmt)
            removed += int(getattr(result, "rowcount", 0) or 0)
        self.db.commit()
        return removed
