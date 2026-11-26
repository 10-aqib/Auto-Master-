"""Auth cookie names and attributes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import Response

from webforge_api.config import Settings
from webforge_api.services.auth import IssuedTokens


@dataclass(frozen=True)
class CookieNames:
    access: str
    refresh: str
    csrf: str

    @classmethod
    def for_settings(cls, settings: Settings) -> CookieNames:
        # __Host- prefix: browser enforces Secure, Path=/ and no Domain attribute.
        prefix = "__Host-" if settings.cookie_secure else ""
        return cls(access=f"{prefix}wf_at", refresh=f"{prefix}wf_rt", csrf=f"{prefix}wf_csrf")


def _max_age(until: datetime, now: datetime) -> int:
    return max(0, int((until - now).total_seconds()))


def set_auth_cookies(
    response: Response, tokens: IssuedTokens, settings: Settings, now: datetime
) -> None:
    names = CookieNames.for_settings(settings)
    common = {"secure": settings.cookie_secure, "samesite": "lax", "path": "/"}
    response.set_cookie(
        names.access,
        tokens.access_token,
        max_age=_max_age(tokens.access_expires_at, now),
        httponly=True,
        **common,  # type: ignore[arg-type]
    )
    if tokens.refresh_token is not None:
        response.set_cookie(
            names.refresh,
            tokens.refresh_token,
            max_age=_max_age(tokens.session.refresh_expires_at, now),
            httponly=True,
            **common,  # type: ignore[arg-type]
        )
    # Readable by the dashboard's JavaScript so it can echo it in X-CSRF-Token.
    response.set_cookie(
        names.csrf,
        tokens.csrf_token,
        max_age=_max_age(tokens.session.absolute_expires_at, now),
        httponly=False,
        **common,  # type: ignore[arg-type]
    )


def clear_auth_cookies(response: Response, settings: Settings) -> None:
    names = CookieNames.for_settings(settings)
    for name in (names.access, names.refresh, names.csrf):
        response.delete_cookie(name, path="/", secure=settings.cookie_secure, samesite="lax")
