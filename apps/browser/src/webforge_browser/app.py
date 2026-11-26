"""Sandbox HTTP API (listens only on the internal sandbox network)."""

from __future__ import annotations

import asyncio
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from webforge_browser import __version__
from webforge_browser.auditor import Limits, run_audit
from webforge_browser.pdf import render_pdf
from webforge_browser.selftest import run_selftest
from webforge_browser.validator import VIEWPORTS, run_validation

PROXY = os.environ.get("EGRESS_PROXY_URL")  # e.g. http://egress-proxy:3128
app = FastAPI(
    title="WEBFORGE browser sandbox",
    version=__version__,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
_slot = asyncio.Semaphore(int(os.environ.get("BROWSER_CONCURRENCY", "1")))


class AuditRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=8, max_length=2048, pattern=r"^https?://")
    max_pages: int = Field(default=10, ge=1, le=20)
    max_depth: int = Field(default=2, ge=0, le=3)
    page_timeout_s: float = Field(default=30, gt=0, le=60)
    total_timeout_s: float = Field(default=300, gt=0, le=600)
    user_agent: str = Field(default="WEBFORGE-AI-Audit/0.1", max_length=200)


class ValidateRequest(BaseModel):
    """Validate one concept page (all other pages are needed to check navigation). Fully offline."""

    model_config = ConfigDict(extra="forbid")

    pages: dict[str, str] = Field(min_length=1, max_length=12)
    slug: str = Field(pattern=r"^[a-z]{2,20}$")
    viewports: list[str] = Field(
        default_factory=lambda: list(VIEWPORTS), min_length=1, max_length=3
    )


class PdfRequest(BaseModel):
    """Render a self-contained proposal document to PDF. Fully offline."""

    model_config = ConfigDict(extra="forbid")

    html: str = Field(min_length=20, max_length=60_000_000)
    footer_notice: str = Field(min_length=1, max_length=200)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/selftest")
async def selftest() -> dict[str, Any]:
    return await run_selftest(PROXY)


@app.post("/audit")
async def audit(body: AuditRequest) -> dict[str, Any]:
    if not PROXY and os.environ.get("ALLOW_NO_PROXY") != "1":
        raise HTTPException(503, "Egress proxy not configured; refusing to browse.")
    limits = Limits(
        max_pages=body.max_pages,
        max_depth=body.max_depth,
        page_timeout_s=body.page_timeout_s,
        total_timeout_s=body.total_timeout_s,
        user_agent=body.user_agent,
    )
    async with _slot:
        try:
            return await asyncio.wait_for(
                run_audit(body.url, limits, PROXY), body.total_timeout_s + 30
            )
        except TimeoutError as exc:
            raise HTTPException(504, "Audit exceeded its time limit.") from exc


@app.post("/validate")
async def validate(body: ValidateRequest) -> dict[str, Any]:
    if body.slug not in body.pages or any(v not in VIEWPORTS for v in body.viewports):
        raise HTTPException(422, "Unknown page or viewport.")
    if any(len(html) > 300_000 for html in body.pages.values()) or any(
        not k.isalpha() for k in body.pages
    ):
        raise HTTPException(413, "Page too large or invalid page key.")
    async with _slot:
        try:
            return await asyncio.wait_for(
                run_validation(body.pages, body.slug, body.viewports), 120
            )
        except TimeoutError as exc:
            raise HTTPException(504, "Validation exceeded its time limit.") from exc


@app.post("/pdf")
async def pdf(body: PdfRequest) -> Response:
    async with _slot:
        try:
            data, blocked = await asyncio.wait_for(render_pdf(body.html, body.footer_notice), 180)
        except TimeoutError as exc:
            raise HTTPException(504, "PDF rendering exceeded its time limit.") from exc
    return Response(
        data,
        media_type="application/pdf",
        headers={"X-Blocked-Requests": str(len(blocked)), "Cache-Control": "no-store"},
    )
