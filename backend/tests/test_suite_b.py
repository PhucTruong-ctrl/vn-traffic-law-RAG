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
