"""Append-only evaluation run manifests and results (VNLRAG-147)."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
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
            "git_commit": self.git_commit,
            "corpus_version": self.corpus_version,
            "corpus_hash": self.corpus_hash,
            "gold_set_version": self.gold_set_version,
            "gold_set_hash": self.gold_set_hash,
            "suite": self.suite,
            "variant": self.variant,
            "config_snapshot": self.config_snapshot,
            "model_ids": self.model_ids,
            "prompt_versions": self.prompt_versions,
            "parser_versions": self.parser_versions,
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

    def start(
        self, manifest: EvaluationRunManifest, *, session: Session, storage: ObjectStoragePort
    ) -> str:
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
            json.dumps(
                {
                    "run_id": run_id,
                    "format": "per-question-jsonl",
                    "results_prefix": results_prefix,
                }
            ).encode(),
            content_type="application/json",
        )
        row = EvaluationRun(
            run_id=run_id,
            git_commit=manifest.git_commit,
            corpus_version=manifest.corpus_version,
            corpus_hash=manifest.corpus_hash,
            gold_set_version=manifest.gold_set_version,
            gold_set_hash=manifest.gold_set_hash,
            suite=manifest.suite,
            variant=manifest.variant,
            run_manifest_hash=manifest.manifest_hash(),
            config_snapshot=manifest.config_snapshot,
            model_ids=manifest.model_ids,
            prompt_versions=manifest.prompt_versions,
            parser_versions=manifest.parser_versions,
            raw_results_path=descriptor_path,
            status="RUNNING",
            metric_availability={},
        )
        try:
            session.add(row)
            session.flush()
        except Exception:
            with contextlib.suppress(Exception):
                session.expunge(row)
            with contextlib.suppress(Exception):
                storage.delete(_BUCKET, descriptor_path)
            raise
        return run_id

    def append_result(
        self,
        run_id: str,
        result: Mapping[str, object],
        *,
        session: Session,
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
        if session.scalar(
            select(EvaluationResult).where(
                EvaluationResult.evaluation_run_id == run.id,
                EvaluationResult.question_id == question_id,
            )
        ):
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
                evaluation_run_id=run.id,
                question_id=question_id,
                input=obj("input"),
                retrieval=obj("retrieval"),
                output=obj("output"),
                metrics=obj("metrics"),
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
        self,
        run_id: str,
        *,
        metrics: Mapping[str, object],
        metric_availability: Mapping[str, str],
        status: Literal["COMPLETED", "FAILED"],
        session: Session,
        storage: ObjectStoragePort | None = None,
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
            json.dumps(
                {
                    "run_id": run_id,
                    "status": status,
                    "metrics": dict(metrics),
                    "metric_availability": dict(metric_availability),
                },
                sort_keys=True,
                default=str,
            ).encode(),
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


def _metric_report(report: Any) -> dict[str, Any]:
    """Serialize a MetricReport without coupling reports to Pydantic."""
    return {
        "value": report.value,
        "status": report.status,
        "numerator": report.numerator,
        "denominator": report.denominator,
        "na_reason": report.na_reason,
        "per_query": dict(report.per_query),
        "by_category": dict(report.by_category),
    }


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dict(dumped) if isinstance(dumped, Mapping) else {}
    return {}


def _field(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _sequence(value: object) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _citation_ids(value: object) -> list[str]:
    citations = _sequence(value)
    return [
        str(item.get("provision_id"))
        for item in citations
        if isinstance(item, Mapping) and item.get("provision_id")
    ]


def evaluate_release_records(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Compute release metrics and fail closed on semantic outcome failures."""
    from app.evaluation.metrics import evaluate_evidence, evaluate_retrieval, evaluate_temporal

    retrieval_records: list[dict[str, Any]] = []
    evidence_records: list[dict[str, Any]] = []
    temporal_records: list[dict[str, Any]] = []
    abstentions: dict[str, int] = {}
    invalid_citations = non_serving = superseded = unsupported_numeric = workflow_failures = 0
    semantic_failures = 0
    verified = 0
    seen_ids: set[str] = set()
    for record in records:
        question_id = str(_field(record, "question_id", ""))
        input_data = _mapping(_field(record, "input", {}))
        retrieval = _mapping(_field(record, "retrieval", {}))
        output = _mapping(_field(record, "output", {}))
        metrics = _mapping(_field(record, "metrics", {}))
        expected_status = str(input_data.get("expected_status", "VERIFIED")).upper()
        evidence_required = bool(
            input_data.get("evidence_required", bool(input_data.get("required_evidence")))
        )
        retrieved = [str(value) for value in _sequence(retrieval.get("retrieved_ids"))]
        citations = _sequence(output.get("citations", _field(record, "citations")))
        required = _sequence(input_data.get("required_evidence"))
        category = str(input_data.get("category", "uncategorized"))
        retrieval_records.append(
            {
                "id": question_id,
                "category": category,
                "retrieved": retrieved,
                "relevant": _sequence(input_data.get("expected_provision_ids")),
            }
        )
        covered = _sequence(metrics.get("covered_evidence", retrieved))
        evidence_records.append(
            {
                "id": question_id,
                "category": category,
                "required_evidence": required,
                "covered_evidence": covered,
                "retrieved_evidence": retrieved,
            }
        )
        temporal_records.append(
            {
                "id": question_id,
                "category": category,
                "query_date": input_data.get("query_date"),
                "citations": [item for item in citations if isinstance(item, Mapping)],
                "comparison_dates": input_data.get("comparison_dates"),
                "comparison_citations": metrics.get("comparison_citations"),
            }
        )
        status = str(output.get("status", _field(record, "status", ""))).upper()
        abstention_reason = str(
            output.get("abstention_reason")
            or output.get("reason_code")
            or _field(record, "error")
            or "UNCLASSIFIED"
        )
        expected_abstention = expected_status in {
            "INSUFFICIENT_EVIDENCE",
            "UNSUPPORTED",
            "INVALID",
        }
        status_matches = status == expected_status
        has_evidence = bool(retrieved and citations and covered)
        if status_matches and expected_abstention:
            abstentions[abstention_reason] = abstentions.get(abstention_reason, 0) + 1
        elif status_matches and status in {"VERIFIED", "VALID", "COMPLETED"}:
            if evidence_required and not has_evidence:
                semantic_failures += 1
                abstentions["MISSING_EVIDENCE"] = abstentions.get("MISSING_EVIDENCE", 0) + 1
            elif (
                evidence_required
                and required
                and not set(map(str, required)).issubset(set(map(str, covered)))
            ):
                semantic_failures += 1
                abstentions["INCOMPLETE_EVIDENCE"] = abstentions.get("INCOMPLETE_EVIDENCE", 0) + 1
            else:
                verified += 1
        else:
            semantic_failures += 1
            abstentions[abstention_reason] = abstentions.get(abstention_reason, 0) + 1
        if not question_id or question_id in seen_ids:
            semantic_failures += 1
        seen_ids.add(question_id)
        if evidence_required and not retrieved:
            semantic_failures += 1
        invalid_citations += int(metrics.get("invalid_citation", 0) or 0)
        non_serving += int(metrics.get("non_serving_evidence", 0) or 0)
        superseded += int(metrics.get("superseded_current_answer", 0) or 0)
        unsupported_numeric += int(metrics.get("unsupported_numeric_claim", 0) or 0)
        workflow_failures += int(metrics.get("unclassified_workflow_failure", 0) or 0)

    retrieval_reports = evaluate_retrieval(retrieval_records)
    evidence_reports = evaluate_evidence(evidence_records)
    temporal_reports = evaluate_temporal(temporal_records)
    total = len(records)
    hard_gates = {
        "all_questions_executed": total == 200 and len(seen_ids) == 200,
        "semantic_outcomes": total == 200 and semantic_failures == 0,
        "invalid_citation_rate_zero": total > 0 and invalid_citations == 0,
        "no_non_serving_evidence": non_serving == 0,
        "no_superseded_current_answer": superseded == 0,
        "no_unsupported_numeric_claim": unsupported_numeric == 0,
        "no_unclassified_workflow_failure": workflow_failures == 0,
    }
    remediation = [
        {"gate": name, "action": f"Remediate {name} before release"}
        for name, passed in hard_gates.items()
        if not passed
    ]
    return {
        "retrieval": {name: _metric_report(value) for name, value in retrieval_reports.items()},
        "evidence": {name: _metric_report(value) for name, value in evidence_reports.items()},
        "temporal": {name: _metric_report(value) for name, value in temporal_reports.items()},
        "citation": {
            "invalid_citation_count": invalid_citations,
            "invalid_citation_rate": invalid_citations / total if total else None,
        },
        "numeric": {"unsupported_numeric_claim_count": unsupported_numeric},
        "verified_answer_rate": verified / total if total else None,
        "abstention_taxonomy": abstentions,
        "semantic_failure_count": semantic_failures,
        "hard_gates": hard_gates,
        "remediation_evidence": remediation,
        "feedback": {"gating": False, "note": "LIKE/DISLIKE telemetry is non-gating"},
        "release_status": "RELEASED" if all(hard_gates.values()) else "BLOCKED",
    }


def _atomic_checkpoint(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        with contextlib.suppress(FileNotFoundError):
            os.unlink(temporary)


def _load_checkpoint(path: Path | None, inputs: Mapping[str, Any]) -> dict[str, Any]:
    if path is None or not path.exists():
        return {}
    try:
        checkpoint = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}
    return (
        checkpoint
        if isinstance(checkpoint, dict) and checkpoint.get("inputs") == dict(inputs)
        else {}
    )


async def run_serving_evaluation(
    records: list[Any],
    *,
    serving_runtime: Any,
    writer: EvaluationRunWriter,
    manifest: EvaluationRunManifest,
    session: Session,
    storage: ObjectStoragePort,
) -> tuple[str, dict[str, Any]]:
    """Run every gold record through an injected actual serving runtime."""
    if len(records) != 200:
        raise ValueError(f"serving evaluation requires exactly 200 records (got {len(records)})")
    run_id = writer.start(manifest, session=session, storage=storage)
    outcomes: list[dict[str, Any]] = []
    try:
        for record in records:
            question_id = str(_field(record, "id", "") or "")
            question = str(_field(record, "question", "") or "")
            started = __import__("time").perf_counter()
            result: dict[str, Any] | None = None
            error: str | None = None
            try:
                value = serving_runtime(
                    question,
                    query_date=_field(record, "query_date", None),
                )
                if hasattr(value, "__await__"):
                    value = await value
                result = dict(value)
                payload = _mapping(result.get("payload", result))
            except Exception as exc:
                payload = {
                    "status": "ERROR",
                    "abstention": {"reason_code": "WORKFLOW_UNAVAILABLE"},
                }
                error = f"{type(exc).__name__}: {exc}"
            latency_ms = (__import__("time").perf_counter() - started) * 1000
            retrieved = _mapping(result.get("retrieval")) if result is not None else {}
            outcome = {
                "question_id": question_id,
                "input": {
                    "question": question,
                    "category": _field(record, "category", "uncategorized"),
                    "query_date": str(_field(record, "query_date", "") or ""),
                    "expected_provision_ids": list(_field(record, "expected_provision_ids", [])),
                    "required_evidence": list(_field(record, "required_evidence", [])),
                },
                "retrieval": {
                    "retrieved_ids": retrieved.get("retrieved_ids", result.get("retrieved_ids", []))
                    if result is not None
                    else [],
                },
                "output": payload,
                "metrics": {
                    "latency_ms": latency_ms,
                    "invalid_citation": int(payload.get("invalid_citation", False)),
                    "non_serving_evidence": int(payload.get("non_serving_evidence", False)),
                    "superseded_current_answer": int(
                        payload.get("superseded_current_answer", False)
                    ),
                    "unsupported_numeric_claim": int(
                        payload.get("unsupported_numeric_claim", False)
                    ),
                    "unclassified_workflow_failure": int(error is not None),
                },
            }
            if error:
                outcome["error"] = error
            outcomes.append(outcome)
            writer.append_result(run_id, outcome, session=session, storage=storage)
        report = evaluate_release_records(outcomes)
        writer.finish(
            run_id,
            metrics=report,
            metric_availability={name: "AVAILABLE" for name in report},
            status="COMPLETED" if report["release_status"] == "RELEASED" else "FAILED",
            session=session,
            storage=storage,
        )
        return run_id, report
    except Exception:
        writer.finish(
            run_id,
            metrics={
                "release_status": "BLOCKED",
                "remediation_evidence": [{"gate": "runner_failure"}],
            },
            metric_availability={"release": "ABSENT_RUN_FAILURE"},
            status="FAILED",
            session=session,
            storage=storage,
        )
        raise


__all__ = [
    "EvaluationRunManifest",
    "EvaluationRunWriter",
    "evaluate_release_records",
    "run_serving_evaluation",
]
