from __future__ import annotations

from datetime import date

from langchain_core.documents import Document

from app.rag.service import RAGService


class StubRetriever:
    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents

    def retrieve(self, *args, **kwargs):
        return list(self.documents)

    def search(self, *args, **kwargs):
        return list(self.documents)


class GeneratorSpy:
    def __init__(self) -> None:
        self.documents: list[Document] = []

    def __call__(self, question, documents, *args, **kwargs) -> str:
        self.documents = list(documents)
        return (
            "Theo quy định hiện hành, hành vi này bị phạt từ 18.000.000 đồng đến 20.000.000 đồng."
        )


def _document(
    chunk_id: str,
    document_id: str,
    status: str,
    content: str,
    *,
    normalized_action: str = "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
    article: str = "5",
    clause: str = "5",
    point: str = "a",
) -> Document:
    return Document(
        content,
        metadata={
            "chunk_id": chunk_id,
            "document_id": document_id,
            "document_number": f"{document_id}/NĐ-CP",
            "article": article,
            "clause": clause,
            "point": point,
            "status": status,
            "normalized_action": normalized_action,
            "vehicle_categories": ["car"],
            "context_scope": ["road_traffic"],
        },
    )


def _documents() -> list[Document]:
    old_action = _document(
        "nd-100-2019__dieu-5__khoan-5__diem-a",
        "nd-100-2019",
        "PARTIALLY_EFFECTIVE",
        "Điểm a khoản 5 Điều 5: Không chấp hành hiệu lệnh của đèn tín hiệu giao thông.",
    )
    old_header = _document(
        "nd-100-2019__dieu-5__khoan-5",
        "nd-100-2019",
        "PARTIALLY_EFFECTIVE",
        "Phạt tiền từ 3.000.000 đồng đến 5.000.000 đồng đối với người điều khiển xe "
        "thực hiện một trong các hành vi vi phạm sau đây:",
        normalized_action="",
        point="",
    )
    current_header = _document(
        "nd-168-2024__dieu-6__khoan-9",
        "nd-168-2024",
        "EFFECTIVE",
        "Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng đối với người điều khiển xe "
        "thực hiện một trong các hành vi vi phạm sau đây:",
        normalized_action="",
        article="6",
        clause="9",
        point="",
    )
    current_action = _document(
        "nd-168-2024__dieu-6__khoan-9__diem-a",
        "nd-168-2024",
        "EFFECTIVE",
        "Điểm a khoản 9 Điều 6: Không chấp hành hiệu lệnh của đèn tín hiệu giao thông.",
        article="6",
        clause="9",
        point="a",
    )
    return [old_action, old_header, current_header, current_action]


def test_answer_prefers_current_versions_before_generation(monkeypatch) -> None:
    generator = GeneratorSpy()
    monkeypatch.setattr("app.rag.service.generate_answer", generator)

    result = RAGService(StubRetriever(_documents())).answer(
        "Ô tô không chấp hành đèn tín hiệu bị phạt bao nhiêu?"
    )

    assert result["status"] == "verified"
    generated_ids = {document.metadata["chunk_id"] for document in generator.documents}
    generated_text = " ".join(document.page_content for document in generator.documents)
    assert "3.000.000" not in generated_text and "5.000.000" not in generated_text
    assert not any(chunk_id.startswith("nd-100-2019") for chunk_id in generated_ids)


def test_single_version_document_is_retained(monkeypatch) -> None:
    generator = GeneratorSpy()
    monkeypatch.setattr("app.rag.service.generate_answer", generator)
    lone = _document(
        "nd-50-2020__dieu-1__khoan-1__diem-a",
        "nd-50-2020",
        "PARTIALLY_EFFECTIVE",
        "Không chấp hành biển báo giao thông.",
        normalized_action="Không chấp hành biển báo giao thông",
        article="1",
        clause="1",
    )

    RAGService(StubRetriever([lone])).answer(
        "Ô tô không chấp hành biển báo giao thông bị phạt bao nhiêu?"
    )

    assert generator.documents[0].metadata["chunk_id"] == lone.metadata["chunk_id"]


def test_explicit_reference_and_effective_date_keep_retrieved_versions(monkeypatch) -> None:
    for question, effective_date in (
        ("Theo Nghị định 100/2019, ô tô không chấp hành đèn tín hiệu bị phạt bao nhiêu?", None),
        ("Ô tô không chấp hành đèn tín hiệu bị phạt bao nhiêu?", date(2020, 1, 1)),
    ):
        documents = _documents()
        generator = GeneratorSpy()
        monkeypatch.setattr("app.rag.service.generate_answer", generator)

        RAGService(StubRetriever(documents)).answer(question, effective_date=effective_date)

        generated_ids = {document.metadata["chunk_id"] for document in generator.documents}
        assert "nd-100-2019__dieu-5__khoan-5" in generated_ids
        assert "nd-100-2019__dieu-5__khoan-5__diem-a" in generated_ids


def test_amount_header_partially_effective_is_dropped_for_current_twin(monkeypatch) -> None:
    generator = GeneratorSpy()
    monkeypatch.setattr("app.rag.service.generate_answer", generator)
    old_header = _document(
        "nd-100-2019__dieu-5__khoan-5",
        "nd-100-2019",
        "PARTIALLY_EFFECTIVE",
        "Phạt tiền từ 3.000.000 đồng đến 5.000.000 đồng.",
        normalized_action="Phạt tiền từ 3.000.000 đồng đến 5.000.000 đồng",
        point="",
    )
    current_header = _document(
        "nd-168-2024__dieu-6__khoan-9",
        "nd-168-2024",
        "EFFECTIVE",
        "Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng.",
        normalized_action="Phạt tiền từ 18.000.000 đồng đến 20.000.000 đồng",
        article="6",
        clause="9",
        point="",
    )

    RAGService(StubRetriever([old_header, current_header])).answer("Ô tô bị phạt bao nhiêu?")

    assert {d.metadata["chunk_id"] for d in generator.documents} == {"nd-168-2024__dieu-6__khoan-9"}


def test_amount_header_without_current_twin_is_retained(monkeypatch) -> None:
    generator = GeneratorSpy()
    monkeypatch.setattr("app.rag.service.generate_answer", generator)
    old_header = _document(
        "nd-100-2019__dieu-5__khoan-5",
        "nd-100-2019",
        "PARTIALLY_EFFECTIVE",
        "Phạt tiền từ 3.000.000 đồng đến 5.000.000 đồng.",
        normalized_action="Phạt tiền từ 3.000.000 đồng đến 5.000.000 đồng",
        point="",
    )

    RAGService(StubRetriever([old_header])).answer("Ô tô bị phạt bao nhiêu?")

    assert generator.documents[0].metadata["chunk_id"] == old_header.metadata["chunk_id"]


def test_non_monetary_digits_do_not_merge_versions(monkeypatch) -> None:
    generator = GeneratorSpy()
    monkeypatch.setattr("app.rag.service.generate_answer", generator)
    old = _document(
        "old",
        "nd-100-2019",
        "PARTIALLY_EFFECTIVE",
        "Chở 03 người.",
        normalized_action="Chở 03 người",
    )
    current = _document(
        "current",
        "nd-168-2024",
        "EFFECTIVE",
        "Chở 04 người.",
        normalized_action="Chở 04 người",
    )

    RAGService(StubRetriever([old, current])).answer("Ô tô chở người?")

    assert {"old", "current"} <= {d.metadata["chunk_id"] for d in generator.documents}
