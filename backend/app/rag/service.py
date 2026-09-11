"""Retrieval and grounded answer orchestration."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

from langchain_core.documents import Document

from .evidence import assess_evidence
from .generator import generate_answer
from .retrieval import Retriever


def _citation(document: Document) -> dict[str, Any]:
    metadata = document.metadata
    source_file = metadata.get("source_file") or metadata.get("source")
    return {
        "document": metadata.get("document_name")
        or metadata.get("document_number")
        or "Văn bản pháp luật",
        "article": metadata.get("article"),
        "clause": metadata.get("clause"),
        "point": metadata.get("point"),
        "page": metadata.get("page") or metadata.get("page_number") or 1,
        "source_file": source_file or "unknown",
        "excerpt": document.page_content,
        "pdf_url": metadata.get("pdf_url"),
    }


class RAGService:
    """Retrieval and grounded answer orchestration."""

    def __init__(self, retriever: Retriever | None = None) -> None:
        self.retriever = retriever or Retriever()

    def retrieve(
        self, question: str, *, top_k: int = 5, effective_date: date | None = None
    ) -> list[Document]:
        return self.retriever.retrieve(question, top_k=top_k, effective_date=effective_date)

    def answer(
        self,
        question: str,
        *,
        chunks: Iterable[Document] | None = None,
        top_k: int = 5,
        effective_date: date | None = None,
        history: Iterable[dict[str, Any]] = (),
    ) -> dict[str, Any]:
        documents = (
            list(chunks)
            if chunks is not None
            else self.retrieve(question, top_k=top_k, effective_date=effective_date)
        )
        decision = assess_evidence(documents)
        if not decision.allowed:
            return {
                "answer": decision.message or "",
                "citations": [],
                "status": "insufficient_evidence",
            }
        answer = generate_answer(question, documents)
        return {
            "answer": answer,
            "citations": [_citation(document) for document in documents],
            "status": "complete",
        }


__all__ = ["RAGService"]
