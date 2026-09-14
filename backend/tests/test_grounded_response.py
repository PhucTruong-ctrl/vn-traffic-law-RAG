"""Focused behavioral coverage for grounded RAG responses."""

from __future__ import annotations

from datetime import date

from langchain_core.documents import Document

from app.rag.service import RAGService


def _doc(chunk_id: str, text: str, **metadata: object) -> Document:
    return Document(
        text,
        metadata={"chunk_id": chunk_id, "document_id": "nd-168-2024", **metadata},
    )


def test_verified_claims_and_citations_are_bidirectional(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.service.generate_answer", lambda *_args, **_kwargs: "Đáp án")
    evidence = _doc(
        "chunk-1",
        "Hành vi bị phạt tiền.",
        article="6",
        document_number="168/2024/NĐ-CP",
    )
    service = RAGService()
    result = service.answer("Điều 6 Nghị định 168/2024 quy định gì?", chunks=[evidence])
    assert result["status"] == "verified"
    citation_ids = {item["source_id"] for item in result["citations"]}
    claim_ids = {source_id for claim in result["claims"] for source_id in claim["provision_ids"]}
    assert citation_ids == claim_ids == {"chunk-1"}


def test_every_explicit_reference_is_required() -> None:
    first = _doc("chunk-1", "Quy định thứ nhất.", article="6")
    result = RAGService().answer(
        "Điều 6 và Điều 7 Nghị định 168/2024 quy định gì?",
        chunks=[first],
    )
    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "reference_not_found"


def test_railway_evidence_is_excluded_without_railway_context() -> None:
    railway = _doc("rail", "Đường sắt: vượt rào chắn bị phạt.", article="6")
    result = RAGService().answer("Vượt đèn đỏ bị phạt thế nào?", chunks=[railway])
    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "insufficient_evidence"


def test_invalid_citation_identity_abstains() -> None:
    result = RAGService().answer(
        "Vượt đèn đỏ bị phạt thế nào?",
        chunks=[
            Document(
                "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông.",
                metadata={"document_id": "nd-168-2024"},
            )
        ],
    )
    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "insufficient_evidence"


def test_incomplete_legal_identity_never_verifies(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.service.generate_answer", lambda *_args, **_kwargs: "unsafe")
    result = RAGService().answer(
        "Vượt đèn đỏ bị phạt thế nào?",
        chunks=[
            _doc(
                "chunk-unsafe",
                "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông.",
                document_id="nd-168-2024",
            )
        ],
    )
    assert result["status"] == "insufficient_evidence"
    assert not result["citations"]


def test_multi_intent_missing_evidence_abstains(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.service.generate_answer", lambda *_args, **_kwargs: "partial")
    result = RAGService().answer(
        "Vượt đèn đỏ và dùng điện thoại khi lái xe bị phạt thế nào?",
        chunks=[
            _doc(
                "chunk-one",
                "Vượt đèn đỏ bị phạt.",
                document_id="nd-168-2024",
                document_number="168/2024/NĐ-CP",
                article="6",
            )
        ],
    )
    assert result["status"] == "insufficient_evidence"


def test_effective_date_filters_future_evidence() -> None:
    future = _doc(
        "future",
        "Quy định mới.",
        article="6",
        effective_from="2027-01-01",
    )
    result = RAGService().answer(
        "Điều 6 Nghị định 168/2024 quy định gì?",
        chunks=[future],
        effective_date=date(2026, 1, 1),
    )
    assert result["status"] == "insufficient_evidence"
    assert result["reason_code"] == "temporal_mismatch"


def test_explicit_railway_context_overrides_default_road_context(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.service.generate_answer", lambda *_args, **_kwargs: "Đáp án")
    railway = _doc(
        "rail",
        "Không chấp hành hiệu lệnh đèn đỏ tại đường ngang.",
        article="47",
        normalized_action="không chấp hành hiệu lệnh của đèn tín hiệu giao thông",
        context_scope=["railway_crossing"],
    )

    result = RAGService().answer(
        "Vượt đèn đỏ tại đường ngang bị phạt thế nào?",
        chunks=[railway],
    )

    assert result["status"] == "verified"
    assert result["citations"][0]["source_id"] == "rail"


def test_current_query_drops_ceased_and_superseded_candidates(monkeypatch) -> None:
    monkeypatch.setattr("app.rag.service.generate_answer", lambda *_args, **_kwargs: "Đáp án")
    action = "Không chấp hành hiệu lệnh của đèn tín hiệu giao thông."
    current = _doc(
        "current",
        action,
        article="6",
        normalized_action=action,
        vehicle_categories=["car"],
        context_scope=["road_traffic"],
        status="EFFECTIVE",
    )
    old = _doc(
        "old",
        action,
        article="5",
        normalized_action=action,
        vehicle_categories=["car"],
        context_scope=["road_traffic"],
        status="PARTIALLY_EFFECTIVE",
        document_id="nd-100-2019",
    )
    ceased = _doc(
        "ceased",
        "Nội dung sát hạch đèn đỏ.",
        article="6",
        context_scope=[],
        status="CEASED",
        document_id="tt-05-2024",
    )

    result = RAGService().answer(
        "Ô tô vượt đèn đỏ bị phạt thế nào?",
        chunks=[old, ceased, current],
    )

    assert result["status"] == "verified"
    assert [citation["source_id"] for citation in result["citations"]] == ["current"]


def test_out_of_scope_and_missing_context_abstain_with_distinct_reasons() -> None:
    out_of_scope = RAGService().answer("Thời tiết Hà Nội ngày mai thế nào?", chunks=[])
    mismatched_context = _doc(
        "rail-only",
        "Vượt đường ngang khi đèn đỏ đã bật sáng.",
        article="47",
        context_scope=["railway_crossing"],
    )
    missing_context = RAGService().answer(
        "Vượt đèn đỏ bị phạt thế nào?",
        chunks=[mismatched_context],
    )

    assert out_of_scope["reason_code"] == "out_of_scope"
    assert missing_context["status"] == "insufficient_evidence"
    assert missing_context["reason_code"] == "no_relevant_provision"
