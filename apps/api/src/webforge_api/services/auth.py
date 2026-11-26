"""Authentication, session lifecycle and MFA.

Sessions are rows in `user_sessions`. The browser holds:
- a short-lived signed access token (checked against the session row on every request,
  so revocation is immediate),
- an opaque refresh token (stored only as a keyed hash; rotated on every use; reuse of a
  rotated token outside a short grace window revokes the session),
- a CSRF token bound to the session id.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from webforge_api.config import Settings
from webforge_api.models import MfaRecoveryCode, User, UserSession
from webforge_api.models.enums import Role
from webforge_api.security import passwords, totp
from webforge_api.security.crypto import Crypto, normalize_email
from webforge_api.security.rate_limit import RateLimiter, RateLimiterUnavailableError
from webforge_api.security.tokens import (
    AccessClaims,
    InvalidAccessTokenError,
    csrf_token_for,
    decode_access_token,
    hash_token,
    issue_access_token,
    new_opaque_token,
)
from webforge_api.services import activity
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import (
    AuthenticationError,
    ConflictError,
    PermissionDeniedError,
    RateLimitedError,
    ServiceError,
    UnavailableError,
)

REFRESH_GRACE_SECONDS = 30
MFA_SECRET_CONTEXT = "users.mfa_secret"  # noqa: S105 (AEAD context label)
GENERIC_LOGIN_FAILURE = "Invalid email or password, or the account is temporarily locked."


class SessionState(StrEnum):
    MFA_PENDING = "mfa_pending"
    MFA_ENROLLMENT_REQUIRED = "mfa_enrollment_required"
    PASSWORD_CHANGE_REQUIRED = "password_change_required"  # noqa: S105
    ACTIVE = "active"


@dataclass
class IssuedTokens:
    session: UserSession
    user: User
    access_token: str
    access_expires_at: datetime
    csrf_token: str
    # None when the refresh token was not rotated (concurrent refresh inside grace window).
    refresh_token: str | None


@dataclass(frozen=True)
class Principal:
    user: User
    session: UserSession
    state: SessionState


@dataclass(frozen=True)
class MfaSetup:
    secret: str
    otpauth_uri: str
    qr_svg_data_uri: str


def mfa_required_for(user: User, settings: Settings) -> bool:
    return settings.mfa_required_for_owner and user.role in (Role.OWNER, Role.ADMIN)


def session_state(user: User, session: UserSession, settings: Settings) -> SessionState:
    if user.mfa_enabled and not session.mfa_verified:
        return SessionState.MFA_PENDING
    if mfa_required_for(user, settings) and not user.mfa_enabled:
        return SessionState.MFA_ENROLLMENT_REQUIRED
    if user.password_change_required:
        return SessionState.PASSWORD_CHANGE_REQUIRED
    return SessionState.ACTIVE


class AuthService:
    def __init__(
        self,
        db: Session,
        settings: Settings,
        crypto: Crypto,
        limiter: RateLimiter,
        now: datetime,
    ) -> None:
        self.db = db
        self.settings = settings
        self.crypto = crypto
        self.limiter = limiter
        self.now = now
        self._token_key = settings.jwt_signing_key.get_secret_value().encode()
        self._csrf_key = settings.app_secret_key.get_secret_value().encode()

    # ------------------------------------------------------------------ helpers

    def _hash(self, token: str) -> str:
        return hash_token(token, self._token_key)

    def _limit(self, key: str, *, limit: int, window: int) -> None:
        try:
            allowed = self.limiter.hit(key, limit=limit, window_seconds=window)
        except RateLimiterUnavailableError as exc:
            raise UnavailableError(
                "rate_limiter_unavailable", "Sign-in is temporarily unavailable. Try again shortly."
            ) from exc
        if not allowed:
            raise RateLimitedError("rate_limited", "Too many attempts. Wait and try again.")

    def _issue(self, session: UserSession, user: User, refresh_token: str | None) -> IssuedTokens:
        ttl = timedelta(minutes=self.settings.access_token_minutes)
        # A session never outlives its refresh window (MFA-pending sessions are short).
        ttl = min(ttl, session.refresh_expires_at - self.now)
        token, exp = issue_access_token(
            session_id=session.id,
            user_id=user.id,
            now=self.now,
            ttl=ttl,
            key=self.settings.jwt_signing_key.get_secret_value(),
        )
        return IssuedTokens(
            session=session,
            user=user,
            access_token=token,
            access_expires_at=exp,
            csrf_token=csrf_token_for(session.id, self._csrf_key),
            refresh_token=refresh_token,
        )

    def _new_session(
        self, user: User, meta: RequestMeta, *, mfa_verified: bool
    ) -> tuple[UserSession, str]:
        refresh = new_opaque_token()
        absolute = self.now + timedelta(days=self.settings.session_max_days)
        if mfa_verified:
            refresh_exp = min(self.now + timedelta(days=self.settings.refresh_token_days), absolute)
        else:
            refresh_exp = self.now + timedelta(minutes=self.settings.mfa_pending_minutes)
        session = UserSession(
            id=uuid.uuid4(),
            user_id=user.id,
            refresh_token_hash=self._hash(refresh),
            mfa_verified=mfa_verified,
            created_at=self.now,
            last_seen_at=self.now,
            refresh_expires_at=refresh_exp,
            absolute_expires_at=absolute,
            ip_hash=self.crypto.lookup_hash(meta.ip, purpose="ip") if meta.ip else None,
            user_agent=meta.safe_user_agent,
        )
        self.db.add(session)
        return session, refresh

    def _revoke(self, session: UserSession, reason: str) -> None:
        if session.revoked_at is None:
            session.revoked_at = self.now
            session.revoke_reason = reason

    def revoke_all_sessions(
        self, user_id: uuid.UUID, reason: str, *, except_session_id: uuid.UUID | None = None
    ) -> int:
        stmt = (
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=self.now, revoke_reason=reason)
        )
        if except_session_id is not None:
            stmt = stmt.where(UserSession.id != except_session_id)
        result = self.db.execute(stmt)
        return int(getattr(result, "rowcount", 0) or 0)

    def _decrypt_mfa_secret(self, blob: bytes) -> str:
        return self.crypto.decrypt_str(blob, context=MFA_SECRET_CONTEXT)

    # ------------------------------------------------------------------ login

    def login(self, email: str, password: str, meta: RequestMeta) -> IssuedTokens:
        email = normalize_email(email)
        account_ref = self.crypto.lookup_hash(email, purpose="login")
        if meta.ip:
            self._limit(
                f"login:ip:{self.crypto.lookup_hash(meta.ip, purpose='ip')}",
                limit=self.settings.login_rate_limit_per_ip_per_minute,
                window=60,
            )
        self._limit(
            f"login:acct:{account_ref}",
            limit=self.settings.login_rate_limit_per_account_per_hour,
            window=3600,
        )

        user = self.db.scalar(select(User).where(User.email == email).with_for_update())
        password_ok = passwords.verify_password(user.password_hash if user else None, password)
        locked = user is not None and user.locked_until is not None and user.locked_until > self.now

        if user is None or not password_ok or locked or not user.is_active:
            reason = (
                "unknown_account"
                if user is None
                else "locked"
                if locked
                else "inactive"
                if not user.is_active
                else "bad_password"
            )
            if user is not None and not password_ok and not locked:
                user.failed_login_count += 1
                if user.failed_login_count >= self.settings.account_lockout_threshold:
                    user.locked_until = self.now + timedelta(
                        minutes=self.settings.account_lockout_minutes
                    )
                    user.failed_login_count = 0
                    activity.record(
                        self.db,
                        self.crypto,
                        action="auth.account.locked",
                        actor_user_id=None,
                        meta=meta,
                        outcome="denied",
                        entity_type="user",
                        entity_id=user.id,
                    )
            activity.record(
                self.db,
                self.crypto,
                action="auth.login",
                actor_user_id=None,
                meta=meta,
                outcome="failure",
                entity_type="user" if user else None,
                entity_id=user.id if user else None,
                metadata={"reason": reason},
            )
            self.db.commit()
            raise AuthenticationError("invalid_credentials", GENERIC_LOGIN_FAILURE)

        user.failed_login_count = 0
        user.locked_until = None
        if passwords.needs_rehash(user.password_hash):
            user.password_hash = passwords.hash_password(password)
        session, refresh = self._new_session(user, meta, mfa_verified=not user.mfa_enabled)
        if not user.mfa_enabled:
            user.last_login_at = self.now
        activity.record(
            self.db,
            self.crypto,
            action="auth.login",
            actor_user_id=user.id,
            meta=meta,
            entity_type="session",
            entity_id=session.id,
            metadata={"mfa_pending": user.mfa_enabled},
        )
        self.db.commit()
        return self._issue(session, user, refresh)

    # ------------------------------------------------------------------ request auth

    def authenticate(self, access_token: str | None) -> Principal:
        if not access_token:
            raise AuthenticationError("not_authenticated", "Sign in to continue.")
        try:
            claims: AccessClaims = decode_access_token(
                access_token, key=self.settings.jwt_signing_key.get_secret_value(), now=self.now
            )
        except InvalidAccessTokenError as exc:
            message = "Session expired." if exc.code == "token_expired" else "Sign in to continue."
            raise AuthenticationError(exc.code, message) from exc

        session = self.db.get(UserSession, claims.session_id)
        if (
            session is None
            or session.user_id != claims.user_id
            or session.revoked_at is not None
            or session.absolute_expires_at <= self.now
        ):
            raise AuthenticationError("session_revoked", "Session ended. Sign in again.")
        user = self.db.get(User, session.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("session_revoked", "Session ended. Sign in again.")
        if (self.now - session.last_seen_at) > timedelta(minutes=1):
            session.last_seen_at = self.now
            self.db.commit()
        return Principal(
            user=user, session=session, state=session_state(user, session, self.settings)
        )

    # ------------------------------------------------------------------ refresh / logout

    def refresh(self, refresh_token: str | None, meta: RequestMeta) -> IssuedTokens:
        if not refresh_token:
            raise AuthenticationError("not_authenticated", "Sign in to continue.")
        token_hash = self._hash(refresh_token)

        session = self.db.scalar(
            select(UserSession)
            .where(UserSession.refresh_token_hash == token_hash)
            .with_for_update()
        )
        if session is None:
            previous = self.db.scalar(
                select(UserSession)
                .where(UserSession.previous_refresh_token_hash == token_hash)
                .with_for_update()
            )
            if previous is None:
                raise AuthenticationError("invalid_refresh_token", "Sign in to continue.")
            in_grace = (
                previous.rotated_at is not None
                and (self.now - previous.rotated_at).total_seconds() <= REFRESH_GRACE_SECONDS
                and previous.revoked_at is None
            )
            if in_grace:
                user = self.db.get(User, previous.user_id)
                if user is None or not user.is_active:
                    raise AuthenticationError("session_revoked", "Session ended. Sign in again.")
                return self._issue(previous, user, None)
            # A rotated token came back after the grace window: treat as theft.
            self._revoke(previous, "refresh_token_reuse")
            activity.record(
                self.db,
                self.crypto,
                action="auth.refresh.reuse_detected",
                actor_user_id=previous.user_id,
                meta=meta,
                outcome="denied",
                entity_type="session",
                entity_id=previous.id,
            )
            self.db.commit()
            raise AuthenticationError("refresh_token_reused", "Session ended. Sign in again.")

        user = self.db.get(User, session.user_id)
        if (
            session.revoked_at is not None
            or session.refresh_expires_at <= self.now
            or session.absolute_expires_at <= self.now
            or user is None
            or not user.is_active
        ):
            raise AuthenticationError("session_revoked", "Session ended. Sign in again.")
        if not session.mfa_verified and user.mfa_enabled:
            raise AuthenticationError("mfa_pending", "Complete two-factor verification.")

        new_refresh = new_opaque_token()
        session.previous_refresh_token_hash = session.refresh_token_hash
        session.refresh_token_hash = self._hash(new_refresh)
        session.rotated_at = self.now
        session.last_seen_at = self.now
        session.refresh_expires_at = min(
            self.now + timedelta(days=self.settings.refresh_token_days),
            session.absolute_expires_at,
        )
        self.db.commit()
        return self._issue(session, user, new_refresh)

    def logout(self, principal: Principal, meta: RequestMeta) -> None:
        self._revoke(principal.session, "logout")
        activity.record(
            self.db,
            self.crypto,
            action="auth.logout",
            actor_user_id=principal.user.id,
            meta=meta,
            entity_type="session",
            entity_id=principal.session.id,
        )
        self.db.commit()

    def logout_all(self, principal: Principal, meta: RequestMeta) -> int:
        count = self.revoke_all_sessions(principal.user.id, "logout_all")
        activity.record(
            self.db,
            self.crypto,
            action="auth.logout_all",
            actor_user_id=principal.user.id,
            meta=meta,
            entity_type="user",
            entity_id=principal.user.id,
            metadata={"sessions_revoked": count},
        )
        self.db.commit()
        return count

    def list_sessions(self, user_id: uuid.UUID) -> list[UserSession]:
        return list(
            self.db.scalars(
                select(UserSession)
                .where(
                    UserSession.user_id == user_id,
                    UserSession.revoked_at.is_(None),
                    UserSession.refresh_expires_at > self.now,
                )
                .order_by(UserSession.last_seen_at.desc())
            )
        )

    def revoke_own_session(
        self, principal: Principal, session_id: uuid.UUID, meta: RequestMeta
    ) -> None:
        session = self.db.get(UserSession, session_id)
        if session is None or session.user_id != principal.user.id:
            raise ServiceError("not_found", "Session not found.", status_code=404)
        self._revoke(session, "user_revoked")
        activity.record(
            self.db,
            self.crypto,
            action="auth.session.revoked",
            actor_user_id=principal.user.id,
            meta=meta,
            entity_type="session",
            entity_id=session_id,
        )
        self.db.commit()

    # ------------------------------------------------------------------ MFA

    def _check_second_factor(self, user: User, code: str, kind: str, meta: RequestMeta) -> bool:
        self._limit(
            f"mfa:{user.id}", limit=self.settings.login_rate_limit_per_ip_per_minute, window=60
        )
        if kind == "recovery":
            code_hash = self._hash("recovery:" + totp.normalize_recovery_code(code))
            row = self.db.scalar(
                select(MfaRecoveryCode)
                .where(
                    MfaRecoveryCode.user_id == user.id,
                    MfaRecoveryCode.code_hash == code_hash,
                    MfaRecoveryCode.used_at.is_(None),
                )
                .with_for_update()
            )
            if row is None:
                return False
            row.used_at = self.now
            return True
        if not user.mfa_secret_encrypted:
            return False
        step = totp.verify(
            self._decrypt_mfa_secret(user.mfa_secret_encrypted),
            code,
            now=self.now,
            last_used_step=user.mfa_last_used_step,
        )
        if step is None:
            return False
        user.mfa_last_used_step = step
        return True

    def verify_mfa(
        self, principal: Principal, code: str, kind: str, meta: RequestMeta
    ) -> IssuedTokens:
        user, session = principal.user, principal.session
        if principal.state is not SessionState.MFA_PENDING:
            raise ConflictError("mfa_not_pending", "Two-factor verification is not pending.")
        if not self._check_second_factor(user, code, kind, meta):
            activity.record(
                self.db,
                self.crypto,
                action="auth.mfa.verify",
                actor_user_id=user.id,
                meta=meta,
                outcome="failure",
                metadata={"method": kind},
            )
            self.db.commit()
            raise AuthenticationError("invalid_mfa_code", "The code is not valid.")

        # Replace the pending session with a fresh, fully verified one (no fixation).
        self._revoke(session, "mfa_upgraded")
        new_session, refresh = self._new_session(user, meta, mfa_verified=True)
        user.last_login_at = self.now
        activity.record(
            self.db,
            self.crypto,
            action="auth.mfa.verify",
            actor_user_id=user.id,
            meta=meta,
            entity_type="session",
            entity_id=new_session.id,
            metadata={"method": kind},
        )
        self.db.commit()
        return self._issue(new_session, user, refresh)

    def begin_mfa_setup(self, principal: Principal, meta: RequestMeta) -> MfaSetup:
        user = principal.user
        if user.mfa_enabled:
            raise ConflictError("mfa_already_enabled", "Two-factor authentication is already on.")
        secret = totp.new_secret()
        user.mfa_pending_secret_encrypted = self.crypto.encrypt_str(
            secret, context=MFA_SECRET_CONTEXT
        )
        activity.record(
            self.db, self.crypto, action="auth.mfa.setup_started", actor_user_id=user.id, meta=meta
        )
        self.db.commit()
        uri = totp.provisioning_uri(secret, user.email)
        return MfaSetup(secret=secret, otpauth_uri=uri, qr_svg_data_uri=totp.qr_svg_data_uri(uri))

    def _replace_recovery_codes(self, user: User) -> list[str]:
        self.db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == user.id).delete()
        codes = totp.new_recovery_codes()
        for code in codes:
            self.db.add(
                MfaRecoveryCode(
                    user_id=user.id,
                    code_hash=self._hash("recovery:" + totp.normalize_recovery_code(code)),
                    created_at=self.now,
                )
            )
        return codes

    def enable_mfa(
        self, principal: Principal, code: str, meta: RequestMeta
    ) -> tuple[IssuedTokens, list[str]]:
        user = principal.user
        if user.mfa_enabled:
            raise ConflictError("mfa_already_enabled", "Two-factor authentication is already on.")
        if not user.mfa_pending_secret_encrypted:
            raise ConflictError("mfa_setup_not_started", "Start two-factor setup first.")
        self._limit(
            f"mfa:{user.id}", limit=self.settings.login_rate_limit_per_ip_per_minute, window=60
        )
        secret = self._decrypt_mfa_secret(user.mfa_pending_secret_encrypted)
        step = totp.verify(secret, code, now=self.now, last_used_step=None)
        if step is None:
            raise AuthenticationError("invalid_mfa_code", "The code is not valid.")

        user.mfa_secret_encrypted = user.mfa_pending_secret_encrypted
        user.mfa_pending_secret_encrypted = None
        user.mfa_enabled = True
        user.mfa_last_used_step = step
        codes = self._replace_recovery_codes(user)
        # Other sessions were authenticated without MFA; end them and start a verified one.
        self.revoke_all_sessions(user.id, "mfa_enabled")
        new_session, refresh = self._new_session(user, meta, mfa_verified=True)
        activity.record(
            self.db, self.crypto, action="auth.mfa.enabled", actor_user_id=user.id, meta=meta
        )
        self.db.commit()
        return self._issue(new_session, user, refresh), codes

    def disable_mfa(
        self, principal: Principal, password: str, code: str, meta: RequestMeta
    ) -> None:
        user = principal.user
        if mfa_required_for(user, self.settings):
            raise PermissionDeniedError(
                "mfa_required_for_role", "Two-factor authentication is required for your role."
            )
        if not user.mfa_enabled:
            raise ConflictError("mfa_not_enabled", "Two-factor authentication is not on.")
        if not passwords.verify_password(
            user.password_hash, password
        ) or not self._check_second_factor(user, code, "totp", meta):
            self.db.commit()
            raise AuthenticationError("invalid_credentials", "Password or code is not valid.")
        user.mfa_enabled = False
        user.mfa_secret_encrypted = None
        user.mfa_last_used_step = None
        self.db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == user.id).delete()
        activity.record(
            self.db, self.crypto, action="auth.mfa.disabled", actor_user_id=user.id, meta=meta
        )
        self.db.commit()

    def regenerate_recovery_codes(
        self, principal: Principal, code: str, meta: RequestMeta
    ) -> list[str]:
        user = principal.user
        if not user.mfa_enabled:
            raise ConflictError("mfa_not_enabled", "Two-factor authentication is not on.")
        if not self._check_second_factor(user, code, "totp", meta):
            self.db.commit()
            raise AuthenticationError("invalid_mfa_code", "The code is not valid.")
        codes = self._replace_recovery_codes(user)
        activity.record(
            self.db,
            self.crypto,
            action="auth.mfa.recovery_codes_regenerated",
            actor_user_id=user.id,
            meta=meta,
        )
        self.db.commit()
        return codes

    def remaining_recovery_codes(self, user_id: uuid.UUID) -> int:
        return (
            self.db.query(MfaRecoveryCode)
            .filter(MfaRecoveryCode.user_id == user_id, MfaRecoveryCode.used_at.is_(None))
            .count()
        )

    # ------------------------------------------------------------------ password

    def change_password(
        self, principal: Principal, current: str, new: str, meta: RequestMeta
    ) -> IssuedTokens:
        user = principal.user
        self._limit(
            f"pwchange:{user.id}", limit=self.settings.login_rate_limit_per_ip_per_minute, window=60
        )
        if not passwords.verify_password(user.password_hash, current):
            activity.record(
                self.db,
                self.crypto,
                action="auth.password.change",
                actor_user_id=user.id,
                meta=meta,
                outcome="failure",
            )
            self.db.commit()
            raise AuthenticationError("invalid_credentials", "Current password is not valid.")
        if passwords.verify_password(user.password_hash, new):
            raise ServiceError(
                "password_reused",
                "Choose a password different from the current one.",
                status_code=422,
                field_errors={"new_password": "Must differ from the current password."},
            )
        try:
            passwords.validate_password(new, email=user.email)
        except passwords.PasswordPolicyError as exc:
            raise ServiceError(
                "password_policy",
                str(exc),
                status_code=422,
                field_errors={"new_password": str(exc)},
            ) from exc

        user.password_hash = passwords.hash_password(new)
        user.password_changed_at = self.now
        user.password_change_required = False
        # Revoke everything, then continue in a fresh session.
        self.revoke_all_sessions(user.id, "password_changed")
        new_session, refresh = self._new_session(
            user, meta, mfa_verified=principal.session.mfa_verified
        )
        activity.record(
            self.db, self.crypto, action="auth.password.changed", actor_user_id=user.id, meta=meta
        )
        self.db.commit()
        return self._issue(new_session, user, refresh)
