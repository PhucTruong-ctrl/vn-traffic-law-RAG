from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]


def load_runner():
    path = ROOT / "scripts" / "run_thesis_evaluation.py"
    spec = importlib.util.spec_from_file_location("thesis_runner_identity", path)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def case(provision_id: str) -> dict:
    return {
        "id": "identity-case",
        "category": "exact_reference",
        "question": "q",
        "expected": {
            "provision_ids": [provision_id],
            "document_ids": [provision_id.split("__", 1)[0]],
            "article_ids": [provision_id],
            "clause_ids": [provision_id],
            "point_ids": [],
            "abstain": False,
        },
    }


def test_fresh_run_citation_prefers_document_id_over_display_number() -> None:
    runner = load_runner()
    provision_id = "nd-168-2024__dieu-6__khoan-9"
    result = runner.score_case(
        case(provision_id),
        {
            "status": "VERIFIED",
            "citations": [
                {
                    "document_id": "nd-168-2024",
                    "document_number": "168/2024/NĐ-CP",
                    "article": "6",
                    "clause": "9",
                    "source_id": "nd-168-2024:0024",
                }
            ],
        },
    )
    assert result["retrieval_hit_at_k"] is True
    assert result["document_accuracy"] == 1.0
    assert result["clause_accuracy"] == 1.0


def test_fresh_run_citation_accepts_document_id_without_display_number() -> None:
    runner = load_runner()
    provision_id = "tt-16-2024__dieu-3__khoan-1__diem-a"
    result = runner.score_case(
        case(provision_id),
        {
            "status": "VERIFIED",
            "citations": [
                {
                    "document_id": "tt-16-2024",
                    "article": "3",
                    "clause": "1",
                    "point": "a",
                }
            ],
        },
    )
    assert result["retrieval_hit_at_k"] is True
    assert result["point_accuracy"] == 1.0


def test_fresh_run_source_suffix_is_not_a_legal_coordinate() -> None:
    runner = load_runner()
    provision_id = "nd-168-2024__dieu-6"
    result = runner.score_case(
        case(provision_id),
        {"status": "VERIFIED", "citations": [{"source_id": "nd-168-2024:0024"}]},
    )
    assert result["retrieval_hit_at_k"] is False
    assert result["citation_validity"] is False


def test_fresh_run_genuine_document_id_mismatch_is_not_a_hit() -> None:
    runner = load_runner()
    result = runner.score_case(
        case("nd-168-2024__dieu-6__khoan-9"),
        {
            "status": "VERIFIED",
            "citations": [
                {
                    "document_id": "nd-165-2024",
                    "document_number": "168/2024/NĐ-CP",
                    "article": "6",
                    "clause": "9",
                }
            ],
        },
    )
    assert result["retrieval_hit_at_k"] is False
    assert result["document_accuracy"] == 0.0
    assert result["clause_accuracy"] == 0.0


def test_aggregate_category_metrics_use_only_category_rows() -> None:
    runner = load_runner()
    rows = [
        {
            "category": "natural_language",
            "retrieval_hit_at_k": True,
            "document_accuracy": True,
            "article_accuracy": None,
            "clause_accuracy": None,
            "point_accuracy": None,
            "citation_validity": True,
            "answer_correctness_manual": None,
            "abstention_accuracy": True,
            "latency_ms": 10,
        },
        {
            "category": "insufficient_evidence",
            "retrieval_hit_at_k": False,
            "document_accuracy": False,
            "article_accuracy": False,
            "clause_accuracy": False,
            "point_accuracy": False,
            "citation_validity": False,
            "answer_correctness_manual": None,
            "abstention_accuracy": False,
            "latency_ms": 20,
        },
    ]

    result = runner.aggregate(rows, {"run_id": "aggregate-proof"})

    assert result["metrics"]["retrieval_hit_at_k"] == 0.5
    assert result["by_category"]["natural_language"]["retrieval_hit_at_k"] == 1.0
    assert result["by_category"]["insufficient_evidence"]["retrieval_hit_at_k"] == 0.0


def test_aggregate_category_metrics_keep_nullable_values_nullable() -> None:
    runner = load_runner()
    rows = [
        {
            "category": "natural_language",
            "retrieval_hit_at_k": None,
            "document_accuracy": None,
            "article_accuracy": None,
            "clause_accuracy": None,
            "point_accuracy": None,
            "citation_validity": None,
            "answer_correctness_manual": None,
            "abstention_accuracy": None,
            "latency_ms": None,
        }
    ]

    result = runner.aggregate(rows, {"run_id": "nullable-proof"})

    category = result["by_category"]["natural_language"]
    assert category["count"] == 1
    assert category["retrieval_hit_at_k"] is None
    assert category["answer_correctness_manual"] is None


def test_load_predictions_unwraps_one_saved_scored_row_and_preserves_metadata(
    tmp_path: Path,
) -> None:
    runner = load_runner()
    path = tmp_path / "predictions.jsonl"
    path.write_text(
        '{"case_id":"c1","prediction":{"status":"OK","citations":[{"document_id":"d1"}]},'
        '"latency_ms":12.5,"error":null}\n',
        encoding="utf-8",
    )
    result = runner.load_predictions(path)["c1"]
    assert result["status"] == "OK"
    assert result["citations"] == [{"document_id": "d1"}]
    assert result["latency_ms"] == 12.5


def test_load_predictions_null_saved_prediction_is_error(tmp_path: Path) -> None:
    runner = load_runner()
    path = tmp_path / "predictions.jsonl"
    path.write_text('{"case_id":"c1","prediction":null,"error":"timeout","latency_ms":3}\n')
    result = runner.load_predictions(path)["c1"]
    assert result["status"] == "ERROR"
    assert result["prediction"] is None
    assert result["error"] == "timeout"
    assert result["latency_ms"] == 3


def test_load_predictions_does_not_recursively_unwrap(tmp_path: Path) -> None:
    runner = load_runner()
    path = tmp_path / "predictions.jsonl"
    path.write_text('{"case_id":"c1","prediction":{"prediction":{"citations":[]}}}\n')
    result = runner.load_predictions(path)["c1"]
    assert result["prediction"] == {"citations": []}
