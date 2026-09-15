"""Retrieval must degrade to the local sparse index instead of returning nothing."""

from __future__ import annotations

from time import sleep, time
from typing import Any

import pytest
from langchain_core.documents import Document

from app.rag.retrieval import RetrievalProviderError, Retriever
from app.rag.service import RAGService


class _Store:
    """Hybrid store stub whose dense search fails the way a throttled provider does."""

    def __init__(self, *, error: Exception | None = None) -> None:
        self.client = object()
        self.collection_name = "traffic_law"
        self.error = error
        self.searched: list[str] = []

    def similarity_search(self, question: str, k: int) -> list[Document]:
        self.searched.append(question)
        if self.error is not None:
            raise self.error
        return [
            Document("Từ điển hybrid", metadata={"chunk_id": "hybrid-1", "document_id": "nd-1"})
        ]


def _retriever_with(store: _Store, sparse_documents: list[Document]) -> Retriever:
    retriever = Retriever()
    retriever._store = store
    retriever._sparse_embeddings = object()
    retriever._client = object()
    retriever._sparse_search = lambda question, limit: sparse_documents  # type: ignore[method-assign]
    return retriever


def test_dense_provider_failure_uses_sparse_index() -> None:
    store = _Store(error=RuntimeError("provider timeout"))
    sparse_documents = [
        Document("Điều 6. Không đội mũ bảo hiểm.", metadata={"chunk_id": "sparse-1"})
    ]
    retriever = _retriever_with(store, sparse_documents)
    documents = retriever.retrieve("không đội mũ bảo hiểm", top_k=3)

    assert [document.metadata["chunk_id"] for document in documents] == ["sparse-1"]


def test_no_documents_from_any_path_is_reported_as_provider_failure() -> None:
    store = _Store(error=RuntimeError("provider timeout"))
    retriever = _retriever_with(store, [])

    with pytest.raises(RetrievalProviderError):
        retriever.retrieve("không đội mũ bảo hiểm", top_k=3)


class _SlowRetriever:
    """First query hangs past the deadline, the second answers immediately."""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.started = 0

    def retrieve(
        self, question: str, *, top_k: int = 5, effective_date: Any = None
    ) -> list[Document]:
        self.started += 1
        if "treo" in question:
            sleep(2.0)
        if self.fail:
            raise RetrievalProviderError("provider down")
        return [
            Document(
                f"Kết quả cho {question}", metadata={"chunk_id": "doc-1", "document_id": "nd-1"}
            )
        ]


def test_fusion_keeps_results_that_arrive_before_the_deadline() -> None:
    service = RAGService(_SlowRetriever())
    started = time()
    documents = service._search_and_fuse(
        [("treo máy", "treo"), ("nhanh", "nhanh")],
        top_k=3,
        effective_date=None,
        deadline=service.clock() + 0.3,
    )
    elapsed = time() - started

    assert documents, "the fast query result must survive the slow one"
    assert elapsed < 1.5, f"fusion waited for the hanging query: {elapsed:.1f}s"


def test_fusion_reports_provider_failure_instead_of_empty_evidence() -> None:
    service = RAGService(_SlowRetriever(fail=True))

    with pytest.raises(RetrievalProviderError):
        service._search_and_fuse(
            [("a", "a"), ("b", "b")], top_k=3, effective_date=None, deadline=None
        )
