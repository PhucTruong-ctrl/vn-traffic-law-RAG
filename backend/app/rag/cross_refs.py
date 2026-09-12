"""Bounded deterministic cross-reference extraction and expansion."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from .references import LegalReference, extract_references


def extract_cross_references(text: str, *, limit: int = 4) -> list[LegalReference]:
    return extract_references(text, limit=min(limit, 4))


def expand_sibling_completions(
    documents: Iterable[Any],
    resolver: Callable[..., Iterable[Any]],
    *,
    max_documents: int | None = None,
    max_siblings: int = 2,
) -> list[Any]:
    """Attach bounded sanction-completion siblings while preserving originals."""
    originals = list(documents)
    if max_documents is None:
        max_documents = len(originals) + len(originals) * max_siblings
    if max_documents < 0:
        raise ValueError("max_documents must be non-negative")
    originals = originals[:max_documents]
    if max_siblings < 1 or len(originals) >= max_documents:
        return originals
    result = list(originals)
    seen = {_identity(document) for document in originals}
    for original in originals:
        remaining = max_documents - len(result)
        if not remaining:
            break
        source_id = _source_id(original)
        try:
            siblings = resolver(original, limit=min(max_siblings, remaining))
        except TypeError:
            siblings = resolver(original)
        added = 0
        for sibling in siblings:
            if added >= max_siblings or len(result) >= max_documents:
                break
            identity = _identity(sibling)
            if identity in seen:
                continue
            seen.add(identity)
            result.append(_with_provenance(sibling, source_id, "SIBLING", 0))
            added += 1
    return result


def _with_provenance(document: Any, source_id: str, added_by: str, depth: int) -> Any:
    metadata = dict(getattr(document, "metadata", {}) or {})
    metadata.update(added_by=added_by, depth=depth, source_id=source_id)
    try:
        return document.__class__(
            page_content=getattr(document, "page_content", ""),
            metadata=metadata,
        )
    except (TypeError, AttributeError):
        return _DocumentLikeClone(document, metadata)


def expand_cross_references(
    documents: Iterable[Any],
    resolver: Callable[..., Iterable[Any]],
    *,
    max_depth: int = 1,
    max_references: int = 4,
    max_documents: int | None = None,
) -> list[Any]:
    """Return originals plus one bounded expansion hop; never recurse beyond depth 1."""
    originals = list(documents)
    if max_documents is None:
        max_documents = len(originals) + max_references
    if max_documents < 0:
        raise ValueError("max_documents must be non-negative")
    originals = originals[:max_documents]
    if max_depth < 1 or max_references < 1 or not originals:
        return originals
    expanded: list[Any] = []
    references: list[LegalReference] = []
    seen = {_identity(document) for document in originals}
    reference_sources: dict[LegalReference, str] = {}
    for document in originals:
        text = str(getattr(document, "page_content", document))
        for reference in extract_cross_references(text, limit=max_references):
            if reference not in references:
                references.append(reference)
                reference_sources[reference] = _source_id(document)
            if len(references) >= max_references:
                break
        if len(references) >= max_references:
            break
    remaining = max_documents - len(originals)
    per_reference_limit = max(1, remaining) if remaining else 0
    for reference in references:
        if not remaining:
            break
        try:
            resolved = resolver(reference, limit=per_reference_limit)
        except TypeError:
            resolved = resolver(reference)
        for document in resolved:
            identity = _identity(document)
            if identity not in seen:
                seen.add(identity)
                expanded.append(
                    _with_provenance(
                        document,
                        reference_sources.get(reference, ""),
                        "CROSS_REFERENCE",
                        1,
                    )
                )
                remaining -= 1
                if not remaining:
                    break
    return originals + expanded


def _identity(document: Any) -> tuple[str, str]:
    metadata = getattr(document, "metadata", {}) or {}
    chunk_id = str(metadata.get("chunk_id", "")).strip()
    if chunk_id:
        return "chunk_id", chunk_id
    source = metadata.get("source_file") or metadata.get("source") or ""
    content = getattr(document, "page_content", "")
    return str(source), str(content)


def _source_id(document: Any) -> str:
    metadata = getattr(document, "metadata", {}) or {}
    return str(
        metadata.get("chunk_id") or metadata.get("source_file") or metadata.get("source") or ""
    )


class _DocumentLikeClone:
    def __init__(self, document: Any, metadata: dict[str, Any]) -> None:
        self.page_content = getattr(document, "page_content", "")
        self.metadata = metadata


__all__ = [
    "expand_cross_references",
    "expand_sibling_completions",
    "extract_cross_references",
]
