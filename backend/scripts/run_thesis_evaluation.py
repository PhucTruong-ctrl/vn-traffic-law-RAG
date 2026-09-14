"""Run the deterministic 40-case thesis evaluation.

The runner accepts a JSON array/object dataset and either invokes the HTTP chat
endpoint or scores an existing prediction JSONL. It never infers semantic
answer correctness: that field is supplied later by the manual reviewer.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, NoReturn
from urllib import error, request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.auth.test_auth import obtain_access_token  # noqa: E402
from app.evaluation.metrics import canonical_coordinate_string, normalize_coordinate  # noqa: E402
from app.evaluation.schemas import Coordinate  # noqa: E402

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
CORPUS_NOT_COVERED_CASES = frozenset(
    {
        "thesis-gold-40-00",
        "thesis-gold-40-15",
        "thesis-gold-40-16",
        "thesis-gold-40-17",
        "thesis-gold-40-18",
        "thesis-gold-40-19",
    }
)
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
    """Normalize current and historical thesis gold schemas."""
    if "query" not in case:
        return case
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
        prediction = value.get("prediction")
        if "prediction" in value:
            if isinstance(prediction, dict):
                outer = value
                value = {**prediction, "case_id": case_id}
                for key in ("latency_ms", "error"):
                    if key in outer and key not in value:
                        value[key] = outer[key]
            else:
                value = {
                    "status": "ERROR",
                    "prediction": None,
                    "error": value.get("error") or "saved prediction is null",
                    "latency_ms": value.get("latency_ms"),
                    "case_id": case_id,
                }
        predictions[case_id] = value
    return predictions


def _values(expected: dict[str, Any], *keys: str) -> set[str]:
    values: list[Any] = []
    for key in keys:
        value = expected.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif isinstance(value, str):
            values.append(value)
    return {str(value).strip() for value in values if str(value).strip()}


def _canonical_ids(values: set[str], level: str | None = None) -> set[str]:
    result: set[str] = set()
    for value in values:
        parsed = parse_coordinate(value)
        if parsed and (
            level is None or parsed[EXPECTED_COORDINATE_LEVELS.index(level)] is not None
        ):
            result.add(parsed[4])
    return result


def expected_ids(case: dict[str, Any]) -> set[str]:
    expected = case.get("expected")
    if not isinstance(expected, dict):
        expected = {
            key.removeprefix("expected_"): value
            for key, value in case.items()
            if key.startswith("expected_")
        }
    return _canonical_ids(
        _values(expected, "provision_ids", "expected_provision_ids", "acceptable_provision_ids")
    )


def _expected_coordinates(expected: dict[str, Any], level: str) -> set[str]:
    values = _values(expected, f"{level}_ids", f"expected_{level}_ids")
    result: set[str] = set()
    for value in values:
        parsed = parse_coordinate(value)
        if not parsed:
            continue
        index = EXPECTED_COORDINATE_LEVELS.index(level)
        if parsed[index] is not None:
            result.add("__".join(part for part in parsed[4].split("__")[: index + 1]))
    return result


def _level_expected_coordinates(expected: dict[str, Any], level: str) -> set[str]:
    direct = _expected_coordinates(expected, level)
    if direct:
        return direct
    provision_values = _values(
        expected, "provision_ids", "expected_provision_ids", "acceptable_provision_ids"
    )
    result: set[str] = set()
    index = EXPECTED_COORDINATE_LEVELS.index(level)
    for value in provision_values:
        parsed = parse_coordinate(value)
        if parsed and parsed[index] is not None:
            result.add("__".join(part for part in parsed[4].split("__")[: index + 1]))
    return result


def parse_coordinate(value: Any) -> tuple[str, str | None, str | None, str | None, str] | None:
    """Parse a canonical coordinate, rejecting chunk/source suffixes."""
    raw_parts = value.strip().split("__")
    document = raw_parts[0].strip()
    if not document or ":" in document:
        return None
    levels: dict[str, str] = {}
    prefixes = (
        ("article", ("điều-", "dieu-")),
        ("clause", ("khoản-", "khoan-")),
        ("point", ("điểm-", "diem-")),
    )
    previous_index = -1
    for raw_part in raw_parts[1:]:
        part = " ".join(raw_part.split()).casefold()
        matched: tuple[str, str] | None = None
        for index, (level, accepted) in enumerate(prefixes):
            if index <= previous_index:
                continue
            prefix = next((prefix for prefix in accepted if part.startswith(prefix)), None)
            if prefix is not None:
                matched = level, part[len(prefix) :].rstrip(".")
                previous_index = index
                break
        if matched is None:
            return None
        level, raw = matched
        if not raw:
            return None
        if level != "point" and raw.isdigit():
            raw = str(int(raw))
        levels[level] = raw
    try:
        coordinate = Coordinate(
            document_id=raw_parts[0].strip(),
            article=levels.get("article"),
            clause=levels.get("clause"),
            point=levels.get("point"),
        )
        document, article, clause, point = normalize_coordinate(coordinate)
    except (TypeError, ValueError):
        return None
    return document, article, clause, point, canonical_coordinate_string(coordinate)


def _coordinate_from_metadata(
    item: Any,
) -> tuple[str, str | None, str | None, str | None, str] | None:
    if not isinstance(item, dict):
        return None
    for key in ("provision_id", "provision_ids"):
        candidate = item.get(key)
        values = (
            [candidate]
            if isinstance(candidate, str)
            else candidate
            if isinstance(candidate, list)
            else []
        )
        for value in values:
            parsed = parse_coordinate(value)
            if parsed:
                return parsed
    document = item.get("document_id")
    if not isinstance(document, str) or not document.strip():
        document = item.get("document_number")
    article, clause, point = item.get("article"), item.get("clause"), item.get("point")
    if not isinstance(document, str) or not any(
        value is not None and str(value).strip() for value in (article, clause, point)
    ):
        return None
    return parse_coordinate(
        "__".join(
            [document.strip()]
            + [
                f"{prefix}{value}"
                for prefix, value in zip(
                    ("dieu-", "khoan-", "diem-"), (article, clause, point), strict=True
                )
                if value is not None and str(value).strip()
            ]
        )
    )


def _prediction_coordinates(
    prediction: dict[str, Any],
) -> list[tuple[str, str | None, str | None, str | None, str]]:
    coordinates: list[tuple[str, str | None, str | None, str | None, str]] = []
    citations = prediction.get("citations", [])
    if isinstance(citations, list):
        coordinates.extend(
            item for citation in citations if (item := _coordinate_from_metadata(citation))
        )
    claims = prediction.get("claims", [])
    if isinstance(claims, list):
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            ids = claim.get("provision_ids")
            if isinstance(ids, str):
                ids = [ids]
            if isinstance(ids, list):
                coordinates.extend(item for value in ids if (item := parse_coordinate(value)))
    return coordinates


def _level_accuracy(
    expected: dict[str, Any],
    coordinates: list[tuple[str, str | None, str | None, str | None, str]],
    level: str,
) -> bool | None:
    wanted = _level_expected_coordinates(expected, level)
    if not wanted:
        return None
    index = EXPECTED_COORDINATE_LEVELS.index(level)
    actual = {
        "__".join(part for part in coordinate[4].split("__")[: index + 1])
        for coordinate in coordinates
        if coordinate[index] is not None
    }
    return wanted <= actual


def score_case(
    case: dict[str, Any], prediction: dict[str, Any], latency_ms: float | None = None
) -> dict[str, Any]:
    citations = prediction.get("citations", [])
    if not isinstance(citations, list):
        citations = []
    if not isinstance(case.get("expected"), dict):
        case = normalize_case(case, 0)
    expected = case["expected"]
    wanted = expected_ids(case)
    corpus_not_covered = case["id"] in CORPUS_NOT_COVERED_CASES
    coordinates = _prediction_coordinates(prediction)
    cited_ids = {item[4] for item in coordinates}
    status = str(prediction.get("status", "")).upper()
    timed_out = status in {"TIMEOUT", "ERROR", "FAILED"}
    should_abstain = bool(expected.get("abstain", False))
    actual_abstain = status in {"INSUFFICIENT_EVIDENCE", "OUT_OF_SCOPE"}
    citation_validity = (
        None if timed_out or corpus_not_covered else bool(citations) if citations else not wanted
    )
    if citations and not coordinates:
        citation_validity = False if not corpus_not_covered else None
    result = {
        "case_id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "prediction": prediction,
        "corpus_covered": not corpus_not_covered,
        "corpus_not_covered": corpus_not_covered,
        "retrieval_hit_at_k": None
        if timed_out or corpus_not_covered or not wanted
        else bool(cited_ids & wanted),
        "document_accuracy": None
        if timed_out or corpus_not_covered
        else _level_accuracy(expected, coordinates, "document"),
        "article_accuracy": None
        if timed_out or corpus_not_covered
        else _level_accuracy(expected, coordinates, "article"),
        "clause_accuracy": None
        if timed_out or corpus_not_covered
        else _level_accuracy(expected, coordinates, "clause"),
        "point_accuracy": None
        if timed_out or corpus_not_covered
        else _level_accuracy(expected, coordinates, "point"),
        "citation_validity": citation_validity,
        "answer_correctness_manual": None,
        "abstention_accuracy": None
        if timed_out or corpus_not_covered
        else actual_abstain == should_abstain,
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
    }
    return result


def post_json(
    url: str, payload: dict[str, Any], timeout: float, bearer_token: str | None = None
) -> tuple[dict[str, Any], float]:
    body = json.dumps(payload, ensure_ascii=False).encode()
    headers = {"Content-Type": "application/json"}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    req = request.Request(url, data=body, headers=headers, method="POST")
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
    fields = (
        "retrieval_hit_at_k",
        "document_accuracy",
        "article_accuracy",
        "clause_accuracy",
        "point_accuracy",
        "citation_validity",
        "answer_correctness_manual",
        "abstention_accuracy",
    )
    covered_rows = [row for row in rows if row.get("corpus_covered", True)]

    def rate(field: str, subset: list[dict[str, Any]]) -> float | None:
        values = [row[field] for row in subset if isinstance(row.get(field), bool)]
        return round(sum(values) / len(values), 4) if values else None

    def numeric_mean(field: str) -> float | None:
        values = [
            float(row[field]) for row in covered_rows if isinstance(row.get(field), (int, float))
        ]
        return round(statistics.mean(values), 2) if values else None

    def percentile(field: str, p: float) -> float | None:
        values = sorted(
            float(row[field]) for row in covered_rows if isinstance(row.get(field), (int, float))
        )
        if not values:
            return None
        rank = (len(values) - 1) * p / 100
        low = int(rank)
        high = min(low + 1, len(values) - 1)
        return round(values[low] + (values[high] - values[low]) * (rank - low), 2)

    by_category = {}
    for category in sorted(CATEGORIES):
        subset = [row for row in covered_rows if row["category"] == category]
        by_category[category] = {
            "count": len(subset),
            **{field: rate(field, subset) for field in fields},
        }
    return {
        "run": metadata,
        "count": len(rows),
        "covered_count": len(covered_rows),
        "corpus_not_covered": [row["case_id"] for row in rows if row.get("corpus_not_covered")],
        "metrics": {field: rate(field, covered_rows) for field in fields},
        "latency_ms": {
            "mean": numeric_mean("latency_ms"),
            "p50": percentile("latency_ms", 50),
            "p95": percentile("latency_ms", 95),
        },
        "by_category": by_category,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--predictions", type=Path)
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000/api/v1/chat")
    parser.add_argument("--bearer-token", default=os.getenv("TEST_BEARER_TOKEN"))
    parser.add_argument("--model-label", default="unspecified")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--output-dir", type=Path, default=Path("thesis-evaluation"))
    args = parser.parse_args()
    if args.predictions is None and not args.bearer_token:
        args.bearer_token = obtain_access_token()
    cases = load_dataset(args.dataset)
    saved = load_predictions(args.predictions) if args.predictions else {}
    rows: list[dict[str, Any]] = []
    for case in cases:
        if case["id"] in saved:
            saved_prediction = saved[case["id"]]
            rows.append(score_case(case, saved_prediction, saved_prediction.get("latency_ms")))
            continue
        if args.predictions:
            rows.append(
                score_case(
                    case,
                    {"status": "ERROR", "error": f"missing prediction for {case['id']}"},
                    None,
                )
            )
            rows[-1]["error"] = f"missing prediction for {case['id']}"
            continue
        try:
            prediction, latency = post_json(
                args.endpoint,
                {
                    "question": case["question"],
                    "top_k": args.top_k,
                    "effective_date": case.get("query_date"),
                },
                args.timeout,
                args.bearer_token,
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
