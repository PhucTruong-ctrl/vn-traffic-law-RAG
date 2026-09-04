import pytest
from pydantic import ValidationError

from app.verification.l1_schema import ClaimType, StructuredAnswer


def claim() -> dict[str, object]:
    return {
        "claim": "Mức phạt là 4.000.000 đồng",
        "claim_type": ClaimType.MONETARY_PENALTY,
        "provision_ids": ["prov-1"],
    }


def test_non_abstaining_answer_requires_summary_and_claims() -> None:
    with pytest.raises(ValidationError):
        StructuredAnswer(answer_summary=" ", claims=[claim()])
    with pytest.raises(ValidationError):
        StructuredAnswer(answer_summary="Có mức phạt", claims=[])


def test_abstaining_answer_may_omit_answer_content() -> None:
    answer = StructuredAnswer(answer_summary="", claims=[], should_abstain=True)
    assert answer.should_abstain


def test_schema_forbids_unknown_fields_and_empty_provision_ids() -> None:
    with pytest.raises(ValidationError):
        StructuredAnswer(answer_summary="Có", claims=[{**claim(), "extra": 1}])
    with pytest.raises(ValidationError):
        StructuredAnswer(answer_summary="Có", claims=[{**claim(), "provision_ids": [" "]}])
    with pytest.raises(ValidationError):
        StructuredAnswer(answer_summary="Có", claims=[{**claim(), "claim_type": "UNKNOWN"}])
