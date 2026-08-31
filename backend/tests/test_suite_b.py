from __future__ import annotations

from datetime import date

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


def test_manifest_provenance_uses_configured_prompt_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import app.evaluation.suites.suite_b as suite_b

    monkeypatch.setattr(
        suite_b,
        "get_settings",
        lambda: type(
            "Settings",
            (),
            {
                "prompt_source": "CACHE",
                "fallback_prompt_version_query_analyzer": "analyzer-7",
                "fallback_prompt_version_query_rewriter": "rewriter-8",
                "fallback_prompt_version_hyde": "hyde-9",
                "fallback_prompt_version_generator": "generator-10",
                "fallback_prompt_version_claim_verifier": "verifier-11",
            },
        )(),
    )
    prompts, parsers, source = suite_b._manifest_provenance()
    assert prompts["query_analyzer"] == "analyzer-7"
    assert prompts["hyde"] == "hyde-9"
    assert parsers == {"document_ir_schema": "document-ir-v2"}
    assert source == "CACHE"


def test_runner_appends_failed_questions_and_aggregates_optional_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    import app.evaluation.suites.suite_b as suite_b

    records = [
        SimpleNamespace(
            id=f"q-{index}",
            question=f"question {index}",
            query_date=date(2024, 1, 15) if index == 0 else None,
            category=SimpleNamespace(value="CURRENT"),
            expected_provision_ids=["p-1"],
        )
        for index in range(40)
    ]

    class Storage:
        def __init__(self) -> None:
            self.results: list[dict[str, object]] = []

    storage = Storage()
    appended: list[dict[str, object]] = []
    finished: list[dict[str, object]] = []

    class Writer:
        def __init__(self) -> None:
            self.manifests: list[object] = []

        def start(self, manifest: object, *args: object, **kwargs: object) -> str:
            self.manifests.append(manifest)
            return "run-1"

        def append_result(
            self,
            run_id: str,
            result: dict[str, object],
            *,
            session: object,
            storage: Storage,
        ) -> None:
            storage.results.append(result)
            appended.append(result)

        def finish(self, run_id: str, **kwargs: object) -> None:
            finished.append(kwargs)

    monkeypatch.setattr(suite_b, "_records", lambda _: records)

    def retrieve(record: object, variant: object) -> dict[str, object]:
        if record.id == "q-1":
            raise RuntimeError("provider unavailable")
        if record.id == "q-2":
            return {
                "status": "FAILED",
                "error": "provider returned failure",
                "retrieved": [],
            }
        return {
            "retrieved": ["p-1"],
            "latency_ms": 10,
            "token_usage": {"total": 2},
        }

    writer = Writer()
    assert run_suite_b(
        records,
        retrieve,
        session=None,
        storage=storage,
        writer=writer,
        pricing={"gemini-embedding-2": {"total_per_million": 100.0}},
        variants=("E1",),
    ) == ["run-1"]
    manifest = writer.manifests[0]
    assert manifest.prompt_versions == {
        "query_analyzer": "1",
        "query_rewriter": "1",
        "hyde": "1",
        "generator": "1",
        "claim_verifier": "1",
    }
    assert manifest.parser_versions == {"document_ir_schema": "document-ir-v2"}
    assert len(appended) == len(storage.results) == 40
    dated = next(result for result in appended if result["question_id"] == "q-0")
    assert dated["input"] == {"question": "question 0", "query_date": "2024-01-15"}
    undated = next(result for result in appended if result["question_id"] == "q-1")
    assert undated["input"] == {"question": "question 1"}
    failed = next(result for result in appended if result["question_id"] == "q-1")
    assert failed["retrieval"]["status"] == "FAILED"
    returned_failure = next(result for result in appended if result["question_id"] == "q-2")
    assert returned_failure["retrieval"]["status"] == "FAILED"
    metrics = finished[0]["metrics"]
    assert metrics["latency_ms"]["value"] == 10
    assert metrics["token_usage"]["value"] == {"total": 76.0}
    assert metrics["estimated_cost"]["value"] == pytest.approx(0.0002)
    assert finished[0]["metric_availability"]["estimated_cost"] == "AVAILABLE"
    assert finished[0]["status"] == "FAILED"
    assert finished[0]["metric_availability"]["recall@5"] == "ABSENT_PROVIDER_FAILURE"
