"""Run the deterministic 40-case thesis evaluation.

The runner accepts a JSON array/object dataset and either invokes the HTTP chat
endpoint or scores an existing prediction JSONL. It never infers semantic
answer correctness: that field is supplied later by the manual reviewer.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
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


def _citation_coordinates(
    citations: list[Any],
    index: dict[str, set[tuple[str, str | None, str | None, str | None]]],
) -> tuple[bool, list[str]]:
    invalid: list[str] = []
    for citation in citations:
        coordinate = _coordinate_from_metadata(citation)
        identifier = citation.get("source_id") if isinstance(citation, dict) else None
        identifier = (
            str(identifier or citation.get("provision_id", ""))
            if isinstance(citation, dict)
            else ""
        )
        if coordinate is None or coordinate[:4] not in index.get(coordinate[0], set()):
            invalid.append(identifier or coordinate[4] if coordinate else identifier or "<unknown>")
    return not invalid, invalid


def load_coordinate_index(
    path: Path,
) -> dict[str, set[tuple[str, str | None, str | None, str | None]]]:
    index: dict[str, set[tuple[str, str | None, str | None, str | None]]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        fail(f"cannot read chunks {path}: {exc}")
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        metadata = item.get("metadata", item) if isinstance(item, dict) else {}
        coordinate = _coordinate_from_metadata(metadata)
        if coordinate:
            index.setdefault(coordinate[0], set()).add(coordinate[:4])
    return index


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


def _ancestor_hit(actual: set[str], expected: set[str]) -> bool:
    return any(
        candidate == wanted
        or candidate.startswith(wanted + "__")
        or wanted.startswith(candidate + "__")
        for candidate in actual
        for wanted in expected
    )


def score_case(
    case: dict[str, Any],
    prediction: dict[str, Any],
    latency_ms: float | None = None,
    coverage: dict[str, Any] | None = None,
    coordinate_index: dict[str, set[tuple[str, str | None, str | None, str | None]]] | None = None,
) -> dict[str, Any]:
    citations = prediction.get("citations", [])
    if not isinstance(citations, list):
        citations = []
    if not isinstance(case.get("expected"), dict):
        case = normalize_case(case, 0)
    expected = case["expected"]
    wanted = expected_ids(case)
    coordinates = _prediction_coordinates(prediction)
    cited_ids = {item[4] for item in coordinates}
    retrieved_ids = _retrieved_ids(prediction)
    status = str(prediction.get("status", "")).upper()
    timed_out = status in {"TIMEOUT", "ERROR", "FAILED"}
    coverage = coverage or {"status": "scored", "basis": "fallback", "missing_coordinates": []}
    actual_abstain = status in {"INSUFFICIENT_EVIDENCE", "OUT_OF_SCOPE"}
    should_abstain = bool(expected.get("abstain", False))
    scored = coverage["status"] in {"scored", "parser_gap"}
    citation_present = bool(citations)
    citation_validity, invalid_citations = _citation_coordinates(citations, coordinate_index or {})
    result = {
        "case_id": case["id"],
        "category": case["category"],
        "question": case["question"],
        "prediction": prediction,
        "coverage": coverage,
        "corpus_covered": scored,
        "corpus_not_covered": not scored,
        "retrieved_provision_ids": sorted(retrieved_ids or set()),
        "cited_provision_ids": sorted(cited_ids),
        "expected_provision_ids": sorted(wanted),
        "retrieval_hit_at_k": None
        if timed_out or not scored or not wanted
        else bool(cited_ids & wanted),
        "retrieval_hit_at_k_hierarchical": None
        if timed_out or not scored or not wanted
        else _ancestor_hit(cited_ids, wanted),
        "retrieval_candidate_hit_at_k": None
        if timed_out or not scored or not wanted or retrieved_ids is None
        else _ancestor_hit(retrieved_ids, wanted),
        "document_accuracy": None
        if timed_out or not scored
        else _level_accuracy(expected, coordinates, "document"),
        "article_accuracy": None
        if timed_out or not scored
        else _level_accuracy(expected, coordinates, "article"),
        "clause_accuracy": None
        if timed_out or not scored
        else _level_accuracy(expected, coordinates, "clause"),
        "point_accuracy": None
        if timed_out or not scored
        else _level_accuracy(expected, coordinates, "point"),
        # A refusal is meant to cite nothing, so presence is only defined for cases
        # that must be answered from evidence.
        "citation_present": None
        if timed_out or not scored or should_abstain
        else citation_present,
        "citation_validity": None if timed_out or not scored else citation_validity,
        "invalid_citations": invalid_citations,
        "citation_support": None,
        "answer_correctness_manual": None,
        "abstention_accuracy": None if timed_out else actual_abstain == should_abstain,
        "abstained": actual_abstain,
        "answer_text": prediction.get("answer") or prediction.get("answer_text"),
        "latency_ms": round(latency_ms, 2) if latency_ms is not None else None,
        "history_used": bool(case.get("conversation_history")),
    }
    result["error_classification"] = classify_error(result)
    return result


def _retrieved_ids(prediction: dict[str, Any]) -> set[str] | None:
    debug = prediction.get("debug")
    if not isinstance(debug, dict) or not isinstance(debug.get("retrieved_provision_ids"), list):
        return None
    return {
        parsed[4]
        for value in debug["retrieved_provision_ids"]
        if (parsed := parse_coordinate(value))
    }


def classify_error(row: dict[str, Any]) -> str:
    if row.get("coverage", {}).get("status") == "out_of_corpus":
        return "no_corpus_evidence"
    if row.get("retrieval_hit_at_k") is False:
        return "retrieval_miss"
    for level in ("document", "article", "clause", "point"):
        if row.get(f"{level}_accuracy") is False:
            return f"wrong_{level}"
    if row.get("abstention_accuracy") is False:
        return (
            "refusal_error_false_negative"
            if row.get("expected_abstain")
            else "refusal_error_false_positive"
        )
    if row.get("citation_validity") is False:
        return "citation_missing"
    prediction = row.get("prediction") or {}
    if str(prediction.get("status", "")).upper() in {"TIMEOUT", "ERROR", "FAILED"}:
        return "timeout"
    return "none"


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


def _percentile(values: list[float], fraction: float) -> float | None:
    """Linear-interpolation percentile; `fraction` in [0, 1] (documented in the report)."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _latency_block(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"mean": None, "min": None, "max": None, "p50": None, "p95": None, "count": 0}
    return {
        "mean": round(sum(values) / len(values), 2),
        "min": round(min(values), 2),
        "max": round(max(values), 2),
        "p50": round(_percentile(values, 0.5) or 0.0, 2),
        "p95": round(_percentile(values, 0.95) or 0.0, 2),
        "count": len(values),
    }


def _coverage_status(row: dict[str, Any]) -> str:
    """Rows saved before coverage tracking, or by external tools, count as scored."""
    coverage = row.get("coverage")
    if not isinstance(coverage, dict):
        return "scored"
    return str(coverage.get("status") or "scored")


def _refusal_block(rows: list[dict[str, Any]], *, treat_uncovered_as_abstain: bool) -> dict[str, Any]:
    """Refusal confusion matrix; positive class = the case should have been refused."""
    tp = fp = tn = fn = 0
    excluded = 0
    false_negatives: list[dict[str, Any]] = []
    for row in rows:
        if row.get("error") or row.get("prediction") is None:
            # A transport/timeout failure is not a decision the system made, so it
            # must not be scored as a refusal error.
            excluded += 1
            continue
        expected = bool(row.get("expected_abstain"))
        if treat_uncovered_as_abstain and _coverage_status(row) != "scored":
            # No gold evidence exists in the corpus, so an answer cannot be grounded.
            expected = True
        actual = bool(row.get("abstained"))
        if expected and actual:
            tp += 1
        elif expected:
            fn += 1
            prediction = row.get("prediction") or {}
            citations = prediction.get("citations")
            false_negatives.append(
                {
                    "case_id": row.get("case_id"),
                    "category": row.get("category"),
                    "question": row.get("question"),
                    "status": prediction.get("status"),
                    "reason_code": prediction.get("reason_code"),
                    "coverage_status": _coverage_status(row),
                    "cited": sorted(
                        str(citation.get("source_id"))
                        for citation in (citations if isinstance(citations, list) else [])
                        if isinstance(citation, dict)
                    )[:6],
                }
            )
        elif actual:
            fp += 1
        else:
            tn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "confusion_matrix": {"tp": tp, "fp": fp, "tn": tn, "fn": fn},
        "precision_refusal": round(precision, 4),
        "recall_refusal": round(recall, 4),
        "f1_refusal": round(f1, 4),
        "denominators": {
            "should_refuse": tp + fn,
            "should_answer": fp + tn,
            "cases": tp + fp + tn + fn,
            "excluded_transport_errors": excluded,
        },
        "false_negatives": false_negatives,
    }


def aggregate(rows: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "retrieval_hit_at_k",
        "retrieval_hit_at_k_hierarchical",
        "retrieval_candidate_hit_at_k",
        "document_accuracy",
        "article_accuracy",
        "clause_accuracy",
        "point_accuracy",
        "citation_present",
        "citation_validity",
        "citation_support",
        "answer_correctness_manual",
        "faithfulness",
        "completeness",
        "abstention_accuracy",
    )

    def metric(field: str, subset: list[dict[str, Any]]) -> dict[str, Any]:
        values = [
            row.get(field) for row in subset if isinstance(row.get(field), (bool, int, float))
        ]
        return {"value": round(sum(values) / len(values), 4) if values else None, "n": len(values)}

    # Only cases whose gold evidence exists in the index can be scored for retrieval;
    # `parser_gap` stays scored on purpose so a real parser defect remains visible.
    scored = [row for row in rows if _coverage_status(row) in {"scored", "parser_gap"}]
    with_evidence = [row for row in scored if expected_ids(row)]
    categories = sorted({str(row.get("category")) for row in rows})
    stage_values: dict[str, list[float]] = {}
    stage_reports = 0
    for row in rows:
        debug = (row.get("prediction") or {}).get("debug")
        stages = debug.get("stage_ms") if isinstance(debug, dict) else None
        if not isinstance(stages, dict) or not stages:
            continue
        stage_reports += 1
        for key, value in stages.items():
            if isinstance(value, (int, float)):
                stage_values.setdefault(str(key), []).append(float(value))
    latencies = [
        float(row["latency_ms"])
        for row in rows
        if isinstance(row.get("latency_ms"), (int, float))
    ]
    manual = metric("answer_correctness_manual", rows)
    return {
        "run": metadata,
        "count": len(rows),
        "covered_count": len(scored),
        "out_of_corpus_count": sum(_coverage_status(row) == "out_of_corpus" for row in rows),
        "parser_gap_count": sum(_coverage_status(row) == "parser_gap" for row in rows),
        "retrieval_case_count": len(with_evidence),
        "metrics": {field: metric(field, scored) for field in fields},
        "by_category": {
            category: {
                "count": sum(row.get("category") == category for row in rows),
                "scored_count": sum(row.get("category") == category for row in scored),
                **{
                    field: metric(
                        field, [row for row in scored if row.get("category") == category]
                    )
                    for field in fields
                },
            }
            for category in categories
        },
        "refusal": _refusal_block(rows, treat_uncovered_as_abstain=False),
        "refusal_effective": _refusal_block(rows, treat_uncovered_as_abstain=True),
        "manual_correctness": manual["value"],
        "manual_scored_count": manual["n"],
        "manual_missing_count": len(rows) - manual["n"],
        "latency_ms": _latency_block(latencies),
        "percentile_method": "linear interpolation between closest ranks",
        "stage_latency_ms": {
            key: _latency_block(values) for key, values in sorted(stage_values.items())
        },
        "stage_coverage": round(stage_reports / len(rows), 4) if rows else None,
        "case_accounting": {
            status: sorted(str(row.get("case_id")) for row in rows if _coverage_status(row) == status)
            for status in ("scored", "out_of_corpus", "parser_gap")
        },
        "error_classification": {
            name: sum(row.get("error_classification") == name for row in rows)
            for name in sorted({str(row.get("error_classification")) for row in rows})
        },
    }


def _sha256(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def coverage_for_case(case: dict[str, Any], chunks: Path, manifest: Path | None) -> dict[str, Any]:
    available: set[str] = set()
    try:
        for line in chunks.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            metadata = item.get("metadata", item) if isinstance(item, dict) else {}
            coordinate = _coordinate_from_metadata(metadata)
            if coordinate:
                parts = coordinate[4].split("__")
                available.update("__".join(parts[:index]) for index in range(1, len(parts) + 1))
    except (OSError, json.JSONDecodeError):
        pass
    missing = sorted(expected_ids(case) - available)
    if not missing:
        return {
            "status": "scored",
            "basis": "chunks+manifest" if manifest and manifest.exists() else "chunks_only",
            "missing_coordinates": [],
        }
    markers: set[str] = set()
    if manifest and manifest.exists():
        try:
            raw = json.loads(manifest.read_text(encoding="utf-8"))
            for entry in raw.get("parser_gaps", []):
                if isinstance(entry, str):
                    markers.add(entry)
            for document, values in raw.get("markdown_markers", {}).items():
                for key in ("articles", "clauses", "points"):
                    for value in values.get(key, []):
                        markers.add(
                            str(value)
                            if str(value).startswith(document)
                            else f"{document}__{value.replace('/', '__')}"
                        )
        except (OSError, json.JSONDecodeError, AttributeError):
            pass
    parser_gap = [
        value
        for value in missing
        if value in markers
        or any(marker.startswith(value) or value.startswith(marker) for marker in markers)
    ]
    return {
        "status": "parser_gap" if parser_gap else "out_of_corpus",
        "basis": "chunks+manifest" if manifest and manifest.exists() else "chunks_only",
        "missing_coordinates": missing,
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
    parser.add_argument("--chunks", type=Path, default=ROOT / "data/processed/chunks.jsonl")
    parser.add_argument(
        "--coverage", type=Path, default=ROOT / "data/evaluation/corpus-coverage.json"
    )
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("thesis-evaluation"))
    args = parser.parse_args()
    if args.predictions is None and not args.bearer_token:
        args.bearer_token = obtain_access_token()
    cases = load_dataset(args.dataset)
    saved = load_predictions(args.predictions) if args.predictions else {}
    coordinate_index = load_coordinate_index(args.chunks)
    reviews: dict[str, dict[str, Any]] = {}
    if args.reviews and args.reviews.exists():
        for line in args.reviews.read_text(encoding="utf-8").splitlines():
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict) and isinstance(value.get("case_id"), str):
                reviews[value["case_id"]] = value
    rows: list[dict[str, Any]] = []
    for case in cases:
        coverage = coverage_for_case(case, args.chunks, args.coverage)
        if case["id"] in saved:
            prediction = saved[case["id"]]
            row = score_case(
                case, prediction, prediction.get("latency_ms"), coverage, coordinate_index
            )
        elif args.predictions:
            row = score_case(
                case,
                {"status": "ERROR", "error": f"missing prediction for {case['id']}"},
                None,
                coverage,
                coordinate_index,
            )
        else:
            try:
                payload = {
                    "question": case["question"],
                    "top_k": args.top_k,
                    "effective_date": case.get("query_date"),
                }
                if case.get("conversation_history"):
                    payload["history"] = case["conversation_history"]
                prediction, latency = post_json(
                    args.endpoint, payload, args.timeout, args.bearer_token
                )
                row = score_case(case, prediction, latency, coverage, coordinate_index)
            except RuntimeError as exc:
                row = score_case(
                    case, {"status": "ERROR", "error": str(exc)}, None, coverage, coordinate_index
                )
        row["expected_abstain"] = bool(case.get("expected", {}).get("abstain", False))
        row.update(
            {key: value for key, value in reviews.get(case["id"], {}).items() if key != "case_id"}
        )
        rows.append(row)
    if len(rows) != len(cases):
        fail("incomplete evaluation")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    try:
        git_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        git_commit = ""
    metadata = {
        "run_id": run_id,
        "created_at": datetime.now(UTC).isoformat(),
        "git_commit": git_commit,
        "dataset": str(args.dataset),
        "dataset_sha256": _sha256(args.dataset),
        "chunks_sha256": _sha256(args.chunks),
        "endpoint": None if args.predictions else args.endpoint,
        "top_k": args.top_k,
        "timeout_seconds": args.timeout,
        "model_label": args.model_label,
        **{
            key: os.getenv(key.upper(), "")
            for key in (
                "generation_model",
                "analyzer_model",
                "embedding_model",
                "embedding_dimensions",
            )
        },
    }
    raw_path = args.output_dir / f"{run_id}.jsonl"
    aggregate_path = args.output_dir / f"{run_id}.aggregate.json"
    csv_path = args.output_dir / f"{run_id}.cases.csv"
    raw_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )
    aggregate_path.write_text(
        json.dumps(aggregate(rows, metadata), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    columns = [
        "case_id",
        "category",
        "question",
        "coverage_status",
        "coverage_basis",
        "retrieved_provision_ids",
        "cited_provision_ids",
        "expected_provision_ids",
        "invalid_citations",
        "retrieval_hit_at_k",
        "retrieval_candidate_hit_at_k",
        "document_accuracy",
        "article_accuracy",
        "clause_accuracy",
        "point_accuracy",
        "citation_present",
        "citation_validity",
        "citation_support",
        "answer_correctness_manual",
        "abstained",
        "latency_ms",
        "error_classification",
    ]
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    column: json.dumps(row.get(column), ensure_ascii=False)
                    if isinstance(row.get(column), (list, dict))
                    else row.get(column)
                    for column in columns
                    if column not in {"coverage_status", "coverage_basis"}
                }
                | {
                    "coverage_status": row["coverage"]["status"],
                    "coverage_basis": row["coverage"]["basis"],
                }
            )
    print(
        json.dumps(
            {
                "raw": str(raw_path),
                "aggregate": str(aggregate_path),
                "cases": str(csv_path),
                "count": len(rows),
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
