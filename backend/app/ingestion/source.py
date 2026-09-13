"""Shared source metadata normalization for legal ingestion adapters."""

from __future__ import annotations

from collections.abc import Mapping
from os import PathLike
from pathlib import PurePath
from typing import Any, Literal

SourceKind = Literal["markdown", "pdf"]


def normalize_source_kind(
    *,
    source_file: str | PathLike[str] | None = None,
    source_kind: Any = None,
    source_type: Any = None,
) -> SourceKind:
    """Return viewer-facing kind without rewriting provenance ``source_type``.

    Explicit canonical values win. Otherwise, only a PDF extension or an
    explicitly PDF-like source type selects ``pdf``; values such as
    ``secondary_html`` remain Markdown-backed sources.
    """
    if source_kind in {"markdown", "pdf"}:
        return source_kind
    suffix = PurePath(str(source_file or "")).suffix.casefold()
    if suffix == ".pdf":
        return "pdf"
    if str(source_type or "").casefold() in {"pdf", "application/pdf"}:
        return "pdf"
    return "markdown"


def normalized_metadata(
    metadata: Mapping[str, Any], *, source_file: str | PathLike[str] | None = None
) -> dict[str, Any]:
    """Copy metadata while adding canonical ``source_kind``."""
    normalized = dict(metadata)
    normalized["source_kind"] = normalize_source_kind(
        source_file=source_file or normalized.get("source_file"),
        source_kind=normalized.get("source_kind"),
        source_type=normalized.get("source_type"),
    )
    return normalized


__all__ = ["SourceKind", "normalize_source_kind", "normalized_metadata"]
