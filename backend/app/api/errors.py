"""Standard API error shape and exception handlers (doc 03 §3.28.3).

Every error response follows the contract::

    {"error": {"code": str, "message": str, "trace_id": str}}

``trace_id`` correlates the failing request across logs; it is generated per
error unless one is supplied. Handlers are registered on the FastAPI app via
:func:`register_error_handlers`.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

#: Error codes returned in the standard error shape (doc 03 §3.28.3).
VALIDATION_ERROR = "VALIDATION_ERROR"
INTERNAL_ERROR = "INTERNAL_ERROR"
UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
INVALID_CONTENT_TYPE = "INVALID_CONTENT_TYPE"
INVALID_DOCUMENT_ID = "INVALID_DOCUMENT_ID"
FILE_TOO_LARGE = "FILE_TOO_LARGE"
JOB_NOT_FOUND = "JOB_NOT_FOUND"


def _new_trace_id() -> str:
    """Return a fresh 32-hex trace id for an error response."""
    return uuid.uuid4().hex


def error_response(
    status_code: int,
    code: str,
    message: str,
    trace_id: str | None = None,
) -> JSONResponse:
    """Build a standard-shape error response (doc 03 §3.28.3)."""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "trace_id": trace_id or _new_trace_id(),
            }
        },
    )


def _validation_error_message(errors: Sequence[Any]) -> str:
    """Render pydantic/FastAPI validation errors into one readable line."""
    details = [
        f"{'.'.join(str(loc) for loc in err.get('loc', ()))}: {err.get('msg', 'invalid')}"
        for err in errors
    ]
    return "Request validation failed: " + "; ".join(details)


def register_error_handlers(app: FastAPI) -> None:
    """Register the standard error handlers on ``app``.

    * ``RequestValidationError`` -> 422 ``VALIDATION_ERROR``
    * ``HTTPException`` -> its status with the standard shape (``HTTP_ERROR``)
    * any other exception -> 500 ``INTERNAL_ERROR`` (logged with trace_id)
    """

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            422,
            VALIDATION_ERROR,
            _validation_error_message(exc.errors()),
        )

    @app.exception_handler(HTTPException)
    async def _on_http_error(request: Request, exc: HTTPException) -> JSONResponse:
        return error_response(exc.status_code, "HTTP_ERROR", str(exc.detail))

    @app.exception_handler(Exception)
    async def _on_internal_error(request: Request, exc: Exception) -> JSONResponse:
        trace_id = _new_trace_id()
        logger.exception(
            "unhandled error trace_id=%s method=%s path=%s",
            trace_id,
            request.method,
            request.url.path,
        )
        return error_response(
            500,
            INTERNAL_ERROR,
            "Internal server error.",
            trace_id=trace_id,
        )
