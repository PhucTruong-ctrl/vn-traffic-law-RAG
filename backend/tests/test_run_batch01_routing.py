"""Unit tests for the pure helpers of scripts/run_batch01_routing.py (VNLRAG-35).

Covers the script's deterministic building blocks — IR construction from
fixture text, the manifest-interval application policy, the scan-policy Group
A certification view, routing aggregation, per-document quality stats and the
markdown report renderer. No database, no parser backends, no side effects.
"""

from __future__ import annotations

from app.ingestion.document_ir import ParsedDocument
from app.ingestion.quality_gates import GateResult, GroupAResult, GroupBResult
from app.ingestion.review_routing import (
    D_D_AMBIGUITY,
    LOW_OCR_COVERAGE,
    RoutingDecision,
)
from app.ingestion.structure_extractor import ExtractedLegalProvision
from scripts.run_batch01_routing import (
    aggregate_routing,
    apply_manifest_interval,
    build_ir_from_lines,
    certifying_group_a,
    document_level_decision,
    quality_stats_for,
    render_report,
)

_DOC_VERSION = "dv-nd-168-2024"
_SLUG = "nd-168-2024"


def _provision(**overrides: object) -> ExtractedLegalProvision:
    base: dict[str, object] = {
        "provision_id": f"{_SLUG}__dieu-5__khoan-1__diem-a",
        "document_version_id": _DOC_VERSION,
        "chapter": None,
        "section": None,
        "article": "Điều 5",
        "clause": "Khoản 1",
        "point": "Điểm a)",
        "heading": None,
        "source_text": "a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        "retrieval_text": "Khoản 1. ... a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        "parent_context": "Điều 5. Xử phạt người điều khiển xe ô tô ...",
        "page_number": 1,
        "bbox": None,
        "source_element_ids": ["e1"],
        "content_hash": "hash",
        "node_kind": "POINT",
        "point_label": "a)",
        "short_point": False,
        "needs_review": False,
        "ambiguity": None,
        "effective_from": "2025-01-01",
    }
    base.update(overrides)
    return ExtractedLegalProvision(**base)


def _gate(gate: str, value: float | None, threshold: float | None, status: str) -> GateResult:
    return GateResult(gate=gate, value=value, threshold=threshold, status=status)


def _passing_group_a() -> GroupAResult:
    return GroupAResult(
        provenance_coverage=_gate("provenance_coverage", 1.0, 0.9, "passed"),
        text_extraction_rate=_gate("text_extraction_rate", 1.0, 0.8, "passed"),
        table_detection_rate=_gate("table_detection_rate", None, 0.6, "na"),
        layout_coherence=_gate("layout_coherence", None, None, "na"),
        verdict="passed",
    )


def _passing_group_b() -> GroupBResult:
    return GroupBResult(
        passed=True,
        metrics={
            "point_label_detection_rate": 1.0,
            "hierarchy_completeness": 1.0,
            "short_point_retention_rate": 1.0,
            "orphan_point_count": 0,
            "orphan_clause_count": 0,
            "duplicate_count": 0,
        },
        failed_checks=[],
    )


_MANIFEST_EFFECTIVE = {
    "document_id": _SLUG,
    "document_type": "DECREE",
    "status": "EFFECTIVE",
    "effective_from": "2025-01-01",
    "effective_to": None,
}
_MANIFEST_PARTIAL = dict(_MANIFEST_EFFECTIVE, status="PARTIALLY_EFFECTIVE")
_MANIFEST_EXPIRED = {
    **_MANIFEST_EFFECTIVE,
    "status": "EXPIRED",
    "effective_to": "2025-01-01",
}


# ────────────────────────────────────────────────────────────────────────────
# build_ir_from_lines
# ────────────────────────────────────────────────────────────────────────────


def test_build_ir_from_lines_creates_valid_document() -> None:
    document = build_ir_from_lines(
        ["Điều 5. Tiêu đề", "1. Khoản", "a) Điểm"], "nd-168-2024"
    )
    assert isinstance(document, ParsedDocument)
    assert document.document_id == "nd-168-2024"
    assert document.ir_schema_version == "document-ir-v2"
    assert len(document.pages) == 1
    elements = document.pages[0].elements
    assert [element.text for element in elements] == ["Điều 5. Tiêu đề", "1. Khoản", "a) Điểm"]
    assert {element.element_id for element in elements} == {"e0", "e1", "e2"}
    assert all(element.page_number == 1 for element in elements)
    assert all(element.source_parser == "FIXTURE_TEXT" for element in elements)
    # Deterministic row-major bboxes: later lines are lower on the page.
    tops = [element.bbox.top for element in elements]
    assert tops == sorted(tops)


def test_build_ir_from_lines_preserves_given_lines() -> None:
    # The helper builds elements from exactly the lines it is given; the
    # caller (run_batch01_routing) filters blank lines before calling it.
    document = build_ir_from_lines(["a", "", "  ", "b"], "nd-168-2024")
    assert [element.text for element in document.pages[0].elements] == ["a", "", "  ", "b"]


# ────────────────────────────────────────────────────────────────────────────
# apply_manifest_interval
# ────────────────────────────────────────────────────────────────────────────


def test_apply_manifest_interval_effective_is_uniform() -> None:
    provisions = [_provision(effective_from=None, effective_to=None)]
    applied = apply_manifest_interval(provisions, _MANIFEST_EFFECTIVE)
    assert applied[0].effective_from == "2025-01-01"
    assert applied[0].effective_to is None
    # Inputs are never mutated.
    assert provisions[0].effective_from is None


def test_apply_manifest_interval_partial_and_expired_untouched() -> None:
    for manifest in (_MANIFEST_PARTIAL, _MANIFEST_EXPIRED):
        provisions = [_provision(effective_from=None, effective_to=None)]
        applied = apply_manifest_interval(provisions, manifest)
        assert applied[0].effective_from is None
        assert applied[0].effective_to is None


def test_apply_manifest_interval_missing_from_untouched() -> None:
    manifest = dict(_MANIFEST_EFFECTIVE, effective_from=None)
    provisions = [_provision(effective_from=None)]
    assert apply_manifest_interval(provisions, manifest)[0].effective_from is None


# ────────────────────────────────────────────────────────────────────────────
# certifying_group_a
# ────────────────────────────────────────────────────────────────────────────


def test_certifying_group_a_born_digital_passes_through() -> None:
    measured = _passing_group_a()
    assert certifying_group_a(measured, scan_only=False) is measured


def test_certifying_group_a_scan_only_fails_extraction_gates() -> None:
    measured = _passing_group_a()
    certifying = certifying_group_a(measured, scan_only=True)
    assert certifying.verdict == "failed"
    assert certifying.text_extraction_rate.status == "failed"
    assert certifying.provenance_coverage.status == "failed"
    # Measured values are preserved for transparency.
    assert certifying.text_extraction_rate.value == 1.0
    policy = certifying.text_extraction_rate.detail["scan_policy"].casefold()
    assert "scan-only" in policy and "not certified" in policy


# ────────────────────────────────────────────────────────────────────────────
# aggregate_routing / document_level_decision
# ────────────────────────────────────────────────────────────────────────────


def _decision(provision_id: str, status: str, codes: list[str]) -> RoutingDecision:
    return RoutingDecision(
        provision_id=provision_id,
        status=status,
        reason_codes=codes,
        auto_accepted=status == "ACCEPTED",
    )


def test_aggregate_routing_counts_states_and_reasons() -> None:
    decisions = [
        _decision("p1", "ACCEPTED", []),
        _decision("p2", "NEEDS_REVIEW", [LOW_OCR_COVERAGE]),
        _decision("p3", "NEEDS_REVIEW", [LOW_OCR_COVERAGE, D_D_AMBIGUITY]),
        _decision("p4", "DROPPED", ["DUPLICATE_PROVISION"]),
    ]
    aggregated = aggregate_routing(decisions)
    assert aggregated["provision_states"] == {
        "ACCEPTED": 1,
        "NEEDS_REVIEW": 2,
        "DROPPED": 1,
    }
    assert aggregated["auto_accepted_count"] == 1
    assert aggregated["reason_histogram"] == {
        LOW_OCR_COVERAGE: 2,
        D_D_AMBIGUITY: 1,
        "DUPLICATE_PROVISION": 1,
    }


def test_aggregate_routing_empty() -> None:
    aggregated = aggregate_routing([])
    assert aggregated["provision_states"] == {"ACCEPTED": 0, "NEEDS_REVIEW": 0, "DROPPED": 0}
    assert aggregated["auto_accepted_count"] == 0
    assert aggregated["reason_histogram"] == {}


def test_document_level_decision_mirrors_actor_outcome() -> None:
    # Any NEEDS_REVIEW provision -> document NEEDS_REVIEW.
    aggregated = aggregate_routing(
        [_decision("p1", "ACCEPTED", []), _decision("p2", "NEEDS_REVIEW", [LOW_OCR_COVERAGE])]
    )
    decision = document_level_decision(
        _MANIFEST_EFFECTIVE, has_provisions=True, aggregated=aggregated, scan_only=False
    )
    assert decision == {"decision": "NEEDS_REVIEW", "reason_codes": [LOW_OCR_COVERAGE]}

    # All ACCEPTED -> document ACCEPTED.
    aggregated = aggregate_routing(
        [_decision("p1", "ACCEPTED", []), _decision("p2", "ACCEPTED", [])]
    )
    decision = document_level_decision(
        _MANIFEST_EFFECTIVE, has_provisions=True, aggregated=aggregated, scan_only=False
    )
    assert decision == {"decision": "ACCEPTED", "reason_codes": []}


def test_document_level_decision_no_provisions_routes_review() -> None:
    aggregated = aggregate_routing([])
    decision = document_level_decision(
        _MANIFEST_EFFECTIVE, has_provisions=False, aggregated=aggregated, scan_only=True
    )
    assert decision == {"decision": "NEEDS_REVIEW", "reason_codes": [LOW_OCR_COVERAGE]}


# ────────────────────────────────────────────────────────────────────────────
# quality_stats_for
# ────────────────────────────────────────────────────────────────────────────


def test_quality_stats_for_computes_ticket_metrics() -> None:
    provisions = [
        _provision(),
        _provision(
            provision_id="nd-168-2024__dieu-5",
            article="Điều 5",
            clause=None,
            point=None,
            point_label=None,
            node_kind="ARTICLE",
        ),
    ]
    stats = quality_stats_for(provisions, _MANIFEST_EFFECTIVE, _SLUG)
    assert stats["provision_counts"]["total"] == 2
    assert stats["point_label_detection_rate"] == 1.0
    assert stats["provenance_coverage"] == 1.0
    assert stats["parent_context_coverage"] == 1.0
    assert stats["d_da_detection_rate"] == 0.0
    assert stats["short_point_retention"] == 0.0  # no flagged short points
    assert stats["group_b_metrics"]["duplicate_count"] == 0
    assert stats["corpus_qa"]["article_count"] == 1
    assert stats["corpus_qa"]["point_count"] == 1


def test_quality_stats_for_empty_provision_set() -> None:
    stats = quality_stats_for([], _MANIFEST_EFFECTIVE, _SLUG)
    assert stats["provision_counts"]["total"] == 0
    assert stats["point_label_detection_rate"] == 0.0
    assert stats["provenance_coverage"] == 0.0


# ────────────────────────────────────────────────────────────────────────────
# render_report
# ────────────────────────────────────────────────────────────────────────────


def _minimal_artifact() -> dict:
    documents: dict[str, dict] = {}
    for document_id in (
        "nd-168-2024",
        "nd-100-2019",
        "luat-36-2024-qh15",
        "tt-79-2024",
        "tt-24-2023",
    ):
        documents[document_id] = {
            "document_id": document_id,
            "source_kind": "scan-only 1-bit CCITT (no text layer)",
            "extraction_input": {"kind": "none_available", "path": None, "note": "no input"},
            "manifest_interval": {"effective_from": "2025-01-01", "effective_to": None},
            "gate_metrics": {
                "group_a_routing_basis": None,
                "group_b": None,
            },
            "routing": {
                "decision": "NEEDS_REVIEW",
                "reason_codes": [LOW_OCR_COVERAGE],
                "provision_states": {"ACCEPTED": 0, "NEEDS_REVIEW": 0, "DROPPED": 0},
                "reason_histogram": {},
            },
            "quality_stats": {
                "provision_counts": {"total": 0, "ARTICLE": 0, "CLAUSE": 0, "POINT": 0},
                "point_label_detection_rate": 0.0,
                "d_da_detection_rate": 0.0,
                "provenance_coverage": 0.0,
                "parent_context_coverage": 0.0,
                "short_point_retention": 0.0,
            },
            "review_backlog": {"count": 0},
        }
    return {
        "artifact": "batch-01-routing",
        "version": "batch-01-routing-v1",
        "generated_at": "2026-08-14T00:00:00+00:00",
        "command": "cd backend && uv run python scripts/run_batch01_routing.py",
        "base_commit": "22e740d",
        "thresholds": {"group_a": {}, "group_b": {}},
        "indexing": {"performed": False, "statement": "NO indexing performed"},
        "documents": documents,
        "summary": {
            "documents": 5,
            "documents_routed": 5,
            "documents_by_decision": {"ACCEPTED": 0, "NEEDS_REVIEW": 5, "DROPPED": 0},
            "total_provisions": 0,
            "provision_states": {"ACCEPTED": 0, "NEEDS_REVIEW": 0, "DROPPED": 0},
        },
    }


def test_render_report_contains_required_content() -> None:
    report = render_report(_minimal_artifact())
    assert "VNLRAG-35" in report
    assert "NO indexing was performed" in report
    assert "Gate M2" in report
    assert "resolver-derived effective interval" in report
    for document_id in (
        "nd-168-2024",
        "nd-100-2019",
        "luat-36-2024-qh15",
        "tt-79-2024",
        "tt-24-2023",
    ):
        assert document_id in report
    assert "Review backlog summary" in report
    assert "cd backend && uv run python scripts/run_batch01_routing.py" in report
    assert "tests/test_run_batch01_routing.py" in report
    assert "validate_manifest" in report
