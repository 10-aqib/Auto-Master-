"""Unit tests for crypto, password, token, TOTP, rate-limit and client-IP helpers."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pyotp
import pytest
from starlette.requests import Request

from tests.conftest import make_settings, random_key32
from webforge_api.api.deps import client_ip
from webforge_api.config import ConfigurationError
from webforge_api.security import passwords, totp
from webforge_api.security.crypto import Crypto, DecryptionError
from webforge_api.security.rate_limit import MemoryRateLimiter
from webforge_api.security.tokens import (
    InvalidAccessTokenError,
    csrf_matches,
    csrf_token_for,
    decode_access_token,
    hash_token,
    issue_access_token,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _crypto(**overrides: str) -> Crypto:
    return Crypto.from_settings(make_settings(**overrides))


def test_encrypt_roundtrip_and_randomised_nonce() -> None:
    c = _crypto()
    a = c.encrypt_str("owner@business.test", context="email_contacts.email")
    b = c.encrypt_str("owner@business.test", context="email_contacts.email")
    assert a != b
    assert b"owner@business.test" not in a
    assert c.decrypt_str(a, context="email_contacts.email") == "owner@business.test"


def test_ciphertext_bound_to_context() -> None:
    c = _crypto()
    blob = c.encrypt_str("x", context="a")
    with pytest.raises(DecryptionError):
        c.decrypt_str(blob, context="b")


def test_tampered_ciphertext_rejected() -> None:
    c = _crypto()
    blob = bytearray(c.encrypt_str("secret", context="ctx"))
    blob[-1] ^= 1
    with pytest.raises(DecryptionError):
        c.decrypt_str(bytes(blob), context="ctx")


def test_key_rotation_reads_previous_key_and_reencrypts() -> None:
    old_key = random_key32()
    old = _crypto(encryption_key=old_key)
    blob = old.encrypt_str("value", context="ctx")
    rotated = _crypto(encryption_key=random_key32(), encryption_key_previous=old_key)
    assert rotated.needs_reencryption(blob)
    assert rotated.decrypt_str(blob, context="ctx") == "value"
    fresh = rotated.reencrypt(blob, context=b"ctx")
    assert not rotated.needs_reencryption(fresh)
    assert rotated.decrypt_str(fresh, context="ctx") == "value"


def test_unknown_key_rejected() -> None:
    blob = _crypto().encrypt_str("v", context="c")
    with pytest.raises(DecryptionError, match="unknown key"):
        _crypto().decrypt_str(blob, context="c")


def test_invalid_keys_fail_fast() -> None:
    with pytest.raises(ConfigurationError):
        _crypto(encryption_key="not-a-key")
    with pytest.raises(ConfigurationError):
        _crypto(lookup_hash_key="short")


def test_email_hash_normalises_and_is_keyed() -> None:
    c1, c2 = _crypto(), _crypto()
    assert c1.email_hash(" Owner@Business.TEST ") == c1.email_hash("owner@business.test")
    assert c1.email_hash("owner@business.test") != c2.email_hash("owner@business.test")
    assert len(c1.email_hash("a@b.test")) == 64


@pytest.mark.parametrize(
    "bad",
    ["short", "a" * 129, " leading-space-pw", "aaaaaaaaaaaaaa", "password1234", "owner@biz.test"],
)
def test_password_policy_rejects(bad: str) -> None:
    with pytest.raises(passwords.PasswordPolicyError):
        passwords.validate_password(bad, email="owner@biz.test")


def test_password_hash_is_argon2id_and_verifies() -> None:
    h = passwords.hash_password("Correct-Horse-Battery-9")
    assert h.startswith("$argon2id$")
    assert passwords.verify_password(h, "Correct-Horse-Battery-9")
    assert not passwords.verify_password(h, "wrong")
    assert not passwords.verify_password(None, "anything")
    assert not passwords.verify_password("not-a-hash", "anything")


def test_access_token_roundtrip_and_expiry() -> None:
    sid, uid = uuid.uuid4(), uuid.uuid4()
    token, exp = issue_access_token(
        session_id=sid, user_id=uid, now=NOW, ttl=timedelta(minutes=15), key="k" * 40
    )
    claims = decode_access_token(token, key="k" * 40, now=NOW + timedelta(minutes=14))
    assert (claims.session_id, claims.user_id) == (sid, uid)
    with pytest.raises(InvalidAccessTokenError) as info:
        decode_access_token(token, key="k" * 40, now=exp)
    assert info.value.code == "token_expired"
    with pytest.raises(InvalidAccessTokenError):
        decode_access_token(token, key="x" * 40, now=NOW)


def test_csrf_token_bound_to_session() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    token = csrf_token_for(a, b"k" * 32)
    assert csrf_matches(token, csrf_token_for(a, b"k" * 32))
    assert not csrf_matches(token, csrf_token_for(b, b"k" * 32))
    assert not csrf_matches(token, None)


def test_hash_token_is_keyed() -> None:
    assert hash_token("t", b"a" * 32) != hash_token("t", b"b" * 32)


def test_totp_window_and_replay() -> None:
    secret = totp.new_secret()
    code = pyotp.TOTP(secret).at(NOW)
    step = totp.verify(secret, code, now=NOW, last_used_step=None)
    assert step is not None
    assert totp.verify(secret, code, now=NOW, last_used_step=step) is None
    assert totp.verify(secret, code, now=NOW + timedelta(seconds=90), last_used_step=None) is None
    assert totp.verify(secret, "12345", now=NOW, last_used_step=None) is None
    assert totp.verify(secret, "abcdef", now=NOW, last_used_step=None) is None


def test_recovery_codes_unique_and_formatted() -> None:
    codes = totp.new_recovery_codes()
    assert len(set(codes)) == 10
    assert all(len(c) == 11 and c[5] == "-" for c in codes)


def test_memory_rate_limiter() -> None:
    rl = MemoryRateLimiter()
    assert [rl.hit("k", limit=2, window_seconds=60) for _ in range(3)] == [True, True, False]
    rl.reset("k")
    assert rl.hit("k", limit=2, window_seconds=60)


def _request(peer: str, xff: str | None = None) -> Request:
    headers = [(b"x-forwarded-for", xff.encode())] if xff else []
    return Request({"type": "http", "client": (peer, 1234), "headers": headers})


def test_client_ip_ignores_spoofed_forwarded_for_from_untrusted_peer() -> None:
    s = make_settings(trusted_proxy_cidrs="172.28.0.0/24")
    assert client_ip(_request("203.0.113.9", "1.2.3.4"), s) == "203.0.113.9"


def test_client_ip_uses_rightmost_untrusted_hop_behind_trusted_proxy() -> None:
    s = make_settings(trusted_proxy_cidrs="172.28.0.0/24")
    req = _request("172.28.0.5", "6.6.6.6, 198.51.100.7, 172.28.0.9")
    assert client_ip(req, s) == "198.51.100.7"
    assert client_ip(_request("172.28.0.5"), s) == "172.28.0.5"
