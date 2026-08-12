"""Content-hash helpers for document versions and provisions (VNLRAG-39).

Every ``DocumentVersion`` and ``LegalProvision`` row carries a required
``content_hash`` (doc 03 §3.9.3/§3.9.4). Digests are deterministic
``sha256`` values with the same ``sha256:`` prefix used by
``LegalDocument.file_hash``.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

_PREFIX = "sha256:"


def content_hash(content: str) -> str:
    """Return ``sha256:<hex>`` of the UTF-8 encoded content."""
    return _PREFIX + hashlib.sha256(content.encode("utf-8")).hexdigest()


def manifest_hash(manifest: Mapping[str, object]) -> str:
    """Return ``content_hash`` over the canonical JSON form of a manifest.

    ``sort_keys=True`` makes the digest independent of key insertion order,
    so the same manifest always hashes identically.
    """
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return content_hash(canonical)
