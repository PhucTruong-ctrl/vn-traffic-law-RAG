"""Standard API error taxonomy, trace propagation, and exception handlers."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from contextvars import ContextVar
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

VALIDATION_ERROR = "VALIDATION_ERROR"
NOT_FOUND = "NOT_FOUND"
JOB_NOT_FOUND = "JOB_NOT_FOUND"
PROVIDER_ERROR = "PROVIDER_ERROR"
ABSTENTION = "ABSTENTION"
INTERNAL_ERROR = "INTERNAL_ERROR"
UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
INVALID_CONTENT_TYPE = "INVALID_CONTENT_TYPE"
INVALID_DOCUMENT_ID = "INVALID_DOCUMENT_ID"
FILE_TOO_LARGE = "FILE_TOO_LARGE"

_TRACE_ID: ContextVar[str | None] = ContextVar("api_trace_id", default=None)


class APIError(Exception):
    """Expected, safe-to-return API failure."""

    status_code = 500
    code = INTERNAL_ERROR

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code


class NotFoundError(APIError):
    status_code = 404
    code = NOT_FOUND


class ProviderError(APIError):
    status_code = 502
    code = PROVIDER_ERROR


def new_trace_id() -> str:
    """Return a fresh request correlation id."""
    return uuid.uuid4().hex


def current_trace_id() -> str | None:
    return _TRACE_ID.get()


def set_trace_id(trace_id: str | None) -> None:
    _TRACE_ID.set(trace_id)


def error_response(
    status_code: int,
    code: str,
    message: str,
    trace_id: str | None = None,
) -> JSONResponse:
    """Build the only error payload shape exposed by the API."""
    correlation_id = trace_id or current_trace_id() or new_trace_id()
    response = JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "trace_id": correlation_id}},
    )
    response.headers["X-Trace-ID"] = correlation_id
    return response


def _validation_error_message(errors: Sequence[Any]) -> str:
    details = [
        f"{'.'.join(str(loc) for loc in err.get('loc', ()))}: {err.get('msg', 'invalid')}"
        for err in errors
    ]
    return "Request validation failed: " + "; ".join(details)


def register_error_handlers(app: FastAPI) -> None:
    """Register safe handlers; abstentions are never treated as system errors."""

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(422, VALIDATION_ERROR, _validation_error_message(exc.errors()))

    @app.exception_handler(APIError)
    async def _on_api_error(request: Request, exc: APIError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message)

    @app.exception_handler(HTTPException)
    async def _on_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        code = NOT_FOUND if exc.status_code == 404 else "HTTP_ERROR"
        return error_response(exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _on_internal_error(request: Request, exc: Exception) -> JSONResponse:
        trace_id = current_trace_id() or new_trace_id()
        logger.exception(
            "unhandled error trace_id=%s method=%s path=%s",
            trace_id,
            request.method,
            request.url.path,
        )
        return error_response(500, INTERNAL_ERROR, "Internal server error.", trace_id=trace_id)
