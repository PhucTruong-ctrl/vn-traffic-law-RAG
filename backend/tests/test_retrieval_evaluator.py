from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from langchain_core.documents import Document

from app.evaluation.metrics import coordinate_accuracy, recall_at_k
from app.evaluation.schemas import Coordinate


def load_eval():
    root = Path(__file__).parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    path = root / "scripts" / "eval.py"
    spec = importlib.util.spec_from_file_location("retrieval_eval", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_recall_uses_stable_coordinates_and_nulls_empty_expected() -> None:
    expected = [Coordinate(document_id="nd-119-2024", article="010")]
    actual = [Coordinate(document_id="nd-119-2024", article="10")]
    assert recall_at_k(expected, actual, 5) == 1.0
    assert recall_at_k([], actual, 5) is None


def test_coordinate_accuracy_has_level_specific_denominators() -> None:
    expected = [
        Coordinate(document_id="nd-119-2024", article="1"),
        Coordinate(document_id="nd-119-2024", article="2", clause="3", point="a"),
    ]
    actual = [Coordinate(document_id="nd-119-2024", article="1")]
    assert coordinate_accuracy(expected, actual, 0) == 1.0
    assert coordinate_accuracy(expected, actual, 1) == 0.5
    assert coordinate_accuracy(expected, actual, 2) == 0.0


def test_record_preserves_metadata_and_expected_null_semantics() -> None:
    evaluator = load_eval()
    case = {
        "id": "c1",
        "category": "out_of_scope",
        "question": "q",
        "expected": {"provision_ids": []},
    }
    document = Document("text", metadata={"document_id": "nd-119-2024", "article": "1"})
    row = evaluator._record(case, [document], 12.345, 10)
    assert row["returned_documents"][0]["document_id"] == "nd-119-2024"
    assert row["recall_at_5"] is None
    assert row["recall_at_10"] is None


def test_error_record_keeps_latency_and_null_metrics() -> None:
    evaluator = load_eval()
    raw_case = {
        "id": "c1",
        "category": "exact_reference",
        "query": "q",
        "expected_status": "answer",
        "expected_abstain": False,
        "expected_document_ids": ["nd-119-2024"],
        "expected_article_ids": ["nd-119-2024__dieu-1"],
        "expected_clause_ids": [],
        "expected_point_ids": [],
        "expected_provision_ids": ["nd-119-2024__dieu-1"],
    }
    row = evaluator._error_record(
        evaluator.normalize_case(raw_case, 0),
        RuntimeError("provider unavailable"),
        4.2,
    )
    assert row["error"] == "RuntimeError: provider unavailable"
    assert row["latency_ms"] == 4.2
    assert row["recall_at_5"] is None
    assert row["document_accuracy"] is None
