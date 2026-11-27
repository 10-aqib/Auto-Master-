"""Service-layer errors mapped to stable API error codes."""

from __future__ import annotations


class ServiceError(Exception):
    status_code = 400

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int | None = None,
        field_errors: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.field_errors = field_errors or {}


class AuthenticationError(ServiceError):
    status_code = 401


class PermissionDeniedError(ServiceError):
    status_code = 403


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class RateLimitedError(ServiceError):
    status_code = 429


class UnavailableError(ServiceError):
    status_code = 503


class ValidationFailedError(ServiceError):
    status_code = 422
