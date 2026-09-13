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
