from datetime import date

import pytest
from pydantic import ValidationError

from app.evaluation.gold_set import (
    DatasetSplit,
    GoldCategory,
    GoldOutcome,
    GoldRecord,
    assign_split,
    validate_record,
)


def payload() -> dict:
    value = {
        "id": "q-001",
        "question": "Luật hiện hành là gì?",
        "category": "CURRENT",
        "query_date": "2026-08-26",
        "expected_provision_ids": ["p-1"],
        "acceptable_provision_ids": ["p-1", "p-2"],
        "required_evidence": ["p-1"],
        "must_include_facts": ["effective"],
        "must_not_include_facts": [],
        "temporal_metadata": {"basis": "query_date"},
        "review_status": "REVIEWED",
        "reviewed_by": "reviewer",
        "gold_version": "v1",
    }
    value["evidence_required"] = True
    value["expected_status"] = GoldOutcome.VERIFIED.value
    value["hash"] = GoldRecord.model_validate({**value, "hash": "0" * 64}).computed_hash()
    return value


def test_all_categories_are_accepted() -> None:
    for category in GoldCategory:
        item = payload()
        item["category"] = category.value
        if category is GoldCategory.OUT_OF_SCOPE:
            item["expected_provision_ids"] = []
            item["acceptable_provision_ids"] = []
            item["required_evidence"] = []
            item["evidence_required"] = False
            item["expected_status"] = "OUT_OF_SCOPE"
        elif category in {
            GoldCategory.MISSING_INFORMATION,
            GoldCategory.AMBIGUOUS,
            GoldCategory.COLLOQUIAL_QUERY,
            GoldCategory.ADVERSARIAL_CITATION,
        }:
            item["required_evidence"] = []
            item["evidence_required"] = False
            item["expected_status"] = "INSUFFICIENT_EVIDENCE"
        item["hash"] = GoldRecord.model_validate({**item, "hash": "0" * 64}).computed_hash()
        assert validate_record(item).category is category


def test_cross_field_invariants_are_rejected() -> None:
    item = payload()
    item["expected_provision_ids"] = ["not-accepted"]
    with pytest.raises(ValidationError, match="subset"):
        validate_record(item, verify_hash=False)
    item = payload()
    item["required_evidence"] = []
    item["evidence_required"] = True
    with pytest.raises(ValidationError, match="match required_evidence"):
        validate_record(item, verify_hash=False)
    item = payload()
    item["temporal_metadata"] = {}
    with pytest.raises(ValidationError, match="must not be empty"):
        validate_record(item, verify_hash=False)
    item = payload()
    item["expected_status"] = "INVALID"
    with pytest.raises(ValidationError, match="normal evidence-backed"):
        validate_record(item, verify_hash=False)
    item = payload()
    item["category"] = "OUT_OF_SCOPE"
    item["expected_provision_ids"] = []
    item["acceptable_provision_ids"] = []
    item["required_evidence"] = []
    item["evidence_required"] = False
    item["expected_status"] = "OUT_OF_SCOPE"
    record = GoldRecord.model_validate({**item, "hash": "0" * 64})
    assert record.expected_status is GoldOutcome.OUT_OF_SCOPE
    item["hash"] = record.computed_hash()
    assert validate_record(item).evidence_required is False


def test_abstention_categories_require_insufficient_evidence() -> None:
    item = payload()
    item["category"] = "AMBIGUOUS"
    item["required_evidence"] = []
    item["evidence_required"] = False
    item["expected_status"] = "INSUFFICIENT_EVIDENCE"
    assert (
        GoldRecord.model_validate({**item, "hash": "0" * 64}).expected_status
        is GoldOutcome.INSUFFICIENT_EVIDENCE
    )
    item["expected_status"] = "VERIFIED"
    with pytest.raises(ValidationError, match="requires INSUFFICIENT_EVIDENCE"):
        GoldRecord.model_validate({**item, "hash": "0" * 64})


def test_evidence_required_must_match_evidence_list() -> None:
    item = payload()
    item["evidence_required"] = False
    with pytest.raises(ValidationError, match="match required_evidence"):
        GoldRecord.model_validate({**item, "hash": "0" * 64})
    item = payload()
    item["category"] = "OUT_OF_SCOPE"
    with pytest.raises(ValidationError, match="OUT_OF_SCOPE"):
        validate_record(item, verify_hash=False)


def test_required_fields_and_unknown_fields_are_rejected() -> None:
    item = payload()
    del item["question"]
    with pytest.raises(ValidationError):
        validate_record(item, verify_hash=False)
    item = payload()
    item["unexpected"] = True
    with pytest.raises(ValidationError):
        validate_record(item, verify_hash=False)


def test_hash_is_stable_for_equivalent_json_order() -> None:
    first = payload()
    second = dict(reversed(list(first.items())))
    assert validate_record(first).computed_hash() == (validate_record(second).computed_hash())


def test_hash_tampering_fails_clearly() -> None:
    item = payload()
    item["hash"] = "0" * 64
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_record(item)


def test_split_assignment_is_deterministic_and_exhaustive() -> None:
    assert assign_split("same-id") == assign_split("same-id")
    assert {assign_split(f"id-{n}") for n in range(100)} == set(DatasetSplit)
    with pytest.raises(ValueError):
        assign_split("")


def test_date_is_normalized_by_pydantic() -> None:
    record = validate_record(payload())
    assert record.query_date == date(2026, 8, 26)
