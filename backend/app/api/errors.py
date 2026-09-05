"""Standard API error taxonomy, trace propagation, and exception handlers."""

from __future__ import annotations
…
from fastapi.responses import JSONResponse

from app.security import redact_sensitive

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
…
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
…
) -> JSONResponse:
    """Build the only error payload shape exposed by the API."""
…
    return response


def _validation_error_message(errors: Sequence[Any]) -> str:
    details = [
…
    return "Request validation failed: " + "; ".join(details)


def register_error_handlers(app: FastAPI) -> None:
    """Register safe handlers; abstentions are never treated as system errors."""
…
        return error_response(500, INTERNAL_ERROR, "Internal server error.", trace_id=trace_id)