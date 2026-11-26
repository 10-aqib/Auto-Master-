"""/api/v1/auth — login, MFA, refresh, logout, password and session management."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from webforge_api.api.cookies import CookieNames, clear_auth_cookies, set_auth_cookies
from webforge_api.api.deps import (
    AnyPrincipal,
    AuthDep,
    MetaDep,
    NowDep,
    SettingsDep,
    principal_in_states,
    verify_origin,
)
from webforge_api.api.v1.schemas import (
    AuthResponse,
    CountResponse,
    LoginRequest,
    MeResponse,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaEnableResponse,
    MfaSetupResponse,
    MfaVerifyRequest,
    PasswordChangeRequest,
    RecoveryCodesResponse,
    SessionOut,
    SessionStatus,
    UserOut,
)
from webforge_api.services.auth import IssuedTokens, Principal, SessionState, session_state

router = APIRouter(prefix="/auth", tags=["auth"])

OriginChecked = Annotated[None, Depends(verify_origin)]
PendingMfa = Annotated[Principal, Depends(principal_in_states(SessionState.MFA_PENDING))]
CanEnrollMfa = Annotated[
    Principal,
    Depends(
        principal_in_states(
            SessionState.MFA_ENROLLMENT_REQUIRED,
            SessionState.PASSWORD_CHANGE_REQUIRED,
            SessionState.ACTIVE,
        )
    ),
]
CanChangePassword = Annotated[
    Principal,
    Depends(principal_in_states(SessionState.PASSWORD_CHANGE_REQUIRED, SessionState.ACTIVE)),
]
Active = Annotated[Principal, Depends(principal_in_states(SessionState.ACTIVE))]


def _auth_response(tokens: IssuedTokens, auth: AuthDep, settings: SettingsDep) -> AuthResponse:
    state = session_state(tokens.user, tokens.session, settings)
    return AuthResponse(
        user=UserOut.model_validate(tokens.user),
        session=SessionStatus(
            state=state.value,
            session_id=tokens.session.id,
            access_expires_at=tokens.access_expires_at,
        ),
        csrf_token=tokens.csrf_token,
    )


@router.post("/login", response_model=AuthResponse)
def login(
    body: LoginRequest,
    response: Response,
    auth: AuthDep,
    settings: SettingsDep,
    meta: MetaDep,
    now: NowDep,
    _origin: OriginChecked,
) -> AuthResponse:
    tokens = auth.login(body.email, body.password, meta)
    set_auth_cookies(response, tokens, settings, now)
    return _auth_response(tokens, auth, settings)


@router.post("/mfa/verify", response_model=AuthResponse)
def verify_mfa(
    body: MfaVerifyRequest,
    principal: PendingMfa,
    response: Response,
    auth: AuthDep,
    settings: SettingsDep,
    meta: MetaDep,
    now: NowDep,
) -> AuthResponse:
    tokens = auth.verify_mfa(principal, body.code, body.method, meta)
    set_auth_cookies(response, tokens, settings, now)
    return _auth_response(tokens, auth, settings)


@router.post("/refresh", response_model=AuthResponse)
def refresh(
    request: Request,
    response: Response,
    auth: AuthDep,
    settings: SettingsDep,
    meta: MetaDep,
    now: NowDep,
    _origin: OriginChecked,
) -> AuthResponse:
    # The refresh cookie itself is the credential; it is HttpOnly + SameSite=Lax and only
    # ever returns tokens to the caller's own origin, so no CSRF token is required here.
    names = CookieNames.for_settings(settings)
    tokens = auth.refresh(request.cookies.get(names.refresh), meta)
    set_auth_cookies(response, tokens, settings, now)
    return _auth_response(tokens, auth, settings)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    principal: AnyPrincipal, response: Response, auth: AuthDep, settings: SettingsDep, meta: MetaDep
) -> Response:
    auth.logout(principal, meta)
    response.status_code = status.HTTP_204_NO_CONTENT
    clear_auth_cookies(response, settings)
    return response


@router.post("/logout-all", response_model=CountResponse)
def logout_all(
    principal: AnyPrincipal, response: Response, auth: AuthDep, settings: SettingsDep, meta: MetaDep
) -> CountResponse:
    count = auth.logout_all(principal, meta)
    clear_auth_cookies(response, settings)
    return CountResponse(count=count)


@router.get("/me", response_model=MeResponse)
def me(principal: AnyPrincipal, auth: AuthDep) -> MeResponse:
    remaining = (
        auth.remaining_recovery_codes(principal.user.id)
        if principal.user.mfa_enabled and principal.state is not SessionState.MFA_PENDING
        else None
    )
    return MeResponse(
        user=UserOut.model_validate(principal.user),
        session=SessionStatus(
            state=principal.state.value,
            session_id=principal.session.id,
            recovery_codes_remaining=remaining,
        ),
    )


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def mfa_setup(principal: CanEnrollMfa, auth: AuthDep, meta: MetaDep) -> MfaSetupResponse:
    setup = auth.begin_mfa_setup(principal, meta)
    return MfaSetupResponse(
        secret=setup.secret, otpauth_uri=setup.otpauth_uri, qr_svg_data_uri=setup.qr_svg_data_uri
    )


@router.post("/mfa/enable", response_model=MfaEnableResponse)
def mfa_enable(
    body: MfaCodeRequest,
    principal: CanEnrollMfa,
    response: Response,
    auth: AuthDep,
    settings: SettingsDep,
    meta: MetaDep,
    now: NowDep,
) -> MfaEnableResponse:
    tokens, codes = auth.enable_mfa(principal, body.code, meta)
    set_auth_cookies(response, tokens, settings, now)
    base = _auth_response(tokens, auth, settings)
    return MfaEnableResponse(**base.model_dump(), recovery_codes=codes)


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def mfa_disable(
    body: MfaDisableRequest, principal: Active, auth: AuthDep, meta: MetaDep
) -> Response:
    auth.disable_mfa(principal, body.password, body.code, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/mfa/recovery-codes", response_model=RecoveryCodesResponse)
def regenerate_recovery_codes(
    body: MfaCodeRequest, principal: Active, auth: AuthDep, meta: MetaDep
) -> RecoveryCodesResponse:
    return RecoveryCodesResponse(
        recovery_codes=auth.regenerate_recovery_codes(principal, body.code, meta)
    )


@router.post("/password", response_model=AuthResponse)
def change_password(
    body: PasswordChangeRequest,
    principal: CanChangePassword,
    response: Response,
    auth: AuthDep,
    settings: SettingsDep,
    meta: MetaDep,
    now: NowDep,
) -> AuthResponse:
    tokens = auth.change_password(principal, body.current_password, body.new_password, meta)
    set_auth_cookies(response, tokens, settings, now)
    return _auth_response(tokens, auth, settings)


@router.get("/sessions", response_model=list[SessionOut])
def list_sessions(principal: Active, auth: AuthDep) -> list[SessionOut]:
    return [
        SessionOut(
            id=s.id,
            created_at=s.created_at,
            last_seen_at=s.last_seen_at,
            user_agent=s.user_agent,
            current=s.id == principal.session.id,
        )
        for s in auth.list_sessions(principal.user.id)
    ]


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: uuid.UUID, principal: Active, auth: AuthDep, meta: MetaDep
) -> Response:
    auth.revoke_own_session(principal, session_id, meta)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
