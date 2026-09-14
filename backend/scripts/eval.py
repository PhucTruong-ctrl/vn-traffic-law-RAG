"""Run retrieval-only evaluation against the frozen 40-case thesis gold set."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.evaluation.metrics import canonical_coordinate_string, recall_at_k  # noqa: E402
from app.evaluation.schemas import Coordinate  # noqa: E402
from app.rag.references import extract_references  # noqa: E402
from app.rag.retrieval import Retriever  # noqa: E402
from scripts.run_thesis_evaluation import load_dataset, normalize_case  # noqa: E402


def _coordinate_from_metadata(metadata: dict[str, Any]) -> Coordinate | None:
    provision = metadata.get("provision_id")
    if isinstance(provision, str) and provision.strip():
        fields: dict[str, str] = {"document_id": provision.split("__", 1)[0]}
        for part in provision.split("__")[1:]:
            prefix, _, value = part.partition("-")
            if prefix == "dieu":
                fields["article"] = value
            elif prefix == "khoan":
                fields["clause"] = value
            elif prefix == "diem":
                fields["point"] = value
        try:
            return Coordinate.model_validate(fields)
        except ValueError:
            return None
    document = metadata.get("document_id")
    if not isinstance(document, str) or not document.strip():
        return None
    if not any(metadata.get(key) not in (None, "") for key in ("article", "clause", "point")):
        return None
    try:
        return Coordinate(
            document_id=document,
            article=str(metadata["article"]) if metadata.get("article") is not None else None,
            clause=str(metadata["clause"]) if metadata.get("clause") is not None else None,
            point=str(metadata["point"]) if metadata.get("point") is not None else None,
        )
    except ValueError:
        return None


def _expected_coordinates(case: dict[str, Any]) -> list[Coordinate]:
    values = case["expected"].get("provision_ids", [])
    result: list[Coordinate] = []
    for value in values if isinstance(values, list) else [values]:
        if not isinstance(value, str):
            continue
        fields: dict[str, str] = {"document_id": value.split("__", 1)[0]}
        for part in value.split("__")[1:]:
            prefix, _, item = part.partition("-")
            if prefix == "dieu":
                fields["article"] = item
            elif prefix == "khoan":
                fields["clause"] = item
            elif prefix == "diem":
                fields["point"] = item
        try:
            result.append(Coordinate.model_validate(fields))
        except ValueError:
            continue
    return result


def _record(
    case: dict[str, Any],
    docs: list[Any],
    latency_ms: float,
    top_k: int,
    *,
    references: list[Any] | None = None,
    stage: str = "hybrid",
    error: str | None = None,
) -> dict[str, Any]:
    references = references or []
    pairs = [
        (document, coordinate)
        for document in docs
        if (coordinate := _coordinate_from_metadata(dict(document.metadata))) is not None
    ]
    coordinates = [coordinate for _, coordinate in pairs]
    expected = _expected_coordinates(case)
    expected_ids = {canonical_coordinate_string(item) for item in expected}
    actual_ids = {canonical_coordinate_string(item) for item in coordinates}
    return {
        "case_id": case["id"],
        "category": case["category"],
        "query": case["question"],
        "parsed_references": [reference.as_dict() for reference in references],
        "expected_provision_ids": sorted(expected_ids),
        "stage": stage,
        "top_k": top_k,
        "latency_ms": round(latency_ms, 2),
        "error": error,
        "returned_documents": [
            {
                "document_id": document.metadata.get("document_id"),
                "document_number": document.metadata.get("document_number"),
                "article": document.metadata.get("article"),
                "clause": document.metadata.get("clause"),
                "point": document.metadata.get("point"),
                "chunk_id": document.metadata.get("chunk_id"),
                "coordinate": canonical_coordinate_string(coordinate),
            }
            for document, coordinate in pairs
        ],
        "retrieved_coordinates": sorted(actual_ids),
        "found_expected": bool(expected_ids & actual_ids) if expected_ids else None,
        "recall_at_5": recall_at_k(expected, coordinates, 5),
        "recall_at_10": recall_at_k(expected, coordinates, 10),
    }


def _error_record(
    case: dict[str, Any],
    exc: Exception,
    latency_ms: float,
    *,
    references: list[Any] | None = None,
    top_k: int = 10,
) -> dict[str, Any]:
    if "expected" not in case and "query" in case:
        case = normalize_case(case, 0)
    references = references or []
    error = f"{type(exc).__name__}: {exc}"
    message = str(exc).lower()
    if "timeout" in message or "timed out" in message:
        diagnosis = "timeout"
    elif "filter" in message:
        diagnosis = "filter"
    else:
        diagnosis = "error"
    return {
        "case_id": case["id"],
        "category": case["category"],
        "query": case["question"],
        "parsed_references": [reference.as_dict() for reference in references],
        "expected_provision_ids": sorted(
            canonical_coordinate_string(item) for item in _expected_coordinates(case)
        ),
        "stage": "retrieval",
        "top_k": top_k,
        "latency_ms": round(latency_ms, 2),
        "error": error,
        "diagnosis": diagnosis,
        "returned_documents": [],
        "retrieved_coordinates": [],
        "found_expected": None,
        "recall_at_5": None,
        "recall_at_10": None,
        "document_accuracy": None,
    }


def _aggregate(rows: list[dict[str, Any]], dataset: Path, top_k: int) -> dict[str, Any]:
    def mean(field: str) -> float | None:
        values = [row[field] for row in rows if isinstance(row.get(field), (int, float))]
        return sum(values) / len(values) if values else None

    return {
        "dataset": str(dataset),
        "case_count": len(rows),
        "top_k": top_k,
        "errors": sum(row["error"] is not None for row in rows),
        "recall_at_5": mean("recall_at_5"),
        "recall_at_10": mean("recall_at_10"),
        "latency_ms": {"mean": mean("latency_ms")},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("evaluation-results"))
    args = parser.parse_args()
    if args.top_k < 10:
        raise SystemExit("--top-k must be at least 10 for Recall@10")
    cases = load_dataset(args.dataset)
    retriever = Retriever(top_k=args.top_k)
    rows: list[dict[str, Any]] = []
    for case in cases:
        if not any(case["id"].endswith(f"-{index:02d}") for index in (*range(5), *range(15, 25))):
            continue
        started = time.perf_counter()
        references = extract_references(case["question"])
        try:
            documents: list[Any] = []
            for reference in references:
                documents.extend(retriever.resolve_reference(reference, limit=args.top_k))
            rows.append(
                _record(
                    case,
                    documents,
                    (time.perf_counter() - started) * 1000,
                    args.top_k,
                    references=references,
                    stage="exact" if references else "hybrid",
                )
            )
        except Exception as exc:
            rows.append(
                _error_record(
                    case,
                    exc,
                    (time.perf_counter() - started) * 1000,
                    references=references,
                    top_k=args.top_k,
                )
            )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    raw_path = args.output_dir / f"{stamp}.jsonl"
    aggregate_path = args.output_dir / f"{stamp}.aggregate.json"
    raw_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    aggregate_path.write_text(
        json.dumps(_aggregate(rows, args.dataset, args.top_k), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"raw": str(raw_path), "aggregate": str(aggregate_path), "count": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
