"""Append-only evaluation run manifests and results (VNLRAG-147)."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.persistence.models import EvaluationResult, EvaluationRun
from app.storage.object_storage import ObjectStoragePort

_BUCKET = "evaluation-artifacts"


class EvaluationRunManifest(BaseModel):
    """The immutable inputs that identify an evaluation run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str | None = None
    git_commit: str
    corpus_version: str
    corpus_hash: str
    gold_set_version: str
    gold_set_hash: str
    suite: str
    variant: str
    config_snapshot: dict[str, Any] = Field(default_factory=dict)
    model_ids: dict[str, Any] = Field(default_factory=dict)
    prompt_versions: dict[str, Any] = Field(default_factory=dict)
    parser_versions: dict[str, Any] = Field(default_factory=dict)

    def manifest_hash(self) -> str:
        payload = {
            "config_snapshot": self.config_snapshot,
            "model_ids": self.model_ids,
            "prompt_versions": self.prompt_versions,
            "corpus_hash": self.corpus_hash,
            "gold_set_hash": self.gold_set_hash,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(encoded.encode()).hexdigest()


class EvaluationRunWriter:
    """Persist a run and append one durable raw result at a time."""

    def __init__(self) -> None:
        self._storage_by_run: dict[str, ObjectStoragePort] = {}

    @staticmethod
    def _result_path(run_id: str, question_id: str) -> str:
        digest = hashlib.sha256(question_id.encode("utf-8")).hexdigest()
        return f"{run_id}/results/{digest}.json"

    @staticmethod
    def _run_path(run_id: str) -> str:
        return f"{run_id}/results.jsonl"

    @staticmethod
    def _run(run_id: str, session: Session) -> EvaluationRun:
        run = session.scalar(select(EvaluationRun).where(EvaluationRun.run_id == run_id))
        if run is None:
            raise KeyError(f"unknown evaluation run: {run_id}")
        return run
    def start(
        self,
        manifest: EvaluationRunManifest,
        *,
        session: Session,
        storage: ObjectStoragePort,
    ) -> str:
        run_id = manifest.run_id or str(uuid.uuid4())
        if session.scalar(select(EvaluationRun).where(EvaluationRun.run_id == run_id)):
            raise ValueError(f"evaluation run already exists: {run_id}")
        path = self._run_path(run_id)
        if storage.list(_BUCKET, prefix=path):
            raise ValueError(f"evaluation artifact already exists: {path}")
        session.add(EvaluationRun(
            run_id=run_id, git_commit=manifest.git_commit, corpus_version=manifest.corpus_version,
            corpus_hash=manifest.corpus_hash, gold_set_version=manifest.gold_set_version,
            gold_set_hash=manifest.gold_set_hash, suite=manifest.suite, variant=manifest.variant,
            run_manifest_hash=manifest.manifest_hash(), config_snapshot=manifest.config_snapshot,
            model_ids=manifest.model_ids, prompt_versions=manifest.prompt_versions,
            parser_versions=manifest.parser_versions, raw_results_path=path, status="RUNNING",
            metric_availability={},
        ))
        session.flush()
        # This immutable marker reserves the run prefix; query results use unique keys.
        storage.put(_BUCKET, path, b"", content_type="application/x-ndjson")
        self._storage_by_run[run_id] = storage
        return run_id

    def append_result(self, run_id: str, result: Mapping[str, object], *, session: Session) -> None:
        run = self._run(run_id, session)
        if run.status != "RUNNING":
            raise ValueError(f"evaluation run is terminal: {run_id}")
        question_id = result.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise ValueError("result.question_id must be a non-empty string")
        if session.scalar(select(EvaluationResult).where(
            EvaluationResult.evaluation_run_id == run.id,
            EvaluationResult.question_id == question_id,
        )):
            raise ValueError(f"result already appended: {question_id}")

        def obj(name: str) -> dict[str, Any]:
            value = result.get(name, {})
            if not isinstance(value, Mapping):
                raise ValueError(f"result.{name} must be an object")
            return dict(value)

        session.add(EvaluationResult(
            evaluation_run_id=run.id, question_id=question_id, input=obj("input"),
            retrieval=obj("retrieval"), output=obj("output"), metrics=obj("metrics"),
        ))
        session.flush()
        payload = json.dumps(dict(result), sort_keys=True, default=str).encode() + b"\n"
        self._storage_by_run[run_id].put(
            _BUCKET, self._result_path(run_id, question_id), payload,
            content_type="application/x-ndjson",
        )

    def finish(self, run_id: str, *, metrics: Mapping[str, object],
               metric_availability: Mapping[str, str], status: Literal["COMPLETED", "FAILED"],
               session: Session, storage: ObjectStoragePort) -> None:
        run = self._run(run_id, session)
        if run.status != "RUNNING":
            raise ValueError(f"evaluation run is terminal: {run_id}")
        if storage is not self._storage_by_run.get(run_id):
            raise ValueError("evaluation artifact storage does not match the run")
        run.status = status
        run.metrics = dict(metrics)
        run.metric_availability = dict(metric_availability)
        run.completed_at = datetime.now(UTC)
        session.flush()
