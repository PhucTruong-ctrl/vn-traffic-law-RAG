"""Unit tests: Corpus QA — the 16 FR-10 metrics (VNLRAG-127).

Covers each metric on small synthetic provision lists: empty corpus → all
zeros; temporal conflict (``effective_to < effective_from``); unresolved vs
resolvable REFERS_TO cross-references (rulespec §7); đ) present vs absent
(rulespec §4); short-Point retention (rulespec §5 — no token-length
threshold); parent-context coverage; manifest-driven expected Point/Table
counts; unknown effective dates; the report shape matching the
``CorpusQaReport`` persistence fields; and corpus-QA repository
serialization without PostgreSQL.

The cross-module contracts (VNLRAG-29 ``provenance_coverage``, VNLRAG-30
``validate_hierarchy``) are developed in parallel worktrees and may not exist
yet, so every test monkeypatches them with contract-matching fakes; the
orchestrator verifies the real integration after merge.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

import app.evaluation.corpus_qa as corpus_qa
from app.evaluation.corpus_qa import (
    CORPUS_QA_VERSION,
    CorpusQaReportShape,
    find_cross_references,
    resolve_cross_reference,
    run_corpus_qa,
    run_corpus_qa_from_manifests,
    structural_qa_report,
    vietnamese_d_detection_rate,
)
from app.ingestion.structure_extractor import ExtractedLegalProvision
from app.persistence.models import CorpusQaReport
from app.persistence.repositories.corpus_qa import CorpusQaReportRepository, report_row_kwargs

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS_DIR = REPO_ROOT / "data" / "manifests"

#: The EXACT 16 FR-10 metrics (doc 00 §10.3, doc 03 §3.10.5).
EXPECTED_METRIC_KEYS = {
    "document_count",
    "article_count",
    "clause_count",
    "point_count",
    "point_coverage",
    "short_point_retention",
    "d_point_detection_rate",
    "orphan_point_count",
    "orphan_clause_count",
    "duplicate_provision_count",
    "parent_context_coverage",
    "provenance_coverage",
    "table_coverage",
    "unresolved_cross_reference_count",
    "unknown_effective_date_count",
    "temporal_conflict_count",
}

#: Contract-matching fake hierarchy metrics (VNLRAG-30 key contract).
HIERARCHY_METRICS = {
    "orphan_point_count": 2,
    "orphan_clause_count": 1,
    "duplicate_count": 3,
    "point_label_detection_rate": 0.75,
}

ZERO_HIERARCHY_METRICS = {
    "orphan_point_count": 0,
    "orphan_clause_count": 0,
    "duplicate_count": 0,
    "point_label_detection_rate": 0.0,
}


def _fake_validate_hierarchy(provisions: list[ExtractedLegalProvision]) -> SimpleNamespace:
    """Contract fake: empty corpus → zero metrics, non-empty → HIERARCHY_METRICS."""
    return SimpleNamespace(
        violations=[],
        metrics=dict(ZERO_HIERARCHY_METRICS if not provisions else HIERARCHY_METRICS),
    )


def _fake_provenance_coverage(provisions: list[ExtractedLegalProvision]) -> float:
    """Contract fake: 0.0 for an empty corpus, otherwise a fixed share."""
    return 0.0 if not provisions else 0.5


def _patch_contracts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire the cross-module fakes onto the corpus_qa module-level names."""
    monkeypatch.setattr(corpus_qa, "validate_hierarchy", _fake_validate_hierarchy)
    monkeypatch.setattr(corpus_qa, "provenance_coverage", _fake_provenance_coverage)


def _provision(
    provision_id: str = "nd-168-2024__dieu-5__khoan-1__diem-a",
    **overrides: object,
) -> ExtractedLegalProvision:
    """A minimal valid ``ExtractedLegalProvision`` with sensible defaults."""

    source_text = str(overrides.get("source_text", "a) Điều khiển xe lạng lách"))
    values: dict[str, object] = {
        "provision_id": provision_id,
        "document_version_id": "nd-168-2024",
        "chapter": None,
        "section": None,
        "article": "Điều 5",
        "clause": "Khoản 1",
        "point": "Điểm a)",
        "heading": None,
        "source_text": source_text,
        "retrieval_text": source_text,
        "parent_context": "Khoản 1. Phạt tiền từ 4.000.000 đồng đến 6.000.000 đồng",
        "effective_from": None,
        "effective_to": None,
        "status": "UNKNOWN",
        "page_number": 1,
        "bbox": None,
        "source_element_ids": ["e1"],
        "content_hash": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
        "version": 1,
        "review_status": "PENDING",
        "node_kind": "POINT",
        "point_label": None,
        "short_point": False,
        "needs_review": False,
        "ambiguity": None,
    }
    values.update(overrides)
    if "content_hash" not in overrides:
        values["content_hash"] = hashlib.sha256(
            str(values["source_text"]).encode("utf-8")
        ).hexdigest()
    return ExtractedLegalProvision(**values)


# ────────────────────────────────────────────────────────────────────────────
# Empty corpus → all zeros + report shape
# ────────────────────────────────────────────────────────────────────────────


def test_empty_corpus_all_metrics_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    report = run_corpus_qa([], corpus_version="v1", corpus_hash="sha256:empty")

    metrics = report.metrics
    for name in EXPECTED_METRIC_KEYS:
        assert getattr(metrics, name) == 0 or getattr(metrics, name) == 0.0, name
    assert metrics.model_dump() == {
        "document_count": 0,
        "article_count": 0,
        "clause_count": 0,
        "point_count": 0,
        "point_coverage": 0.0,
        "short_point_retention": 0.0,
        "d_point_detection_rate": 0.0,
        "orphan_point_count": 0,
        "orphan_clause_count": 0,
        "duplicate_provision_count": 0,
        "parent_context_coverage": 0.0,
        "provenance_coverage": 0.0,
        "table_coverage": 0.0,
        "unresolved_cross_reference_count": 0,
        "unknown_effective_date_count": 0,
        "temporal_conflict_count": 0,
    }
    assert report.documents_analyzed == []
    assert report.notes and CORPUS_QA_VERSION in report.notes


def test_report_shape_matches_corpus_qa_report_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    report = run_corpus_qa(
        [_provision()], corpus_version="v1", corpus_hash="sha256:corpus"
    )

    # CorpusQaReport fields minus the DB-generated id.
    expected_fields = set(CorpusQaReport.__table__.columns.keys()) - {"id"}
    assert set(CorpusQaReportShape.model_fields) == expected_fields
    assert report.report_id.startswith("corpus-qa-")
    assert report.corpus_version == "v1"
    assert report.corpus_hash == "sha256:corpus"
    assert report.generated_at.tzinfo is not None
    # Exactly the 16 documented metric keys serialize to the JSONB payload.
    serialized = report.metrics.model_dump()
    assert set(serialized) == EXPECTED_METRIC_KEYS
    assert len(serialized) == 16


# ────────────────────────────────────────────────────────────────────────────
# Counts and coverage metrics
# ────────────────────────────────────────────────────────────────────────────


def test_document_article_clause_point_counts(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    provisions = [
        _provision(
            "nd-168-2024__dieu-5", node_kind="ARTICLE", article="Điều 5", clause=None, point=None
        ),
        _provision(
            "nd-168-2024__dieu-6", node_kind="ARTICLE", article="Điều 6", clause=None, point=None
        ),
        _provision(
            "nd-168-2024__dieu-5__khoan-1", node_kind="CLAUSE", clause="Khoản 1", point=None
        ),
        _provision(
            "nd-168-2024__dieu-5__khoan-2", node_kind="CLAUSE", clause="Khoản 2", point=None
        ),
        _provision(
            "nd-168-2024__dieu-5__khoan-3", node_kind="CLAUSE", clause="Khoản 3", point=None
        ),
        _provision("nd-168-2024__dieu-5__khoan-1__diem-a"),
        _provision("nd-168-2024__dieu-5__khoan-1__diem-b"),
        _provision("nd-168-2024__dieu-5__khoan-1__diem-c"),
        _provision("nd-168-2024__dieu-5__khoan-1__diem-d"),
        _provision(
            "luat-36-2024-qh15__dieu-8__khoan-1__diem-a",
            article="Điều 8",
            clause="Khoản 1",
        ),
    ]
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")

    assert report.metrics.document_count == 2
    assert report.metrics.article_count == 2
    assert report.metrics.clause_count == 3
    assert report.metrics.point_count == 5
    assert len(report.documents_analyzed or []) == 2
    per_document = {entry["document_id"]: entry for entry in report.documents_analyzed or []}
    assert per_document["nd-168-2024"]["provision_count"] == 9
    assert per_document["luat-36-2024-qh15"]["provision_count"] == 1
    assert per_document["nd-168-2024"]["structural_qa"]["provision_count"] == 9


def test_point_coverage_expected_from_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    provisions = [
        _provision("nd-168-2024__dieu-5__khoan-1__diem-a"),
        _provision("nd-168-2024__dieu-5__khoan-1__diem-b"),
        _provision("nd-168-2024__dieu-5__khoan-1__diem-c"),
    ]
    manifests = {"nd-168-2024": {"status": "EFFECTIVE", "expected_points": 6}}
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h", manifests=manifests)

    assert report.metrics.point_count == 3
    assert report.metrics.point_coverage == pytest.approx(0.5)
    # Manifest declaration wins over the gold fallback.
    gold_only = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")
    assert gold_only.metrics.point_coverage == pytest.approx(3 / 19)  # nd-gold: 19 points
    assert "gold fixtures" in (gold_only.notes or "")
    # No expectation declared for a non-gold document → 0 baseline (noted).
    synthetic = [_provision("test-doc-1__dieu-1__khoan-1__diem-a")]
    no_expectation = run_corpus_qa(synthetic, corpus_version="v1", corpus_hash="h")
    assert no_expectation.metrics.point_coverage == 0.0
    assert "baseline" in (no_expectation.notes or "")


def test_table_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    table = _provision(
        "nd-168-2024__bảng-1",
        node_kind="TABLE",
        article=None,
        clause=None,
        point=None,
        heading=None,
        source_text="Bảng 1. Mức phạt tiền",
    )
    provisions = [table, _provision("nd-168-2024__dieu-5__khoan-1__diem-a")]
    manifests = {"nd-168-2024": {"status": "EFFECTIVE", "expected_tables": 2}}
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h", manifests=manifests)

    assert report.metrics.table_coverage == pytest.approx(0.5)
    # No expected_tables declared → 0 baseline with a note.
    baseline = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")
    assert baseline.metrics.table_coverage == 0.0
    assert "expected_tables" in (baseline.notes or "")


def test_short_point_retention(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    # 3 short points flagged; one was dropped by review → not retained.
    provisions = [
        _provision(
            "luat-36-2024-qh15__dieu-8__khoan-1__diem-a",
            source_text="a) Đường cao tốc",
            short_point=True,
        ),
        _provision(
            "luat-36-2024-qh15__dieu-8__khoan-1__diem-d",
            source_text="d) Đường huyện",
            short_point=True,
        ),
        _provision(
            "luat-36-2024-qh15__dieu-8__khoan-1__diem-đ",
            source_text="đ) Đường xã",
            short_point=True,
            review_status="DROPPED",
        ),
    ]
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")
    assert report.metrics.short_point_retention == pytest.approx(2 / 3)

    all_retained = run_corpus_qa(
        [_provision(short_point=True)], corpus_version="v1", corpus_hash="h"
    )
    assert all_retained.metrics.short_point_retention == 1.0


def test_parent_context_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    provisions = [
        _provision(parent_context="Khoản 1. Phạt tiền"),
        _provision(parent_context="  "),
        _provision(parent_context=None),
    ]
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")
    assert report.metrics.parent_context_coverage == pytest.approx(1 / 3)


# ────────────────────────────────────────────────────────────────────────────
# đ) detection
# ────────────────────────────────────────────────────────────────────────────


def test_vietnamese_d_detection_present_vs_absent() -> None:
    with_d_da = [
        _provision(point_label="a)"),
        _provision(point_label="d)"),
        _provision(point_label="đ)"),
        _provision(point_label="e)"),
    ]
    assert vietnamese_d_detection_rate(with_d_da) == pytest.approx(0.25)

    without_d_da = [
        _provision(point_label="a)"),
        _provision(point_label="b)"),
        _provision(point_label="c)"),
    ]
    assert vietnamese_d_detection_rate(without_d_da) == 0.0
    assert vietnamese_d_detection_rate([]) == 0.0


def test_d_point_detection_rate_comes_from_hierarchy(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    report = run_corpus_qa(
        [_provision(point_label="đ)"), _provision(point_label="d)")],
        corpus_version="v1",
        corpus_hash="h",
    )
    assert report.metrics.d_point_detection_rate == 0.75  # fake hierarchy value


def test_d_point_detection_falls_back_to_local_computation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        corpus_qa,
        "validate_hierarchy",
        lambda provisions: SimpleNamespace(
            violations=[],
            metrics={"orphan_point_count": 0, "orphan_clause_count": 0, "duplicate_count": 0},
        ),
    )
    monkeypatch.setattr(corpus_qa, "provenance_coverage", _fake_provenance_coverage)

    provisions = [_provision(point_label="a)"), _provision(point_label="đ)")]
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")
    assert report.metrics.d_point_detection_rate == pytest.approx(0.5)


# ────────────────────────────────────────────────────────────────────────────
# Cross-module feed-through (VNLRAG-29/30 contracts)
# ────────────────────────────────────────────────────────────────────────────


def test_hierarchy_and_provenance_feed_through_to_metrics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_contracts(monkeypatch)

    provisions = [_provision(), _provision("nd-168-2024__dieu-5__khoan-1__diem-b")]
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")

    assert report.metrics.orphan_point_count == 2
    assert report.metrics.orphan_clause_count == 1
    assert report.metrics.duplicate_provision_count == 3
    assert report.metrics.d_point_detection_rate == 0.75
    assert report.metrics.provenance_coverage == 0.5
    # Every analyzed document carries the hierarchy reuse.
    entry = (report.documents_analyzed or [])[0]
    assert entry["structural_qa"]["hierarchy_metrics"]["duplicate_count"] == 3


def test_structural_qa_report_reuses_validate_hierarchy(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Violation(BaseModel):
        provision_id: str
        kind: str

    def fake(provisions: list[ExtractedLegalProvision]) -> SimpleNamespace:
        return SimpleNamespace(
            violations=[_Violation(provision_id="p-1", kind="orphan_point")],
            metrics=dict(HIERARCHY_METRICS),
        )

    monkeypatch.setattr(corpus_qa, "validate_hierarchy", fake)
    monkeypatch.setattr(corpus_qa, "provenance_coverage", _fake_provenance_coverage)

    result = structural_qa_report([_provision()], document_id="nd-168-2024")
    assert result["document_id"] == "nd-168-2024"
    assert result["provision_count"] == 1
    assert result["hierarchy_violations"] == [
        {"provision_id": "p-1", "kind": "orphan_point"}
    ]
    assert result["hierarchy_metrics"] == HIERARCHY_METRICS


# ────────────────────────────────────────────────────────────────────────────
# Cross-references (rulespec §7)
# ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Hành vi quy định tại Điều 7", ["quy định tại Điều 7"]),
        ("theo quy định tại Khoản 4 Điều 6", ["theo quy định tại Khoản 4 Điều 6"]),
        (
            "hành vi quy định tại Điểm a Khoản 4 Điều 7",
            ["quy định tại Điểm a Khoản 4 Điều 7"],
        ),
        ("theo Khoản 13", ["theo Khoản 13"]),
        ("theo Điều 52", ["theo Điều 52"]),
        (
            "quy định tại Điều 7 Nghị định 168/2024/NĐ-CP",
            ["quy định tại Điều 7 Nghị định 168/2024/NĐ-CP"],
        ),
        # Article headings are NOT citations.
        ("Điều 5. Xử phạt người điều khiển xe ô tô vi phạm quy tắc giao thông", []),
        # rulespec §7 false-positive guards.
        ("khoảng cách an toàn", []),
        ("số điểm của giấy phép", []),
    ],
)
def test_find_cross_references(text: str, expected: list[str]) -> None:
    assert find_cross_references(text) == expected


def test_find_cross_references_multiple_and_no_duplicate_spans() -> None:
    text = "Hành vi quy định tại Khoản 4 Điều 6 bị xử phạt theo quy định tại Điều 7."
    assert find_cross_references(text) == [
        "quy định tại Khoản 4 Điều 6",
        "theo quy định tại Điều 7",
    ]


def test_resolve_cross_reference() -> None:
    known = [
        "nd-168-2024__dieu-6__khoan-4",
        "nd-168-2024__dieu-7",
        "nd-168-2024__dieu-7__khoan-4__diem-a",
        "nd-168-2024__dieu-5__khoan-13",
    ]
    assert (
        resolve_cross_reference(
            "quy định tại Khoản 4 Điều 6",
            citing_provision_id="nd-168-2024__dieu-7__khoan-2",
            known_provision_ids=known,
        )
        == "nd-168-2024__dieu-6__khoan-4"
    )
    assert (
        resolve_cross_reference(
            "quy định tại Điểm a Khoản 4 Điều 7",
            citing_provision_id="nd-168-2024__dieu-7__khoan-2",
            known_provision_ids=known,
        )
        == "nd-168-2024__dieu-7__khoan-4__diem-a"
    )
    # PENALTY_COMPANION: "Khoản 13" resolves against the citing Điều.
    assert (
        resolve_cross_reference(
            "quy định tại Khoản 13",
            citing_provision_id="nd-168-2024__dieu-5__khoan-1",
            known_provision_ids=known,
        )
        == "nd-168-2024__dieu-5__khoan-13"
    )
    # Out-of-corpus target → unresolved.
    assert (
        resolve_cross_reference(
            "quy định tại Khoản 9 Điều 12",
            citing_provision_id="nd-168-2024__dieu-7__khoan-2",
            known_provision_ids=known,
        )
        is None
    )
    # Cross-document citation resolves via the document mention.
    assert (
        resolve_cross_reference(
            "quy định tại Điều 7 Nghị định 168/2024/NĐ-CP",
            citing_provision_id="luat-36-2024-qh15__dieu-8__khoan-1",
            known_provision_ids=known + ["luat-36-2024-qh15__dieu-8"],
        )
        == "nd-168-2024__dieu-7"
    )
    # Cited document not in the corpus → unresolved.
    assert (
        resolve_cross_reference(
            "quy định tại Điều 5 Nghị định 100/2019/NĐ-CP",
            citing_provision_id="nd-168-2024__dieu-7__khoan-2",
            known_provision_ids=known,
        )
        is None
    )


def test_unresolved_cross_references_counted_only_when_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_contracts(monkeypatch)

    provisions = [
        _provision(
            "nd-168-2024__dieu-7__khoan-2",
            node_kind="CLAUSE",
            clause="Khoản 2",
            point=None,
            source_text="Hành vi quy định tại Khoản 4 Điều 6 bị xử phạt.",
        ),
        _provision(
            "nd-168-2024__dieu-6__khoan-4",
            node_kind="CLAUSE",
            article="Điều 6",
            clause="Khoản 4",
            point=None,
            source_text="Hành vi bị xử phạt theo quy định tại Điều 52.",
        ),
    ]
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")
    # "Khoản 4 Điều 6" resolves (clause exists); "Điều 52" does not.
    assert report.metrics.unresolved_cross_reference_count == 1


def test_cross_reference_patterns_can_be_overridden(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    provisions = [
        _provision(
            "nd-168-2024__dieu-7__khoan-2",
            node_kind="CLAUSE",
            clause="Khoản 2",
            point=None,
            source_text="Hành vi quy định tại Khoản 4 Điều 6.",
        )
    ]
    default = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")
    assert default.metrics.unresolved_cross_reference_count == 1

    custom = run_corpus_qa(
        provisions,
        corpus_version="v1",
        corpus_hash="h",
        cross_reference_patterns=(re.compile(r"xyzzy"),),
    )
    assert custom.metrics.unresolved_cross_reference_count == 0


# ────────────────────────────────────────────────────────────────────────────
# Temporal metrics (rulespec §8)
# ────────────────────────────────────────────────────────────────────────────


def test_temporal_conflict_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    provisions = [
        # effective_to < effective_from → conflict (half-open [from, to)).
        _provision(
            "nd-168-2024__dieu-5__khoan-1",
            node_kind="CLAUSE",
            clause="Khoản 1",
            point=None,
            effective_from="2025-01-01",
            effective_to="2024-12-31",
        ),
        # Zero-length interval is NOT a conflict under the strict < rule.
        _provision(
            "nd-168-2024__dieu-5__khoan-2",
            node_kind="CLAUSE",
            clause="Khoản 2",
            point=None,
            effective_from="2025-01-01",
            effective_to="2025-01-01",
        ),
        # Valid half-open interval.
        _provision(
            "nd-168-2024__dieu-5__khoan-3",
            node_kind="CLAUSE",
            clause="Khoản 3",
            point=None,
            effective_from="2025-01-01",
            effective_to="2026-01-01",
        ),
        # Unknown interval → not a conflict.
        _provision(
            "nd-168-2024__dieu-5__khoan-4",
            node_kind="CLAUSE",
            clause="Khoản 4",
            point=None,
            effective_from=None,
            effective_to=None,
        ),
    ]
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h")
    assert report.metrics.temporal_conflict_count == 1


def test_unknown_effective_date_count(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    provisions = [
        # ACCEPTED but no effective_from → unknown effective date.
        _provision(
            "nd-168-2024__dieu-5__khoan-1",
            node_kind="CLAUSE",
            clause="Khoản 1",
            point=None,
            review_status="ACCEPTED",
            effective_from=None,
        ),
        # ACCEPTED with an effective_from → fine.
        _provision(
            "nd-168-2024__dieu-5__khoan-2",
            node_kind="CLAUSE",
            clause="Khoản 2",
            point=None,
            review_status="ACCEPTED",
            effective_from="2025-01-01",
        ),
        # PENDING without effective_from → not counted (not accepted).
        _provision(
            "nd-168-2024__dieu-5__khoan-3",
            node_kind="CLAUSE",
            clause="Khoản 3",
            point=None,
            review_status="PENDING",
            effective_from=None,
        ),
        # Document with manifest status UNKNOWN → all its provisions count.
        _provision(
            "vbhn-49-2026-vpqh__dieu-1__khoan-1",
            document_version_id="vbhn-49-2026-vpqh",
            node_kind="CLAUSE",
            article="Điều 1",
            clause="Khoản 1",
            point=None,
            review_status="ACCEPTED",
            effective_from="2026-01-01",
        ),
    ]
    manifests = {"vbhn-49-2026-vpqh": {"status": "UNKNOWN"}}
    report = run_corpus_qa(provisions, corpus_version="v1", corpus_hash="h", manifests=manifests)
    # 1 (accepted without from) + 1 (UNKNOWN-status document) — no double count.
    assert report.metrics.unknown_effective_date_count == 2


# ────────────────────────────────────────────────────────────────────────────
# Manifest-driven run
# ────────────────────────────────────────────────────────────────────────────


def test_run_corpus_qa_from_manifests(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    expected_manifests = len(list(MANIFESTS_DIR.rglob("*.manifest.json")))
    assert expected_manifests > 0

    report = run_corpus_qa_from_manifests(
        str(MANIFESTS_DIR), corpus_version="corpus-v1", corpus_hash="sha256:corpus"
    )

    assert report.corpus_version == "corpus-v1"
    assert report.corpus_hash == "sha256:corpus"
    assert f"manifests loaded: {expected_manifests} documents" in (report.notes or "")
    # No extraction output exists under data/ yet → computed over 0 provisions.
    for name in EXPECTED_METRIC_KEYS:
        value = getattr(report.metrics, name)
        assert value == 0 or value == 0.0, name


def test_run_corpus_qa_from_manifests_with_extraction_output(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _patch_contracts(monkeypatch)

    manifests_dir = tmp_path / "manifests"
    (manifests_dir / "batch-01").mkdir(parents=True)
    manifest = {
        "document_id": "nd-168-2024",
        "status": "EFFECTIVE",
        "expected_points": 2,
    }
    (manifests_dir / "batch-01" / "nd-168-2024.manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    extraction = tmp_path / "nd-168-2024" / "provisions.json"
    extraction.parent.mkdir(parents=True)
    extraction.write_text(
        json.dumps(
            [
                _provision("nd-168-2024__dieu-5__khoan-1__diem-a").model_dump(),
                _provision("nd-168-2024__dieu-5__khoan-1__diem-b").model_dump(),
            ]
        ),
        encoding="utf-8",
    )

    report = run_corpus_qa_from_manifests(
        str(manifests_dir), corpus_version="corpus-v1", corpus_hash="sha256:corpus"
    )

    assert "manifests loaded: 1 documents" in (report.notes or "")
    assert "provisions loaded for 1 documents (2 provisions)" in (report.notes or "")
    assert report.metrics.point_count == 2
    assert report.metrics.point_coverage == 1.0


# ────────────────────────────────────────────────────────────────────────────
# Repository serialization (no PostgreSQL needed)
# ────────────────────────────────────────────────────────────────────────────


class _FakeSession:
    """Duck-typed Session capturing add/flush/scalar for unit testing."""

    def __init__(self) -> None:
        self.added: object | None = None
        self.flushed = False
        self.statement: object | None = None
        self.scalar_result: object | None = None

    def add(self, obj: object) -> None:
        self.added = obj

    def flush(self) -> None:
        self.flushed = True

    def scalar(self, statement: object) -> object | None:
        self.statement = statement
        return self.scalar_result


def test_report_row_kwargs_serialization(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    report = run_corpus_qa(
        [_provision()], corpus_version="v1", corpus_hash="sha256:corpus"
    )
    kwargs = report_row_kwargs(report)

    assert set(kwargs) == {
        "report_id",
        "corpus_version",
        "corpus_hash",
        "metrics",
        "documents_analyzed",
        "notes",
        "generated_at",
    }
    assert kwargs["report_id"] == report.report_id
    assert kwargs["metrics"] == report.metrics.model_dump()
    assert set(kwargs["metrics"]) == EXPECTED_METRIC_KEYS
    assert kwargs["generated_at"] == report.generated_at

    # The kwargs construct a real ORM row without touching a database.
    row = CorpusQaReport(**kwargs)
    assert row.report_id == report.report_id
    assert row.metrics["point_count"] == 1


def test_repository_save_and_get_latest(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_contracts(monkeypatch)

    report = run_corpus_qa(
        [_provision()], corpus_version="v1", corpus_hash="sha256:corpus"
    )

    session = _FakeSession()
    repository = CorpusQaReportRepository(session)  # type: ignore[arg-type]
    row = repository.save(report)

    assert isinstance(row, CorpusQaReport)
    assert session.added is row
    assert session.flushed is True
    assert row.report_id == report.report_id
    assert row.corpus_version == "v1"
    assert set(row.metrics) == EXPECTED_METRIC_KEYS

    session.scalar_result = row
    latest = repository.get_latest("v1")
    assert latest is row
    statement_sql = str(session.statement)
    assert "corpus_qa_reports" in statement_sql
    assert "corpus_version" in statement_sql
    assert "ORDER BY" in statement_sql
    assert "LIMIT" in statement_sql
