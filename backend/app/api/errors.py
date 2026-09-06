"""Standard API error shape and exception handlers."""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

VALIDATION_ERROR = "VALIDATION_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"
UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
INVALID_CONTENT_TYPE = "INVALID_CONTENT_TYPE"
INVALID_DOCUMENT_ID = "INVALID_DOCUMENT_ID"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
JOB_NOT_FOUND = "JOB_NOT_FOUND"
ABSTENTION = "ABSTENTION"
NOT_FOUND = "NOT_FOUND"


class ProviderError(Exception):
    """Raised when an upstream provider cannot safely answer."""


class APIError(Exception):
    """Application error carrying a standard API code and status."""

    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def new_trace_id() -> str:
    return uuid.uuid4().hex


def error_response(
    status_code: int,
    code: str,
    message: str,
    trace_id: str | None = None,
) -> JSONResponse:
    trace = trace_id or new_trace_id()
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "trace_id": trace}},
        headers={"X-Trace-ID": trace},
    )


def _validation_error_message(errors: Sequence[Any]) -> str:
    details = [
        f"{'.'.join(str(loc) for loc in err.get('loc', ()))}: {err.get('msg', 'invalid')}"
        for err in errors
    ]
    return "Request validation failed: " + "; ".join(details)


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            422,
            VALIDATION_ERROR,
            _validation_error_message(exc.errors()),
            request.headers.get("X-Trace-ID"),
        )

    @app.exception_handler(APIError)
    async def api_error_handler(request: Request, exc: APIError) -> JSONResponse:
        return error_response(
            exc.status_code,
            exc.code,
            str(exc),
            request.headers.get("X-Trace-ID"),
        )

    @app.exception_handler(ProviderError)
    async def provider_error_handler(request: Request, exc: ProviderError) -> JSONResponse:
        return error_response(
            502,
            "PROVIDER_ERROR",
            str(exc),
            request.headers.get("X-Trace-ID"),
        )

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        code = NOT_FOUND if exc.status_code == 404 else "HTTP_ERROR"
        return error_response(
            exc.status_code,
            code,
            str(exc.detail),
            request.headers.get("X-Trace-ID"),
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception) -> JSONResponse:
        trace_id = request.headers.get("X-Trace-ID") or new_trace_id()
        logger.exception("unhandled error trace_id=%s", trace_id)
        return error_response(500, INTERNAL_ERROR, "Internal server error", trace_id)
