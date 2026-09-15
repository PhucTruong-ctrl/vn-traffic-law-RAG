"""Measure retrieval stages against the frozen 40-case thesis gold set."""

from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import statistics
import subprocess
import sys
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.rag.analyzer import analyze_request  # noqa: E402

CONFIGS = ("sparse", "dense", "hybrid", "hybrid_rrf", "full")
SWEEP_DEFAULTS: dict[str, tuple[Any, ...]] = {
    "per_query_top_k": (None,),
    "expand_queries": (None,),
    "rrf_k": (60,),
    "per_provision_cap": (None,),
    "enrich": (None,),
    "analyzers": (None,),
}


def _csv_values(value: str, cast: Any = str) -> tuple[Any, ...]:
    values = tuple(cast(item.strip()) for item in value.split(",") if item.strip())
    if not values:
        raise argparse.ArgumentTypeError("value list must not be empty")
    return values


def parse_configs(value: str) -> tuple[str, ...]:
    configs = tuple(item.strip() for item in value.split(",") if item.strip())
    unknown = sorted(set(configs) - set(CONFIGS))
    if not configs or unknown:
        raise argparse.ArgumentTypeError(f"unsupported configs: {', '.join(unknown) or 'none'}")
    return configs


def parse_bool(value: str) -> bool:
    normalized = value.strip().casefold()
    if normalized in {"on", "true", "1", "yes"}:
        return True
    if normalized in {"off", "false", "0", "no"}:
        return False
    raise argparse.ArgumentTypeError("boolean sweep values must be on or off")


def expand_configs(configs: Iterable[str], **sweeps: Iterable[Any]) -> list[dict[str, Any]]:
    dimensions = {key: tuple(values) for key, values in sweeps.items() if values is not None}
    for key, defaults in SWEEP_DEFAULTS.items():
        dimensions.setdefault(key, defaults)
    names = tuple(sorted(dimensions))
    rows: list[dict[str, Any]] = []
    for config in configs:
        for values in itertools.product(*(dimensions[name] for name in names)):
            row = {"config": config}
            row.update(dict(zip(names, values, strict=True)))
            rows.append(row)
    return rows


def canonical_id(metadata: Mapping[str, Any]) -> str | None:
    value = metadata.get("provision_id")
    if isinstance(value, str) and value.strip():
        return value.strip()
    document = metadata.get("document_id")
    if not isinstance(document, str) or not document.strip():
        return None
    parts = [document.strip()]
    for key, prefix in (("article", "dieu"), ("clause", "khoan"), ("point", "diem")):
        value = metadata.get(key)
        if value not in (None, ""):
            parts.append(f"{prefix}-{value}")
    return "__".join(parts) if len(parts) > 1 else None


def coordinate_matches(candidate: str, expected: str) -> bool:
    return (
        candidate == expected
        or candidate.startswith(expected + "__")
        or expected.startswith(candidate + "__")
    )


def hit_predicate(retrieved: Iterable[str], expected: Iterable[str]) -> bool:
    return any(
        coordinate_matches(candidate, wanted) for candidate in retrieved for wanted in expected
    )


def _level_accuracy(retrieved: list[str], expected: list[str], level: int) -> float | None:
    if not expected:
        return None
    expected_prefixes = {"__".join(item.split("__")[: level + 1]) for item in expected}
    matched = {
        prefix
        for prefix in expected_prefixes
        if any(coordinate_matches(candidate, prefix) for candidate in retrieved)
    }
    return len(matched) / len(expected_prefixes)


def _expected_ids(case: Mapping[str, Any]) -> list[str]:
    expected = case.get("expected", {})
    values = expected.get("provision_ids", case.get("expected_provision_ids", []))
    return sorted(
        {
            str(item).strip()
            for item in (values if isinstance(values, list) else [values])
            if str(item).strip()
        }
    )


def load_cases(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    cases = raw.get("cases") if isinstance(raw, dict) else raw
    if not isinstance(cases, list):
        raise ValueError("dataset must contain a cases array")
    result = []
    for case in cases:
        if not isinstance(case, dict):
            raise ValueError("each case must be an object")
        normalized = dict(case)
        normalized["question"] = str(case.get("question") or case.get("query") or "")
        normalized["expected"] = dict(
            case.get("expected") or {"provision_ids": case.get("expected_provision_ids", [])}
        )
        result.append(normalized)
    return result


def available_coordinates(path: Path) -> set[str]:
    available: set[str] = set()
    if not path.is_file():
        return available
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        metadata = row.get("metadata", row) if isinstance(row, dict) else {}
        if isinstance(metadata, dict) and (value := canonical_id(metadata)):
            available.add(value)
    return available


def covered(case: Mapping[str, Any], available: set[str]) -> bool:
    expected = _expected_ids(case)
    return any(any(coordinate_matches(actual, item) for actual in available) for item in expected)


def _retrieve(retriever: Any, query: str, config: Mapping[str, Any], top_k: int) -> list[Any]:
    method = retriever.retrieve
    kwargs: dict[str, Any] = {"top_k": int(config.get("per_query_top_k") or top_k)}
    try:
        return list(method(query, **kwargs))
    except TypeError:
        return list(method(query))


def retrieve_case(
    retriever: Any,
    case: Mapping[str, Any],
    config: Mapping[str, Any],
    top_k: int,
    analyzer_cache: dict[str, Any],
) -> tuple[list[Any], float]:
    started = time.perf_counter()
    query = str(case["question"])
    name = str(config["config"])
    queries = [query]
    if name == "full" and config.get("analyzers", True):
        analysis = analyzer_cache.get(query)
        if analysis is None:
            analysis = analyze_request(query)
            analyzer_cache[query] = analysis
        queries = list(
            getattr(analysis, "expanded_queries", ())
            or (getattr(analysis, "standalone_query", query),)
        )
        queries = queries[: int(config.get("expand_queries") or len(queries))]
    docs: list[Any] = []
    seen: set[str] = set()
    for item in queries:
        for doc in _retrieve(retriever, item, config, top_k):
            metadata = getattr(doc, "metadata", {}) or {}
            identity = str(
                metadata.get("chunk_id")
                or canonical_id(metadata)
                or getattr(doc, "page_content", "")
            )
            if identity not in seen:
                docs.append(doc)
                seen.add(identity)
            if len(docs) >= top_k:
                break
        if len(docs) >= top_k:
            break
    return docs[:top_k], (time.perf_counter() - started) * 1000


def _score(
    case: Mapping[str, Any],
    docs: list[Any],
    latency: float,
    top_k: int,
) -> dict[str, Any]:
    retrieved = sorted(
        {value for doc in docs if (value := canonical_id(getattr(doc, "metadata", {}) or {}))}
    )
    expected = _expected_ids(case)
    return {
        "case_id": case["id"],
        "category": case.get("category", "unknown"),
        "query": case["question"],
        "expected_provision_ids": expected,
        "retrieved_coordinates": retrieved,
        "hit_at_k": hit_predicate(retrieved[:top_k], expected),
        "document_accuracy": _level_accuracy(retrieved[:top_k], expected, 0),
        "article_accuracy": _level_accuracy(retrieved[:top_k], expected, 1),
        "clause_accuracy": _level_accuracy(retrieved[:top_k], expected, 2),
        "point_accuracy": _level_accuracy(retrieved[:top_k], expected, 3),
        "candidate_count": len(retrieved),
        "retrieval_ms": round(latency, 3),
    }


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = (
        "hit_at_k",
        "document_accuracy",
        "article_accuracy",
        "clause_accuracy",
        "point_accuracy",
    )
    metrics: dict[str, Any] = {}
    for field in fields:
        values = [float(row[field]) for row in rows if row[field] is not None]
        metrics[field] = {
            "value": statistics.fmean(values) if values else None,
            "case_count": len(values),
        }
    latencies = [float(row["retrieval_ms"]) for row in rows]
    metrics["mean_candidates"] = {
        "value": statistics.fmean([row["candidate_count"] for row in rows]) if rows else None,
        "case_count": len(rows),
    }
    metrics["retrieval_ms"] = {
        "p50": statistics.median(latencies) if latencies else None,
        "p95": (sorted(latencies)[max(0, int(len(latencies) * 0.95) - 1)] if latencies else None),
        "mean": statistics.fmean(latencies) if latencies else None,
        "case_count": len(latencies),
    }
    return metrics


def run_ablation(
    cases: list[dict[str, Any]], configs: list[dict[str, Any]], retriever: Any, available: set[str]
) -> dict[str, Any]:
    excluded = sorted(case["id"] for case in cases if not covered(case, available))
    included = [case for case in cases if case["id"] not in excluded]
    analyzer_cache: dict[str, Any] = {}
    results: dict[str, Any] = {}
    all_rows: list[dict[str, Any]] = []
    for config in configs:
        key = config_label(config)
        rows: list[dict[str, Any]] = []
        for case in included:
            docs, latency = retrieve_case(
                retriever, case, config, int(config.get("top_k", 5)), analyzer_cache
            )
            row = _score(case, docs, latency, int(config.get("top_k", 5)))
            row["config"] = key
            rows.append(row)
        results[key] = {
            "config": config,
            "metrics": _summary(rows),
            "by_category": {
                category: _summary([row for row in rows if row["category"] == category])
                for category in sorted({row["category"] for row in rows})
            },
            "rows": rows,
        }
        all_rows.extend(rows)
    return {
        "excluded_case_ids": excluded,
        "included_case_count": len(included),
        "configs": results,
        "rows": all_rows,
    }


def config_label(config: Mapping[str, Any]) -> str:
    extras = [
        f"{key}={config[key]}"
        for key in sorted(config)
        if key != "config" and config[key] is not None
    ]
    return str(config["config"]) + ("[" + ",".join(extras) + "]" if extras else "")


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    rows = list(rows)
    fields = (
        "config",
        "case_id",
        "category",
        "query",
        "expected_provision_ids",
        "retrieved_coordinates",
        "hit_at_k",
        "document_accuracy",
        "article_accuracy",
        "clause_accuracy",
        "point_accuracy",
        "candidate_count",
        "retrieval_ms",
    )
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    field: json.dumps(row[field], ensure_ascii=False)
                    if isinstance(row.get(field), list)
                    else row.get(field)
                    for field in fields
                }
            )


def write_markdown(path: Path, payload: Mapping[str, Any]) -> None:
    fields = (
        "hit_at_k",
        "document_accuracy",
        "article_accuracy",
        "clause_accuracy",
        "point_accuracy",
        "mean_candidates",
    )
    lines = [
        "# Retrieval ablation",
        "",
        "| Config | " + " | ".join(fields) + " |",
        "|---|" + "---|" * len(fields),
    ]
    values = {
        field: [
            float(item["metrics"][field]["value"])
            for item in payload["configs"].values()
            if item["metrics"][field].get("value") is not None
        ]
        for field in fields
    }
    winners = {field: max(items) if items else None for field, items in values.items()}
    for name, item in payload["configs"].items():
        rendered = []
        for field in fields:
            value = item["metrics"][field].get("value")
            text = "—" if value is None else f"{value:.4f}"
            if value is not None and value == winners[field]:
                text = f"**{text}**"
            rendered.append(text)
        lines.append("| " + name + " | " + " | ".join(rendered) + " |")
    lines.extend(
        ["", f"Excluded cases: {', '.join(payload.get('excluded_case_ids', [])) or 'none'}"]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--configs", type=parse_configs, default=CONFIGS)
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=Path("data/evaluation/ablation"))
    parser.add_argument(
        "--per-query-top-k", type=lambda value: _csv_values(value, int), default=None
    )
    parser.add_argument(
        "--expand-queries", type=lambda value: _csv_values(value, int), default=None
    )
    parser.add_argument("--rrf-k", type=lambda value: _csv_values(value, int), default=None)
    parser.add_argument(
        "--per-provision-cap", type=lambda value: _csv_values(value, int), default=None
    )
    parser.add_argument("--enrich", type=lambda value: _csv_values(value, parse_bool), default=None)
    parser.add_argument(
        "--analyzers", type=lambda value: _csv_values(value, parse_bool), default=None
    )
    parser.add_argument("--chunks", type=Path, default=ROOT / "data/processed/chunks.jsonl")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.top_k < 1:
        raise SystemExit("--top-k must be positive")
    sweeps = {key: getattr(args, key) for key in SWEEP_DEFAULTS if getattr(args, key) is not None}
    configs = expand_configs(args.configs, **sweeps)
    for config in configs:
        config["top_k"] = args.top_k
    cases = load_cases(args.dataset)
    from app.rag.retrieval import Retriever

    result = run_ablation(
        cases, configs, Retriever(top_k=args.top_k), available_coordinates(args.chunks)
    )
    embedding = __import__(
        "app.config", fromlist=["get_embedding_settings"]
    ).get_embedding_settings()
    result["metadata"] = {
        "timestamp": datetime.now(UTC).isoformat(),
        "git_commit": subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=False
        ).stdout.strip()
        or None,
        "dataset": str(args.dataset),
        "chunks_sha256": _sha256(args.chunks),
        "embedding_model": getattr(embedding, "model", None),
        "configs": configs,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    write_json(args.output_dir / f"{run_id}.json", result)
    write_csv(args.output_dir / f"{run_id}.csv", result["rows"])
    write_markdown(args.output_dir / f"{run_id}.md", result)
    print(
        json.dumps(
            {
                "run_id": run_id,
                "output_dir": str(args.output_dir),
                "excluded_case_ids": result["excluded_case_ids"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
