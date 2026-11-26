"""Stable error envelope: {code, message, correlation_id, field_errors}."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from webforge_api.logging_config import get_logger
from webforge_api.services.errors import ServiceError

log = get_logger(__name__)

_HTTP_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
}


def error_body(
    request: Request,
    code: str,
    message: str,
    field_errors: dict[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "correlation_id": getattr(request.state, "request_id", None),
        "field_errors": field_errors or {},
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError) -> JSONResponse:
        headers = {"Retry-After": "60"} if exc.status_code == 429 else None
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(request, exc.code, exc.message, exc.field_errors),
            headers=headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo submitted values (they may be passwords or personal data).
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", ()) if p not in ("body", "query", "path")]
            fields[".".join(loc) or "request"] = str(err.get("msg", "Invalid value"))
        return JSONResponse(
            status_code=422,
            content=error_body(request, "validation_error", "Some fields are invalid.", fields),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = _HTTP_CODES.get(exc.status_code, "error")
        message = exc.detail if isinstance(exc.detail, str) else code.replace("_", " ").capitalize()
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(request, code, message),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_error", error_type=type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content=error_body(request, "internal_error", "Something went wrong."),
        )
