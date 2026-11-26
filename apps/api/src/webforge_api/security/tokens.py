"""Opaque refresh tokens, signed access tokens and CSRF tokens."""

from __future__ import annotations

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

ACCESS_TOKEN_TYPE = "access"  # noqa: S105 (token type label, not a secret)
_ALGORITHM = "HS256"
_ISSUER = "webforge-api"


def new_opaque_token() -> str:
    """256-bit random URL-safe token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str, key: bytes) -> str:
    """Keyed hash used to store refresh/recovery tokens (a DB leak alone cannot forge them)."""
    return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class AccessClaims:
    session_id: uuid.UUID
    user_id: uuid.UUID
    expires_at: datetime


class InvalidAccessTokenError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def issue_access_token(
    *, session_id: uuid.UUID, user_id: uuid.UUID, now: datetime, ttl: timedelta, key: str
) -> tuple[str, datetime]:
    exp = now + ttl
    payload = {
        "iss": _ISSUER,
        "typ": ACCESS_TOKEN_TYPE,
        "sid": str(session_id),
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "jti": secrets.token_hex(8),
    }
    return jwt.encode(payload, key, algorithm=_ALGORITHM), exp


def decode_access_token(token: str, *, key: str, now: datetime) -> AccessClaims:
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[_ALGORITHM],
            issuer=_ISSUER,
            options={
                "require": ["exp", "iat", "sid", "sub", "typ", "iss"],
                # Time claims are checked below against the injected clock.
                "verify_exp": False,
                "verify_iat": False,
                "verify_nbf": False,
            },
        )
    except jwt.PyJWTError as exc:
        raise InvalidAccessTokenError("invalid_token") from exc
    if payload.get("typ") != ACCESS_TOKEN_TYPE:
        raise InvalidAccessTokenError("invalid_token")
    # Expiry is checked against the injected clock so tests and the app agree on time.
    if int(payload["exp"]) <= int(now.timestamp()):
        raise InvalidAccessTokenError("token_expired")
    try:
        sid, sub = uuid.UUID(payload["sid"]), uuid.UUID(payload["sub"])
    except (ValueError, TypeError) as exc:
        raise InvalidAccessTokenError("invalid_token") from exc
    return AccessClaims(
        session_id=sid,
        user_id=sub,
        expires_at=datetime.fromtimestamp(int(payload["exp"]), tz=now.tzinfo),
    )


def csrf_token_for(session_id: uuid.UUID, key: bytes) -> str:
    """CSRF token bound to the session; verified by recomputation (no storage needed)."""
    return hmac.new(key, b"csrf:" + str(session_id).encode(), hashlib.sha256).hexdigest()


def csrf_matches(expected: str, provided: str | None) -> bool:
    return provided is not None and hmac.compare_digest(expected, provided)
