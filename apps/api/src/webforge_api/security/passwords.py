"""Argon2id password hashing and password policy."""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

# OWASP-recommended Argon2id parameters (m=19 MiB is the floor; we use 64 MiB).
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, hash_len=32, salt_len=16)

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128

# Hash of a random value, verified when the user does not exist to equalise timing.
_DUMMY_HASH = _hasher.hash("webforge-timing-equaliser-not-a-real-password")

_COMMON = frozenset(
    {
        "password1234",
        "passwordpassword",
        "123456789012",
        "qwertyuiop12",
        "letmein12345",
        "administrator",
        "welcome12345",
        "changeme1234",
        "iloveyou1234",
        "webforge1234",
    }
)


class PasswordPolicyError(ValueError):
    """Raised with a user-safe message when a password does not meet policy."""


def validate_password(password: str, *, email: str | None = None) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise PasswordPolicyError(f"Password must be at most {MAX_PASSWORD_LENGTH} characters.")
    if password.strip() != password:
        raise PasswordPolicyError("Password must not start or end with whitespace.")
    if len(set(password)) < 5:
        raise PasswordPolicyError("Password is too repetitive.")
    lowered = password.lower()
    if lowered in _COMMON:
        raise PasswordPolicyError("Password is too common.")
    if email and (lowered == email.lower() or lowered == email.split("@", 1)[0].lower()):
        raise PasswordPolicyError("Password must not match your email address.")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    """Constant-work verification. Pass None for a missing user to equalise timing."""
    try:
        return _hasher.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)
