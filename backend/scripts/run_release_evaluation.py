"""Run frozen serving evaluation with observable, resumable execution."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import subprocess
import tempfile
import time
from datetime import date
from pathlib import Path
from typing import Any

from app.api import chat as chat_api
from app.api.chat import _response_payload
from app.api.db import get_db
from app.evaluation.gold_set import validate_record
from app.evaluation.run import (
    EvaluationRunManifest,
    EvaluationRunWriter,
    build_evaluation_retrieval_envelope,
    evaluate_release_records,
)
from app.storage.object_storage import ObjectStoragePort, get_object_storage

ROOT = Path(__file__).resolve().parents[2]
GOLD_PATH = ROOT / "data/gold-sets/gold-v1/gold.json"
READINESS_PATH = ROOT / "data/gold-sets/gold-v1/READINESS.json"
CORPUS_PATH = ROOT / "data/candidate-corpus-manifest.json"
EVALUATION_SCHEMA = "serving-release-v2"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _identity(gold_hash: str, corpus_hash: str) -> dict[str, str]:
    active_collection = os.environ.get("QDRANT_ACTIVE_COLLECTION")
    embedding_hash = os.environ.get("EMBEDDING_MODEL_HASH")
    if not active_collection or not embedding_hash:
        raise RuntimeError(
            "release identity requires QDRANT_ACTIVE_COLLECTION and EMBEDDING_MODEL_HASH"
        )
    sparse_path = ROOT / "data/sparse-vocab/bm25-v2.json"
    return {
        "schema": EVALUATION_SCHEMA,
        "git_commit": _git_commit(),
        "code_hash": _sha256(ROOT / "backend/scripts/run_release_evaluation.py"),
        "gold_hash": gold_hash,
        "corpus_hash": corpus_hash,
        "active_alias": os.environ.get("QDRANT_ACTIVE_ALIAS", "legal_provisions_active"),
        "active_collection": active_collection,
        "embedding_version": os.environ.get("EMBEDDING_VERSION", "paddle-e5-base-v1"),
        "embedding_hash": embedding_hash,
        "sparse_version": os.environ.get("SPARSE_VOCABULARY_VERSION", "bm25-v2"),
        "sparse_hash": _sha256(sparse_path),
    }


def load_frozen_gold(
    path: Path = GOLD_PATH, readiness_path: Path = READINESS_PATH
) -> tuple[list[Any], str]:
    readiness = json.loads(readiness_path.read_text(encoding="utf-8"))
    if readiness.get("frozen") is not True or readiness.get("freeze_status") != "FROZEN":
        raise RuntimeError("gold set is not frozen")
    payload = json.loads(path.read_text(encoding="utf-8"))
    records = payload.get("records")
    if not isinstance(records, list) or len(records) != 200:
        raise RuntimeError("frozen gold set must contain exactly 200 records")
    parsed = [validate_record(item) for item in records]
    ids = [str(item.id) for item in parsed]
    if len(ids) != len(set(ids)):
        raise RuntimeError("frozen gold set contains duplicate IDs")
    actual_hash = _sha256(path)
    if readiness.get("gold_set_hash") != actual_hash:
        raise RuntimeError("frozen gold hash does not match gold artifact")
    return parsed, actual_hash


def _git_commit() -> str:
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()


def _runtime(session: Any):
    services = chat_api.production_services(session=session)
    graph = chat_api.build_query_graph(services)

    async def serve(question: str, *, query_date: date | None = None) -> dict[str, Any]:
        state = {"question": question, "query_date": query_date or date.today()}
        result = await graph.ainvoke(state)
        trace_id = str(result.get("trace_id", "release-evaluation"))
        payload = _response_payload(result, trace_id)
        return {
            "payload": payload,
            "retrieval": build_evaluation_retrieval_envelope(result),
        }

    return serve


def _session() -> Any:
    database = get_db()
    return next(database)


async def run_release(*, output_dir: Path, checkpoint_path: Path | None = None) -> dict[str, Any]:
    records, gold_hash = load_frozen_gold()
    corpus = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    corpus_hash = str(corpus.get("artifact_sha256", ""))
    if corpus.get("coverage", {}).get("documents") != 14:
        raise RuntimeError("serving corpus must contain exactly 14 documents")
    identity = _identity(gold_hash, corpus_hash)
    checkpoint_path = checkpoint_path or output_dir / "working-checkpoint.json"
    expected_ids = {str(item.id) for item in records}
    checkpoint: dict[str, Any] = {}
    if checkpoint_path.exists():
        try:
            loaded = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError):
            loaded = {}
        if isinstance(loaded, dict) and loaded.get("identity") == identity:
            checkpoint = loaded
    raw_outcomes = checkpoint.get("outcomes", [])
    completed: dict[str, dict[str, Any]] = {}
    if isinstance(raw_outcomes, list):
        for item in raw_outcomes:
            if not isinstance(item, dict):
                continue
            qid = str(item.get("question_id", ""))
            if qid in expected_ids and qid not in completed:
                completed[qid] = item
    ordered = sorted(records, key=lambda item: str(item.id))
    storage: ObjectStoragePort = get_object_storage()
    storage.ensure_buckets()
    session = _session()
    try:
        manifest = EvaluationRunManifest(
            git_commit=identity["git_commit"],
            corpus_version="candidate-corpus-14",
            corpus_hash=corpus_hash,
            gold_set_version="gold-v1",
            gold_set_hash=gold_hash,
            suite="serving-release",
            variant="production-runtime",
            config_snapshot={"runtime": "app.api.chat production workflow", "identity": identity},
        )
        services = chat_api.production_services(session=session)
        graph = chat_api.build_query_graph(services)
        writer = EvaluationRunWriter()
        run_id = writer.start(manifest, session=session, storage=storage)
        outcomes: list[dict[str, Any]] = []
        for index, record in enumerate(ordered, 1):
            qid = str(record.id)
            if qid in completed:
                outcomes.append(completed[qid])
                print(f"[{index}/{len(ordered)}] {qid} RESUMED", flush=True)
                continue
            started = time.perf_counter()
            error = None
            try:
                result = await asyncio.wait_for(
                    graph.ainvoke(
                        {"question": str(record.question), "query_date": record.query_date}
                    ),
                    timeout=120,
                )
                payload = _response_payload(
                    result, str(result.get("trace_id", "release-evaluation"))
                )
                expected_status = str(
                    getattr(record, "expected_status", None)
                    or (
                        "OUT_OF_SCOPE"
                        if str(record.category) == "OUT_OF_SCOPE"
                        else "INSUFFICIENT_EVIDENCE"
                        if str(record.category)
                        in {
                            "MISSING_INFORMATION",
                            "AMBIGUOUS",
                            "COLLOQUIAL_QUERY",
                            "ADVERSARIAL_CITATION",
                        }
                        else "VERIFIED"
                    )
                )
                expected_evidence = list(record.required_evidence)
                outcome = {
                    "question_id": qid,
                    "input": {
                        "question": str(record.question),
                        "category": str(record.category),
                        "query_date": str(record.query_date),
                        "expected_provision_ids": list(record.expected_provision_ids),
                        "required_evidence": expected_evidence,
                        "expected_status": expected_status,
                        "evidence_required": bool(expected_evidence),
                    },
                    "retrieval": build_evaluation_retrieval_envelope(result),
                    "output": payload,
                    "metrics": {"latency_ms": (time.perf_counter() - started) * 1000},
                }
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                expected_status = str(
                    getattr(record, "expected_status", None)
                    or (
                        "OUT_OF_SCOPE"
                        if str(record.category) == "OUT_OF_SCOPE"
                        else "INSUFFICIENT_EVIDENCE"
                        if str(record.category)
                        in {
                            "MISSING_INFORMATION",
                            "AMBIGUOUS",
                            "COLLOQUIAL_QUERY",
                            "ADVERSARIAL_CITATION",
                        }
                        else "VERIFIED"
                    )
                )
                expected_evidence = list(record.required_evidence)
                outcome = {
                    "question_id": qid,
                    "input": {
                        "question": str(record.question),
                        "category": str(record.category),
                        "query_date": str(record.query_date),
                        "expected_provision_ids": list(record.expected_provision_ids),
                        "required_evidence": expected_evidence,
                        "expected_status": expected_status,
                        "evidence_required": bool(expected_evidence),
                    },
                    "retrieval": {},
                    "output": {
                        "status": "ERROR",
                        "abstention": {"reason_code": "WORKFLOW_UNAVAILABLE"},
                    },
                    "metrics": {
                        "latency_ms": (time.perf_counter() - started) * 1000,
                        "unclassified_workflow_failure": 1,
                    },
                    "error": error,
                }
            writer.append_result(run_id, outcome, session=session, storage=storage)
            session.commit()
            outcomes.append(outcome)
            _atomic_json(
                checkpoint_path, {"identity": identity, "status": "WORKING", "outcomes": outcomes}
            )
            print(
                f"[{index}/{len(ordered)}] {qid} {record.category} "
                f"{outcome['output'].get('status')} "
                f"{outcome['metrics']['latency_ms'] / 1000:.2f}s"
                + (f" error={error}" if error else ""),
                flush=True,
            )
        expected_order = [str(item.id) for item in ordered]
        if [str(x.get("question_id")) for x in outcomes] != expected_order:
            raise RuntimeError(
                "cannot finalize evaluation with incomplete or non-canonical outcomes"
            )
        report = evaluate_release_records(outcomes)
        writer.finish(
            run_id,
            metrics=report,
            metric_availability={"release": "AVAILABLE"},
            status="COMPLETED" if report["release_status"] == "RELEASED" else "FAILED",
            session=session,
            storage=storage,
        )
        session.commit()
        output_dir.mkdir(parents=True, exist_ok=True)
        report_path = output_dir / f"{run_id}.report.json"
        report_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
        )
        manifest_path = output_dir / f"{run_id}.manifest.json"
        manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
        return {
            "run_id": run_id,
            "status": report["release_status"],
            "report_artifact": str(report_path.resolve().relative_to(ROOT.resolve())),
            "manifest_artifact": str(manifest_path.resolve().relative_to(ROOT.resolve())),
            "report_sha256": _sha256(report_path),
            "manifest_sha256": _sha256(manifest_path),
            "gold_set_hash": gold_hash,
        }
    finally:
        session.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "data/evaluation/release-runs")
    parser.add_argument("--checkpoint", type=Path, default=None)
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(
            run_release(output_dir=args.output_dir, checkpoint_path=args.checkpoint)
        )
    except Exception as exc:
        print(
            json.dumps({"status": "BLOCKED", "error": f"{type(exc).__name__}: {exc}"}), flush=True
        )
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True), flush=True)
    return 0 if result["status"] == "RELEASED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
