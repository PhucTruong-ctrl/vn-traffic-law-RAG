from __future__ import annotations

from langchain_core.documents import Document

from app.rag.service import RAGService


class StubRetriever:
    def __init__(self, documents: list[Document] | None = None) -> None:
        self.documents = documents or []

    def search(self, *args, **kwargs):
        return list(self.documents)


class GeneratorSpy:
    def __init__(
        self, answer: str = "Theo Điều 6, hành vi vượt đèn đỏ bị xử phạt theo quy định."
    ) -> None:
        self.answer = answer
        self.calls = 0

    def __call__(self, *args, **kwargs) -> str:
        self.calls += 1
        return self.answer


def test_insufficient_evidence_gold_queries_clarify_without_generation(monkeypatch) -> None:
    questions = [
        "Tôi bị phạt hôm qua, phải làm gì và mức phạt chính xác bao nhiêu?",
        "Mức phạt là bao nhiêu?",
        "Bị phạt thì phải làm gì?",
        "Tôi vi phạm giao thông, mức phạt thế nào?",
        "Phạt nguội phải xử lý ra sao?",
    ]
    generator = GeneratorSpy()
    monkeypatch.setattr("app.rag.service.generate_answer", generator)

    for question in questions:
        result = RAGService(StubRetriever()).answer(question, chunks=[])
        assert result["status"] == "insufficient_evidence"
        assert result["reason_code"] == "clarification_required"
        assert result["citations"] == []
    assert generator.calls == 0


def test_verified_penalty_answer_returns_citations_and_debug_ids(monkeypatch) -> None:
    question = "Xe máy vượt đèn đỏ bị phạt bao nhiêu?"
    document = Document(
        "Điều 6. Người điều khiển xe mô tô vượt đèn đỏ bị phạt 1.000.000 đồng.",
        metadata={
            "chunk_id": "nd-168-2024__dieu-6__khoan-1",
            "document_id": "nd-168-2024",
            "document_number": "168/2024/NĐ-CP",
            "article": "6",
            "clause": "1",
        },
    )
    generator = GeneratorSpy()
    monkeypatch.setattr("app.rag.service.generate_answer", generator)

    result = RAGService(StubRetriever()).answer(question, chunks=[document])

    assert result["status"] == "verified"
    assert result["citations"]
    assert result["debug"]["cited_provision_ids"]
    assert result["debug"]["cited_provision_ids"] == ["nd-168-2024__dieu-6__khoan-1"]
    assert generator.calls == 1


def test_foreign_domain_query_refuses_as_out_of_scope(monkeypatch) -> None:
    generator = GeneratorSpy()
    monkeypatch.setattr("app.rag.service.generate_answer", generator)

    result = RAGService(StubRetriever()).answer(
        "Tính thuế thu nhập cá nhân cho người lái xe", chunks=[]
    )

    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "out_of_scope"
    assert result["citations"] == []
    assert generator.calls == 0
