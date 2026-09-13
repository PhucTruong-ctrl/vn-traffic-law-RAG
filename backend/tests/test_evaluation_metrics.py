from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.evaluation.metrics import aggregate_metrics, normalize_coordinate, score_case
from app.evaluation.schemas import CitationPrediction, Coordinate, ExpectedCase, Prediction


def coordinate(document: str = "luat-x", **levels: str) -> Coordinate:
    return Coordinate(document=document, **levels)


def prediction(
    case_id: str, *, retrieved=(), citations=(), abstained=False, latency=10.0, manual=None
) -> Prediction:
    return Prediction(
        case_id=case_id,
        retrieved_coordinates=list(retrieved),
        citations=list(citations),
        abstained=abstained,
        latency_ms=latency,
        manual_answer_correctness=manual,
    )


def test_hit_at_k_requires_full_expected_coordinate_match() -> None:
    expected = coordinate(article="12", clause="2", point="a")
    case = ExpectedCase(
        case_id="c1", category="exact_reference", query="q", expected_coordinates=[expected]
    )

    assert (
        score_case(
            case, prediction("c1", retrieved=[coordinate(article="12", clause="2", point="a")])
        ).retrieval_hit_at_k
        is True
    )
    assert (
        score_case(
            case, prediction("c1", retrieved=[coordinate(article="12", clause="2")])
        ).retrieval_hit_at_k
        is False
    )


def test_hierarchical_accuracy_uses_level_specific_denominators() -> None:
    case = ExpectedCase(
        case_id="c1",
        category="cross_reference",
        query="q",
        expected_coordinates=[
            coordinate(article="1"),
            coordinate(article="2", clause="3", point="b"),
        ],
    )
    result = score_case(
        case,
        prediction("c1", retrieved=[coordinate(article="1"), coordinate(article="2", clause="3")]),
    )

    assert result.document_accuracy == 1.0
    assert result.article_accuracy == 1.0
    assert result.clause_accuracy == 1.0
    assert result.point_accuracy == 0.0


def test_citation_validity_is_nullable_for_no_citations_and_false_for_invalid() -> None:
    case = ExpectedCase(
        case_id="c1", category="natural_language", query="q", expected_coordinates=[coordinate()]
    )
    assert (
        score_case(
            case,
            prediction("c1"),
        ).citation_validity
        is None
    )
    invalid = CitationPrediction(coordinate=coordinate(), valid=False)
    assert score_case(case, prediction("c1", citations=[invalid])).citation_validity is False
    assert (
        score_case(
            case, prediction("c1", citations=[CitationPrediction(coordinate=coordinate())])
        ).citation_validity
        is True
    )


def test_abstention_accuracy_follows_expected_abstention() -> None:
    case = ExpectedCase(
        case_id="c1", category="insufficient_evidence", query="q", abstention_expected=True
    )
    assert score_case(case, prediction("c1", abstained=True)).abstention_accuracy is True
    assert score_case(case, prediction("c1", abstained=False)).abstention_accuracy is False


def test_manual_correctness_remains_explicit_nullable_value() -> None:
    case = ExpectedCase(
        case_id="c1", category="penalty", query="q", expected_coordinates=[coordinate()]
    )
    assert score_case(case, prediction("c1", manual=None)).answer_correctness_manual is None
    assert score_case(case, prediction("c1", manual=True)).answer_correctness_manual is True
    assert score_case(case, prediction("c1", manual=False)).answer_correctness_manual is False


def test_latency_summary_uses_interpolated_percentiles() -> None:
    cases = [ExpectedCase(case_id=f"c{i}", category="follow_up", query="q") for i in range(4)]
    predictions = [
        prediction(f"c{i}", latency=latency) for i, latency in enumerate([10, 20, 30, 40])
    ]
    summary = aggregate_metrics(cases, predictions)

    assert summary.latency.count == 4
    assert summary.latency.mean_ms == 25.0
    assert summary.latency.p50_ms == 25.0
    assert summary.latency.p95_ms == pytest.approx(38.5)


def test_coordinate_normalization_is_case_and_whitespace_insensitive() -> None:
    assert normalize_coordinate({"document": "  Luat-X ", "article": " 12 ", "clause": "A  B"}) == (
        "luat-x",
        "12",
        "a b",
        None,
    )


def test_schema_rejects_malformed_extras() -> None:
    with pytest.raises(ValidationError):
        Prediction(case_id="c1", latency_ms=1, unexpected=True)
    with pytest.raises(ValidationError):
        Coordinate(document="x", unexpected="value")


def test_thesis_dataset_shape_normalizes_to_runner_contract() -> None:
    import importlib.util
    import json
    from pathlib import Path

    path = Path(__file__).parents[1] / "scripts" / "run_thesis_evaluation.py"
    spec = importlib.util.spec_from_file_location("thesis_runner", path)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)

    dataset = Path(__file__).parents[2] / "data/evaluation/thesis-gold-40.json"
    raw = json.loads(dataset.read_text(encoding="utf-8"))
    cases = runner.load_dataset(dataset)
    assert len(cases) == 40
    assert cases[0]["question"] == raw["cases"][0]["query"]
    assert cases[0]["expected"]["provision_ids"] == raw["cases"][0]["expected_provision_ids"]


def load_thesis_runner():
    """Import runner functions without executing its CLI entry point."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).parents[1] / "scripts" / "run_thesis_evaluation.py"
    spec = importlib.util.spec_from_file_location("thesis_runner_metrics", path)
    assert spec and spec.loader
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    return runner


def runner_case(provision_id: str, category: str = "exact_reference") -> dict:
    return {
        "id": "runner-case",
        "category": category,
        "question": "q",
        "expected": {
            # Gold level arrays intentionally retain the full canonical
            # provision ID; the runner derives each ancestor level from it.
            "provision_ids": [provision_id],
            "document_ids": [provision_id],
            "article_ids": [provision_id],
            "clause_ids": [provision_id] if "__khoan-" in provision_id else [],
            "point_ids": [provision_id] if "__diem-" in provision_id else [],
            "abstain": False,
        },
    }


def test_runner_explicit_canonical_claim_satisfies_exact_retrieval() -> None:
    runner = load_thesis_runner()
    provision_id = "nd-119-2024__dieu-10__khoan-2__diem-a"
    case = runner_case(provision_id)
    result = runner.score_case(
        case,
        {
            "claims": [{"provision_ids": [provision_id]}],
            "status": "VERIFIED",
        },
    )
    assert result["retrieval_hit_at_k"] is True


def test_runner_parses_canonical_article_clause_and_point_ids() -> None:
    runner = load_thesis_runner()
    case = runner_case("nd-119-2024__dieu-10__khoan-2__diem-a")
    assert runner.expected_ids(case) == {"nd-119-2024__dieu-10__khoan-2__diem-a"}


def test_runner_child_citation_satisfies_ancestor_level_not_exact_provision() -> None:
    runner = load_thesis_runner()
    case = runner_case("nd-119-2024__dieu-10__khoan-2")
    child = {
        "document_id": "nd-119-2024",
        "article": "10",
        "clause": "2",
        "point": "a",
        "provision_ids": ["nd-119-2024__dieu-10__khoan-2__diem-a"],
        "source_id": "chunk-123",
    }
    result = runner.score_case(case, {"citations": [child], "status": "VERIFIED"})
    assert result["retrieval_hit_at_k"] is False
    assert result["document_accuracy"] == 1.0
    assert result["article_accuracy"] == 1.0
    assert result["clause_accuracy"] == 1.0


def test_runner_chunk_source_id_alone_cannot_create_provision_hit() -> None:
    runner = load_thesis_runner()
    case = runner_case("nd-119-2024__dieu-10")
    result = runner.score_case(
        case,
        {"citations": [{"source_id": "nd-119-2024__dieu-10"}], "status": "VERIFIED"},
    )
    assert result["retrieval_hit_at_k"] is False


def test_runner_structured_citation_metadata_produces_level_accuracy() -> None:
    runner = load_thesis_runner()
    case = runner_case("nd-119-2024__dieu-10__khoan-2__diem-a")
    citation = {
        "document_id": "nd-119-2024",
        "article": "10",
        "clause": "2",
        "point": "a",
        "provision_ids": ["nd-119-2024__dieu-10__khoan-2__diem-a"],
        "source_id": "chunk-123",
    }
    result = runner.score_case(case, {"citations": [citation], "status": "VERIFIED"})
    assert result["retrieval_hit_at_k"] is True
    assert result["document_accuracy"] == 1.0
    assert result["article_accuracy"] == 1.0
    assert result["clause_accuracy"] == 1.0
    assert result["point_accuracy"] == 1.0


def test_runner_aggregate_isolates_categories_and_preserves_nulls() -> None:
    runner = load_thesis_runner()
    rows = [
        {
            "case_id": "a",
            "category": "exact_reference",
            "retrieval_hit_at_k": True,
            "document_accuracy": 1.0,
            "article_accuracy": 1.0,
            "clause_accuracy": None,
            "point_accuracy": None,
            "citation_validity": True,
            "answer_correctness_manual": None,
            "abstention_accuracy": True,
            "latency_ms": 10.0,
        },
        {
            "case_id": "b",
            "category": "penalty",
            "retrieval_hit_at_k": False,
            "document_accuracy": 0.0,
            "article_accuracy": 0.0,
            "clause_accuracy": None,
            "point_accuracy": None,
            "citation_validity": False,
            "answer_correctness_manual": None,
            "abstention_accuracy": False,
            "latency_ms": None,
        },
    ]
    aggregate = runner.aggregate(rows, {"source": "test"})
    assert aggregate["count"] == 2
    assert aggregate["metrics"]["retrieval_hit_at_k"] == 0.5
    assert aggregate["by_category"]["exact_reference"]["retrieval_hit_at_k"] == 1.0
    assert aggregate["by_category"]["penalty"]["retrieval_hit_at_k"] == 0.0
    assert aggregate["by_category"]["natural_language"]["count"] == 0
    assert aggregate["by_category"]["natural_language"]["retrieval_hit_at_k"] is None
    assert aggregate["latency_ms"] == {"mean": 10.0, "p50": 10.0, "p95": 10.0}


def test_runner_timeout_row_keeps_nullable_metrics() -> None:
    runner = load_thesis_runner()
    case = runner_case("nd-119-2024__dieu-10")
    result = runner.score_case(case, {"status": "TIMEOUT"}, latency_ms=None)
    assert result["retrieval_hit_at_k"] is None
    assert result["document_accuracy"] is None
    assert result["citation_validity"] is None
    assert result["latency_ms"] is None
