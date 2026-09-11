from __future__ import annotations

from typing import Any

from langchain_core.documents import Document

from app.rag.retrieval import Retriever


class FakeStore:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.searches: list[tuple[str, int, Any]] = []
        self.client = FakeClient(documents)
        self.collection_name = "laws"

    def similarity_search(self, query: str, *, k: int, filter: Any = None) -> list[Document]:
        self.searches.append((query, k, filter))
        return list(self.documents)


class FakeClient:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self.scrolls: list[dict[str, Any]] = []

    def scroll(self, **kwargs: Any) -> tuple[list[Any], None]:
        self.scrolls.append(kwargs)
        return [FakePoint(document) for document in self.documents], None


class FakePoint:
    def __init__(self, document: Document) -> None:
        self.payload = {
            "page_content": document.page_content,
            "metadata": dict(document.metadata),
        }


def test_retrieve_expands_explicit_reference_through_exact_lookup_with_total_cap() -> None:
    original = Document(
        "Quy định này dẫn chiếu Điều 12.",
        metadata={"chunk_id": "original", "article": "7"},
    )
    target = Document(
        "Nội dung Điều 12.",
        metadata={"chunk_id": "target", "article": "12"},
    )
    duplicate_target = Document(
        target.page_content,
        metadata=dict(target.metadata),
    )
    store = FakeStore([original, target, duplicate_target])
    retriever = Retriever(top_k=2)
    retriever._store = store

    result = retriever.retrieve("Tìm quy định liên quan", top_k=2)

    assert result == [original, target]
    assert [document.metadata["chunk_id"] for document in result] == [
        "original",
        "target",
    ]
    assert result[1] is target
    assert store.searches and store.searches[0][1] == 6
    assert store.client.scrolls == []


def test_retrieve_keeps_original_when_explicit_reference_is_unresolved() -> None:
    original = Document(
        "Quy định này dẫn chiếu Điều 99.",
        metadata={"chunk_id": "original", "article": "7"},
    )
    store = FakeStore([original])
    retriever = Retriever()
    retriever._store = store

    assert retriever.retrieve("Tìm quy định", top_k=1) == [original]
