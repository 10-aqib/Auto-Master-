"""Public, unauthenticated endpoints (Phase 09): provider webhooks and one-click unsubscribe.

Webhooks require a valid HMAC signature within the freshness window and are deduplicated by event ID.
Unsubscribe needs only the unguessable token from the message; it never shows or accepts an email address.
"""

from __future__ import annotations

import html
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse

from webforge_api.api.deps import CryptoDep, DbDep, NowDep, SettingsDep, client_ip, get_rate_limiter
from webforge_api.security.rate_limit import RateLimiter, RateLimiterUnavailableError
from webforge_api.services import outreach
from webforge_api.services.email.provider import EmailProvider
from webforge_api.services.errors import NotFoundError, RateLimitedError, ServiceError

router = APIRouter(include_in_schema=True, tags=["public"])
MAX_WEBHOOK_BYTES = 1_000_000
PAGE_HEADERS = {
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
    "X-Frame-Options": "DENY",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
}


def _limit(request: Request, limiter: RateLimiter, settings: Any, bucket: str, limit: int) -> None:
    try:
        ok = limiter.hit(f"{bucket}:{client_ip(request, settings)}", limit=limit, window_seconds=60)
    except RateLimiterUnavailableError:
        ok = False
    if not ok:
        raise RateLimitedError("rate_limited", "Too many requests.")


def _provider(request: Request, name: str) -> EmailProvider:
    provider: EmailProvider = request.app.state.email_provider
    if provider.name != name:
        raise NotFoundError("not_found", "Unknown provider.")
    return provider


async def _body(request: Request) -> bytes:
    raw = await request.body()
    if len(raw) > MAX_WEBHOOK_BYTES:
        raise ServiceError("payload_too_large", "Payload too large.", status_code=413)
    return raw


Limiter = Annotated[RateLimiter, Depends(get_rate_limiter)]


@router.post("/webhooks/email/{provider_name}/events")
async def email_events(provider_name: str, request: Request, db: DbDep, settings: SettingsDep, crypto: CryptoDep, now: NowDep,
                       limiter: Limiter) -> dict[str, int]:  # fmt: skip
    _limit(request, limiter, settings, "webhook", 600)
    provider = _provider(request, provider_name)
    raw = await _body(request)
    return outreach.process_events(
        db, settings, crypto, provider, headers=dict(request.headers), raw=raw, now=now
    )


@router.post("/webhooks/email/{provider_name}/inbound")
async def email_inbound(provider_name: str, request: Request, db: DbDep, settings: SettingsDep, crypto: CryptoDep, now: NowDep,
                        limiter: Limiter) -> dict[str, Any]:  # fmt: skip
    _limit(request, limiter, settings, "webhook", 600)
    provider = _provider(request, provider_name)
    raw = await _body(request)
    reply = outreach.process_inbound(
        db, settings, crypto, provider, headers=dict(request.headers), raw=raw, now=now
    )
    return {"accepted": True, "duplicate": reply is None}


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    doc = (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">'
           f"<title>{html.escape(title)}</title><style>body{{font:16px/1.6 system-ui,sans-serif;max-width:34rem;margin:3rem auto;padding:0 1rem;color:#111}}"
           f"button{{font:inherit;padding:.6rem 1.2rem;min-height:44px;border-radius:8px;border:1px solid #111;background:#111;color:#fff;cursor:pointer}}</style>"
           f"</head><body><h1>{html.escape(title)}</h1>{body}</body></html>")  # fmt: skip
    return HTMLResponse(doc, status_code=status, headers=PAGE_HEADERS)


@router.get("/u/{token}", include_in_schema=False)
def unsubscribe_page(
    token: str, request: Request, settings: SettingsDep, limiter: Limiter
) -> Response:
    """Shows a confirmation button. GET never changes state (link scanners prefetch URLs)."""
    _limit(request, limiter, settings, "unsubscribe", 30)
    safe = html.escape(token, quote=True)
    return _page("Unsubscribe", f'<p>Stop receiving messages from {html.escape(settings.email_from_name)}?</p>'
                 f'<form method="post" action="/u/{safe}"><button type="submit">Unsubscribe</button></form>')  # fmt: skip


@router.post("/u/{token}", include_in_schema=False)
def unsubscribe(
    token: str,
    request: Request,
    db: DbDep,
    crypto: CryptoDep,
    settings: SettingsDep,
    now: NowDep,
    limiter: Limiter,
) -> Response:
    """Form submission and RFC 8058 one-click (List-Unsubscribe-Post) both land here."""
    _limit(request, limiter, settings, "unsubscribe", 30)
    if outreach.unsubscribe(db, crypto, token=token, now=now):
        return _page(
            "You are unsubscribed",
            "<p>You will not receive any further messages. No other action is needed.</p>",
        )
    return _page("Link not recognised", "<p>This unsubscribe link is not valid. Reply to the message with the word "
                 "&ldquo;unsubscribe&rdquo; and it will be honoured.</p>", status=404)  # fmt: skip
