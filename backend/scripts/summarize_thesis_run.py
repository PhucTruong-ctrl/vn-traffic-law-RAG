#!/usr/bin/env python3
"""Render a completed thesis evaluation run as deterministic Markdown."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
RUN_DIR = ROOT / "data" / "evaluation" / "thesis-run"
MISSING = "—"
METRICS = (
    "retrieval_hit_at_k", "retrieval_hit_at_k_hierarchical", "retrieval_candidate_hit_at_k",
    "document_accuracy", "article_accuracy", "clause_accuracy", "point_accuracy",
    "citation_present", "citation_validity", "citation_support", "answer_correctness_manual",
    "faithfulness", "completeness", "abstention_accuracy",
)
CATEGORIES = ("count", "scored_count", "retrieval_hit_at_k_hierarchical", "document_accuracy", "article_accuracy", "clause_accuracy", "point_accuracy", "abstention_accuracy")
CLASS_NOTES = {
    "no_corpus_evidence": "Không có bằng chứng trong corpus để trả lời có căn cứ.",
    "retrieval_miss": "Truy hồi không đưa được điều khoản kỳ vọng vào ứng viên.",
    "citation_missing": "Câu trả lời có trích dẫn nhưng trích dẫn không hợp lệ hoặc thiếu.",
    "timeout": "Pipeline không hoàn tất trong thời gian cho phép.",
}
DEFAULT_TARGETS = {"retrieval_hit_at_k_hierarchical": .80, "document_accuracy": .85, "article_accuracy": .80, "clause_accuracy": .75, "point_accuracy": .70, "citation_validity": .95, "refusal_recall": .85, "refusal_f1": .85, "latency_p95_lt": 15.0}

def _load(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default

def resolve_run(value: str) -> tuple[Path, str]:
    path = Path(value)
    if not path.exists():
        path = RUN_DIR / value
    if path.suffix == ".jsonl":
        run_id = path.stem
    else:
        run_id = path.stem.removesuffix(".aggregate")
        path = path.with_suffix(".jsonl")
    return path, run_id

def fmt(value: Any) -> str:
    if value is None or value == "": return MISSING
    if isinstance(value, float): return f"{value:.4f}".rstrip("0").rstrip(".")
    if isinstance(value, (list, tuple, set)): return ", ".join(map(str, value)) or MISSING
    return str(value)

def metric(value: Any) -> tuple[Any, Any]:
    return (value.get("value"), value.get("n")) if isinstance(value, dict) else (value, MISSING)

def table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join("---" for _ in headers) + " |"]
    out += ["| " + " | ".join(fmt(x) for x in row) + " |" for row in rows]
    return out

def read_rows(path: Path) -> list[dict[str, Any]]:
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
                if isinstance(item, dict): rows.append(item)
            except json.JSONDecodeError: pass
    except OSError: pass
    return rows

def load_targets(value: str | None) -> dict[str, float]:
    if not value: return DEFAULT_TARGETS.copy()
    path = Path(value)
    data = _load(path, None) if path.exists() else None
    if data is None:
        try: data = json.loads(value)
        except json.JSONDecodeError: return DEFAULT_TARGETS.copy()
    return {**DEFAULT_TARGETS, **{str(k): float(v) for k, v in data.items() if isinstance(v, (int, float))}}

def render(aggregate: dict[str, Any], rows: list[dict[str, Any]], reviews: list[dict[str, Any]], run_id: str, targets: dict[str, float] | None = None) -> str:
    run = aggregate.get("run") if isinstance(aggregate.get("run"), dict) else {}
    lines = [f"# Thesis evaluation run: {run_id}", "", "## Header", ""]
    lines += table(["Field", "Value"], [[k, run.get(k)] for k in ("run_id", "created_at", "git_commit", "model_label", "generation_model", "analyzer_model", "embedding_model", "endpoint", "top_k", "dataset_sha256", "chunks_sha256", "percentile_method")])
    accounting = aggregate.get("case_accounting") if isinstance(aggregate.get("case_accounting"), dict) else {}
    count = aggregate.get("count", len(rows)); lists = {s: accounting.get(s, []) if isinstance(accounting.get(s, []), list) else [] for s in ("scored", "out_of_corpus", "parser_gap")}
    lines += ["", "## Coverage accounting", "", f"Total cases: **{fmt(count)}**; scored: **{len(lists['scored'])}**; out_of_corpus: **{len(lists['out_of_corpus'])}**; parser_gap: **{len(lists['parser_gap'])}** (denominator: {fmt(count)})."]
    if sum(map(len, lists.values())) != count: lines.append(f"WARNING: coverage lists sum to {sum(map(len, lists.values()))}, expected {fmt(count)}.")
    lines += table(["Status", "Case IDs", "n"], [[s, lists[s], len(lists[s])] for s in lists])
    lines += ["", "## Main metrics", "", *table(["Metric", "Value", "n"], [[m, *metric((aggregate.get("metrics") or {}).get(m))] for m in METRICS])]
    lines += ["", "## Per-category", "", *table(["Category", *CATEGORIES], [[cat, *[(catdata.get(c) if c in ("count", "scored_count") else metric(catdata.get(c))[0]) for c in CATEGORIES]] for cat, catdata in sorted((aggregate.get("by_category") or {}).items()) if isinstance(catdata, dict)])]
    lines += ["", "## Refusal analysis", ""]
    for name in ("refusal", "refusal_effective"):
        block = aggregate.get(name) or {}; cm = block.get("confusion_matrix") or {}; lines += [f"### {name}", "", *table(["TP", "FP", "TN", "FN", "Precision", "Recall", "F1", "Denominators"], [[cm.get("tp"), cm.get("fp"), cm.get("tn"), cm.get("fn"), block.get("precision_refusal"), block.get("recall_refusal"), block.get("f1_refusal"), block.get("denominators")]])]
    fns = (aggregate.get("refusal_effective") or {}).get("false_negatives") or []; lines += ["", "### Trả lời khi đáng lẽ phải từ chối", "", *table(["Case ID", "Category", "Status", "Reason code", "Cited IDs"], [[r.get("case_id"), r.get("category"), r.get("coverage_status", r.get("status")), r.get("reason_code"), r.get("cited", r.get("cited_provision_ids"))] for r in fns])]
    lat = aggregate.get("latency_ms") or {}; lines += ["", "## Latency", "", *table(["Mean", "Min", "Max", "p50", "p95", "Count"], [[lat.get(k) for k in ("mean", "min", "max", "p50", "p95", "count")]])]
    stages = aggregate.get("stage_latency_ms") or {}; lines += ["", *table(["Stage", "Mean", "Min", "Max", "p50", "p95", "Count"], [[s, *[v.get(k) for k in ("mean", "min", "max", "p50", "p95", "count")]] for s, v in sorted(stages.items()) if isinstance(v, dict)]), "", f"stage_coverage: {fmt(aggregate.get('stage_coverage'))}"]
    errors = aggregate.get("error_classification") or {}; lines += ["", "## Error classification", "", *table(["Class", "Count"], [[k, v] for k, v in sorted(errors.items())])]
    failures = sorted([r for r in rows if r.get("error_classification", "none") != "none"], key=lambda r: (str(r.get("error_classification")), str(r.get("case_id"))))[:15]
    lines += ["", "### Representative failures (maximum 15)", ""]
    for cls in sorted({str(r.get("error_classification")) for r in failures}):
        lines += [f"**{cls}** — {CLASS_NOTES.get(cls, 'Lỗi cần xem xét trong pipeline legal-RAG.')}", "", *table(["Case ID", "Category", "Question", "Expected provision IDs", "Cited IDs", "Classification"], [[r.get("case_id"), r.get("category"), str(r.get("question", ""))[:120], r.get("expected_provision_ids"), r.get("cited_provision_ids"), cls] for r in failures if str(r.get("error_classification")) == cls]), ""]
    targets = targets or DEFAULT_TARGETS; lines += ["## Verdict", ""]
    checks = []
    metrics = aggregate.get("metrics") or {}; ref = aggregate.get("refusal_effective") or {}; lat = aggregate.get("latency_ms") or {}
    for key, target in targets.items():
        if key == "refusal_recall": actual = ref.get("recall_refusal"); ok = actual is not None and actual >= target
        elif key == "refusal_f1": actual = ref.get("f1_refusal"); ok = actual is not None and actual >= target
        elif key == "latency_p95_lt": actual = lat.get("p95"); ok = actual is not None and actual < target
        else: actual, _ = metric(metrics.get(key)); ok = actual is not None and actual >= target
        checks.append(ok); lines.append(f"- {key}: {fmt(actual)} vs {target} → **{'ĐẠT' if ok else 'CHƯA ĐẠT'}**")
    lines += ["", f"**Overall verdict: {'ĐẠT' if all(checks) else 'CHƯA ĐẠT'}**", ""]
    return "\n".join(lines)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("run"); parser.add_argument("--aggregate", type=Path); parser.add_argument("--reviews", type=Path); parser.add_argument("--output", type=Path); parser.add_argument("--targets"); args = parser.parse_args()
    raw, run_id = resolve_run(args.run); aggregate_path = args.aggregate or raw.with_suffix(".aggregate.json"); aggregate = _load(aggregate_path, {}); rows = read_rows(raw); reviews = read_rows(args.reviews) if args.reviews else []
    output = render(aggregate, rows, reviews, run_id, load_targets(args.targets)); text = output + "\n"
    if args.output: args.output.write_text(text, encoding="utf-8")
    else: sys.stdout.write(text)
    return 0

if __name__ == "__main__": raise SystemExit(main())
