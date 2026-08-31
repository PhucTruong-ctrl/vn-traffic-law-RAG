"""Append-only evaluation run manifests and results (VNLRAG-147)."""

from __future__ import annotations

import contextlib
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
from app.storage.object_storage import ObjectStoragePort, get_object_storage

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

    @staticmethod
    def _storage(storage: ObjectStoragePort | None) -> ObjectStoragePort:
        """Resolve storage from composition, never from writer-local state."""
        return storage if storage is not None else get_object_storage()

    @staticmethod
    def _validate_descriptor(run: EvaluationRun, storage: ObjectStoragePort) -> None:
        """Load the durable descriptor before mutating a persisted run."""
        try:
            descriptor = json.loads(storage.get(_BUCKET, run.raw_results_path))
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"evaluation run artifact is unavailable: {run.run_id}") from exc
        if (
            not isinstance(descriptor, dict)
            or descriptor.get("run_id") != run.run_id
            or descriptor.get("format") != "per-question-jsonl"
            or descriptor.get("results_prefix") != f"{run.run_id}/results/"
        ):
            raise ValueError(f"invalid evaluation run artifact: {run.run_id}")

    @staticmethod
    def _result_path(run_id: str, question_id: str) -> str:
        digest = hashlib.sha256(question_id.encode("utf-8")).hexdigest()
        return f"{run_id}/results/{digest}.json"

    @staticmethod
    def _run_path(run_id: str) -> str:
        return f"{run_id}/results.jsonl"

    @staticmethod
    def _finish_path(run_id: str) -> str:
        return f"{run_id}/finished.json"

    @staticmethod
    def _run(run_id: str, session: Session) -> EvaluationRun:
        run = session.scalar(select(EvaluationRun).where(EvaluationRun.run_id == run_id))
        if run is None:
            raise KeyError(f"unknown evaluation run: {run_id}")
        return run

    def start(self, manifest: EvaluationRunManifest, *, session: Session,
              storage: ObjectStoragePort) -> str:
        run_id = manifest.run_id or str(uuid.uuid4())
        if session.scalar(select(EvaluationRun).where(EvaluationRun.run_id == run_id)):
            raise ValueError(f"evaluation run already exists: {run_id}")
        descriptor_path = self._run_path(run_id)
        results_prefix = f"{run_id}/results/"
        if descriptor_path in storage.list(_BUCKET, prefix=descriptor_path):
            raise ValueError(f"evaluation artifact already exists: {descriptor_path}")
        if storage.list(_BUCKET, prefix=results_prefix):
            raise ValueError(f"evaluation artifacts already exist: {results_prefix}")
        # Storage first: failures cannot leave a DB row for a missing artifact.
        storage.put(
            _BUCKET,
            descriptor_path,
            json.dumps({
                "run_id": run_id,
                "format": "per-question-jsonl",
                "results_prefix": results_prefix,
            }).encode(),
            content_type="application/json",
        )
        session.add(EvaluationRun(
            run_id=run_id, git_commit=manifest.git_commit, corpus_version=manifest.corpus_version,
            corpus_hash=manifest.corpus_hash, gold_set_version=manifest.gold_set_version,
            gold_set_hash=manifest.gold_set_hash, suite=manifest.suite, variant=manifest.variant,
            run_manifest_hash=manifest.manifest_hash(), config_snapshot=manifest.config_snapshot,
            model_ids=manifest.model_ids, prompt_versions=manifest.prompt_versions,
            parser_versions=manifest.parser_versions, raw_results_path=descriptor_path,
            status="RUNNING", metric_availability={},
        ))
        session.flush()
        return run_id

    def append_result(
        self, run_id: str, result: Mapping[str, object], *, session: Session,
        storage: ObjectStoragePort | None = None,
    ) -> None:
        run = self._run(run_id, session)
        if run.status != "RUNNING":
            raise ValueError(f"evaluation run is terminal: {run_id}")
        resolved_storage = self._storage(storage)
        self._validate_descriptor(run, resolved_storage)
        question_id = result.get("question_id")
        if not isinstance(question_id, str) or not question_id:
            raise ValueError("result.question_id must be a non-empty string")
        if session.scalar(select(EvaluationResult).where(
            EvaluationResult.evaluation_run_id == run.id,
            EvaluationResult.question_id == question_id,
        )):
            raise ValueError(f"result already appended: {question_id}")
        result_path = self._result_path(run_id, question_id)
        if result_path in resolved_storage.list(_BUCKET, prefix=result_path):
            raise ValueError(f"evaluation artifact already exists: {result_path}")

        def obj(name: str) -> dict[str, Any]:
            value = result.get(name, {})
            if not isinstance(value, Mapping):
                raise ValueError(f"result.{name} must be an object")
            return dict(value)

        payload = json.dumps(dict(result), sort_keys=True, default=str).encode() + b"\n"
        resolved_storage.put(_BUCKET, result_path, payload, content_type="application/x-ndjson")
        row: EvaluationResult | None = None
        try:
            row = EvaluationResult(
                evaluation_run_id=run.id, question_id=question_id, input=obj("input"),
                retrieval=obj("retrieval"), output=obj("output"), metrics=obj("metrics"),
                raw_results_path=result_path,
            )
            session.add(row)
            session.flush()
        except Exception:
            if row is not None:
                with contextlib.suppress(Exception):
                    session.expunge(row)
            with contextlib.suppress(Exception):
                resolved_storage.delete(_BUCKET, result_path)
            raise

    def finish(
        self, run_id: str, *, metrics: Mapping[str, object],
        metric_availability: Mapping[str, str], status: Literal["COMPLETED", "FAILED"],
        session: Session, storage: ObjectStoragePort | None = None,
    ) -> None:
        run = self._run(run_id, session)
        if run.status != "RUNNING":
            raise ValueError(f"evaluation run is terminal: {run_id}")
        resolved_storage = self._storage(storage)
        self._validate_descriptor(run, resolved_storage)
        finish_path = self._finish_path(run_id)
        if resolved_storage.list(_BUCKET, prefix=finish_path):
            raise ValueError(f"evaluation artifact already exists: {finish_path}")
        resolved_storage.put(
            _BUCKET,
            finish_path,
            json.dumps({
                "run_id": run_id,
                "status": status,
                "metrics": dict(metrics),
                "metric_availability": dict(metric_availability),
            }, sort_keys=True, default=str).encode(),
            content_type="application/json",
        )
        original = (run.status, run.metrics, run.metric_availability, run.completed_at)
        try:
            run.status = status
            run.metrics = dict(metrics)
            run.metric_availability = dict(metric_availability)
            run.completed_at = datetime.now(UTC)
            session.flush()
        except Exception:
            run.status, run.metrics, run.metric_availability, run.completed_at = original
            with contextlib.suppress(Exception):
                resolved_storage.delete(_BUCKET, finish_path)
            raise
