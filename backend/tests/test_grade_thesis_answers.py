from __future__ import annotations

import json
from pathlib import Path

from scripts.grade_thesis_answers import (
    grade_row,
    parse_judge_response,
    write_outputs,
)


def test_valid_judge_json_parses() -> None:
    value = parse_judge_response(
        json.dumps(
            {
                "accuracy": 1,
                "faithfulness": 0.8,
                "completeness": 1,
                "citation_support": 0.9,
                "notes": "ok",
                "evidence": ["excerpt"],
            }
        )
    )
    assert value["accuracy"] == 1


def test_malformed_judge_retries_then_error() -> None:
    calls = []

    def judge(_: str) -> str:
        calls.append(1)
        return "nope"

    row = {
        "case_id": "x",
        "category": "normal",
        "question": "q",
        "prediction": {"answer": "a", "citations": []},
    }
    result = grade_row(row, {}, judge)
    assert result["answer_correctness_manual"] is None
    assert result["notes"].startswith("judge_error")
    assert len(calls) == 2


def test_refusal_has_null_semantic_scores() -> None:
    row = {
        "case_id": "x",
        "category": "insufficient_evidence",
        "prediction": {"answer": "Không có thông tin", "status": "abstain"},
    }
    result = grade_row(row, {}, None)
    assert result["answer_correctness_manual"] == 1
    assert result["faithfulness"] is None
    assert result["completeness"] is None
    assert result["citation_support"] is None


def test_writers_emit_jsonl_csv_and_summary(tmp_path: Path) -> None:
    prefix = tmp_path / "run"
    rows = [
        {
            "case_id": "a",
            "answer_correctness_manual": 0.5,
            "faithfulness": 0.5,
            "completeness": 1,
            "citation_support": 0.5,
            "notes": "partial",
            "judge": "j",
            "evidence": [],
            "human_override": "",
            "coverage_status": "corpus",
            "category": "normal",
        },
        {
            "case_id": "b",
            "answer_correctness_manual": 1,
            "faithfulness": None,
            "completeness": None,
            "citation_support": None,
            "notes": "refusal",
            "judge": "d",
            "evidence": [],
            "human_override": "",
            "coverage_status": "out_of_corpus",
            "category": "out_of_scope",
        },
    ]
    write_outputs(prefix, rows)
    assert len(prefix.with_suffix(".reviews.jsonl").read_text().splitlines()) == 2
    assert "case_id" in prefix.with_suffix(".reviews.csv").read_text()
    assert "Out of corpus" in prefix.with_suffix(".review-summary.md").read_text()
