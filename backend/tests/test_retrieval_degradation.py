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


def test_clause_header_outranks_other_siblings() -> None:
    """Article context comes first, then the fine-bearing clause header."""
    from app.rag.retrieval import _sibling_completion_documents

    class _ScrollClient:
        collection_name = "traffic_law"

        def scroll(self, **kwargs: Any) -> tuple[list[Any], None]:
            scroll_filter = kwargs["scroll_filter"]
            is_article = any(type(c).__name__ == "IsEmptyCondition" for c in scroll_filter.must)
            payloads = (
                [
                    _point(
                        "nd-168-2024:article:6", "Xử phạt người điều khiển ô tô.", None, clause=None
                    )
                ]
                if is_article
                else [
                    _point(
                        "nd-168-2024:0146",
                        "Điều khiển xe trên đường mà trong máu có nồng độ cồn.",
                        "a",
                    ),
                    _point(
                        "nd-168-2024:0145",
                        "Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng "
                        "đối với người điều khiển xe.",
                        None,
                    ),
                ]
            )
            return payloads, None

    class _Store:
        client = _ScrollClient()
        collection_name = "traffic_law"

    original = Document(
        "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông;",
        metadata={
            "chunk_id": "nd-168-2024:0147",
            "document_id": "nd-168-2024",
            "article": "6",
            "clause": "9",
            "point": "b",
        },
    )
    siblings = _sibling_completion_documents(_Store(), original, 2)
    assert [s.metadata["chunk_id"] for s in siblings] == [
        "nd-168-2024:article:6",
        "nd-168-2024:0145",
    ]


def test_completion_scroll_failures_are_isolated() -> None:
    from app.rag.retrieval import _sibling_completion_documents

    class _ScrollClient:
        collection_name = "traffic_law"

        def __init__(self, fail_article: bool = False, fail_clause: bool = False) -> None:
            self.fail_article = fail_article
            self.fail_clause = fail_clause

        def scroll(self, **kwargs: Any) -> tuple[list[Any], None]:
            is_article = any(
                condition.__class__.__name__ == "IsEmptyCondition"
                for condition in kwargs["scroll_filter"].must
            )
            if (is_article and self.fail_article) or (not is_article and self.fail_clause):
                raise RuntimeError("scroll failure")
            return [
                _point(
                    "article" if is_article else "clause",
                    "Xử phạt người điều khiển ô tô." if is_article else "Phạt tiền từ 1 đồng.",
                    None,
                    clause=None if is_article else "9",
                )
            ], None

    class _Store:
        def __init__(self, client: _ScrollClient) -> None:
            self.client = client
            self.collection_name = "traffic_law"

    original = Document(
        "violation",
        metadata={"chunk_id": "orig", "document_id": "nd-168-2024", "article": "6", "clause": "9"},
    )
    assert [
        d.metadata["chunk_id"]
        for d in _sibling_completion_documents(
            _Store(_ScrollClient(fail_article=True)), original, 2
        )
    ] == ["clause"]
    assert [
        d.metadata["chunk_id"]
        for d in _sibling_completion_documents(_Store(_ScrollClient(fail_clause=True)), original, 2)
    ] == ["article"]


def test_clauseless_original_keeps_single_scroll_behavior() -> None:
    from app.rag.retrieval import _sibling_completion_documents

    class _ScrollClient:
        collection_name = "traffic_law"

        def __init__(self) -> None:
            self.calls = 0

        def scroll(self, **kwargs: Any) -> tuple[list[Any], None]:
            self.calls += 1
            return [
                _point("sibling", "Phạt tiền từ 1 đồng.", None, document_id="d", article="1")
            ], None

    class _Store:
        client = _ScrollClient()
        collection_name = "traffic_law"

    original = Document("header", metadata={"chunk_id": "orig", "document_id": "d", "article": "1"})
    assert [
        doc.metadata["chunk_id"] for doc in _sibling_completion_documents(_Store(), original, 2)
    ] == ["sibling"]
    assert _Store.client.calls == 1


def _point(
    chunk_id: str,
    text: str,
    point: str | None,
    *,
    clause: str | None = "9",
    document_id: str = "nd-168-2024",
    article: str = "6",
) -> Any:
    from qdrant_client.models import PointStruct

    metadata = {
        "chunk_id": chunk_id,
        "document_id": document_id,
        "document_number": "168/2024/NĐ-CP",
        "article": article,
        "clause": clause,
    }
    if point:
        metadata["point"] = point
    return PointStruct(
        id=abs(hash(chunk_id)) % (10**12),
        vector={"dense": [0.0] * 3},
        payload={"metadata": metadata, "page_content": text},
    )


class _StubEmbeddingSettings:
    openrouter_api_key = "test-key"
    openrouter_base_url = "https://example.invalid"
    model = "test-embedding"
    dimensions = 3
    timeout_seconds = 1.0
    max_retries = 0


class _StubSparse:
    def __init__(self, *args: Any, **kwargs: Any) -> None: ...

    def embed_query(self, text: str) -> list[float]:
        return []


def _patch_store_dependencies(monkeypatch: Any) -> None:
    import langchain_qdrant

    from app.config import QdrantSettings
    from app.rag import retrieval as retrieval_module

    monkeypatch.setattr(
        retrieval_module, "get_embedding_settings", lambda: _StubEmbeddingSettings()
    )
    monkeypatch.setattr(retrieval_module, "get_qdrant_settings", lambda: QdrantSettings())
    monkeypatch.setattr(retrieval_module, "QdrantClient", lambda **kwargs: object())
    monkeypatch.setattr(langchain_qdrant, "FastEmbedSparse", _StubSparse)


def test_store_creation_survives_throttled_provider(monkeypatch) -> None:
    """Collection validation embeds a probe string.

    A throttled provider must therefore not disable sparse search.
    """
    import langchain_qdrant

    from app.rag.retrieval import Retriever

    validations: list[bool] = []

    class _VectorStore:
        def __init__(self, **kwargs: Any) -> None:
            validate = bool(kwargs.get("validate_collection_config", True))
            validations.append(validate)
            if validate:
                raise RuntimeError("embedding provider timed out")

    _patch_store_dependencies(monkeypatch)
    monkeypatch.setattr(langchain_qdrant, "QdrantVectorStore", _VectorStore)

    store = Retriever()._create_store()

    assert isinstance(store, _VectorStore)
    assert validations == [True, False], "validation must be retried without the probe embedding"


def test_store_creation_still_reports_collection_mismatch(monkeypatch) -> None:
    import langchain_qdrant
    from langchain_qdrant.qdrant import QdrantVectorStoreError

    from app.rag.retrieval import RetrievalProviderError, Retriever

    validations: list[bool] = []

    class _VectorStore:
        def __init__(self, **kwargs: Any) -> None:
            validations.append(bool(kwargs.get("validate_collection_config", True)))
            raise QdrantVectorStoreError("Existing collection lacks dense vector")

    _patch_store_dependencies(monkeypatch)
    monkeypatch.setattr(langchain_qdrant, "QdrantVectorStore", _VectorStore)

    with pytest.raises(RetrievalProviderError):
        Retriever()._create_store()

    assert validations == [True], "a real collection mismatch must not be retried silently"
