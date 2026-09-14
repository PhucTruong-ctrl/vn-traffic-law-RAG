"""Deterministic proof matrix for fail-closed response verification."""

from datetime import date

from langchain_core.documents import Document

from app.rag.references import LegalReference
from app.rag.verification import verify_response


def _citation(source_id: str = "chunk-1", excerpt: str = "Vượt đèn đỏ bị phạt.") -> dict:
    return {
        "source_id": source_id,
        "document_id": "nd-168-2024",
        "document_number": "168/2024/NĐ-CP",
        "article": "6",
        "excerpt": excerpt,
    }


def _doc(
    source_id: str = "chunk-1", text: str = "Vượt đèn đỏ bị phạt.", **metadata: object
) -> Document:
    return Document(
        text,
        metadata={"chunk_id": source_id, "document_id": "nd-168-2024", "article": "6", **metadata},
    )


def _verify(
    *,
    question: str = "Vượt đèn đỏ bị phạt thế nào?",
    route: str = "traffic",
    docs: tuple[Document, ...] = (_doc(),),
    answer: str = "Vượt đèn đỏ bị phạt.",
    citations: tuple[dict, ...] = (_citation(),),
    claims: tuple[dict, ...] = ({"claim": "Vượt đèn đỏ bị phạt.", "provision_ids": ["chunk-1"]},),
    references: tuple = (),
    effective_date: date | None = None,
):
    return verify_response(
        question, route, None, references, effective_date, docs, answer, citations, claims
    )


def test_safe_cases_are_verified_without_provider_calls() -> None:
    assert _verify().allowed
    assert _verify(answer="Theo Điều 6, vượt đèn đỏ bị phạt.").allowed


def test_unsafe_cases_never_verify() -> None:
    unsafe = (
        _verify(route="weather"),
        _verify(citations=()),
        _verify(claims=({"claim": "Không có căn cứ.", "provision_ids": []},)),
        _verify(citations=(_citation(excerpt="Nội dung khác."),)),
        _verify(docs=()),
        _verify(answer=""),
        _verify(citations=({"source_id": "", "excerpt": "Vượt đèn đỏ bị phạt."},)),
    )
    assert all(not decision.allowed and decision.reason for decision in unsafe)


def test_all_requested_references_must_be_covered() -> None:
    reference = LegalReference(number="168/2024/NĐ-CP", article="7")
    decision = _verify(references=(reference,))
    assert not decision.allowed
    assert decision.reason == "reference_not_covered"
