"""Secure one-time OWNER bootstrap. No default credentials exist anywhere."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from webforge_api.models import User
from webforge_api.models.enums import Role
from webforge_api.security import passwords
from webforge_api.security.crypto import Crypto, normalize_email
from webforge_api.services import activity
from webforge_api.services.errors import ConflictError, ServiceError


def bootstrap_owner(
    db: Session, crypto: Crypto, *, email: str, display_name: str, password: str
) -> User:
    """Create the single OWNER. Refuses when any user already exists."""
    email = normalize_email(email)
    if "@" not in email or len(email) > 320:
        raise ServiceError("invalid_email", "Enter a valid email address.")
    if not display_name.strip():
        raise ServiceError("invalid_name", "Display name is required.")
    try:
        passwords.validate_password(password, email=email)
    except passwords.PasswordPolicyError as exc:
        raise ServiceError("password_policy", str(exc)) from exc

    # Serialise concurrent bootstraps; the partial unique index is the final guard.
    db.execute(select(func.pg_advisory_xact_lock(0x5746_0001)))
    if db.scalar(select(func.count()).select_from(User)):
        raise ConflictError("already_bootstrapped", "Users already exist; bootstrap is disabled.")
    owner = User(
        email=email,
        display_name=display_name.strip(),
        role=Role.OWNER,
        password_hash=passwords.hash_password(password),
    )
    db.add(owner)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("already_bootstrapped", "An owner already exists.") from exc
    activity.record(
        db,
        crypto,
        action="owner.bootstrapped",
        actor_user_id=None,
        system=True,
        entity_type="user",
        entity_id=owner.id,
    )
    db.commit()
    return owner
