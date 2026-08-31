from datetime import date

import pytest
from pydantic import ValidationError

from app.query.evidence_plan import required_evidence_for
from app.query.query_understanding import EvidenceType, QueryAnalyzer, QueryIntent, QueryPlan

TODAY = date(2026, 8, 31)


def test_exact_reference_and_vietnamese_point_are_parsed() -> None:
    plan = QueryAnalyzer().analyze(
        "Điều 7 Nghị định 168/2024/NĐ-CP, Điểm đ xe máy phạt bao nhiêu?",
        current_date=TODAY,
    )
    assert plan.intent is QueryIntent.SOURCE_SEARCH
    assert plan.document_number == "168/2024/NĐ-CP"
    assert plan.article == "7"
    assert plan.point == "đ"
    assert plan.vehicle_type == "xe máy"
    assert plan.required_evidence == [EvidenceType.VIOLATION_DEFINITION, EvidenceType.MONETARY_PENALTY]


def test_current_and_historical_dates_are_deterministic() -> None:
    current = QueryAnalyzer().analyze("mức phạt hiện nay", current_date=TODAY)
    historical = QueryAnalyzer().analyze("mức phạt ngày 01/02/2024", current_date=TODAY)
    assert current.intent is QueryIntent.CURRENT and current.effective_date == TODAY
    assert historical.intent is QueryIntent.HISTORICAL
    assert historical.effective_date == date(2024, 2, 1)


def test_ambiguous_effect_year_requires_query_date() -> None:
    plan = QueryAnalyzer().analyze(
        "mức phạt năm 2024",
        current_date=TODAY,
        effect_change_dates=[date(2024, 7, 1)],
    )
    assert plan.missing_query_information == ["query_date"]
    assert plan.effective_date is None


def test_comparison_requires_two_dates() -> None:
    plan = QueryAnalyzer().analyze("so sánh năm 2023 và năm 2025", current_date=TODAY)
    assert plan.intent is QueryIntent.COMPARISON
    assert plan.comparison_from == date(2023, 7, 1)
    assert plan.comparison_to == date(2025, 7, 1)


def test_out_of_scope_has_no_evidence_plan() -> None:
    plan = QueryAnalyzer().analyze("tư vấn cá nhân về tai nạn ở Mỹ", current_date=TODAY)
    assert plan.intent is QueryIntent.OUT_OF_SCOPE
    assert plan.required_evidence == []


def test_fallback_is_injected_not_called_for_deterministic_reference() -> None:
    calls: list[str] = []

    def fallback(question: str, current_date: date) -> QueryPlan:
        calls.append(question)
        return QueryPlan(
            intent=QueryIntent.CURRENT,
            effective_date=current_date,
            comparison_from=None,
            comparison_to=None,
            vehicle_type=None,
            document_number=None,
            article=None,
            clause=None,
            point=None,
            legal_entities=[],
            normalized_query=question,
            required_evidence=[EvidenceType.VIOLATION_DEFINITION],
            missing_query_information=[],
        )

    QueryAnalyzer(fallback).analyze("Điều 7 Nghị định 168/2024/NĐ-CP", current_date=TODAY)
    assert calls == []


def test_query_plan_forbids_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        QueryPlan(
            intent=QueryIntent.CURRENT,
            effective_date=TODAY,
            comparison_from=None,
            comparison_to=None,
            vehicle_type=None,
            document_number=None,
            article=None,
            clause=None,
            point=None,
            legal_entities=[],
            normalized_query="q",
            required_evidence=[],
            missing_query_information=[],
            unexpected="nope",
        )


def test_evidence_mapping_for_multi_requirement_questions() -> None:
    assert required_evidence_for(QueryIntent.CURRENT, "phạt bao nhiêu và bị trừ bao nhiêu điểm?") == [
        EvidenceType.VIOLATION_DEFINITION,
        EvidenceType.MONETARY_PENALTY,
        EvidenceType.LICENSE_POINTS,
    ]
    assert required_evidence_for(QueryIntent.CURRENT, "thủ tục nộp phạt") == [EvidenceType.PROCEDURE]
