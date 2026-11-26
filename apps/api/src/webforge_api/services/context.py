"""Per-request facts passed into services (never trusted for authorization)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RequestMeta:
    ip: str | None = None
    user_agent: str | None = None
    request_id: str | None = None

    @property
    def safe_user_agent(self) -> str | None:
        return self.user_agent[:200] if self.user_agent else None
