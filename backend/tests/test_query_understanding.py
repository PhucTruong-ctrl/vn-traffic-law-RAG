from datetime import date

import pytest
from pydantic import ValidationError

from app.query.evidence_plan import required_evidence_for
from app.query.query_understanding import (
    EvidenceType,
    QueryAnalyzer,
    QueryIntent,
    QueryPlan,
    QueryPlanFallback,
)

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
    assert plan.required_evidence == [
        EvidenceType.VIOLATION_DEFINITION,
        EvidenceType.MONETARY_PENALTY,
    ]


def test_document_number_year_does_not_create_reversed_comparison() -> None:
    plan = QueryAnalyzer().analyze(
        "Nghị định 168/2024/NĐ-CP áp dụng ngày 01/02/2023",
        current_date=TODAY,
    )
    assert plan.intent is QueryIntent.SOURCE_SEARCH
    assert plan.effective_date == date(2023, 2, 1)
    assert plan.comparison_from is None
    assert plan.comparison_to is None


def test_current_and_historical_dates_are_deterministic() -> None:
    current = QueryAnalyzer().analyze("mức phạt hiện nay", current_date=TODAY)
    historical = QueryAnalyzer().analyze("mức phạt ngày 01/02/2024", current_date=TODAY)
    assert current.intent is QueryIntent.CURRENT and current.effective_date == TODAY
    assert historical.intent is QueryIntent.HISTORICAL
    assert historical.effective_date == date(2024, 2, 1)


def test_analyzer_retains_original_question_for_expansion() -> None:
    plan = QueryAnalyzer().analyze("GPLX phat tien", current_date=TODAY)
    assert plan.original_query == "GPLX phat tien"
    assert plan.normalized_query != plan.original_query


def test_invalid_explicit_date_abstains_instead_of_current() -> None:
    plan = QueryAnalyzer().analyze("mức phạt ngày 31/02/2024", current_date=TODAY)
    assert plan.intent is not QueryIntent.CURRENT
    assert plan.effective_date is None
    assert plan.missing_query_information == ["query_date"]


def test_ambiguous_effect_year_requires_query_date() -> None:
    plan = QueryAnalyzer().analyze(
        "mức phạt năm 2024",
        current_date=TODAY,
        effect_change_dates=[date(2024, 7, 1)],
    )
    assert plan.missing_query_information == ["query_date"]
    assert plan.effective_date is None


def test_explicit_date_year_is_not_rechecked_as_ambiguous_effect_year() -> None:
    plan = QueryAnalyzer().analyze(
        "mức phạt ngày 01/02/2024",
        current_date=TODAY,
        effect_change_dates=[date(2024, 7, 1)],
    )
    assert plan.intent is QueryIntent.HISTORICAL
    assert plan.effective_date == date(2024, 2, 1)
    assert plan.missing_query_information == []


def test_comparison_requires_two_dates() -> None:
    plan = QueryAnalyzer().analyze("so sánh năm 2023 và năm 2025", current_date=TODAY)
    assert plan.intent is QueryIntent.COMPARISON
    assert plan.comparison_from == date(2023, 7, 1)
    assert plan.comparison_to == date(2025, 7, 1)


def test_out_of_scope_has_no_evidence_plan() -> None:
    plan = QueryAnalyzer().analyze("tư vấn cá nhân về tai nạn ở Mỹ", current_date=TODAY)
    assert plan.intent is QueryIntent.OUT_OF_SCOPE
    assert plan.required_evidence == []


def test_out_of_scope_precedes_comparison_dates() -> None:
    plan = QueryAnalyzer().analyze(
        "So sánh luật Mỹ năm 2023 và năm 2025 về tư vấn cá nhân",
        current_date=TODAY,
    )
    assert plan.intent is QueryIntent.OUT_OF_SCOPE
    assert plan.comparison_from is None
    assert plan.comparison_to is None
    assert plan.missing_query_information == []


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
    assert required_evidence_for(
        QueryIntent.CURRENT, "phạt bao nhiêu và bị trừ bao nhiêu điểm?"
    ) == [
        EvidenceType.VIOLATION_DEFINITION,
        EvidenceType.MONETARY_PENALTY,
        EvidenceType.LICENSE_POINTS,
    ]
    assert required_evidence_for(QueryIntent.CURRENT, "thủ tục nộp phạt") == [
        EvidenceType.PROCEDURE
    ]


@pytest.mark.parametrize(
    ("question", "extra"),
    [
        ("phạt bao nhiêu và thủ tục nộp phạt", EvidenceType.PROCEDURE),
        ("phạt bao nhiêu và điều kiện áp dụng", EvidenceType.LEGAL_CONDITION),
        ("phạt bao nhiêu và có ngoại lệ nào", EvidenceType.EXCEPTION),
    ],
)
def test_penalty_accumulates_procedure_condition_and_exception(
    question: str, extra: EvidenceType
) -> None:
    assert required_evidence_for(QueryIntent.CURRENT, question) == [
        EvidenceType.VIOLATION_DEFINITION,
        EvidenceType.MONETARY_PENALTY,
        extra,
    ]


def test_suspension_does_not_imply_license_points() -> None:
    evidence = required_evidence_for(
        QueryIntent.CURRENT,
        "Hành vi này có bị tước giấy phép lái xe không?",
        ["giấy phép lái xe"],
    )
    assert evidence == [
        EvidenceType.VIOLATION_DEFINITION,
        EvidenceType.MONETARY_PENALTY,
        EvidenceType.LICENSE_SUSPENSION,
    ]
    assert EvidenceType.LICENSE_POINTS not in evidence


def test_penalty_with_points_and_suspension_requires_all_evidence() -> None:
    assert required_evidence_for(
        QueryIntent.CURRENT,
        "Phạt bao nhiêu, bị trừ bao nhiêu điểm và có bị tước giấy phép không?",
    ) == [
        EvidenceType.VIOLATION_DEFINITION,
        EvidenceType.MONETARY_PENALTY,
        EvidenceType.LICENSE_POINTS,
        EvidenceType.LICENSE_SUSPENSION,
    ]


def _fallback_payload() -> dict[str, object]:
    return {
        "intent": QueryIntent.CURRENT,
        "effective_date": TODAY,
        "comparison_from": None,
        "comparison_to": None,
        "vehicle_type": None,
        "document_number": None,
        "article": None,
        "clause": None,
        "point": None,
        "legal_entities": [],
        "normalized_query": "mức phạt",
        "missing_query_information": [],
        "required_evidence": [
            EvidenceType.VIOLATION_DEFINITION,
            EvidenceType.MONETARY_PENALTY,
        ],
    }


class _FakeModels:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls = 0

    def generate_content(self, **_: object) -> object:
        self.calls += 1
        return self.response


class _FakeClient:
    def __init__(self, response: object) -> None:
        self.models = _FakeModels(response)


def test_structured_fallback_returns_valid_plan() -> None:
    client = _FakeClient(type("Response", (), {"parsed": _fallback_payload()})())
    plan = QueryPlanFallback(client).analyze("mức phạt", current_date=TODAY)
    assert plan.intent is QueryIntent.CURRENT
    assert plan.required_evidence == [
        EvidenceType.VIOLATION_DEFINITION,
        EvidenceType.MONETARY_PENALTY,
    ]
    assert client.models.calls == 1


def test_structured_fallback_invalid_output_abstains() -> None:
    invalid = {"intent": "CURRENT", "unexpected": "reject"}
    client = _FakeClient(type("Response", (), {"parsed": invalid})())
    plan = QueryPlanFallback(client).analyze("mức phạt", current_date=TODAY)
    assert plan.intent is QueryIntent.OUT_OF_SCOPE
    assert plan.missing_query_information == ["query_analysis"]


def test_analyzer_fallback_failure_is_safe_and_deterministic_first() -> None:
    calls: list[str] = []

    def fallback(question: str, current_date: date) -> QueryPlan:
        calls.append(question)
        raise RuntimeError("provider unavailable")

    deterministic = QueryAnalyzer(fallback).analyze(
        "Điều 7 Nghị định 168/2024/NĐ-CP", current_date=TODAY
    )
    assert deterministic.intent is QueryIntent.SOURCE_SEARCH
    assert calls == []
    safe = QueryAnalyzer(fallback).analyze("mức phạt", current_date=TODAY)
    assert safe.intent is QueryIntent.OUT_OF_SCOPE
    assert safe.missing_query_information == ["query_analysis"]
    assert calls == ["mức phạt"]


def test_analyzer_invokes_object_fallback_analyze_method() -> None:
    class Fallback:
        def analyze(self, question: str, *, current_date: date) -> QueryPlan:
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
                required_evidence=[],
                missing_query_information=[],
            )

    plan = QueryAnalyzer(Fallback()).analyze("mức phạt", current_date=TODAY)
    assert plan.intent is QueryIntent.CURRENT


def test_query_plan_rejects_coercive_structured_values() -> None:
    payload = _fallback_payload()
    payload["effective_date"] = TODAY.isoformat()
    with pytest.raises(ValidationError):
        QueryPlan.model_validate(payload)
