from __future__ import annotations

from datetime import date

from langchain_core.documents import Document

from app.rag.evidence import assess_evidence

CURRENT_DATE = date(2025, 6, 15)


def document(*, start: str | None = None, end: str | None = None) -> Document:
    metadata = {}
    if start is not None:
        metadata["effective_from"] = start
    if end is not None:
        metadata["effective_until"] = end
    return Document("Quy định giao thông", metadata=metadata)


def test_current_date_allows_document_on_inclusive_start_and_end() -> None:
    decision = assess_evidence(
        [document(start="2025-06-15", end="2025-06-15")],
        effective_date=CURRENT_DATE,
    )

    assert decision.allowed is True


def test_current_date_rejects_document_outside_effective_interval() -> None:
    decision = assess_evidence(
        [document(start="2025-06-16", end="2025-06-30")],
        effective_date=CURRENT_DATE,
    )

    assert decision.allowed is False
    assert decision.reason == "no_temporally_valid_evidence"


def test_current_date_rejects_malformed_effective_interval() -> None:
    decision = assess_evidence(
        [document(start="not-a-date", end="2025-06-30")],
        effective_date=CURRENT_DATE,
    )

    assert decision.allowed is False
    assert decision.reason == "no_temporally_valid_evidence"


def test_undated_document_remains_eligible_for_current_date() -> None:
    decision = assess_evidence([document()], effective_date=CURRENT_DATE)

    assert decision.allowed is True


def doc(text: str, **metadata: object) -> Document:
    return Document(page_content=text, metadata=metadata)


def test_relevance_vehicle_and_excluded_context_are_required() -> None:
    assert not assess_evidence(
        [doc("quy định đường sắt", document_id="rail")],
        required_action_terms=["vượt đèn đỏ"],
        required_vehicle_terms=["xe máy"],
        excluded_contexts=["đường sắt"],
    ).allowed
    assert not assess_evidence(
        [doc("vượt đèn đỏ cho ô tô", document_id="car")],
        required_vehicle_terms=["xe máy"],
    ).allowed


def test_missing_identity_cannot_satisfy_reference_or_intent() -> None:
    decision = assess_evidence(
        [doc("vượt đèn đỏ xe máy", article="Điều 6", intent="phạt")],
        required_reference={"article": "Điều 6"},
        required_intents=["phạt"],
    )
    assert not decision.allowed


def test_effective_interval_is_inclusive_and_absent_dates_are_eligible() -> None:
    kwargs = {"required_action_terms": ["vượt"], "effective_date": date(2024, 1, 1)}
    assert assess_evidence(
        [doc("vượt", document_id="x", effective_from="2024-01-01", effective_to="2024-12-31")],
        **kwargs,
    ).allowed
    assert not assess_evidence(
        [doc("vượt", document_id="x", effective_from="2024-01-02")], **kwargs
    ).allowed
    assert assess_evidence([doc("vượt", document_id="x")], **kwargs).allowed
