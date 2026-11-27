"""Email provider interface and the mock provider (Phase 09).

Only the mock provider exists. Resend and Postmark were reviewed and both prohibit unsolicited/cold email
(docs/compliance/email-providers.md), so no live adapter is implemented or enabled. A future adapter must
implement `EmailProvider` and be approved by the owner with documented provider permission.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal, Protocol

SIGNATURE_HEADER = "webforge-signature"


@dataclass
class OutgoingEmail:
    to: str
    from_name: str
    from_address: str
    reply_to: str
    subject: str
    text: str
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class SendResult:
    status: Literal["accepted", "ambiguous", "failed"]
    provider_message_id: str | None = None
    error: str | None = None
    permanent: bool = False


@dataclass
class ProviderEvent:
    event_id: str
    event_type: Literal["delivered", "bounced", "complained", "deferred", "opened", "other"]
    message_id: str | None
    occurred_at: datetime
    bounce_type: Literal["hard", "soft"] | None = None
    raw_type: str = ""


@dataclass
class InboundReply:
    event_id: str
    from_address: str
    subject: str
    text: str
    in_reply_to: str | None
    received_at: datetime
    auto_submitted: bool = False


class EmailProvider(Protocol):
    name: str
    is_mock: bool

    def send(self, message: OutgoingEmail, idempotency_key: str) -> SendResult: ...
    def get_message_status(self, idempotency_key: str) -> str | None: ...
    def verify_webhook(
        self, headers: dict[str, str], raw_body: bytes, secret: str, now: float
    ) -> bool: ...
    def parse_events(self, payload: dict[str, Any]) -> list[ProviderEvent]: ...
    def parse_inbound(self, payload: dict[str, Any]) -> InboundReply: ...


def sign(secret: str, raw_body: bytes, timestamp: int) -> str:
    digest = hmac.new(
        secret.encode(), f"{timestamp}.".encode() + raw_body, hashlib.sha256
    ).hexdigest()
    return f"t={timestamp},v1={digest}"


def verify_signature(
    header: str | None, raw_body: bytes, secret: str, now: float, tolerance: int
) -> bool:
    """HMAC-SHA256 over "<timestamp>.<body>" with a freshness window (replays outside it fail)."""
    if not header or not secret:
        return False
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    try:
        ts = int(parts.get("t", ""))
    except ValueError:
        return False
    if abs(now - ts) > tolerance:
        return False
    expected = sign(secret, raw_body, ts).split("v1=", 1)[1]
    return hmac.compare_digest(expected, parts.get("v1", ""))


def _ts(value: Any) -> datetime:
    try:
        return datetime.fromisoformat(str(value)).astimezone(UTC)
    except ValueError:
        return datetime.now(UTC)


class MockEmailProvider:
    """Offline provider. "Accepts" messages without sending anything; remembers idempotency keys so a retried
    send returns the same message ID; failure modes are scriptable for tests."""

    name = "mock"
    is_mock = True
    accepted: ClassVar[
        dict[str, str]
    ] = {}  # idempotency key -> message id (process-local "remote" state)

    def __init__(self, tolerance: int = 300, script: list[str] | None = None) -> None:
        self.tolerance = tolerance
        self.script = list(script or [])  # e.g. ["ambiguous", "failed", "permanent"]
        self.sent: list[tuple[OutgoingEmail, str]] = []

    def send(self, message: OutgoingEmail, idempotency_key: str) -> SendResult:
        if idempotency_key in self.accepted:
            return SendResult("accepted", self.accepted[idempotency_key])
        mode = self.script.pop(0) if self.script else "ok"
        message_id = "mock-" + hashlib.sha256(idempotency_key.encode()).hexdigest()[:24]
        if mode == "failed":
            return SendResult("failed", error="mock transient failure")
        if mode == "permanent":
            return SendResult("failed", error="mock rejected recipient", permanent=True)
        self.accepted[idempotency_key] = message_id
        self.sent.append((message, idempotency_key))
        if mode == "ambiguous":  # accepted remotely, but the response was lost
            return SendResult("ambiguous", error="mock timeout after submit")
        return SendResult("accepted", message_id)

    def get_message_status(self, idempotency_key: str) -> str | None:
        return self.accepted.get(idempotency_key)

    def verify_webhook(
        self, headers: dict[str, str], raw_body: bytes, secret: str, now: float
    ) -> bool:
        return verify_signature(
            headers.get(SIGNATURE_HEADER), raw_body, secret, now, self.tolerance
        )

    def parse_events(self, payload: dict[str, Any]) -> list[ProviderEvent]:
        out: list[ProviderEvent] = []
        for e in payload.get("events", [])[:100]:
            raw = str(e.get("type", ""))
            kind = {"delivered": "delivered", "bounced": "bounced", "complained": "complained",
                    "deferred": "deferred", "opened": "opened"}.get(raw, "other")  # fmt: skip
            bounce = e.get("bounce_type") if e.get("bounce_type") in ("hard", "soft") else None
            out.append(ProviderEvent(str(e["id"])[:255], kind, e.get("message_id"), _ts(e.get("at")), bounce, raw))  # type: ignore[arg-type]  # fmt: skip
        return out

    def parse_inbound(self, payload: dict[str, Any]) -> InboundReply:
        headers = {str(k).lower(): str(v) for k, v in (payload.get("headers") or {}).items()}
        return InboundReply(
            event_id=str(payload["id"])[:255], from_address=str(payload.get("from", ""))[:320],
            subject=str(payload.get("subject", ""))[:500], text=str(payload.get("text", ""))[:20_000],
            in_reply_to=payload.get("in_reply_to"), received_at=_ts(payload.get("at")),
            auto_submitted=headers.get("auto-submitted", "no").lower() not in ("", "no"),
        )  # fmt: skip


def signed_request(secret: str, payload: dict[str, Any]) -> tuple[bytes, dict[str, str]]:
    """Build a signed mock webhook (used by tests and the dev-only simulator)."""
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return raw, {
        SIGNATURE_HEADER: sign(secret, raw, int(time.time())),
        "content-type": "application/json",
    }


def build_provider(name: str, tolerance: int) -> EmailProvider:
    if name == "mock":
        return MockEmailProvider(tolerance)
    raise ValueError(f"No adapter for email provider {name!r}; live providers are not enabled.")
