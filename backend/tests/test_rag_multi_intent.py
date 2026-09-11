from __future__ import annotations

from langchain_core.documents import Document

from app.rag.analyzer import analyze_question, resolve_vehicle_followup
from app.rag.service import RAGService


class FakeRetriever:
    def __init__(self, responses: dict[str, list[Document]] | None = None) -> None:
        self.responses = responses or {}
        self.queries: list[str] = []

    def retrieve(self, query: str, **_: object) -> list[Document]:
        self.queries.append(query)
        return list(self.responses.get(query, []))


def test_speed_limit_road_traffic_questions_are_legal_but_general_questions_are_not() -> None:
    assert (
        analyze_question("Tốc độ tối đa trong khu vực đông dân cư là bao nhiêu km/h?")
        .intents[0]
        .kind
        == "legal"
    )
    assert analyze_question("Thời tiết hôm nay thế nào?").intents[0].kind == "out_of_scope"


def test_red_light_and_no_helmet_decompose_into_both_violations() -> None:
    analysis = analyze_question("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    texts = [intent.text.casefold() for intent in analysis.intents]
    assert len(texts) == 2
    assert any("vượt đèn đỏ" in text for text in texts)
    assert any("không đội mũ bảo hiểm" in text for text in texts)


def test_short_car_followup_rewrites_against_latest_legal_turn() -> None:
    history = [
        {"role": "user", "content": "Xe máy vượt đèn đỏ thì mức phạt bao nhiêu?"},
        {"role": "assistant", "content": "Theo quy định hiện hành..."},
    ]

    assert resolve_vehicle_followup("Còn ô tô?", history) == (
        "Mức phạt đối với ô tô vượt đèn đỏ thì là bao nhiêu?"
    )


def test_vehicle_followup_uses_at_most_six_history_messages() -> None:
    history = [{"role": "user", "content": "Xe máy vượt đèn đỏ thì mức phạt bao nhiêu?"}] + [
        {"role": "assistant", "content": f"older-{index}"} for index in range(6)
    ]

    assert resolve_vehicle_followup("Còn ô tô?", history) == "Còn ô tô?"


def test_penalty_dimensions_are_bounded_and_keep_violation_context() -> None:
    question = (
        "Vượt đèn đỏ thì mức phạt, trừ điểm GPLX, tước quyền sử dụng GPLX "
        "và xử lý phương tiện thế nào?"
    )

    intents = analyze_question(question).intents

    assert len(intents) == 4
    assert all("vượt đèn đỏ" in intent.text.casefold() for intent in intents)
    assert [intent.text.rsplit("; ", 1)[-1] for intent in intents] == [
        "mức phạt",
        "trừ điểm GPLX",
        "tước quyền sử dụng",
        "xử lý/tạm giữ phương tiện",
    ]


def test_retrieve_uses_rrf_and_diversity_cap_with_deterministic_ties() -> None:
    shared = Document(
        "shared", metadata={"chunk_id": "shared", "document_id": "law", "article": 1, "clause": 1}
    )
    distractor = Document(
        "distractor", metadata={"chunk_id": "d", "document_id": "law", "article": 1, "clause": 2}
    )
    fourth = Document(
        "fourth", metadata={"chunk_id": "fourth", "document_id": "law", "article": 1, "clause": 3}
    )
    distinct_clause = Document(
        "distinct",
        metadata={"chunk_id": "distinct", "document_id": "law", "article": 1, "clause": 4},
    )
    retriever = FakeRetriever(
        {
            "vượt đèn đỏ": [shared, distractor, fourth, distinct_clause],
            "không đội mũ bảo hiểm": [shared, distractor, fourth],
        }
    )

    documents = RAGService(retriever).retrieve("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    assert [document.page_content for document in documents] == [
        "shared",
        "distractor",
        "fourth",
        "distinct",
    ]
    assert [document.metadata["chunk_id"] for document in documents] == [
        "shared",
        "d",
        "fourth",
        "distinct",
    ]
    assert len(documents) == 4
    assert [document.metadata["intent"] for document in documents] == [
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
        ["vượt đèn đỏ"],
    ]


def test_retrieve_deduplicates_documents_in_first_seen_order() -> None:
    first = Document("first", metadata={"chunk_id": "a"})
    duplicate = Document("first", metadata={"chunk_id": "a"})
    second = Document("second", metadata={"chunk_id": "b"})
    retriever = FakeRetriever(
        {
            "vượt đèn đỏ": [first, duplicate],
            "không đội mũ bảo hiểm": [duplicate, second],
        }
    )

    documents = RAGService(retriever).retrieve("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    assert [document.page_content for document in documents] == ["first", "second"]
    assert [document.metadata["chunk_id"] for document in documents] == ["a", "b"]
    assert retriever.queries == ["vượt đèn đỏ", "không đội mũ bảo hiểm"]
    assert [document.metadata["intent"] for document in documents] == [
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
        ["không đội mũ bảo hiểm"],
    ]


def test_retrieve_fallback_identity_deduplicates_same_source_and_content() -> None:
    first = Document("same", metadata={"source_file": "law.pdf", "page": 1})
    duplicate = Document("same", metadata={"source": "law.pdf", "page": 2})
    retriever = FakeRetriever(
        {
            "vượt đèn đỏ": [first],
            "không đội mũ bảo hiểm": [duplicate],
        }
    )

    documents = RAGService(retriever).retrieve("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    assert [document.page_content for document in documents] == ["same"]
    assert [document.metadata.get("chunk_id") for document in documents] == [None]
    assert [document.metadata["intent"] for document in documents] == [
        ["không đội mũ bảo hiểm", "vượt đèn đỏ"],
    ]


def test_retrieve_keeps_distinct_chunk_ids_with_same_content() -> None:
    first = Document("same", metadata={"chunk_id": "a", "source_file": "law.pdf"})
    second = Document("same", metadata={"chunk_id": "b", "source_file": "law.pdf"})
    retriever = FakeRetriever(
        {
            "vượt đèn đỏ": [first],
            "không đội mũ bảo hiểm": [second],
        }
    )

    documents = RAGService(retriever).retrieve("Khi vượt đèn đỏ và ko đội mũ bảo hiểm")

    assert [document.page_content for document in documents] == ["same", "same"]
    assert [document.metadata["chunk_id"] for document in documents] == ["a", "b"]
    assert [document.metadata["intent"] for document in documents] == [
        ["vượt đèn đỏ"],
        ["không đội mũ bảo hiểm"],
    ]


def test_answer_generates_with_partial_evidence_and_abstains_when_empty(
    monkeypatch,
) -> None:
    question = "Khi xe máy vượt đèn đỏ?"
    evidence = Document("Điều khoản về vượt đèn đỏ", metadata={"chunk_id": "a"})
    monkeypatch.setattr(
        "app.rag.service.generate_answer",
        lambda received_question, documents, **kwargs: "Có căn cứ",
    )

    partial = RAGService(FakeRetriever()).answer(question, chunks=[evidence])
    empty = RAGService(FakeRetriever()).answer(question, chunks=[])

    assert partial["status"] == "complete"
    assert partial["answer"] == "Có căn cứ"
    assert partial["citations"][0]["excerpt"] == evidence.page_content
    assert empty["status"] == "insufficient_evidence"
    assert empty["citations"] == []
