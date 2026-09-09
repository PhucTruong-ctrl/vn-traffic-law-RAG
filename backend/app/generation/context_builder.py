"""Deterministic, bounded rendering of accepted legal evidence."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any


def _render(
    results: Iterable[Any],
    *,
    applied_date: date | None,
    max_chars: int,
    max_tokens: int | None,
) -> str:
    """Render unique evidence items in their deterministic retrieval order."""
    unique: dict[tuple[str, int], Any] = {}
    for item in results:
        key = (str(item.provision_id), int(item.provision_version))
        if key not in unique:
            unique[key] = item

    ordered = sorted(
        unique.values(),
        key=lambda item: (
            item.rank,
            str(item.provision_id),
            item.provision_version,
        ),
    )

    blocks: list[str] = []
    used_tokens = 0
    for item in ordered:
        effective_to = item.effective_to.isoformat() if item.effective_to else "present"
        effective = f"{item.effective_from.isoformat()}–{effective_to}"
        applied = f"; applied {applied_date.isoformat()}" if applied_date else ""
        provenance = (
            f"source={item.source_id or 'retrieval'}; page={item.page_number}; "
            f"interval={effective}{applied}"
        )

        citation = f"{item.document_number}, Điều {item.article}"
        if item.clause:
            citation += f", khoản {item.clause}"
        if item.point:
            citation += f", điểm {item.point}"

        block = (
            f"[{item.provision_id}@v{item.provision_version}] {citation} "
            f"({provenance})\n{item.text}"
        )
        tokens = len(block.split())
        if max_tokens is not None and used_tokens + tokens > max_tokens:
            continue

        candidate = "\n\n".join([*blocks, block])
        if len(candidate) > max_chars:
            continue

        blocks.append(block)
        used_tokens += tokens

    return "\n\n".join(blocks)


def build_context(
    results: Iterable[Any] | Mapping[str, Iterable[Any]],
    *,
    applied_date: date | None = None,
    max_chars: int = 12_000,
    max_tokens: int | None = None,
) -> str:
    """Render bounded evidence; mappings become explicitly labelled case sections."""
    if max_chars < 0 or (max_tokens is not None and max_tokens < 0):
        raise ValueError("budgets must be non-negative")

    if isinstance(results, Mapping):
        sections = []
        for case_id, case_results in results.items():
            rendered = _render(
                case_results,
                applied_date=applied_date,
                max_chars=max_chars,
                max_tokens=max_tokens,
            )
            sections.append(
                f"## Case {case_id}\n{rendered or '[No verified evidence for this case.]'}"
            )
        return "\n\n".join(sections)

    return _render(
        results,
        applied_date=applied_date,
        max_chars=max_chars,
        max_tokens=max_tokens,
    )


ContextBuilder = build_context
__all__ = ["ContextBuilder", "build_context"]
