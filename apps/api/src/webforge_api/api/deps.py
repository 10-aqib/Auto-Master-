"""Request dependencies: services, authentication, CSRF, origin checks and RBAC."""

import ipaddress
from collections.abc import Callable
from datetime import datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from webforge_api.api.cookies import CookieNames
from webforge_api.config import Settings
from webforge_api.db.session import get_db
from webforge_api.models.enums import Role
from webforge_api.net.safe_fetch import FetchPolicy, SafeFetcher
from webforge_api.security.crypto import Crypto
from webforge_api.security.rate_limit import RateLimiter
from webforge_api.security.tokens import csrf_matches, csrf_token_for
from webforge_api.services.auth import AuthService, Principal, SessionState
from webforge_api.services.campaigns import CampaignService
from webforge_api.services.context import RequestMeta
from webforge_api.services.errors import PermissionDeniedError
from webforge_api.services.places import PlacesService
from webforge_api.services.users import UserService
from webforge_api.sources.registry import SourceRegistry
from webforge_api.sources.usage import UsageService
from webforge_api.sources.website import WebsiteVerifier

UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
CSRF_HEADER = "x-csrf-token"


def get_settings_dep(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_crypto(request: Request) -> Crypto:
    crypto: Crypto = request.app.state.crypto
    return crypto


def get_now(request: Request) -> datetime:
    clock: Callable[[], datetime] = request.app.state.clock
    return clock()


def get_rate_limiter(request: Request) -> RateLimiter:
    limiter: RateLimiter = request.app.state.rate_limiter
    return limiter


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
CryptoDep = Annotated[Crypto, Depends(get_crypto)]
DbDep = Annotated[Session, Depends(get_db)]
NowDep = Annotated[datetime, Depends(get_now)]


def client_ip(request: Request, settings: Settings) -> str | None:
    """Rightmost X-Forwarded-For hop that is not a trusted proxy; else the socket peer."""
    peer = request.client.host if request.client else None
    trusted = settings.trusted_proxies

    def is_trusted(ip: str) -> bool:
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in net for net in trusted)

    if peer is None or not is_trusted(peer):
        return peer
    forwarded = request.headers.get("x-forwarded-for", "")
    hops = [h.strip() for h in forwarded.split(",") if h.strip()]
    for hop in reversed(hops):
        if not is_trusted(hop):
            try:
                return str(ipaddress.ip_address(hop))
            except ValueError:
                return peer
    return peer


def get_request_meta(request: Request, settings: SettingsDep) -> RequestMeta:
    return RequestMeta(
        ip=client_ip(request, settings),
        user_agent=request.headers.get("user-agent"),
        request_id=getattr(request.state, "request_id", None),
    )


MetaDep = Annotated[RequestMeta, Depends(get_request_meta)]


def verify_origin(request: Request, settings: SettingsDep) -> None:
    """Reject cross-site state-changing requests (defence in depth alongside CSRF tokens)."""
    if request.method not in UNSAFE_METHODS:
        return
    origin = request.headers.get("origin")
    if origin is None:
        return  # non-browser clients; CSRF token still required for cookie sessions
    allowed = {o.rstrip("/") for o in [*settings.cors_origins, settings.app_url]}
    if origin.rstrip("/") not in allowed:
        raise PermissionDeniedError("origin_not_allowed", "Request origin is not allowed.")


def get_auth_service(
    db: DbDep, settings: SettingsDep, crypto: CryptoDep, now: NowDep, request: Request
) -> AuthService:
    return AuthService(db, settings, crypto, get_rate_limiter(request), now)


AuthDep = Annotated[AuthService, Depends(get_auth_service)]


def get_user_service(db: DbDep, crypto: CryptoDep, auth: AuthDep, now: NowDep) -> UserService:
    return UserService(db, crypto, auth, now)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]


def _authenticate(request: Request, auth: AuthService, settings: Settings) -> Principal:
    names = CookieNames.for_settings(settings)
    principal = auth.authenticate(request.cookies.get(names.access))
    if request.method in UNSAFE_METHODS:
        expected = csrf_token_for(
            principal.session.id, settings.app_secret_key.get_secret_value().encode()
        )
        if not csrf_matches(expected, request.headers.get(CSRF_HEADER)):
            raise PermissionDeniedError("csrf_failed", "Security token missing or invalid. Reload.")
    return principal


def principal_in_states(*states: SessionState) -> Callable[..., Principal]:
    """Authenticated principal whose session is in one of `states`."""

    def dependency(
        request: Request,
        auth: AuthDep,
        settings: SettingsDep,
        _origin: Annotated[None, Depends(verify_origin)],
    ) -> Principal:
        principal = _authenticate(request, auth, settings)
        if principal.state not in states:
            raise PermissionDeniedError(
                principal.state.value,
                {
                    SessionState.MFA_PENDING: "Complete two-factor verification.",
                    SessionState.MFA_ENROLLMENT_REQUIRED: "Set up two-factor authentication.",
                    SessionState.PASSWORD_CHANGE_REQUIRED: "Change your password to continue.",
                    SessionState.ACTIVE: "This action is not available now.",
                }[principal.state],
            )
        return principal

    return dependency


ANY_STATE = tuple(SessionState)


def require_roles(*roles: Role) -> Callable[..., Principal]:
    """Fully authenticated (ACTIVE) principal holding one of `roles`."""
    active = principal_in_states(SessionState.ACTIVE)

    def dependency(principal: Annotated[Principal, Depends(active)]) -> Principal:
        if principal.user.role not in roles:
            raise PermissionDeniedError("forbidden", "Your role does not allow this action.")
        return principal

    return dependency


AnyPrincipal = Annotated[Principal, Depends(principal_in_states(*ANY_STATE))]
ActivePrincipal = Annotated[Principal, Depends(principal_in_states(SessionState.ACTIVE))]
OwnerOrAdmin = Annotated[Principal, Depends(require_roles(Role.OWNER, Role.ADMIN))]
OwnerOnly = Annotated[Principal, Depends(require_roles(Role.OWNER))]


# ---------------------------------------------------------------------- Phase 02: sources


def get_registry(
    db: DbDep, settings: SettingsDep, crypto: CryptoDep, now: NowDep
) -> SourceRegistry:
    return SourceRegistry(db, settings, crypto, now)


RegistryDep = Annotated[SourceRegistry, Depends(get_registry)]


def get_usage_service(
    db: DbDep, settings: SettingsDep, now: NowDep, request: Request
) -> UsageService:
    return UsageService(db, settings, get_rate_limiter(request), now)


UsageDep = Annotated[UsageService, Depends(get_usage_service)]


def get_places_service(
    request: Request,
    db: DbDep,
    settings: SettingsDep,
    crypto: CryptoDep,
    now: NowDep,
    registry: RegistryDep,
    usage: UsageDep,
) -> PlacesService:
    policy: FetchPolicy = request.app.state.fetch_policy
    verifier = WebsiteVerifier(SafeFetcher(policy), settings.website_fetch_user_agent)
    return PlacesService(
        db, settings, crypto, registry, usage, request.app.state.connectors, verifier, now
    )


PlacesServiceDep = Annotated[PlacesService, Depends(get_places_service)]


# ---------------------------------------------------------------------- Phase 03: discovery


def get_campaign_service(
    db: DbDep, settings: SettingsDep, crypto: CryptoDep, now: NowDep
) -> CampaignService:
    return CampaignService(db, settings, crypto, now)


CampaignServiceDep = Annotated[CampaignService, Depends(get_campaign_service)]
AnyStaff = Annotated[
    Principal, Depends(require_roles(Role.OWNER, Role.ADMIN, Role.REVIEWER, Role.READ_ONLY))
]
Reviewers = Annotated[Principal, Depends(require_roles(Role.OWNER, Role.ADMIN, Role.REVIEWER))]
