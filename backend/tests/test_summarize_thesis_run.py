from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]
spec = importlib.util.spec_from_file_location(
    "summarizer", ROOT / "scripts" / "summarize_thesis_run.py"
)
assert spec and spec.loader
summarizer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(summarizer)


def test_coverage_sum_warning() -> None:
    text = summarizer.render(
        {"count": 40, "case_accounting": {"scored": ["a"], "out_of_corpus": [], "parser_gap": []}},
        [],
        [],
        "r",
    )
    assert "WARNING: coverage lists sum to 1, expected 40." in text


def test_target_verdict_pass_and_fail() -> None:
    aggregate = {
        "metrics": {"retrieval_hit_at_k_hierarchical": {"value": 0.8, "n": 1}},
        "refusal_effective": {"recall_refusal": 0.9, "f1_refusal": 0.9},
        "latency_ms": {"p95": 1},
    }
    assert "retrieval_hit_at_k_hierarchical: 0.8 vs 0.8 → **ĐẠT**" in summarizer.render(
        aggregate, [], [], "r", {"retrieval_hit_at_k_hierarchical": 0.8}
    )
    aggregate["metrics"]["retrieval_hit_at_k_hierarchical"]["value"] = 0.2
    assert "**CHƯA ĐẠT**" in summarizer.render(
        aggregate, [], [], "r", {"retrieval_hit_at_k_hierarchical": 0.8}
    )


def test_failure_selection_is_capped_at_fifteen() -> None:
    rows = [
        {
            "case_id": f"c{i:02}",
            "category": "x",
            "question": "q",
            "error_classification": "retrieval_miss",
        }
        for i in range(20)
    ]
    text = summarizer.render({}, rows, [], "r")
    assert text.count("| retrieval_miss |") == 15


def test_missing_run_and_latency_blocks_render() -> None:
    text = summarizer.render({}, [], [], "missing")
    assert "## Header" in text and "## Latency" in text and "—" in text
