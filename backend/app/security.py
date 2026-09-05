"""Small, dependency-free security helpers for request-boundary checks."""

from __future__ import annotations

import hashlib
import hmac
import re
from collections.abc import Mapping
from pathlib import PurePosixPath

_ADMIN_TOKEN_HEADER = "x-admin-token"
_TOKEN_RE = re.compile(r"^[^\s]{16,}$")


def admin_token_is_valid(headers: Mapping[str, str], expected: str) -> bool:
    """Compare an admin token in constant time, rejecting malformed config/input."""
    supplied = headers.get(_ADMIN_TOKEN_HEADER, "")
    if not expected or not _TOKEN_RE.fullmatch(expected) or not _TOKEN_RE.fullmatch(supplied):
        return False
    return hmac.compare_digest(
        hashlib.sha256(supplied.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    )


def safe_upload_name(name: str) -> bool:
    """Accept only a basename ending in PDF; reject traversal and separators."""
    if not name or name != PurePosixPath(name).name or "\\" in name:
        return False
    return name.lower().endswith(".pdf") and name not in {".", ".."}
