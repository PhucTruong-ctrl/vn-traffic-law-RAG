from __future__ import annotations

from unittest.mock import Mock

import pytest
from sqlalchemy import CheckConstraint

from app.evaluation.run import EvaluationRunManifest, EvaluationRunWriter
from app.persistence.models import EvaluationRun


class MemoryStorage:
    def __init__(self, keys: set[str] | None = None) -> None:
        self.keys = keys or set()
        self.puts: list[str] = []

    def list(self, bucket: str, prefix: str = "") -> list[str]:
        return sorted(key for key in self.keys if key.startswith(prefix))

    def put(self, bucket: str, key: str, data: bytes, *, content_type: str | None = None) -> None:
        self.puts.append(key)


class FailingStorage(MemoryStorage):
    def put(self, bucket: str, key: str, data: bytes, *, content_type: str | None = None) -> None:
        raise OSError("object storage unavailable")


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


def test_start_rejects_preexisting_per_question_artifact() -> None:
    run_id = "run-with-existing-result"
    question_id = "q1"
    result_path = EvaluationRunWriter._result_path(run_id, question_id)
    storage = MemoryStorage({result_path})
    session = Mock()
    session.scalar.return_value = None

    with pytest.raises(ValueError, match="evaluation artifacts already exist"):
        EvaluationRunWriter().start(manifest(run_id=run_id), session=session, storage=storage)

    session.add.assert_not_called()
    assert storage.puts == []


def test_append_rejects_preexisting_per_question_artifact() -> None:
    run_id = "running-run"
    question_id = "q1"
    result_path = EvaluationRunWriter._result_path(run_id, question_id)
    storage = MemoryStorage({result_path})
    session = Mock()
    run = Mock(id="database-run", status="RUNNING")
    session.scalar.side_effect = [run, None]
    writer = EvaluationRunWriter()
    writer._storage_by_run[run_id] = storage

    with pytest.raises(ValueError, match="evaluation artifact already exists"):
        writer.append_result(run_id, {"question_id": question_id}, session=session)

    session.add.assert_not_called()
    assert storage.puts == []


def test_start_storage_failure_does_not_add_dangling_run_row() -> None:
    session = Mock()
    session.scalar.return_value = None

    with pytest.raises(OSError, match="object storage unavailable"):
        EvaluationRunWriter().start(manifest(run_id="storage-failure"), session=session,
                                    storage=FailingStorage())

    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_append_storage_failure_does_not_add_dangling_result_row() -> None:
    session = Mock()
    run = Mock(id="database-run", status="RUNNING")
    session.scalar.side_effect = [run, None]
    writer = EvaluationRunWriter()
    writer._storage_by_run["running-run"] = FailingStorage()

    with pytest.raises(OSError, match="object storage unavailable"):
        writer.append_result("running-run", {"question_id": "q1"}, session=session)

    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_finish_storage_failure_does_not_mutate_run_row() -> None:
    session = Mock()
    run = Mock(id="database-run", status="RUNNING")
    session.scalar.return_value = run
    storage = FailingStorage()
    writer = EvaluationRunWriter()
    writer._storage_by_run["running-run"] = storage

    with pytest.raises(OSError, match="object storage unavailable"):
        writer.finish("running-run", metrics={"recall": 1}, metric_availability={},
                      status="COMPLETED", session=session, storage=storage)

    assert run.status == "RUNNING"
    session.flush.assert_not_called()


def test_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        manifest(unexpected="nope")


def test_evaluation_run_has_non_null_metric_availability_and_status_check() -> None:
    table = EvaluationRun.__table__
    assert table.c.metric_availability.nullable is False
    checks = [c for c in table.constraints if isinstance(c, CheckConstraint)]
    assert any("RUNNING" in str(c.sqltext) and "FAILED" in str(c.sqltext) for c in checks)
