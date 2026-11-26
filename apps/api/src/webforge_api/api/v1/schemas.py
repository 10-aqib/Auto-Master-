"""Request/response models for /api/v1 (auth, users, activity)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from webforge_api.models.enums import Role

EmailStrLite = Field(min_length=3, max_length=320, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)


class LoginRequest(StrictModel):
    email: str = EmailStrLite
    password: str = Field(min_length=1, max_length=256)


class MfaVerifyRequest(StrictModel):
    code: str = Field(min_length=6, max_length=32)
    method: Literal["totp", "recovery"] = "totp"


class MfaCodeRequest(StrictModel):
    code: str = Field(min_length=6, max_length=12)


class MfaDisableRequest(StrictModel):
    password: str = Field(min_length=1, max_length=256)
    code: str = Field(min_length=6, max_length=12)


class PasswordChangeRequest(StrictModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    display_name: str
    role: Role
    is_active: bool
    mfa_enabled: bool
    password_change_required: bool
    last_login_at: datetime | None
    created_at: datetime


class SessionStatus(BaseModel):
    state: str
    session_id: uuid.UUID
    access_expires_at: datetime | None = None
    recovery_codes_remaining: int | None = None


class AuthResponse(BaseModel):
    user: UserOut
    session: SessionStatus
    csrf_token: str


class MeResponse(BaseModel):
    user: UserOut
    session: SessionStatus


class MfaSetupResponse(BaseModel):
    secret: str
    otpauth_uri: str
    qr_svg_data_uri: str


class MfaEnableResponse(AuthResponse):
    recovery_codes: list[str]


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class SessionOut(BaseModel):
    id: uuid.UUID
    created_at: datetime
    last_seen_at: datetime
    user_agent: str | None
    current: bool


class CountResponse(BaseModel):
    count: int


class UserCreateRequest(StrictModel):
    email: str = EmailStrLite
    display_name: str = Field(min_length=1, max_length=120)
    role: Role
    initial_password: str = Field(min_length=1, max_length=256)


class UserUpdateRequest(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    role: Role | None = None
    is_active: bool | None = None


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    occurred_at: datetime
    actor_user_id: uuid.UUID | None
    actor_type: str
    action: str
    entity_type: str | None
    entity_id: str | None
    outcome: str
    request_id: str | None
    metadata: dict[str, Any] = Field(validation_alias="metadata_json")


class ActivityPage(BaseModel):
    items: list[ActivityOut]
    next_cursor: str | None
