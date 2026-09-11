"""Bounded deterministic cross-reference extraction and expansion."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .references import LegalReference, extract_references


def extract_cross_references(text: str, *, limit: int = 4) -> list[LegalReference]:
    return extract_references(text, limit=min(limit, 4))


def expand_cross_references(
    documents: Iterable[Any],
    resolver: Callable[[LegalReference], Iterable[Any]],
    *,
    max_depth: int = 1,
    max_references: int = 4,
) -> list[Any]:
    """Return originals plus one bounded expansion hop; never recurse beyond depth 1."""
    originals = list(documents)
    if max_depth < 1 or max_references < 1:
        return originals
    expanded: list[Any] = []
    seen = {_identity(document) for document in originals}
    references: list[LegalReference] = []
    for document in originals:
        text = str(getattr(document, "page_content", document))
        for reference in extract_cross_references(text, limit=max_references):
            if reference not in references:
                references.append(reference)
            if len(references) >= max_references:
                break
        if len(references) >= max_references:
            break
    for reference in references:
        for document in resolver(reference):
            identity = _identity(document)
            if identity not in seen:
                seen.add(identity)
                expanded.append(document)
    return originals + expanded


def _identity(document: Any) -> tuple[str, str]:
    metadata = getattr(document, "metadata", {}) or {}
    source = metadata.get("source_file") or metadata.get("source") or ""
    content = getattr(document, "page_content", "")
    return str(source), str(content)


__all__ = ["expand_cross_references", "extract_cross_references"]
