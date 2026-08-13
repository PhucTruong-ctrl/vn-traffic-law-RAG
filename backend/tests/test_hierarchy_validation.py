"""Unit tests: legal hierarchy validation (VNLRAG-30).

Covers :mod:`app.ingestion.hierarchy_validation`: orphan Point/Clause
detection via the provision_id grammar and hierarchy labels, duplicate
provision_id detection, Vietnamese point-label detection (PRIMARY run
``a→b→c→d→đ→e`` with ``đ)`` valid and distinct from ``d)``, rulespec §4),
gold-tree completeness against the parser-benchmark gold fixtures, and the
empty-corpus contract (all metrics zero, detection rate 0.0).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.ingestion.hierarchy_validation import (
    HierarchyValidationResult,
    validate_against_gold,
    validate_hierarchy,
)
from app.ingestion.metadata_normalizer import canonical_point_label
from app.ingestion.structure_extractor import ExtractedLegalProvision

GOLD_DIR = Path(__file__).parent / "fixtures" / "parser_benchmark" / "gold"

DOC = "nd-168-2024"
DOC_VERSION = "dv-nd-168-2024"

CONTRACT_METRIC_KEYS = frozenset(
    {
        "orphan_point_count",
        "orphan_clause_count",
        "duplicate_count",
        "point_label_detection_rate",
    }
)


def _provision(**overrides: object) -> ExtractedLegalProvision:
    """Build an ExtractedLegalProvision (default: point ``a)``, Điều 5 Khoản 1)."""

    base: dict[str, object] = {
        "provision_id": f"{DOC}__dieu-5__khoan-1__diem-a",
        "document_version_id": DOC_VERSION,
        "chapter": None,
        "section": None,
        "article": "Điều 5",
        "clause": "Khoản 1",
        "point": "Điểm a)",
        "heading": None,
        "source_text": "a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        "retrieval_text": (
            "Khoản 1. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng ... "
            "a) Điều khiển xe lạng lách, đánh võng trên đường bộ"
        ),
        "parent_context": "Khoản 1. Xử phạt người điều khiển xe ô tô ...",
        "page_number": 1,
        "bbox": None,
        "source_element_ids": ["e1"],
        "content_hash": "hash",
        "node_kind": "POINT",
        "point_label": "a)",
    }
    base.update(overrides)
    return ExtractedLegalProvision(**base)


def _clause(**overrides: object) -> ExtractedLegalProvision:
    """Build a CLAUSE-kind provision under Điều 5 Khoản 1."""

    base: dict[str, object] = {
        "provision_id": f"{DOC}__dieu-5__khoan-1",
        "article": "Điều 5",
        "clause": "Khoản 1",
        "point": None,
        "source_text": "1. Phạt tiền từ 800.000 đồng đến 1.000.000 đồng ...",
        "node_kind": "CLAUSE",
        "point_label": None,
    }
    base.update(overrides)
    return _provision(**base)


def _article(**overrides: object) -> ExtractedLegalProvision:
    """Build an ARTICLE-kind provision for Điều 5."""

    base: dict[str, object] = {
        "provision_id": f"{DOC}__dieu-5",
        "article": "Điều 5",
        "clause": None,
        "point": None,
        "source_text": "Điều 5. Xử phạt người điều khiển xe ô tô ...",
        "node_kind": "ARTICLE",
        "point_label": None,
    }
    base.update(overrides)
    return _provision(**base)


def _provision_from_gold(entry: dict) -> ExtractedLegalProvision:
    """Build an extracted provision from a gold-fixture entry (same fields)."""

    kind = (
        "POINT"
        if entry.get("point")
        else "CLAUSE"
        if entry.get("clause")
        else "ARTICLE"
        if entry.get("article")
        else "OTHER"
    )
    return ExtractedLegalProvision(
        provision_id=entry["provision_id"],
        document_version_id=f"gold:{entry['provision_id'].split('__', 1)[0]}",
        chapter=entry.get("chapter"),
        section=entry.get("section"),
        article=entry.get("article"),
        clause=entry.get("clause"),
        point=entry.get("point"),
        heading=entry.get("heading"),
        source_text=entry.get("source_text") or entry["provision_id"],
        retrieval_text=entry.get("source_text") or entry["provision_id"],
        parent_context=None,
        page_number=1,
        bbox=None,
        source_element_ids=["gold"],
        content_hash="gold",
        node_kind=kind,
        point_label=entry.get("point_label"),
        short_point=bool(entry.get("short_point")),
    )


# ────────────────────────────────────────────────────────────────────────────
# Empty input + contract shape
# ────────────────────────────────────────────────────────────────────────────


def test_empty_list_all_metrics_zero() -> None:
    result = validate_hierarchy([])
    assert isinstance(result, HierarchyValidationResult)
    assert result.violations == []
    assert set(result.metrics) == CONTRACT_METRIC_KEYS
    assert result.metrics["orphan_point_count"] == 0
    assert result.metrics["orphan_clause_count"] == 0
    assert result.metrics["duplicate_count"] == 0
    assert result.metrics["point_label_detection_rate"] == 0.0


def test_metrics_keys_exactly_per_contract() -> None:
    result = validate_hierarchy([_article(), _clause()])
    assert set(result.metrics) == CONTRACT_METRIC_KEYS


# ────────────────────────────────────────────────────────────────────────────
# Orphan detection
# ────────────────────────────────────────────────────────────────────────────


def test_orphan_point_detected() -> None:
    clause = _clause()
    orphan = _provision(
        provision_id=f"{DOC}__dieu-9__khoan-2__diem-a",
        article="Điều 9",
        clause="Khoản 2",
        point="Điểm a)",
        point_label="a)",
    )
    result = validate_hierarchy([_article(), clause, orphan])
    assert [v.type for v in result.violations] == ["orphan_point"]
    assert result.violations[0].provision_id == orphan.provision_id
    assert result.metrics["orphan_point_count"] == 1
    assert result.metrics["orphan_clause_count"] == 0


def test_orphan_point_resolved_by_id_prefix() -> None:
    clause = _clause()
    point = _provision(provision_id=f"{DOC}__dieu-5__khoan-1__diem-a")
    result = validate_hierarchy([_article(), clause, point])
    assert result.violations == []
    assert result.metrics["orphan_point_count"] == 0


def test_orphan_point_resolved_by_labels_when_id_mismatches() -> None:
    """Labels resolve the parent even when the provision_id prefix differs."""

    clause = _clause()
    point = _provision(
        provision_id=f"{DOC}__dieu-5__khoan-9__diem-a",  # id says Khoản 9 …
        article="Điều 5",
        clause="Khoản 1",  # … labels say Khoản 1 → parent found
    )
    result = validate_hierarchy([_article(), clause, point])
    assert result.violations == []
    assert result.metrics["orphan_point_count"] == 0


def test_orphan_point_directly_under_article() -> None:
    """A point without a clause hangs off the ARTICLE (§10 fallback hierarchy)."""

    article = _article(provision_id=f"{DOC}__dieu-1", article="Điều 1")
    point = _provision(
        provision_id=f"{DOC}__dieu-1__diem-a",
        article="Điều 1",
        clause=None,
        point="Điểm a)",
        point_label="a)",
    )
    assert validate_hierarchy([article, point]).violations == []

    orphan = _provision(
        provision_id=f"{DOC}__dieu-2__diem-a",
        article="Điều 2",
        clause=None,
        point="Điểm a)",
        point_label="a)",
    )
    result = validate_hierarchy([article, orphan])
    assert [v.type for v in result.violations] == ["orphan_point"]


def test_orphan_clause_detected() -> None:
    clause = _clause(provision_id=f"{DOC}__dieu-99__khoan-1", article="Điều 99")
    result = validate_hierarchy([clause])
    assert [v.type for v in result.violations] == ["orphan_clause"]
    assert result.violations[0].provision_id == clause.provision_id
    assert result.metrics["orphan_clause_count"] == 1
    assert result.metrics["orphan_point_count"] == 0


def test_orphan_clause_resolved_by_id_or_labels() -> None:
    by_id = validate_hierarchy([_article(), _clause()])
    assert by_id.violations == []

    by_label = validate_hierarchy(
        [
            _article(provision_id=f"{DOC}__dieu-5", article="Điều 5"),
            _clause(provision_id=f"{DOC}__dieu-5__khoan-9"),  # id mismatch → labels
        ]
    )
    assert by_label.violations == []


# ────────────────────────────────────────────────────────────────────────────
# Duplicate detection
# ────────────────────────────────────────────────────────────────────────────


def test_duplicate_provision_detected() -> None:
    clause = _clause()
    point = _provision()
    result = validate_hierarchy([_article(), clause, point, point.model_copy()])
    assert [v.type for v in result.violations] == ["duplicate_provision"]
    assert result.violations[0].provision_id == point.provision_id
    assert "2 times" in result.violations[0].detail
    assert result.metrics["duplicate_count"] == 1


def test_duplicate_detected_across_documents() -> None:
    """provision_id is globally unique — duplicates count regardless of doc."""

    a = _provision()
    b = _provision(document_version_id="dv-other-document")
    # Parents in the second document keep the same hierarchy labels but unique
    # provision_ids, so only the point id stays duplicated across documents.
    b_clause = _clause(
        document_version_id="dv-other-document",
        provision_id=f"{DOC}__dieu-5__khoan-2",
    )
    b_article = _article(
        document_version_id="dv-other-document",
        provision_id=f"{DOC}__dieu-6",
    )
    result = validate_hierarchy([_article(), _clause(), b_article, b_clause, a, b])
    assert [v.type for v in result.violations] == ["duplicate_provision"]
    assert result.metrics["duplicate_count"] == 1


# ────────────────────────────────────────────────────────────────────────────
# Point-label detection (rulespec §4)
# ────────────────────────────────────────────────────────────────────────────


def test_valid_point_run_has_rate_one() -> None:
    """Full PRIMARY run a→b→c→d→đ→e is detected with no violations."""

    article = _article()
    clause = _clause()
    points = [
        _provision(
            provision_id=f"{DOC}__dieu-5__khoan-1__diem-{label}",
            point_label=f"{label})",
        )
        for label in ("a", "b", "c", "d", "đ", "e")
    ]
    result = validate_hierarchy([article, clause, *points])
    assert result.violations == []
    assert result.metrics["point_label_detection_rate"] == 1.0
    assert result.metrics["orphan_point_count"] == 0


def test_dd_label_valid_and_distinct() -> None:
    """đ) is valid and stays distinct from d) (rulespec §4, FR-03)."""

    # Canonical forms are distinct; đ is self-identifying, d resolves at
    # ordinal 4 (PRIMARY rule: d = 4th, đ = 5th letter of the run).
    assert canonical_point_label("đ)") == "đ)"
    assert canonical_point_label("d)", ordinal=4) == "d)"
    assert canonical_point_label("đ)") != canonical_point_label("d)", ordinal=4)

    # Real gold shape (nd dieu-9 khoan-1): run starts at d) then đ) — both
    # valid, and diem-d / diem-đ are two distinct provisions, not duplicates.
    article = _article(provision_id=f"{DOC}__dieu-9", article="Điều 9")
    clause = _clause(provision_id=f"{DOC}__dieu-9__khoan-1", article="Điều 9")
    d_point = _provision(
        provision_id=f"{DOC}__dieu-9__khoan-1__diem-d",
        article="Điều 9",
        clause="Khoản 1",
        point="Điểm d)",
        point_label="d)",
    )
    dd_point = _provision(
        provision_id=f"{DOC}__dieu-9__khoan-1__diem-đ",
        article="Điều 9",
        clause="Khoản 1",
        point="Điểm đ)",
        point_label="đ)",
    )
    result = validate_hierarchy([article, clause, d_point, dd_point])
    assert result.violations == []
    assert result.metrics["point_label_detection_rate"] == 1.0
    assert result.metrics["duplicate_count"] == 0


def test_duplicate_d_resolved_by_ordinal_and_inconsistent_d_flagged() -> None:
    """PRIMARY rule: 1st d in a run → d), 2nd d → đ); a 3rd d is inconsistent."""

    clause = _clause()
    first = _provision(provision_id=f"{DOC}__dieu-5__khoan-1__diem-d", point_label="d)")
    second = _provision(provision_id=f"{DOC}__dieu-5__khoan-1__diem-đ", point_label="d)")
    third = _provision(provision_id=f"{DOC}__dieu-5__khoan-1__diem-e", point_label="d)")
    result = validate_hierarchy([_article(), clause, first, second, third])
    assert [v.type for v in result.violations] == ["invalid_label"]
    assert result.violations[0].provision_id == third.provision_id
    assert result.metrics["point_label_detection_rate"] == pytest.approx(2 / 3)


def test_invalid_point_label_detected() -> None:
    """'x)' is outside the PRIMARY run → invalid_label + counts against rate."""

    clause = _clause()
    valid = _provision()
    invalid = _provision(
        provision_id=f"{DOC}__dieu-5__khoan-1__diem-x",
        point="Điểm x)",
        point_label="x)",
    )
    result = validate_hierarchy([_article(), clause, valid, invalid])
    assert [v.type for v in result.violations] == ["invalid_label"]
    assert result.violations[0].provision_id == invalid.provision_id
    assert result.metrics["point_label_detection_rate"] == pytest.approx(0.5)


def test_missing_point_label_detected() -> None:
    clause = _clause()
    missing = _provision(point_label=None, point=None)
    result = validate_hierarchy([_article(), clause, missing])
    assert [v.type for v in result.violations] == ["invalid_label"]
    assert result.violations[0].provision_id == missing.provision_id
    assert result.metrics["point_label_detection_rate"] == 0.0


def test_glued_and_fullwidth_labels_are_valid() -> None:
    """OCR variants canonicalize (metadata_normalizer): Điểm-prefix, case, full-width."""

    clause = _clause()
    variants = [
        _provision(provision_id=f"{DOC}__dieu-5__khoan-1__diem-a", point_label="Điểm a)"),
        _provision(provision_id=f"{DOC}__dieu-5__khoan-1__diem-b", point_label="b）"),
        _provision(provision_id=f"{DOC}__dieu-5__khoan-1__diem-đ", point_label="Đ)"),
    ]
    result = validate_hierarchy([_article(), clause, *variants])
    assert result.violations == []
    assert result.metrics["point_label_detection_rate"] == 1.0


def test_rate_zero_when_no_point_provisions() -> None:
    result = validate_hierarchy([_article(), _clause()])
    assert result.metrics["point_label_detection_rate"] == 0.0
    assert result.violations == []


# ────────────────────────────────────────────────────────────────────────────
# Gold-tree completeness
# ────────────────────────────────────────────────────────────────────────────

SMALL_GOLD = {
    "document_id": "test-doc",
    "provisions": [
        {
            "provision_id": "test-doc__dieu-1",
            "article": "Điều 1",
            "clause": None,
            "point": None,
            "retained": True,
        },
        {
            "provision_id": "test-doc__dieu-1__khoan-1",
            "article": "Điều 1",
            "clause": "Khoản 1",
            "point": None,
            "retained": True,
        },
        {
            "provision_id": "test-doc__dieu-1__khoan-1__diem-a",
            "article": "Điều 1",
            "clause": "Khoản 1",
            "point": "Điểm a)",
            "point_label": "a)",
            "retained": True,
        },
    ],
}


def test_gold_completeness_full_match() -> None:
    extracted = [
        _provision(
            provision_id="test-doc__dieu-1",
            article="Điều 1",
            clause=None,
            point=None,
            node_kind="ARTICLE",
            point_label=None,
        ),
        _provision(
            provision_id="test-doc__dieu-1__khoan-1",
            article="Điều 1",
            clause="Khoản 1",
            point=None,
            node_kind="CLAUSE",
            point_label=None,
        ),
        _provision(
            provision_id="test-doc__dieu-1__khoan-1__diem-a",
            article="Điều 1",
            clause="Khoản 1",
            point="Điểm a)",
            point_label="a)",
        ),
    ]
    assert validate_against_gold(extracted, SMALL_GOLD) == {
        "completeness": 1.0,
        "missing": [],
        "mismatched": [],
    }


def test_gold_completeness_missing_and_mismatched() -> None:
    gold = {
        "document_id": "test-doc",
        "provisions": [
            {"provision_id": "test-doc__dieu-1", "article": "Điều 1", "retained": True},
            {"provision_id": "test-doc__dieu-2", "article": "Điều 2", "retained": True},
            {"provision_id": "test-doc__dieu-3", "article": "Điều 3", "retained": True},
            {"provision_id": "test-doc__dieu-4", "article": "Điều 4", "retained": True},
        ],
    }
    extracted = [
        _provision(
            provision_id="test-doc__dieu-1",
            article="Điều 1",
            clause=None,
            point=None,
            node_kind="ARTICLE",
            point_label=None,
        ),
        # dieu-2 is absent from the extraction → missing
        _provision(
            provision_id="test-doc__dieu-3",
            article=None,  # non-tree heading: no hierarchy fields → kind None
            clause=None,
            point=None,
            node_kind="HEADING",
            point_label=None,
        ),
        _provision(
            provision_id="test-doc__dieu-4",
            article="Điều 4",
            clause=None,
            point=None,
            node_kind="ARTICLE",
            point_label=None,
        ),
    ]
    result = validate_against_gold(extracted, gold)
    assert result["missing"] == ["test-doc__dieu-2"]
    assert result["mismatched"] == ["test-doc__dieu-3"]
    assert result["completeness"] == pytest.approx(0.5)


def test_gold_completeness_ignores_unretained_entries() -> None:
    gold = {
        "document_id": "test-doc",
        "provisions": [
            {"provision_id": "test-doc__dieu-1", "article": "Điều 1", "retained": True},
            {"provision_id": "test-doc__dieu-2", "article": "Điều 2", "retained": False},
        ],
    }
    extracted = [
        _provision(
            provision_id="test-doc__dieu-1",
            article="Điều 1",
            clause=None,
            point=None,
            node_kind="ARTICLE",
            point_label=None,
        )
    ]
    assert validate_against_gold(extracted, gold) == {
        "completeness": 1.0,
        "missing": [],
        "mismatched": [],
    }


def test_gold_completeness_empty_gold_vacuous() -> None:
    assert validate_against_gold([], {"provisions": []}) == {
        "completeness": 1.0,
        "missing": [],
        "mismatched": [],
    }


def test_gold_completeness_real_fixture_files() -> None:
    """Runs against the actual parser-benchmark gold files (gold vs itself).

    The gold fixtures are deliberately partial trees — parent CLAUSE/ARTICLE
    entries are omitted when only the point/clause is retained — so orphan
    counts are not asserted here; completeness, labels and uniqueness are.
    """

    gold_files = sorted(GOLD_DIR.glob("*-gold.json"))
    assert gold_files, "gold fixture directory is empty"
    for gold_path in gold_files:
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        provisions = [_provision_from_gold(entry) for entry in gold["provisions"]]
        comparison = validate_against_gold(provisions, gold)
        assert comparison == {
            "completeness": 1.0,
            "missing": [],
            "mismatched": [],
        }, gold_path.name
        result = validate_hierarchy(provisions)
        assert set(result.metrics) == CONTRACT_METRIC_KEYS, gold_path.name
        assert result.metrics["duplicate_count"] == 0, gold_path.name
        assert result.metrics["point_label_detection_rate"] == 1.0, gold_path.name
