"""User administration with role-based rules.

- Exactly one OWNER exists; it is created only by the bootstrap CLI and cannot be changed here.
- OWNER manages ADMIN, REVIEWER and READ_ONLY accounts.
- ADMIN manages REVIEWER and READ_ONLY accounts but cannot change roles.
- Nobody modifies their own account through these operations.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webforge_api.models import MfaRecoveryCode, User
from webforge_api.models.enums import Role
from webforge_api.security import passwords
from webforge_api.security.crypto import Crypto, normalize_email
from webforge_api.services import activity
from webforge_api.services.auth import AuthService, Principal
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ServiceError,
)

MANAGEABLE_BY: dict[Role, frozenset[Role]] = {
    Role.OWNER: frozenset({Role.ADMIN, Role.REVIEWER, Role.READ_ONLY}),
    Role.ADMIN: frozenset({Role.REVIEWER, Role.READ_ONLY}),
    Role.REVIEWER: frozenset(),
    Role.READ_ONLY: frozenset(),
}


@dataclass(frozen=True)
class UserChanges:
    display_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None


def _policy_error(exc: passwords.PasswordPolicyError, field: str) -> ServiceError:
    return ServiceError(
        "password_policy", str(exc), status_code=422, field_errors={field: str(exc)}
    )


class UserService:
    def __init__(self, db: Session, crypto: Crypto, auth: AuthService, now: datetime) -> None:
        self.db = db
        self.crypto = crypto
        self.auth = auth
        self.now = now

    def list_users(self) -> list[User]:
        return list(self.db.scalars(select(User).order_by(User.created_at)))

    def _get_managed(self, actor: Principal, user_id: uuid.UUID) -> User:
        target = self.db.get(User, user_id)
        if target is None:
            raise NotFoundError("not_found", "User not found.")
        if target.id == actor.user.id:
            raise PermissionDeniedError(
                "cannot_modify_self", "Use your account settings to change your own account."
            )
        if target.role not in MANAGEABLE_BY[actor.user.role]:
            raise PermissionDeniedError("forbidden", "You cannot manage this account.")
        return target

    def create_user(
        self,
        actor: Principal,
        *,
        email: str,
        display_name: str,
        role: Role,
        initial_password: str,
        meta: RequestMeta,
    ) -> User:
        if role not in MANAGEABLE_BY[actor.user.role]:
            raise PermissionDeniedError("forbidden", "You cannot create accounts with this role.")
        email = normalize_email(email)
        try:
            passwords.validate_password(initial_password, email=email)
        except passwords.PasswordPolicyError as exc:
            raise _policy_error(exc, "initial_password") from exc
        user = User(
            email=email,
            display_name=display_name.strip(),
            role=role,
            password_hash=passwords.hash_password(initial_password),
            password_change_required=True,
        )
        self.db.add(user)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise ConflictError(
                "email_taken",
                "An account with this email already exists.",
                field_errors={"email": "Already in use."},
            ) from exc
        activity.record(
            self.db,
            self.crypto,
            action="user.created",
            actor_user_id=actor.user.id,
            meta=meta,
            entity_type="user",
            entity_id=user.id,
            metadata={"role": role.value},
        )
        self.db.commit()
        return user

    def update_user(
        self, actor: Principal, user_id: uuid.UUID, changes: UserChanges, meta: RequestMeta
    ) -> User:
        target = self._get_managed(actor, user_id)
        changed: dict[str, object] = {}

        if changes.role is not None and changes.role != target.role:
            if actor.user.role is not Role.OWNER:
                raise PermissionDeniedError("forbidden", "Only the owner can change roles.")
            if changes.role not in MANAGEABLE_BY[actor.user.role]:
                raise PermissionDeniedError("forbidden", "This role cannot be assigned.")
            changed["role"] = {"from": target.role.value, "to": changes.role.value}
            target.role = changes.role
            self.auth.revoke_all_sessions(target.id, "role_changed")

        if changes.display_name is not None and changes.display_name.strip() != target.display_name:
            target.display_name = changes.display_name.strip()
            changed["display_name"] = True

        if changes.is_active is not None and changes.is_active != target.is_active:
            target.is_active = changes.is_active
            changed["is_active"] = changes.is_active
            if not changes.is_active:
                self.auth.revoke_all_sessions(target.id, "deactivated")
            else:
                target.failed_login_count = 0
                target.locked_until = None

        if changed:
            activity.record(
                self.db,
                self.crypto,
                action="user.updated",
                actor_user_id=actor.user.id,
                meta=meta,
                entity_type="user",
                entity_id=target.id,
                metadata={"changes": changed},
            )
        self.db.commit()
        return target

    def revoke_sessions(self, actor: Principal, user_id: uuid.UUID, meta: RequestMeta) -> int:
        target = self._get_managed(actor, user_id)
        count = self.auth.revoke_all_sessions(target.id, "admin_revoked")
        activity.record(
            self.db,
            self.crypto,
            action="user.sessions_revoked",
            actor_user_id=actor.user.id,
            meta=meta,
            entity_type="user",
            entity_id=target.id,
            metadata={"sessions_revoked": count},
        )
        self.db.commit()
        return count

    def reset_mfa(self, actor: Principal, user_id: uuid.UUID, meta: RequestMeta) -> None:
        if actor.user.role is not Role.OWNER:
            raise PermissionDeniedError("forbidden", "Only the owner can reset two-factor auth.")
        target = self._get_managed(actor, user_id)
        target.mfa_enabled = False
        target.mfa_secret_encrypted = None
        target.mfa_pending_secret_encrypted = None
        target.mfa_last_used_step = None
        self.db.query(MfaRecoveryCode).filter(MfaRecoveryCode.user_id == target.id).delete()
        self.auth.revoke_all_sessions(target.id, "mfa_reset")
        activity.record(
            self.db,
            self.crypto,
            action="user.mfa_reset",
            actor_user_id=actor.user.id,
            meta=meta,
            entity_type="user",
            entity_id=target.id,
        )
        self.db.commit()
