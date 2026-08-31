from __future__ import annotations

import json
from unittest.mock import Mock

import pytest
from sqlalchemy import CheckConstraint

from app.evaluation.run import EvaluationRunManifest, EvaluationRunWriter
from app.persistence.models import EvaluationRun


class MemoryStorage:
    def __init__(self, keys: set[str] | None = None) -> None:
        self.data = {
            key: json.dumps({
                "run_id": key.split("/", 1)[0],
                "format": "per-question-jsonl",
                "results_prefix": f"{key.split('/', 1)[0]}/results/",
            }).encode()
            for key in (keys or set())
        }
        self.puts: list[str] = []

    def list(self, bucket: str, prefix: str = "") -> list[str]:
        return sorted(key for key in self.data if key.startswith(prefix))

    def get(self, bucket: str, key: str) -> bytes:
        return self.data[key]

    def put(self, bucket: str, key: str, data: bytes, *, content_type: str | None = None) -> None:
        self.data[key] = data
        self.puts.append(key)

    def delete(self, bucket: str, key: str) -> None:
        self.data.pop(key, None)

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


def running(run_id: str) -> Mock:
    return Mock(id="database-run", run_id=run_id, status="RUNNING",
                raw_results_path=EvaluationRunWriter._run_path(run_id))


def test_manifest_hash_is_stable_and_changes_with_inputs() -> None:
    assert manifest().manifest_hash() == manifest().manifest_hash()
    assert manifest(config_snapshot={"k": 2}).manifest_hash() != manifest().manifest_hash()


def test_start_rejects_preexisting_per_question_artifact() -> None:
    run_id = "run-with-existing-result"
    result_path = EvaluationRunWriter._result_path(run_id, "q1")
    storage = MemoryStorage({result_path})
    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(ValueError, match="evaluation artifacts already exist"):
        EvaluationRunWriter().start(manifest(run_id=run_id), session=session, storage=storage)
    session.add.assert_not_called()
    assert storage.puts == []


def test_append_rejects_preexisting_per_question_artifact() -> None:
    run_id = "running-run"
    storage = MemoryStorage({EvaluationRunWriter._run_path(run_id),
                             EvaluationRunWriter._result_path(run_id, "q1")})
    session = Mock()
    session.scalar.side_effect = [running(run_id), None]
    with pytest.raises(ValueError, match="evaluation artifact already exists"):
        EvaluationRunWriter().append_result(run_id, {"question_id": "q1"},
                                            session=session, storage=storage)
    session.add.assert_not_called()
    assert storage.puts == []


def test_running_run_resumes_after_writer_restart() -> None:
    run_id = "resumable-run"
    storage = MemoryStorage()
    start_session = Mock()
    start_session.scalar.return_value = None
    EvaluationRunWriter().start(manifest(run_id=run_id), session=start_session, storage=storage)
    session = Mock()
    session.scalar.side_effect = [running(run_id), None, running(run_id)]
    EvaluationRunWriter().append_result(run_id, {"question_id": "q1"},
                                        session=session, storage=storage)
    resumed_storage = MemoryStorage(set(storage.data))
    EvaluationRunWriter().finish(run_id, metrics={"recall": 1}, metric_availability={},
                                 status="COMPLETED", session=session, storage=resumed_storage)
    assert EvaluationRunWriter._finish_path(run_id) in resumed_storage.data


def test_start_storage_failure_does_not_add_dangling_run_row() -> None:
    session = Mock()
    session.scalar.return_value = None
    with pytest.raises(OSError, match="object storage unavailable"):
        EvaluationRunWriter().start(manifest(run_id="storage-failure"), session=session,
                                    storage=FailingStorage())
    session.add.assert_not_called()
    session.flush.assert_not_called()

def test_start_flush_failure_cleans_descriptor_for_retry() -> None:
    run_id = "retryable-start"
    storage = MemoryStorage()
    session = Mock()
    session.scalar.return_value = None
    session.flush.side_effect = [RuntimeError("flush failed"), None]
    writer = EvaluationRunWriter()

    with pytest.raises(RuntimeError, match="flush failed"):
        writer.start(manifest(run_id=run_id), session=session, storage=storage)
    descriptor_path = EvaluationRunWriter._run_path(run_id)
    assert descriptor_path not in storage.data
    session.expunge.assert_called_once()

    writer.start(manifest(run_id=run_id), session=session, storage=storage)
    assert descriptor_path in storage.data


def test_append_storage_failure_does_not_add_dangling_result_row() -> None:
    run_id = "running-run"
    storage = FailingStorage({EvaluationRunWriter._run_path(run_id)})
    session = Mock()
    session.scalar.side_effect = [running(run_id), None]
    with pytest.raises(OSError, match="object storage unavailable"):
        EvaluationRunWriter().append_result(run_id, {"question_id": "q1"},
                                            session=session, storage=storage)
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_append_flush_failure_cleans_object_for_retry() -> None:
    run_id = "retryable-append"
    storage = MemoryStorage({EvaluationRunWriter._run_path(run_id)})
    session = Mock()
    session.scalar.side_effect = [running(run_id), None, running(run_id), None]
    session.flush.side_effect = [RuntimeError("flush failed"), None]
    writer = EvaluationRunWriter()
    result = {"question_id": "q1"}

    with pytest.raises(RuntimeError, match="flush failed"):
        writer.append_result(run_id, result, session=session, storage=storage)
    assert EvaluationRunWriter._result_path(run_id, "q1") not in storage.data

    writer.append_result(run_id, result, session=session, storage=storage)
    assert EvaluationRunWriter._result_path(run_id, "q1") in storage.data


def test_finish_flush_failure_cleans_object_for_retry() -> None:
    run_id = "retryable-finish"
    storage = MemoryStorage({EvaluationRunWriter._run_path(run_id)})
    session = Mock()
    run = running(run_id)
    session.scalar.side_effect = [run, run]
    session.flush.side_effect = [RuntimeError("flush failed"), None]
    writer = EvaluationRunWriter()

    with pytest.raises(RuntimeError, match="flush failed"):
        writer.finish(run_id, metrics={"recall": 1}, metric_availability={},
                      status="COMPLETED", session=session, storage=storage)
    assert EvaluationRunWriter._finish_path(run_id) not in storage.data
    assert run.status == "RUNNING"

    writer.finish(run_id, metrics={"recall": 1}, metric_availability={},
                  status="COMPLETED", session=session, storage=storage)
    assert EvaluationRunWriter._finish_path(run_id) in storage.data

def test_finish_storage_failure_does_not_mutate_run_row() -> None:
    run_id = "running-run"
    storage = FailingStorage({EvaluationRunWriter._run_path(run_id)})
    session = Mock()
    run = running(run_id)
    session.scalar.return_value = run
    with pytest.raises(OSError, match="object storage unavailable"):
        EvaluationRunWriter().finish(run_id, metrics={"recall": 1}, metric_availability={},
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
