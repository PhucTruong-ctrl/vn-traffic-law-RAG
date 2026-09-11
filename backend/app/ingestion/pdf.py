"""PDF ingestion metadata adapter.

PDF text extraction/chunking remains owned by existing ingestion scripts; this
adapter only normalizes metadata consumed by legal source APIs.
"""

from __future__ import annotations

from collections.abc import Mapping
from os import PathLike
from typing import Any

from .source import normalized_metadata


def normalize_pdf_metadata(
    source_file: str | PathLike[str],
    metadata: Mapping[str, Any] | None = None,
    *,
    pdf_url: str | None = None,
    source_url: str | None = None,
) -> dict[str, Any]:
    """Return existing PDF provenance plus canonical viewer source kind."""
    normalized = normalized_metadata(
        {**(metadata or {}), "source_file": str(source_file), "source_kind": "pdf"},
        source_file=source_file,
    )
    if pdf_url is not None:
        normalized["pdf_url"] = pdf_url
    if source_url is not None:
        normalized["source_url"] = source_url
    return normalized


__all__ = ["normalize_pdf_metadata"]
