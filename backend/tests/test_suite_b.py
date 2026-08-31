from __future__ import annotations

import pytest

from app.evaluation.suites.suite_b import (
    E1,
    E3,
    VARIANTS,
    SuiteBPrerequisiteError,
    collection_config,
    run_suite_b,
    variant_descriptor,
)


def test_variant_descriptors_are_immutable_and_exact() -> None:
    assert [(v.key, v.name, v.model_id, v.vector_size) for v in VARIANTS] == [
        ("E1", "Gemini Embedding 2", "gemini-embedding-2", 768),
        ("E2", "Jina Embeddings v5 text-nano", "jina-embeddings-v5-text-nano", 768),
        ("E3", "Jina Embeddings v5 text-small", "jina-embeddings-v5-text-small", 1024),
    ]
    with pytest.raises((AttributeError, TypeError)):
        E1.vector_size = 1024  # type: ignore[misc]
    assert variant_descriptor("E3") is E3


def test_non_768_variant_gets_isolated_sized_collection() -> None:
    config = collection_config(E3)
    assert config["vectors_config"]["dense"].size == 1024
    assert collection_config(E1)["vectors_config"]["dense"].size == 768


def test_runner_refuses_incomplete_development_set_before_side_effects() -> None:
    with pytest.raises(SuiteBPrerequisiteError, match="VNLRAG-92 incomplete"):
        run_suite_b([], lambda *_: {"retrieved": []}, session=None, storage=None)  # type: ignore[arg-type]


def test_unknown_variant_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown Suite B variant"):
        variant_descriptor("E4")


def test_runner_appends_failed_questions_and_aggregates_optional_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import app.evaluation.suites.suite_b as suite_b

    records = [
        SimpleNamespace(
            id=f"q-{index}", question=f"question {index}",
            category=SimpleNamespace(value="CURRENT"), expected_provision_ids=["p-1"],
        )
        for index in range(40)
    ]
    appended: list[dict[str, object]] = []
    finished: list[dict[str, object]] = []

    class Writer:
        def start(self, *args: object, **kwargs: object) -> str:
            return "run-1"

        def append_result(self, run_id: str, result: dict[str, object], **kwargs: object) -> None:
            appended.append(result)

        def finish(self, run_id: str, **kwargs: object) -> None:
            finished.append(kwargs)

    monkeypatch.setattr(suite_b, "_records", lambda _: records)

    def retrieve(record: object, variant: object) -> dict[str, object]:
        if record.id == "q-1":
            raise RuntimeError("provider unavailable")
        return {
            "retrieved": ["p-1"], "latency_ms": 10,
            "token_usage": {"total": 2}, "estimated_cost": 0.5,
        }

    assert run_suite_b(
        records, retrieve, session=None, storage=None, writer=Writer(), variants=("E1",)
    ) == ["run-1"]
    assert len(appended) == 40
    failed = next(result for result in appended if result["question_id"] == "q-1")
    assert failed["retrieval"]["status"] == "FAILED"
    metrics = finished[0]["metrics"]
    assert metrics["latency_ms"]["value"] == 10
    assert metrics["token_usage"]["value"] == {"total": 78.0}
    assert finished[0]["metric_availability"]["recall@5"] == "ABSENT_PROVIDER_FAILURE"
