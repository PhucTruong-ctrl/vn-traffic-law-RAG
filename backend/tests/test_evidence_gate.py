from datetime import date

import pytest

from app.query.evidence_gate import (
    EvidenceCompletenessGate,
    EvidenceStatus,
    targeted_query_for_gap,
)
from app.query.query_understanding import QueryIntent, QueryPlan
from app.query.query_understanding_types import EvidenceType
from app.retrieval.contracts import RetrievalResult


def _plan(*required: EvidenceType) -> QueryPlan:
    return QueryPlan(
        intent=QueryIntent.CURRENT,
        effective_date=date(2026, 8, 31),
        comparison_from=None,
        comparison_to=None,
        vehicle_type=None,
        document_number=None,
        article=None,
        clause=None,
        point=None,
        legal_entities=[],
        normalized_query="xe máy vượt đèn đỏ",
        required_evidence=list(required),
        missing_query_information=[],
    )


def _result(provision_id: str, text: str) -> RetrievalResult:
    return RetrievalResult(
        rank=1,
        provision_id=provision_id,
        provision_version=1,
        document_id="doc-1",
        document_version_id="version-1",
        text=text,
        source_text=text,
        parent_context=None,
        document_number="168/2024/NĐ-CP",
        article="7",
        clause=None,
        point="đ",
        effective_from=date(2025, 1, 1),
        effective_to=None,
        page_number=1,
        retrieval_sources=["dense"],
        fused_score=None,
        added_by=None,
        source_id=None,
        depth=0,
    )


@pytest.mark.parametrize(
    ("evidence", "text"),
    [
        (EvidenceType.VIOLATION_DEFINITION, "Hành vi vượt đèn đỏ bị xử phạt theo quy định."),
        (EvidenceType.MONETARY_PENALTY, "Phạt tiền 500.000 đồng đối với hành vi này."),
        (EvidenceType.LICENSE_POINTS, "Bị trừ 2 điểm giấy phép lái xe."),
        (EvidenceType.LICENSE_SUSPENSION, "Tước quyền sử dụng giấy phép lái xe 2 tháng."),
        (EvidenceType.EXCEPTION, "Trường hợp được miễn phạt theo quy định."),
        (EvidenceType.PROCEDURE, "Thủ tục nộp phạt thực hiện như sau."),
        (EvidenceType.LEGAL_CONDITION, "Áp dụng khi đáp ứng đủ điều kiện luật định."),
    ],
)
def test_each_evidence_type_is_detected(evidence: EvidenceType, text: str) -> None:
    result = EvidenceCompletenessGate().evaluate(_plan(evidence), [_result("p1", text)])
    assert result.status is EvidenceStatus.COMPLETE
    assert result.evidence_gaps == []
    assert result.covered_provisions == ["p1"]


def test_fine_and_points_stays_incomplete_when_points_are_missing() -> None:
    plan = _plan(
        EvidenceType.VIOLATION_DEFINITION,
        EvidenceType.MONETARY_PENALTY,
        EvidenceType.LICENSE_POINTS,
    )
    context = [_result("fine", "Hành vi vượt đèn đỏ bị phạt tiền 500.000 đồng.")]
    result = EvidenceCompletenessGate().evaluate(plan, context)
    assert result.status is EvidenceStatus.INCOMPLETE
    assert result.evidence_gaps == [EvidenceType.LICENSE_POINTS]


def test_evidence_can_be_covered_by_multiple_provisions() -> None:
    plan = _plan(EvidenceType.MONETARY_PENALTY, EvidenceType.LICENSE_POINTS)
    result = EvidenceCompletenessGate().evaluate(
        plan,
        [
            _result("fine", "Phạt tiền 500.000 đồng."),
            _result("points", "Bị trừ 2 điểm giấy phép lái xe."),
        ],
    )
    assert result.status is EvidenceStatus.COMPLETE
    assert result.covered_provisions == ["fine", "points"]


def test_targeted_query_mentions_original_and_gap_term() -> None:
    query = targeted_query_for_gap(EvidenceType.LICENSE_POINTS, _plan(EvidenceType.LICENSE_POINTS))
    assert query.startswith("xe máy vượt đèn đỏ")
    assert "điểm bị trừ" in query


def test_empty_evidence_plan_is_complete() -> None:
    result = EvidenceCompletenessGate().evaluate(_plan(), [])
    assert result.status is EvidenceStatus.COMPLETE
