"""Dependency-light rescue chat orchestration."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date
from typing import Any

from .generator import generate_answer


def _value(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, Mapping) else getattr(item, name, default)


def _citation(item: Any) -> dict[str, Any]:
    metadata = _value(item, "metadata", {})
    if not isinstance(metadata, Mapping):
        metadata = {}

    def get(key: str) -> Any:
        return metadata.get(key, _value(item, key))

    source_file = get("source_file")
    pdf_url = get("pdf_url") or (
        f"/documents/{str(source_file).rsplit('/', 1)[-1]}" if source_file else None
    )
    excerpt = get("text") or get("source_text") or _value(item, "text", "")
    return {
        "provision_id": get("id") or get("provision_id") or source_file or "chunk",
        "document": get("document_name")
        or get("document")
        or get("document_id")
        or "Văn bản pháp luật",
        "document_number": get("document_name") or get("document_number"),
        "article": get("article"),
        "clause": get("clause"),
        "point": get("point"),
        "page": get("page") or get("page_number"),
        "page_number": get("page") or get("page_number"),
        "source_file": source_file,
        "excerpt": excerpt,
        "source_text": excerpt,
        "pdf_url": pdf_url,
    }


class RescueService:
    """Retrieve local chunks and answer without persistence or conversations."""

    def __init__(
        self, retriever: Any = None, generator: Callable[..., str] = generate_answer
    ) -> None:
        self.retriever = retriever
        self.generator = generator

    def retrieve(
        self, question: str, *, top_k: int = 5, effective_date: date | None = None
    ) -> list[Any]:
        if self.retriever is None:
            return []
        search = getattr(self.retriever, "search", None)
        if search is not None:
            result = search(question, k=top_k)
        else:
            result = self.retriever.retrieve(question, top_k=top_k, effective_date=effective_date)
        if hasattr(result, "results"):
            return list(result.results)
        return list(result or [])

    def answer(
        self,
        question: str,
        *,
        chunks: Iterable[Any] | None = None,
        top_k: int = 5,
        effective_date: date | None = None,
    ) -> dict[str, Any]:
        items = (
            list(chunks)
            if chunks is not None
            else self.retrieve(question, top_k=top_k, effective_date=effective_date)
        )
        context = "\n\n".join(
            str(_value(item, "text", _value(item, "source_text", ""))) for item in items
        )
        answer = self.generator(question, context)
        return {
            "answer": answer,
            "citations": [_citation(item) for item in items],
            "context": context,
        }


__all__ = ["RescueService"]
