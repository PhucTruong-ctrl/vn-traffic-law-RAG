from __future__ import annotations

import pytest

from app.evaluation.suites.suite_c import (
    VARIANTS,
    ValidationSetBlocked,
    run_suite_c,
    validate_validation_set,
)


def test_variants_are_exact_cumulative_r1_to_r10() -> None:
    assert [variant.name for variant in VARIANTS] == [f"R{i}" for i in range(1, 11)]
    assert VARIANTS[0].additions == ("legal_chunk", "dense")
    assert VARIANTS[1].additions[-1] == "sparse_rrf"
    assert VARIANTS[-1].additions[-1] == "complete_pipeline"
    assert all(set(VARIANTS[index].additions) <= set(VARIANTS[index + 1].additions) for index in range(9))


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
            [], evaluator=evaluator, writer=Writer(), manifest_for=lambda _: None, session=None, storage=None
        )
    assert not called


def test_runner_retains_provider_failure_in_raw_result() -> None:
    records = [{"id": str(index), "question": f"question {index}"} for index in range(40)]
    calls: list[str] = []

    class Writer:
        def __init__(self) -> None:
            self.results: list[dict[str, object]] = []

        def start(self, *_args: object, **_kwargs: object) -> str:
            return "run-1"

        def append_result(self, _run_id: str, result: dict[str, object], **_kwargs: object) -> None:
            self.results.append(result)

        def finish(self, *_args: object, **_kwargs: object) -> None:
            return None

    writer = Writer()

    def evaluator(variant: object, record: object) -> dict[str, object]:
        calls.append(str(record))
        if len(calls) == 1:
            raise RuntimeError("provider unavailable")
        return {"status": "OK", "provision_ids": []}

    run_ids = run_suite_c(
        records,
        evaluator=evaluator,
        writer=writer,
        manifest_for=lambda variant: None,
        session=None,
        storage=None,
        variants=VARIANTS[:1],
    )
    assert run_ids == ["run-1"]
    assert len(writer.results) == 40
    assert writer.results[0]["retrieval"]["outcome"] == {
        "status": "FAILED",
        "error": "RuntimeError: provider unavailable",
    }
