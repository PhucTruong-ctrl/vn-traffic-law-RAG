"""Deterministic, bounded rendering of accepted legal evidence."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any


def build_context(
    results: Iterable[Any],
    *,
    applied_date: date | None = None,
    max_chars: int = 12_000,
    max_tokens: int | None = None,
) -> str:
    """Render unique provisions in rank order, bounded by chars and words.

    Entries carry citation, provenance, and temporal annotation so generation
    cannot lose the source details needed for answer grounding.
    """
    if max_chars < 0 or max_tokens is not None and max_tokens < 0:
        raise ValueError("budgets must be non-negative")
    unique: dict[tuple[str, int], Any] = {}
    for item in results:
        key = (str(item.provision_id), int(item.provision_version))
        if key not in unique:
            unique[key] = item
    ordered = sorted(
        unique.values(),
        key=lambda item: (item.rank, str(item.provision_id), item.provision_version),
    )
    blocks: list[str] = []
    used_tokens = 0
    for item in ordered:
        effective_to = item.effective_to.isoformat() if item.effective_to else "present"
        effective = f"{item.effective_from.isoformat()}–{effective_to}"
        applied = f"; applied {applied_date.isoformat()}" if applied_date else ""
        source = item.source_id or "retrieval"
        provenance = (
            f"source={source}; page={item.page_number}; "
            f"interval={effective}{applied}"
        )
        citation = f"{item.document_number}, Điều {item.article}"
        if item.clause:
            citation += f", khoản {item.clause}"
        if item.point:
            citation += f", điểm {item.point}"
        block = f"[{item.provision_id}@v{item.provision_version}] {citation} ({provenance})\n{item.text}"
        tokens = len(block.split())
        if max_tokens is not None and used_tokens + tokens > max_tokens:
            break
        candidate = "\n\n".join([*blocks, block])
        if len(candidate) > max_chars:
            break
        blocks.append(block)
        used_tokens += tokens
    return "\n\n".join(blocks)


# Explicit alias for callers that prefer noun phrasing.
ContextBuilder = build_context

__all__ = ["ContextBuilder", "build_context"]
