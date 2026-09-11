"""Run the deterministic 40-case thesis evaluation.

The runner accepts a JSON array/object dataset and either invokes the HTTP chat
endpoint or scores an existing prediction JSONL. It never infers semantic
answer correctness: that field is supplied later by the manual reviewer.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib import error, request

CATEGORIES = {
    "exact_reference",
    "natural_language",
    "penalty",
    "multi_intent",
    "cross_reference",
    "follow_up",
    "insufficient_evidence",
    "out_of_scope",
}
REQUIRED_CASE = {"id", "category"}
THESIS_EXPECTED_FIELDS = {
    "expected_status",
    "expected_abstain",
    "expected_document_ids",
    "expected_article_ids",
    "expected_clause_ids",
    "expected_point_ids",
    "expected_provision_ids",
}
EXPECTED_COORDINATE_LEVELS = ("document", "article", "clause", "point")


def normalize_case(case: dict[str, Any], index: int) -> dict[str, Any]:
    """Normalize the thesis gold schema to the runner's historical schema."""
    if "query" in case:
        if not isinstance(case["query"], str) or not case["query"].strip():
            fail(f"case {case.get('id', index)} has a blank query")
        expected = {
            "status": case.get("expected_status"),
            "abstain": case.get("expected_abstain"),
            "document_ids": case.get("expected_document_ids"),
            "article_ids": case.get("expected_article_ids"),
            "clause_ids": case.get("expected_clause_ids"),
            "point_ids": case.get("expected_point_ids"),
            "provision_ids": case.get("expected_provision_ids"),
        }
        missing = [key for key, value in expected.items() if value is None]
        if missing:
            fail(f"case {case.get('id', index)} missing thesis fields: {', '.join(missing)}")
        normalized = dict(case)
        normalized["question"] = case["query"]
        normalized["expected"] = expected
        return normalized
    return case


def fail(message: str) -> NoReturn:
    raise SystemExit(f"error: {message}")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"cannot read JSON {path}: {exc}")


def load_dataset(path: Path) -> list[dict[str, Any]]:
    raw = load_json(path)
    records = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(records, list) or len(records) != 40:
        fail("dataset must contain exactly 40 cases under an array or 'cases'")
    seen: set[str] = set()
    counts = {category: 0 for category in CATEGORIES}
    result: list[dict[str, Any]] = []
    for index, raw_case in enumerate(records):
        if not isinstance(raw_case, dict):
            fail(f"case {index} must be an object")
        case = normalize_case(raw_case, index)
        if not case.keys() >= REQUIRED_CASE or not ({"question", "expected"} <= case.keys()):
            fail(f"case {index} must contain id, question, category, expected")
        case_id = case["id"]
        category = case["category"]
        if not isinstance(case_id, str) or not case_id.strip() or case_id in seen:
            fail(f"case {index} has a missing or duplicate id")
        if not isinstance(case.get("question"), str) or not case["question"].strip():
            fail(f"case {case_id} has a blank question")
        if category not in CATEGORIES:
            fail(f"case {case_id} has unsupported category {category!r}")
        if not isinstance(case["expected"], dict):
            fail(f"case {case_id} expected must be an object")
        seen.add(case_id)
        counts[category] += 1
        result.append(case)
    if set(counts.values()) != {5}:
        fail(f"dataset must contain five cases per category; got {counts}")
    return result


def load_predictions(path: Path) -> dict[str, dict[str, Any]]:
    predictions: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail(f"cannot read predictions: {exc}")
    for line_no, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            fail(f"prediction line {line_no} is invalid JSON: {exc}")
        if not isinstance(value, dict) or not isinstance(value.get("case_id"), str):
            fail(f"prediction line {line_no} must be an object with case_id")
        case_id = value["case_id"]
        if case_id in predictions:
            fail(f"duplicate prediction for {case_id}")
        predictions[case_id] = value
    return predictions


def expected_ids(case: dict[str, Any]) -> set[str]:
    expected = case["expected"]
    values: list[Any] = []
    for key in ("provision_ids", "expected_provision_ids", "acceptable_provision_ids"):
        value = expected.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif isinstance(value, str):
            values.append(value)
    return {str(value) for value in values if str(value).strip()}


def citation_id(citation: Any) -> str | None:
    if not isinstance(citation, dict):
        return None
    for key in ("provision_id", "id", "chunk_id"):
        value = citation.get(key)
        if value:
            return str(value)
    document = citation.get("document") or citation.get("document_id")
    article = citation.get("article")
    if document and article:
        return f"{document}__dieu-{article}"
    return None


def score_case(
    case: dict[str, Any], prediction: dict[str, Any], latency_ms: float | None = None
) -> dict[str, Any]:
    citations = prediction.get("citations", [])
    if not isinstance(citations, list):
        citations = []
    ids = {item for item in (citation_id(c) for c in citations) if item}
    wanted = expected_ids(case)
    hit = bool(ids & wanted) if wanted else None
    expected = case["expected"]
    status = str(prediction.get("status", "")).upper()
    should_abstain = bool(expected.get("abstain", expected.get("should_abstain", False)))
    abstention = (status in {"INSUFFICIENT_EVIDENCE", "OUT_OF_SCOPE"}) == should_abstain
    valid_citations = all(isinstance(c, dict) and citation_id(c) for c in citations)
    result = {
        "case_id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "prediction": prediction,
        "retrieval_hit_at_k": hit,
        "document_accuracy": None,
        "article_accuracy": None,
        "clause_accuracy": None,
        "point_accuracy": None,
        "citation_validity": valid_citations if citations else not wanted,
        "answer_correctness_manual": prediction.get("answer_correctness_manual"),
        "abstention_accuracy": abstention,
    }
    if latency_ms is not None:
        result["latency_ms"] = round(latency_ms, 2)
    # Coordinate accuracy is deterministic only when gold coordinates are present
    # and response citations expose the same coordinate fields.
    for field in ("document", "article", "clause", "point"):
        expected_value = expected.get(field)
        if expected_value is not None:
            actual = {
                str(c.get(field))
                for c in citations
                if isinstance(c, dict) and c.get(field) is not None
            }
            result[f"{field}_accuracy"] = str(expected_value) in actual
    return result


def post_json(url: str, payload: dict[str, Any], timeout: float) -> tuple[dict[str, Any], float]:
    body = json.dumps(payload, ensure_ascii=False).encode()
    req = request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    started = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except (OSError, error.HTTPError, json.JSONDecodeError) as exc:
        raise RuntimeError(str(exc)) from exc
    if not isinstance(value, dict):
        raise RuntimeError("endpoint response must be an object")
    return value, (time.perf_counter() - started) * 1000


def aggregate(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    def mean(field: str) -> float | None:
        values = [float(row[field]) for row in rows if isinstance(row.get(field), (int, float))]
        return round(statistics.mean(values), 2) if values else None

    def ratio(field: str) -> float | None:
        values = [row[field] for row in rows if isinstance(row.get(field), bool)]
        return round(sum(values) / len(values), 4) if values else None

    by_category = {}
    for category in sorted(CATEGORIES):
        subset = [row for row in rows if row["category"] == category]
        by_category[category] = {
            "count": len(subset),
            **{
                field: ratio(field)
                for field in (
                    "retrieval_hit_at_k",
                    "document_accuracy",
                    "article_accuracy",
                    "clause_accuracy",
                    "point_accuracy",
                    "citation_validity",
                    "answer_correctness_manual",
                    "abstention_accuracy",
                )
            },
        }
    return {
        "run": metadata,
        "count": len(rows),
        "metrics": {
            field: ratio(field)
            for field in (
                "retrieval_hit_at_k",
                "document_accuracy",
                "article_accuracy",
                "clause_accuracy",
                "point_accuracy",
                "citation_validity",
                "answer_correctness_manual",
                "abstention_accuracy",
            )
        },
        "latency_ms": {
            "mean": mean("latency_ms"),
            "p50": (
                round(
                    statistics.median(
                        [
                            r["latency_ms"]
                            for r in rows
                            if isinstance(r.get("latency_ms"), (int, float))
                        ]
                    ),
                    2,
                )
                if any(isinstance(r.get("latency_ms"), (int, float)) for r in rows)
                else None
            ),
        },
        "by_category": by_category,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/api/v1/chat")
    parser.add_argument("--output-dir", type=Path, default=Path("thesis-evaluation"))
    parser.add_argument("--model-label", default="unspecified")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=60)
    args = parser.parse_args()
    if args.predictions is None and not args.endpoint:
        fail("provide --predictions or --endpoint")
    cases = load_dataset(args.dataset)
    saved = load_predictions(args.predictions) if args.predictions else {}
    rows: list[dict[str, Any]] = []
    for case in cases:
        if case["id"] in saved:
            rows.append(score_case(case, saved[case["id"]], saved[case["id"]].get("latency_ms")))
            continue
        if args.predictions:
            fail(f"missing prediction for {case['id']}")
        try:
            prediction, latency = post_json(
                args.endpoint,
                {
                    "question": case["question"],
                    "top_k": args.top_k,
                    "effective_date": case.get("query_date"),
                },
                args.timeout,
            )
            rows.append(score_case(case, prediction, latency))
        except RuntimeError as exc:
            rows.append(
                {
                    "case_id": case["id"],
                    "category": case["category"],
                    "question": case["question"],
                    "prediction": None,
                    "error": str(exc),
                    "latency_ms": None,
                    "retrieval_hit_at_k": None,
                    "document_accuracy": None,
                    "article_accuracy": None,
                    "clause_accuracy": None,
                    "point_accuracy": None,
                    "citation_validity": None,
                    "answer_correctness_manual": None,
                    "abstention_accuracy": None,
                }
            )
    if len(rows) != len(cases):
        fail("incomplete evaluation")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    metadata = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "model_label": args.model_label,
        "dataset": str(args.dataset),
        "endpoint": None if args.predictions else args.endpoint,
        "top_k": args.top_k,
    }
    raw_path = args.output_dir / f"{run_id}.jsonl"
    aggregate_path = args.output_dir / f"{run_id}.aggregate.json"
    raw_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    aggregate_path.write_text(
        json.dumps(aggregate(rows, metadata), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"raw": str(raw_path), "aggregate": str(aggregate_path), "count": len(rows)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
