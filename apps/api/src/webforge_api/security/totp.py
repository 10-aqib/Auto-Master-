"""TOTP (RFC 6238) with replay protection, plus one-time recovery codes."""

from __future__ import annotations

import secrets
from datetime import datetime

import pyotp
import segno

ISSUER = "WEBFORGE AI"
PERIOD = 30
VALID_WINDOW = 1  # accept one step of clock drift either side
RECOVERY_CODE_COUNT = 10
_RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_secret() -> str:
    return pyotp.random_base32(length=32)


def provisioning_uri(secret: str, account: str) -> str:
    return pyotp.TOTP(secret, interval=PERIOD).provisioning_uri(name=account, issuer_name=ISSUER)


def qr_svg_data_uri(uri: str) -> str:
    return str(segno.make(uri, error="m").svg_data_uri(scale=5, border=2))


def verify(secret: str, code: str, *, now: datetime, last_used_step: int | None) -> int | None:
    """Return the matched time step, or None. Rejects reuse of an already-used step."""
    code = code.strip().replace(" ", "")
    if len(code) != 6 or not code.isdigit():
        return None
    totp = pyotp.TOTP(secret, interval=PERIOD)
    current = int(now.timestamp()) // PERIOD
    for step in range(current - VALID_WINDOW, current + VALID_WINDOW + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if secrets.compare_digest(totp.at(step * PERIOD), code):
            return step
    return None


def new_recovery_codes() -> list[str]:
    def one() -> str:
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(10))
        return f"{raw[:5]}-{raw[5:]}"

    return [one() for _ in range(RECOVERY_CODE_COUNT)]


def normalize_recovery_code(code: str) -> str:
    return code.strip().lower().replace(" ", "")
