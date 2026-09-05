"""Pure helpers for redacting secrets and validating request boundaries."""

from __future__ import annotations

import re


_SENSITIVE_VALUE = r"(?:[^\s,;]+|\"[^\"]*\"|'[^']*')"
_SENSITIVE_PATTERN = re.compile(
    rf"(?P<label>api[-_ ]?key|access[-_ ]?token|auth(?:orization)?|bearer|token|password)"
    rf"(?P<separator>\s*(?:[:=]|is)\s*|\s+)"
    rf"(?P<value>{_SENSITIVE_VALUE})",
    re.IGNORECASE,
)


def redact_sensitive(text: str) -> str:
    """Replace common API-key, token, and password values with a marker."""
    return _SENSITIVE_PATTERN.sub(
        lambda match: f"{match.group('label')}{match.group('separator')}[REDACTED]",
        text,
    )


def security_headers() -> dict[str, str]:
    """Return conservative response headers for integration by the web layer."""
    return {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'",
    }


def validate_request_size(content_length: int | None, max_bytes: int = 1_048_576) -> None:
    """Reject known request sizes above the configured maximum."""
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")
    if content_length is not None and (content_length < 0 or content_length > max_bytes):
        raise ValueError("request body exceeds the maximum allowed size")
