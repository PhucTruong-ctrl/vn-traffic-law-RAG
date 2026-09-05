import pytest

from app.security import redact_sensitive, security_headers, validate_request_size


def test_redact_sensitive_values():
    text = "api_key=abc123 token: secret-token password=hunter2 ordinary=value"

    redacted = redact_sensitive(text)

    assert "abc123" not in redacted
    assert "secret-token" not in redacted
    assert "hunter2" not in redacted
    assert redacted.count("[REDACTED]") == 3
    assert "ordinary=value" in redacted


def test_security_headers_are_safe_defaults():
    assert security_headers() == {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Content-Security-Policy": "default-src 'none'",
    }


def test_validate_request_size_allows_boundary_and_unknown_length():
    validate_request_size(1_048_576)
    validate_request_size(None)

    with pytest.raises(ValueError):
        validate_request_size(1_048_577)
