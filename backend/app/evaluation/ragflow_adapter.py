"""Deterministic RAGFlow citation to canonical provision-ID mapping."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_ID = re.compile(r"^(?P<doc>[a-z0-9-]+):(?P<kind>article|clause|point):(?P<num>[\w.-]+)$", re.I)

def map_citation(citation: Mapping[str, Any], canonical_ids: set[str]) -> str | None:
    """Map only an exact canonical ID or an exact structured citation; never guess."""
    value = citation.get("canonical_provision_id") or citation.get("provision_id") or citation.get("id")
    if not isinstance(value, str):
        return None
    if value in canonical_ids:
        return value
    match = _ID.fullmatch(value)
    normalized = match.group(0).lower() if match else value
    return normalized if normalized in canonical_ids else None

def map_citations(citations: Sequence[Mapping[str, Any]], canonical_ids: set[str]) -> dict[str, Any]:
    mapped = [x for c in citations if (x := map_citation(c, canonical_ids)) is not None]
    unmappable = len(citations) - len(mapped)
    return {"mapped": mapped, "unmappable": unmappable, "mapping_accuracy": len(mapped) / len(citations) if citations else None}

__all__ = ["map_citation", "map_citations"]
