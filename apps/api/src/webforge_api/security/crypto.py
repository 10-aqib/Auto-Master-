"""Application-level encryption (AES-256-GCM) and keyed lookup hashes.

Ciphertext format: b"v1" + key fingerprint(4) + nonce(12) + ciphertext||tag.
The fingerprint (first 4 bytes of SHA-256 of the key) selects ENCRYPTION_KEY or
ENCRYPTION_KEY_PREVIOUS, so data written before a rotation stays readable until re-encrypted.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from webforge_api.config import ConfigurationError, Settings, is_valid_encryption_key

_VERSION = b"v1"
_FP_LEN = 4
_NONCE_LEN = 12
_HEADER = len(_VERSION) + _FP_LEN


def _fingerprint(key: bytes) -> bytes:
    return hashlib.sha256(key).digest()[:_FP_LEN]


class DecryptionError(Exception):
    """Ciphertext is malformed, tampered with or encrypted under an unknown key."""


def _key_bytes(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def normalize_email(email: str) -> str:
    return email.strip().lower()


@dataclass(frozen=True)
class Crypto:
    current_key: bytes
    previous_key: bytes | None
    lookup_key: bytes

    @classmethod
    def from_settings(cls, settings: Settings) -> Crypto:
        enc = settings.encryption_key.get_secret_value()
        if not is_valid_encryption_key(enc):
            raise ConfigurationError(
                "ENCRYPTION_KEY must be 32 random bytes, URL-safe base64 encoded"
            )
        prev = settings.encryption_key_previous.get_secret_value()
        if prev and not is_valid_encryption_key(prev):
            raise ConfigurationError("ENCRYPTION_KEY_PREVIOUS is not a valid 32-byte key")
        lookup = settings.lookup_hash_key.get_secret_value()
        if len(lookup) < 32:
            raise ConfigurationError("LOOKUP_HASH_KEY must be at least 32 characters")
        return cls(
            current_key=_key_bytes(enc),
            previous_key=_key_bytes(prev) if prev else None,
            lookup_key=lookup.encode(),
        )

    def encrypt(self, plaintext: bytes, *, context: bytes = b"") -> bytes:
        """`context` is bound as associated data (e.g. table/column) to prevent swapping."""
        nonce = os.urandom(_NONCE_LEN)
        ct = AESGCM(self.current_key).encrypt(nonce, plaintext, _VERSION + context)
        return _VERSION + _fingerprint(self.current_key) + nonce + ct

    def _key_for(self, fingerprint: bytes) -> bytes:
        for key in (self.current_key, self.previous_key):
            if key is not None and hmac.compare_digest(_fingerprint(key), fingerprint):
                return key
        raise DecryptionError("ciphertext was encrypted with an unknown key")

    def decrypt(self, blob: bytes, *, context: bytes = b"") -> bytes:
        if len(blob) < _HEADER + _NONCE_LEN + 16 or blob[: len(_VERSION)] != _VERSION:
            raise DecryptionError("unsupported ciphertext format")
        key = self._key_for(blob[len(_VERSION) : _HEADER])
        nonce, ct = blob[_HEADER : _HEADER + _NONCE_LEN], blob[_HEADER + _NONCE_LEN :]
        try:
            return AESGCM(key).decrypt(nonce, ct, _VERSION + context)
        except InvalidTag as exc:
            raise DecryptionError("ciphertext failed authentication") from exc

    def needs_reencryption(self, blob: bytes) -> bool:
        return blob[len(_VERSION) : _HEADER] != _fingerprint(self.current_key)

    def reencrypt(self, blob: bytes, *, context: bytes = b"") -> bytes:
        """Decrypt with whichever key matches and encrypt again under the current key."""
        return self.encrypt(self.decrypt(blob, context=context), context=context)

    def encrypt_str(self, value: str, *, context: str) -> bytes:
        return self.encrypt(value.encode(), context=context.encode())

    def decrypt_str(self, blob: bytes, *, context: str) -> str:
        return self.decrypt(blob, context=context.encode()).decode()

    def lookup_hash(self, value: str, *, purpose: str) -> str:
        """Deterministic keyed hash for equality lookups (hex, 64 chars)."""
        msg = purpose.encode() + b"\x00" + value.encode()
        return hmac.new(self.lookup_key, msg, hashlib.sha256).hexdigest()

    def email_hash(self, email: str) -> str:
        return self.lookup_hash(normalize_email(email), purpose="email")
