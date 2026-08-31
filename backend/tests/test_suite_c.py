from __future__ import annotations

from datetime import date

import pytest

from app.evaluation.gold_set import GoldCategory, GoldRecord, ReviewStatus
from app.evaluation.suites.suite_c import (
    VARIANTS,
    ValidationSetBlocked,
    run_suite_c,
    validate_validation_set,
)


def valid_records(count: int = 40) -> list[GoldRecord]:
    records: list[GoldRecord] = []
    for index in range(count):
        payload = {
            "id": str(index),
            "question": f"question {index}",
            "category": GoldCategory.OUT_OF_SCOPE,
            "query_date": date(2025, 1, 1),
            "expected_provision_ids": [],
            "acceptable_provision_ids": [],
            "required_evidence": [],
            "must_include_facts": [],
            "must_not_include_facts": [],
            "temporal_metadata": {"basis": "query_date"},
            "review_status": ReviewStatus.APPROVED,
            "reviewed_by": "test",
            "gold_version": "v1",
            "hash": "0" * 64,
        }
        record = GoldRecord.model_validate(payload)
        payload["hash"] = record.computed_hash()
        records.append(GoldRecord.model_validate(payload))
    return records


def test_variants_are_exact_cumulative_r1_to_r10() -> None:
    assert [variant.name for variant in VARIANTS] == [f"R{i}" for i in range(1, 11)]
    assert VARIANTS[0].additions == ("legal_chunk", "dense")
    assert VARIANTS[1].additions[-1] == "sparse_rrf"
    assert VARIANTS[-1].additions[-1] == "complete_pipeline"
    assert all(
        set(VARIANTS[index].additions) <= set(VARIANTS[index + 1].additions)
        for index in range(9)
    )


def test_incomplete_validation_set_blocks_without_running() -> None:
    with pytest.raises(ValidationSetBlocked, match="exactly 40") as error:
        validate_validation_set([{"id": "draft"}])
    assert error.value.actual == 1


def test_runner_never_invokes_evaluator_when_validation_set_is_incomplete() -> None:
    called = False

    def evaluator(*_args: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    class Writer:
        def start(self, *_args: object, **_kwargs: object) -> str:
            raise AssertionError("writer must not be touched")

    with pytest.raises(ValidationSetBlocked):
        run_suite_c(
            [],
            evaluator=evaluator,
            writer=Writer(),
            manifest_for=lambda _: None,
            session=None,
            storage=None,
        )
    assert not called


def test_runner_retains_provider_failure_in_raw_result() -> None:
    records = valid_records()
    calls: list[str] = []

    class Storage:
        def __init__(self) -> None:
            self.results: list[dict[str, object]] = []

    storage = Storage()

    class Writer:
        def __init__(self) -> None:
            self.results: list[dict[str, object]] = []
            self.finished: list[dict[str, object]] = []

        def start(self, *_args: object, **_kwargs: object) -> str:
            return "run-1"

        def append_result(
            self, _run_id: str, result: dict[str, object], *,
            session: object, storage: Storage,
        ) -> None:
            storage.results.append(result)
            self.results.append(result)

        def finish(self, _run_id: str, **kwargs: object) -> None:
            self.finished.append(kwargs)

    writer = Writer()

    def evaluator(variant: object, record: object) -> dict[str, object]:
        calls.append(str(record))
        if len(calls) == 1:
            raise RuntimeError("provider unavailable")
        if len(calls) == 2:
            return {
                "status": "FAILED",
                "error": "provider returned failure",
                "provision_ids": [],
            }
        return {"status": "OK", "provision_ids": []}

    run_ids = run_suite_c(
        records,
        evaluator=evaluator,
        writer=writer,
        manifest_for=lambda variant: None,
        session=None,
        storage=storage,
        variants=VARIANTS[:1],
    )
    assert run_ids == ["run-1"]
    assert len(writer.results) == len(storage.results) == 40
    assert writer.results[0]["retrieval"]["outcome"] == {
        "status": "FAILED",
        "error": "RuntimeError: provider unavailable",
    }
    assert writer.results[1]["retrieval"]["outcome"]["status"] == "FAILED"
    assert writer.finished[0]["status"] == "FAILED"
    availability = writer.finished[0]["metric_availability"]
    assert availability["recall@5"] == "ABSENT_EVALUATOR_FAILURE"


@pytest.mark.parametrize(
    ("field", "value"),
    [("retrieved", "not-a-ranking"), ("provision_ids", None)],
)
def test_runner_rejects_malformed_rankings_without_dropping_raw_result(
    field: str, value: object,
) -> None:
    class Writer:
        def __init__(self) -> None:
            self.results: list[dict[str, object]] = []
            self.finished: list[dict[str, object]] = []

        def start(self, *_args: object, **_kwargs: object) -> str:
            return "run-1"

        def append_result(
            self, _run_id: str, result: dict[str, object], **_kwargs: object,
        ) -> None:
            self.results.append(result)

        def finish(self, _run_id: str, **kwargs: object) -> None:
            self.finished.append(kwargs)

    writer = Writer()

    def evaluator(_variant: object, record: GoldRecord) -> dict[str, object]:
        if record.id == "0":
            return {field: value, "status": "OK", "raw": {"provider": "evidence"}}
        return {"provision_ids": ["p-1"], "status": "OK"}

    run_suite_c(
        valid_records(),
        evaluator=evaluator,
        writer=writer,
        manifest_for=lambda _variant: None,
        session=None,
        storage=None,
        variants=VARIANTS[:1],
    )

    outcome = writer.results[0]["retrieval"]["outcome"]
    assert outcome[field] == value
    assert outcome["status"] == "FAILED"
    assert "non-string Sequence" in outcome["error"]
    assert outcome["raw"] == {"provider": "evidence"}
    assert writer.finished[0]["status"] == "FAILED"
    assert writer.finished[0]["metric_availability"]["recall@5"] == (
        "ABSENT_EVALUATOR_FAILURE"
    )
    assert "0" not in writer.finished[0]["metrics"]["recall@5"]["per_query"]
