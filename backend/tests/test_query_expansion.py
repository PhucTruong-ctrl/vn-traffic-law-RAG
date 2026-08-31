from datetime import date

import pytest
from pydantic import ValidationError

from app.query.expansion import QueryExpander, QueryVariant
from app.query.hyde import HyDEGenerator
from app.query.query_understanding import QueryPlan
from app.query.query_understanding_types import EvidenceType, QueryIntent


def plan(text: str) -> QueryPlan:
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
        normalized_query=text,
        required_evidence=[],
        missing_query_information=[],
    )


def test_original_is_first_and_normalization_keeps_diacritics() -> None:
    variants = QueryExpander().expand(plan("GPLX phat tien"))
    assert variants[0] == QueryVariant(text="GPLX phat tien", source="original")
    assert variants[1].text == "giấy phép lái xe phạt tiền"
    assert variants[1].source == "normalized"

def test_original_preserves_raw_question_when_plan_is_normalized() -> None:
    variants = QueryExpander().expand(
        plan("giấy phép lái xe phạt tiền").model_copy(
            update={"original_query": "GPLX phat tien"}
        )
    )
    assert variants[0] == QueryVariant(text="GPLX phat tien", source="original")
    assert variants[1] == QueryVariant(text="giấy phép lái xe phạt tiền", source="normalized")


def test_rewrites_are_bounded_and_not_recursive() -> None:
    seen: list[str] = []

    def rewrite(query: str) -> list[str]:
        seen.append(query)
        return ["r1", "r2", "r3", "r4"]

    variants = QueryExpander(rewrite_provider=rewrite).expand(plan("mức phạt"))
    assert [variant.source for variant in variants] == [
        "original",
        "rewrite",
        "rewrite",
        "rewrite",
    ]
    assert [variant.text for variant in variants] == ["mức phạt", "r1", "r2", "r3"]
    assert seen == ["mức phạt"]


def test_hyde_requires_repair_budget_and_is_dense_only() -> None:
    calls: list[EvidenceType] = []

    def hyde(query: str, gap: EvidenceType) -> str:
        calls.append(gap)
        return f"hypothetical {gap.value}"

    generator = HyDEGenerator(hyde)
    expander = QueryExpander(hyde_provider=generator)
    variants = expander.expand(
        plan("mức phạt"),
        repair_attempts=0,
        evidence_gaps=[EvidenceType.MONETARY_PENALTY, EvidenceType.MONETARY_PENALTY],
    )
    assert len([v for v in variants if v.source == "hyde"]) == 1
    assert variants[-1].dense_only
    assert calls == [EvidenceType.MONETARY_PENALTY]

    bounded = expander.expand(
        plan("mức phạt"), repair_attempts=3, evidence_gaps=[EvidenceType.MONETARY_PENALTY]
    )
    assert bounded[-1].source != "hyde"


def test_hyde_is_bounded_once_per_evidence_type_across_attempts() -> None:
    calls: list[EvidenceType] = []

    def provider(query: str, gap: EvidenceType) -> str:
        calls.append(gap)
        return f"hypothetical {gap.value}"

    expander = QueryExpander(hyde_provider=provider)
    first = expander.expand(
        plan("mức phạt"),
        repair_attempts=0,
        evidence_gaps=[EvidenceType.MONETARY_PENALTY],
    )
    second = expander.expand(
        plan("mức phạt"),
        repair_attempts=1,
        evidence_gaps=[EvidenceType.MONETARY_PENALTY],
        existing_variants=first,
    )

    assert calls == [EvidenceType.MONETARY_PENALTY]
    assert [variant for variant in second if variant.source == "hyde"] == []


def test_hyde_does_not_repeat_existing_variant() -> None:
    def provider(query: str, gap: EvidenceType) -> str:
        return "already generated"

    expander = QueryExpander(hyde_provider=provider)
    variants = expander.expand(
        plan("q"),
        evidence_gaps=[EvidenceType.PROCEDURE],
        existing_variants=[QueryVariant(text="already generated", source="hyde")],
    )
    assert all(variant.text != "already generated" for variant in variants)


def test_query_variant_is_strict() -> None:
    with pytest.raises(ValidationError):
        QueryVariant(text="q", source="original", extra="nope")
    with pytest.raises(ValidationError):
        QueryVariant(text=1, source="original")  # type: ignore[arg-type]


def test_query_expander_rejects_malformed_rewrite_output() -> None:
    def rewrite(_query: str) -> list[object]:
        return [123]

    with pytest.raises(ValidationError):
        QueryExpander(rewrite_provider=rewrite).expand(plan("q"))  # type: ignore[arg-type]
