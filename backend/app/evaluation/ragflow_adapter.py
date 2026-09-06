"""Deterministic RAGFlow citation to canonical provision-ID mapping."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

_ID = re.compile(
    r"^(?P<doc>[a-z0-9-]+):(?P<kind>article|clause|point):(?P<num>[\w.-]+)$", re.I
)


@dataclass(frozen=True, slots=True)
class CitationMetadata:
    """The complete, caller-supplied identity of one RAGFlow citation."""

    document_id: str
    page: int | None
    span: str | None
    text: str | None
    content_hash: str | None
    effective_from: str | None
    effective_to: str | None

    @classmethod
    def from_citation(cls, citation: Mapping[str, Any]) -> "CitationMetadata | None":
        document_id = citation.get("document_id")
        if not isinstance(document_id, str) or not document_id:
            return None
        page = citation.get("page", citation.get("page_number"))
        if page is not None and not isinstance(page, int):
            return None
        values = {}
        for field in ("span", "text", "content_hash", "effective_from", "effective_to"):
            value = citation.get(field)
            if value is not None and not isinstance(value, str):
                return None
            values[field] = value
        return cls(document_id, page, **values)


@dataclass(frozen=True, slots=True)
class CitationResolution:
    """Resolved citations retain the original metadata and canonical ID."""

    mapped: list[dict[str, Any]]
    unmappable: int
    mapping_accuracy: float | None


def resolve_citation(
    citation: Mapping[str, Any],
    metadata_map: Mapping[CitationMetadata, str],
) -> dict[str, Any] | None:
    """Resolve only an exact explicit metadata key; otherwise fail closed."""

    metadata = CitationMetadata.from_citation(citation)
    if metadata is None:
        return None
    provision_id = metadata_map.get(metadata)
    if not isinstance(provision_id, str) or not provision_id:
        return None
    return {**dict(citation), "canonical_provision_id": provision_id}


def resolve_citations(
    citations: Sequence[Mapping[str, Any]],
    metadata_map: Mapping[CitationMetadata, str],
) -> CitationResolution:
    """Resolve RAGFlow citations from an explicit metadata-to-ID manifest."""

    mapped = [
        resolved
        for citation in citations
        if (resolved := resolve_citation(citation, metadata_map)) is not None
    ]
    unmappable = len(citations) - len(mapped)
    return CitationResolution(
        mapped=mapped,
        unmappable=unmappable,
        mapping_accuracy=len(mapped) / len(citations) if citations else None,
    )


def map_citation(citation: Mapping[str, Any], canonical_ids: set[str]) -> str | None:
    """Map only an exact canonical ID; never guess."""
    value = (
        citation.get("canonical_provision_id")
        or citation.get("provision_id")
        or citation.get("id")
    )
    if not isinstance(value, str):
        return None
    if value in canonical_ids:
        return value
    match = _ID.fullmatch(value)
    normalized = match.group(0).lower() if match else value
    return normalized if normalized in canonical_ids else None


def map_citations(
    citations: Sequence[Mapping[str, Any]], canonical_ids: set[str]
) -> dict[str, Any]:
    mapped = [x for c in citations if (x := map_citation(c, canonical_ids)) is not None]
    unmappable = len(citations) - len(mapped)
    return {
        "mapped": mapped,
        "unmappable": unmappable,
        "mapping_accuracy": len(mapped) / len(citations) if citations else None,
    }


__all__ = [
    "CitationMetadata",
    "CitationResolution",
    "map_citation",
    "map_citations",
    "resolve_citation",
    "resolve_citations",
]
