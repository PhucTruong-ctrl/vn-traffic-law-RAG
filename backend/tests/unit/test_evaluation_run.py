from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint

from app.evaluation.run import EvaluationRunManifest
from app.persistence.models import EvaluationRun


def manifest(**overrides: object) -> EvaluationRunManifest:
    values: dict[str, object] = {
        "git_commit": "abc", "corpus_version": "v1", "corpus_hash": "c" * 64,
        "gold_set_version": "g1", "gold_set_hash": "g" * 64, "suite": "B", "variant": "E1",
        "config_snapshot": {"k": 1}, "model_ids": {"embedding": "e1"},
        "prompt_versions": {"p": "1"}, "parser_versions": {"parser": "1"},
    }
    values.update(overrides)
    return EvaluationRunManifest.model_validate(values)


def test_manifest_hash_is_stable_and_changes_with_inputs() -> None:
    assert manifest().manifest_hash() == manifest().manifest_hash()
    assert manifest(config_snapshot={"k": 2}).manifest_hash() != manifest().manifest_hash()


def test_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        manifest(unexpected="nope")


def test_evaluation_run_has_non_null_metric_availability_and_status_check() -> None:
    table = EvaluationRun.__table__
    assert table.c.metric_availability.nullable is False
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any("RUNNING" in str(c.sqltext) and "FAILED" in str(c.sqltext) for c in checks)
