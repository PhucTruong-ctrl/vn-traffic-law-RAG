"""Deterministic citation and claim sanitization checks."""

from datetime import date

from langchain_core.documents import Document

from app.rag.generator import CANONICAL_REFUSAL
from app.rag.verification import sanitize_response


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
    return sanitize_response(
        question, route, None, references, effective_date, docs, answer, citations, claims
    )


def test_safe_cases_are_verified_without_provider_calls() -> None:
    assert _verify().allowed
    assert _verify(answer="Theo Điều 6, vượt đèn đỏ bị phạt.").allowed


def test_bad_citation_is_dropped_but_good_response_survives() -> None:
    bad = _citation(source_id="missing")
    decision = _verify(citations=(_citation(), bad))
    assert decision.allowed
    assert decision.citations == (_citation(),)


def test_answer_citation_marker_selects_matching_citation() -> None:
    citation = _citation()
    citation["clause"] = "9"
    citation["point"] = "b"
    answer = "Theo [Điều 6, Khoản 9, Điểm b — Nghị định 168/2024/NĐ-CP]."
    decision = _verify(answer=answer, citations=(citation,))
    assert decision.allowed
    assert decision.citations == (citation,)


def test_unmatched_answer_citation_keeps_fallback_citations() -> None:
    answer = "Theo [Điều 99, Khoản 1 — Nghị định 999/2099]."
    decision = _verify(answer=answer)
    assert decision.allowed
    assert decision.citations == (_citation(),)


def test_canonical_refusal_is_rejected() -> None:
    decision = _verify(answer=CANONICAL_REFUSAL)
    assert not decision.allowed
    assert decision.reason == "generation_insufficient_evidence"


def test_unsupported_claim_is_dropped_supported_claim_survives() -> None:
    claims = (
        {"claim": "supported", "provision_ids": ["chunk-1"]},
        {"claim": "unsupported", "provision_ids": ["missing"]},
    )
    decision = _verify(claims=claims)
    assert decision.allowed
    assert decision.claims == (claims[0],)


def test_answer_figures_must_appear_in_the_evidence() -> None:
    from langchain_core.documents import Document

    from app.rag.verification import sanitize_response

    documents = [
        Document(
            "Phạt tiền từ 3.000.000 đồng đến 5.000.000 đồng đối với hành vi dừng xe "
            "trên đường cao tốc.",
            metadata={
                "chunk_id": "nd-100-2019:0299",
                "document_id": "nd-100-2019",
                "article": "7",
                "clause": "6",
            },
        )
    ]
    common = dict(
        question="Mức phạt là bao nhiêu?",
        route="legal",
        analysis=None,
        references=[],
        effective_date=None,
        filtered_documents=documents,
        citations=[],
        claims=[],
    )

    rejected = sanitize_response(
        answer="Phạt tiền từ 4.000.000 đồng đến 5.000.000 đồng.",
        **common,
    )
    assert rejected.allowed is False
    assert rejected.reason == "unsupported_figures"

    accepted = sanitize_response(
        answer="Phạt tiền từ 3.000.000 đồng đến 5.000.000 đồng (Nghị định 100/2019/NĐ-CP).",
        **common,
    )
    assert accepted.allowed is True
