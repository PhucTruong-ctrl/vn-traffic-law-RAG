from __future__ import annotations

from datetime import date

import pytest

from app.evaluation.gold_set import GoldCategory, GoldRecord, ReviewStatus
from app.evaluation.suites.suite_d import (
    VARIANTS,
    SuiteDPrerequisiteError,
    run_suite_d,
    validate_validation_set,
)


def records(count: int = 40, *, status: ReviewStatus = ReviewStatus.APPROVED) -> list[GoldRecord]:
    result = []
    for i in range(count):
        payload = {
            "id": str(i),
            "question": f"q{i}",
            "category": GoldCategory.OUT_OF_SCOPE,
            "query_date": date(2025, 1, 1),
            "expected_provision_ids": [],
            "acceptable_provision_ids": [],
            "required_evidence": [],
            "must_include_facts": [],
            "must_not_include_facts": [],
            "temporal_metadata": {"basis": "query_date"},
            "review_status": status,
            "reviewed_by": "test",
            "gold_version": "v1",
            "hash": "0" * 64,
        }
        record = GoldRecord.model_validate(payload)
        payload["hash"] = record.computed_hash()
        result.append(GoldRecord.model_validate(payload))
    return result


def test_g1_to_g7_are_cumulative_and_immutable() -> None:
    assert [v.name for v in VARIANTS] == [f"G{i}" for i in range(1, 8)]
    assert all(
        set(a.layers) <= set(b.layers) for a, b in zip(VARIANTS[:-1], VARIANTS[1:], strict=True)
    )
    with pytest.raises((TypeError, AttributeError)):
        VARIANTS[0].layers += ("x",)  # type: ignore[misc]


def test_incomplete_or_unapproved_gold_blocks_before_side_effects() -> None:
    with pytest.raises(SuiteDPrerequisiteError, match="exactly 40"):
        validate_validation_set(records(39))
    with pytest.raises(SuiteDPrerequisiteError, match="not APPROVED"):
        validate_validation_set(records(40, status=ReviewStatus.DRAFT))


def test_runner_evaluates_all_records_and_persists_raw_outcomes() -> None:
    class Writer:
        def __init__(self) -> None:
            self.results: list[dict[str, object]] = []
            self.finished: list[dict[str, object]] = []

        def start(self, *_: object, **__: object) -> str:
            return "run-g1"

        def append_result(self, _run: str, result: dict[str, object], **__: object) -> None:
            self.results.append(result)

        def finish(self, _run: str, **kwargs: object) -> None:
            self.finished.append(kwargs)

    writer = Writer()
    calls: list[str] = []

    def evaluator(variant: object, record: GoldRecord) -> dict[str, object]:
        calls.append(f"{variant.name}:{record.id}")  # type: ignore[union-attr]
        return {
            "status": "OK",
            "output": {"answer": "deterministic"},
            "metrics": {"citation_precision": 1.0},
        }

    assert run_suite_d(
        records(),
        evaluator=evaluator,
        writer=writer,
        manifest_for=lambda _: None,
        session=None,
        storage=None,
        variants=("G1",),
    ) == ["run-g1"]
    assert len(calls) == len(writer.results) == 40
    assert writer.results[0]["question_id"] == "0"
    assert writer.results[0]["metrics"] == {"citation_precision": 1.0}
    assert writer.finished[0]["status"] == "COMPLETED"


def test_runner_never_starts_writer_for_invalid_gold() -> None:
    class Writer:
        def start(self, *_: object, **__: object) -> str:
            raise AssertionError("writer touched")

    called = False

    def evaluator(*_: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    with pytest.raises(SuiteDPrerequisiteError):
        run_suite_d(
            [],
            evaluator=evaluator,
            writer=Writer(),
            manifest_for=lambda _: None,
            session=None,
            storage=None,
        )
    assert not called
