from __future__ import annotations

from datetime import date
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

    assert [document.page_content for document in result] == [
        original.page_content,
        target.page_content,
    ]
    assert [document.metadata["chunk_id"] for document in result] == [
        "original",
        "target",
    ]
    assert result[1].metadata["added_by"] == "CROSS_REFERENCE"
    assert result[1].metadata["source_id"] == "original"
    assert store.searches and store.searches[0][1] == 6
    assert store.client.scrolls[0]["collection_name"] == "laws"


def test_retrieve_keeps_original_when_explicit_reference_is_unresolved() -> None:
    original = Document(
        "Quy định này dẫn chiếu Điều 99.",
        metadata={"chunk_id": "original", "article": "7"},
    )
    store = FakeStore([original])
    retriever = Retriever()
    retriever._store = store

    assert retriever.retrieve("Tìm quy định", top_k=1) == [original]


def test_retrieve_reserves_capacity_for_same_clause_sanction_and_filters_temporal_metadata() -> (
    None
):
    original = Document(
        "Điều 7 khoản 1 quy định hành vi.",
        metadata={
            "chunk_id": "original",
            "document_id": "nd100",
            "article": "7",
            "clause": "1",
            "effective_from": "2025-01-01",
            "effective_to": "2027-01-01",
        },
    )
    sanction = Document(
        "Phạt tiền từ 1.000.000 đồng.",
        metadata={
            "chunk_id": "sanction",
            "document_id": "nd100",
            "article": "7",
            "clause": "1",
            "effective_from": "2025-01-01",
            "effective_to": "2027-01-01",
        },
    )
    malformed = Document(
        "Phạt tiền nhưng ngày hiệu lực hỏng.",
        metadata={
            "chunk_id": "malformed",
            "document_id": "nd100",
            "article": "7",
            "clause": "1",
            "effective_from": "not-a-date",
        },
    )
    out_of_range = Document(
        "Phạt tiền đã hết hiệu lực.",
        metadata={
            "chunk_id": "expired",
            "document_id": "nd100",
            "article": "7",
            "clause": "1",
            "effective_from": "2020-01-01",
            "effective_to": "2021-01-01",
        },
    )
    store = FakeStore([original, sanction, malformed, out_of_range])
    retriever = Retriever(top_k=2)
    retriever._store = store

    result = retriever.retrieve("Điều 7 khoản 1", top_k=2, effective_date=date(2026, 1, 1))

    assert [document.metadata["chunk_id"] for document in result] == ["original", "sanction"]
    assert len(result) == 2


def test_phone_point_pairs_only_with_same_clause_sanction_and_date_window() -> None:
    original = Document(
        "Điểm h khoản 5 Điều 6.",
        metadata={
            "chunk_id": "point",
            "document_id": "nd-168-2024",
            "article": "6",
            "clause": "5",
            "point": "h",
        },
    )
    same_clause = Document(
        "Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng.",
        metadata={
            "chunk_id": "same",
            "document_id": "nd-168-2024",
            "article": "6",
            "clause": "5",
            "effective_from": "2025-01-01",
        },
    )
    other_clause = Document(
        "Phạt tiền từ 800.000 đồng đến 1.000.000 đồng.",
        metadata={"chunk_id": "other", "document_id": "nd-168-2024", "article": "6", "clause": "4"},
    )
    expired = Document(
        "Phạt tiền cũ.",
        metadata={
            "chunk_id": "expired",
            "document_id": "nd-168-2024",
            "article": "6",
            "clause": "5",
            "effective_to": "2024-12-31",
        },
    )
    undated = Document(
        "Trừ điểm giấy phép.",
        metadata={
            "chunk_id": "undated",
            "document_id": "nd-168-2024",
            "article": "6",
            "clause": "5",
        },
    )
    store = FakeStore([original, same_clause, other_clause, expired, undated])
    retriever = Retriever(top_k=1)
    retriever._store = store

    result = retriever.retrieve("Điểm h khoản 5 Điều 6", top_k=1, effective_date=date(2025, 2, 1))
    assert [document.metadata["chunk_id"] for document in result] == ["point"]
    assert same_clause.metadata["clause"] == "5"
    assert other_clause.metadata["clause"] == "4"
    assert expired.metadata["effective_to"] == "2024-12-31"
    assert undated.metadata.get("effective_from") is None


def test_exact_canonical_reference_filters_document_id() -> None:
    first = Document(
        "Nội dung.", metadata={"chunk_id": "one", "document_id": "nd-100-2019", "article": "12"}
    )
    other = Document(
        "Nội dung khác.",
        metadata={"chunk_id": "two", "document_id": "nd-200-2020", "article": "12"},
    )
    store = FakeStore([first, other])
    retriever = Retriever(top_k=1)
    retriever._store = store

    result = retriever.retrieve("nd-100-2019__dieu-12", top_k=1)

    assert result == [first]


def test_action_metadata_lookup_requires_exact_or_context_specific_action() -> None:
    exact = Document(
        "Quy định xử phạt.",
        metadata={
            "chunk_id": "exact",
            "normalized_action": "không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
        },
    )
    railway = Document(
        "Quy định đường ngang.",
        metadata={
            "chunk_id": "railway",
            "normalized_action": "Vượt đường ngang khi đèn đỏ đã bật sáng",
        },
    )
    broader = Document(
        "Nội dung sát hạch.",
        metadata={
            "chunk_id": "broader",
            "normalized_action": (
                "bị truất quyền sát hạch do không chấp hành hiệu lệnh của đèn tín hiệu giao thông"
            ),
        },
    )
    store = FakeStore([broader, railway, exact])
    retriever = Retriever(top_k=3)
    retriever._store = store

    default = retriever.retrieve(
        "Vượt đèn đỏ; không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
        top_k=3,
    )
    scoped = retriever.retrieve(
        "Vượt đèn đỏ tại đường ngang; không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
        top_k=3,
    )

    assert default[0].metadata["chunk_id"] == "exact"
    assert [document.metadata["chunk_id"] for document in scoped[:2]] == [
        "railway",
        "exact",
    ]
