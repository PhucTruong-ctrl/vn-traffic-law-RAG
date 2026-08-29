"""Tests for review routing (VNLRAG-33).

Covers :mod:`app.ingestion.review_routing`: the deterministic
DROPPED / NEEDS_REVIEW / ACCEPTED classification per the auto-accept policy
table (docs/03 §3.7.5) and the scan-review routing policy
(``docs/parser_router.yaml``). All provisions and gate results are synthetic —
routing must be testable without any parser backend.
"""

from __future__ import annotations

from app.ingestion.quality_gates import (
    GateResult,
    GroupAResult,
    GroupBResult,
    evaluate_group_b,
)
from app.ingestion.review_routing import (
    D_D_AMBIGUITY,
    DUPLICATE_PROVISION,
    HEADER_FOOTER_LEAKAGE,
    HIERARCHY_VIOLATION,
    INVALID_POINT_LABEL,
    LOW_OCR_COVERAGE,
    NEEDS_REVIEW,
    POINT_LABEL_AMBIGUOUS,
    UNKNOWN_EFFECTIVE_DATE,
    RoutingDecision,
    evaluate_and_route,
    route_provision,
)
from app.ingestion.structure_extractor import ExtractedLegalProvision

_DOC_VERSION = "dv-nd-168-2024"
_SLUG = "nd-168-2024"

_HEADER_FOOTER_TEXT = "CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM — Độc lập - Tự do - Hạnh phúc"


def _provision(**overrides: object) -> ExtractedLegalProvision:
    """Build a clean ExtractedLegalProvision (default: point ``a)``, Điều 5 Khoản 1)."""

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
        "short_point": False,
        "needs_review": False,
        "ambiguity": None,
        "effective_from": "2025-01-01",
    }
    base.update(overrides)
    return ExtractedLegalProvision(**base)


def _clause(**overrides: object) -> ExtractedLegalProvision:
    base: dict[str, object] = {
        "provision_id": f"{_SLUG}__dieu-5__khoan-1",
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
    base: dict[str, object] = {
        "provision_id": f"{_SLUG}__dieu-5",
        "article": "Điều 5",
        "clause": None,
        "point": None,
        "source_text": "Điều 5. Xử phạt người điều khiển xe ô tô ...",
        "node_kind": "ARTICLE",
        "point_label": None,
    }
    base.update(overrides)
    return _provision(**base)


def _point(index: int, label: str) -> ExtractedLegalProvision:
    letters = "abcdefgh"
    return _provision(
        provision_id=f"{_SLUG}__dieu-5__khoan-1__diem-{letters[index - 1]}",
        point_label=label,
        source_text=f"{label} Nội dung điểm thứ {index}.",
    )


def _clean_tree() -> list[ExtractedLegalProvision]:
    """Điều 5 → Khoản 1 → points a) b): fully clean, Group B passes."""

    return [_article(), _clause(), _point(1, "a)"), _point(2, "b)")]


def _clean_group_b() -> GroupBResult:
    return evaluate_group_b(_clean_tree())


def _failed_group_b() -> GroupBResult:
    return GroupBResult(
        passed=False,
        metrics={
            "point_label_detection_rate": 0.0,
            "hierarchy_completeness": 0.0,
            "short_point_retention_rate": 1.0,
            "orphan_point_count": 0,
            "orphan_clause_count": 0,
            "duplicate_count": 0,
        },
        failed_checks=["point_label_detection", "hierarchy_completeness"],
    )


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


def _low_ocr_group_a() -> GroupAResult:
    """Scan-derived Group A: text extraction and provenance below thresholds."""

    return GroupAResult(
        provenance_coverage=_gate("provenance_coverage", 0.5, 0.9, "failed"),
        text_extraction_rate=_gate("text_extraction_rate", 0.5, 0.8, "failed"),
        table_detection_rate=_gate("table_detection_rate", None, 0.6, "na"),
        layout_coherence=_gate("layout_coherence", None, None, "na"),
        verdict="failed",
    )


def _na_group_a() -> GroupAResult:
    """Everything N/A: nothing computable to assert on."""

    return GroupAResult(
        provenance_coverage=_gate("provenance_coverage", None, 0.9, "na"),
        text_extraction_rate=_gate("text_extraction_rate", None, 0.8, "na"),
        table_detection_rate=_gate("table_detection_rate", None, 0.6, "na"),
        layout_coherence=_gate("layout_coherence", None, None, "na"),
        verdict="na",
    )


def _route(
    provision: ExtractedLegalProvision,
    *,
    group_a: GroupAResult | None = None,
    group_b: GroupBResult | None = None,
    duplicated_ids: frozenset[str] | None = None,
) -> RoutingDecision:
    return route_provision(
        provision,
        group_a=group_a if group_a is not None else _passing_group_a(),
        group_b=group_b if group_b is not None else _clean_group_b(),
        duplicated_ids=duplicated_ids,
    )


# ────────────────────────────────────────────────────────────────────────────
# ACCEPTED — policy row 1: gates pass AND no review flags
# ────────────────────────────────────────────────────────────────────────────


def test_route_provision_accepts_clean_provision() -> None:
    decision = _route(_article())
    assert decision.status == "ACCEPTED"
    assert decision.reason_codes == []
    assert decision.auto_accepted is True


def test_route_provision_accepts_clean_short_point() -> None:
    # Rulespec §5: a short point is retained and routes like any point.
    short = _point(1, "a)").model_copy(update={"short_point": True})
    decision = _route(short)
    assert decision.status == "ACCEPTED"
    assert decision.auto_accepted is True


def test_route_provision_accepts_clean_point_with_đ_label() -> None:
    # đ) is self-identifying (rulespec §4.1) and inside the PRIMARY run.
    decision = _route(_provision(point_label="đ)"))
    assert decision.status == "ACCEPTED"


# ────────────────────────────────────────────────────────────────────────────
# DROPPED — hard structural failures, never indexed
# ────────────────────────────────────────────────────────────────────────────


def test_route_provision_drops_duplicate_provision() -> None:
    decision = _route(_article(), duplicated_ids=frozenset({f"{_SLUG}__dieu-5"}))
    assert decision.status == "DROPPED"
    assert decision.reason_codes == [DUPLICATE_PROVISION]
    assert decision.auto_accepted is False


def test_route_provision_drops_missing_point_label() -> None:
    # A POINT with no label at all cannot be placed in the tree.
    broken = _provision(point_label=None, point=None)
    decision = _route(broken)
    assert decision.status == "DROPPED"
    assert decision.reason_codes == [INVALID_POINT_LABEL]


def test_route_provision_drops_unrecognizable_label() -> None:
    # Text that is not a point label (no close paren) → hard failure.
    decision = _route(_provision(point_label="xyz"))
    assert decision.status == "DROPPED"
    assert decision.reason_codes == [INVALID_POINT_LABEL]


def test_evaluate_and_route_drops_duplicates_via_full_document() -> None:
    tree = _clean_tree() + [_article()]  # Điều 5 appears twice
    # Precomputed passing Group B isolates the per-provision duplicate routing.
    decisions = evaluate_and_route(tree, group_a=_passing_group_a(), group_b=_clean_group_b())
    dropped = [d for d in decisions if d.status == "DROPPED"]
    assert len(dropped) == 2  # both rows sharing the duplicated id
    assert all(d.reason_codes == [DUPLICATE_PROVISION] for d in dropped)
    assert all(d.auto_accepted is False for d in dropped)
    accepted = [d for d in decisions if d.status == "ACCEPTED"]
    assert len(accepted) == 3  # clause + both points are unaffected


def test_evaluate_and_route_duplicate_fails_group_b_document_wide() -> None:
    # A duplicate id is a structural defect: with the computed Group B the
    # completeness drops to 4/5 = 0.8 < 0.9, so the clean provisions cannot
    # auto-accept either (policy row 1) — only the duplicates are DROPPED.
    tree = _clean_tree() + [_article()]
    decisions = evaluate_and_route(tree, group_a=_passing_group_a())
    assert {d.status for d in decisions} == {"DROPPED", "NEEDS_REVIEW"}
    dropped = [d for d in decisions if d.status == "DROPPED"]
    assert len(dropped) == 2
    needs_review = [d for d in decisions if d.status == "NEEDS_REVIEW"]
    assert len(needs_review) == 3
    assert all(NEEDS_REVIEW in d.reason_codes for d in needs_review)


# ────────────────────────────────────────────────────────────────────────────
# NEEDS_REVIEW — every ambiguity / policy reason
# ────────────────────────────────────────────────────────────────────────────


def test_route_provision_needs_review_d_d_ambiguity_from_extractor() -> None:
    # Extractor normalized a duplicate d) run to đ) and flagged review.
    provision = _provision(
        point_label="đ)",
        needs_review=True,
        ambiguity="OCR d/đ ambiguity normalized from duplicate d)",
    )
    decision = _route(provision)
    assert decision.status == "NEEDS_REVIEW"
    assert D_D_AMBIGUITY in decision.reason_codes
    assert decision.auto_accepted is False


def test_route_provision_needs_review_bare_d_label() -> None:
    # A bare d) without ordinal context is d↔đ OCR-ambiguous
    # (canonical_point_label returns None without an ordinal) → review.
    decision = _route(_provision(point_label="d)"))
    assert decision.status == "NEEDS_REVIEW"
    assert decision.reason_codes == [D_D_AMBIGUITY]


def test_route_provision_needs_review_point_label_ambiguous() -> None:
    # g) is a real Vietnamese point label but outside the PRIMARY run
    # a→b→c→d→đ→e → flagged for review, never silently accepted.
    decision = _route(_provision(point_label="g)"))
    assert decision.status == "NEEDS_REVIEW"
    assert decision.reason_codes == [POINT_LABEL_AMBIGUOUS]


def test_route_provision_needs_review_reconstructed_point_label() -> None:
    provision = _provision(
        needs_review=True,
        ambiguity="point label reconstructed from marker-stripped list item",
    )
    decision = _route(provision)
    assert decision.status == "NEEDS_REVIEW"
    assert POINT_LABEL_AMBIGUOUS in decision.reason_codes


def test_route_provision_needs_review_hierarchy_violation() -> None:
    provision = _provision(needs_review=True, ambiguity="orphan point without article/clause")
    decision = _route(provision)
    assert decision.status == "NEEDS_REVIEW"
    assert HIERARCHY_VIOLATION in decision.reason_codes


def test_route_provision_needs_review_low_ocr_coverage() -> None:
    # Scan-derived routing: Group A text_extraction/provenance below
    # thresholds → LOW_OCR_COVERAGE, never auto-index partial OCR output.
    decision = _route(_article(), group_a=_low_ocr_group_a())
    assert decision.status == "NEEDS_REVIEW"
    assert decision.reason_codes == [LOW_OCR_COVERAGE]


def test_route_provision_needs_review_unknown_effective_date() -> None:
    # Policy row 6: an uncertain effective date is UNKNOWN/PENDING_REVIEW
    # until a reviewer decides — never guessed.
    decision = _route(_article(effective_from=None))
    assert decision.status == "NEEDS_REVIEW"
    assert decision.reason_codes == [UNKNOWN_EFFECTIVE_DATE]


def test_route_provision_needs_review_header_footer_leakage() -> None:
    decision = _route(
        _article(source_text=f"{_HEADER_FOOTER_TEXT} Điều 5. ..."),
        group_a=_passing_group_a(),
        group_b=_clean_group_b(),
    )
    assert decision.status == "NEEDS_REVIEW"
    assert HEADER_FOOTER_LEAKAGE in decision.reason_codes


def test_route_provision_needs_review_generic_extractor_flag() -> None:
    # An unmapped extractor review flag falls back to the generic code.
    provision = _provision(needs_review=True, ambiguity="some future ambiguity")
    decision = _route(provision)
    assert decision.status == "NEEDS_REVIEW"
    assert decision.reason_codes == [NEEDS_REVIEW]


def test_route_provision_group_b_failure_blocks_auto_accept() -> None:
    # Policy row 1: Group B must pass for auto-accept; a document-level
    # structural failure sends even a clean provision to review.
    decision = _route(_article(), group_b=_failed_group_b())
    assert decision.status == "NEEDS_REVIEW"
    assert NEEDS_REVIEW in decision.reason_codes


def test_route_provision_na_group_a_blocks_auto_accept() -> None:
    decision = _route(_article(), group_a=_na_group_a())
    assert decision.status == "NEEDS_REVIEW"
    assert NEEDS_REVIEW in decision.reason_codes


def test_route_provision_accumulates_all_review_codes() -> None:
    provision = _provision(
        point_label="d)",
        needs_review=True,
        ambiguity="OCR d/đ ambiguity normalized from duplicate d)",
        effective_from=None,
        source_text=f"{_HEADER_FOOTER_TEXT} a) Điều khiển xe ...",
    )
    decision = _route(provision, group_a=_low_ocr_group_a())
    assert decision.status == "NEEDS_REVIEW"
    assert set(decision.reason_codes) == {
        D_D_AMBIGUITY,
        UNKNOWN_EFFECTIVE_DATE,
        HEADER_FOOTER_LEAKAGE,
        LOW_OCR_COVERAGE,
    }


# ────────────────────────────────────────────────────────────────────────────
# evaluate_and_route — convenience wrapper
# ────────────────────────────────────────────────────────────────────────────


def test_evaluate_and_route_empty_input_routes_empty() -> None:
    assert evaluate_and_route([], group_a=_passing_group_a()) == []


def test_evaluate_and_route_clean_tree_accepts_all() -> None:
    decisions = evaluate_and_route(_clean_tree(), group_a=_passing_group_a())
    assert len(decisions) == 4
    assert all(d.status == "ACCEPTED" for d in decisions)
    assert all(d.auto_accepted for d in decisions)
    assert {d.provision_id for d in decisions} == {p.provision_id for p in _clean_tree()}


def test_evaluate_and_route_mixed_document_matches_per_provision() -> None:
    tree = [
        _article(),
        _clause(),
        _point(1, "a)"),
        _provision(
            provision_id=f"{_SLUG}__dieu-5__khoan-1__diem-g",
            point_label="g)",
        ),  # ambiguous label → review
        _provision(
            provision_id=f"{_SLUG}__dieu-5__khoan-1__diem-h",
            point_label=None,
            point=None,
        ),  # broken label → dropped
        _article(),  # duplicate of the first article → dropped
    ]
    # Precomputed passing Group B isolates the per-provision reasons (the
    # invalid labels in this tree would otherwise fail the document gate).
    decisions = evaluate_and_route(tree, group_a=_passing_group_a(), group_b=_clean_group_b())
    by_id = {d.provision_id: d for d in decisions}
    assert by_id[f"{_SLUG}__dieu-5"].status == "DROPPED"  # duplicate
    assert by_id[f"{_SLUG}__dieu-5__khoan-1"].status == "ACCEPTED"
    assert by_id[f"{_SLUG}__dieu-5__khoan-1__diem-a"].status == "ACCEPTED"
    assert by_id[f"{_SLUG}__dieu-5__khoan-1__diem-g"].status == "NEEDS_REVIEW"
    assert by_id[f"{_SLUG}__dieu-5__khoan-1__diem-g"].reason_codes == [POINT_LABEL_AMBIGUOUS]
    assert by_id[f"{_SLUG}__dieu-5__khoan-1__diem-h"].status == "DROPPED"
    assert by_id[f"{_SLUG}__dieu-5__khoan-1__diem-h"].reason_codes == [INVALID_POINT_LABEL]


def test_evaluate_and_route_accepts_precomputed_group_b() -> None:
    group_b = _clean_group_b()
    decisions = evaluate_and_route(_clean_tree(), group_a=_passing_group_a(), group_b=group_b)
    assert all(d.status == "ACCEPTED" for d in decisions)


# ────────────────────────────────────────────────────────────────────────────
# auto_accepted semantics + reason-code constants
# ────────────────────────────────────────────────────────────────────────────


def test_auto_accepted_flag_is_true_only_for_accepted() -> None:
    assert _route(_article()).auto_accepted is True
    assert _route(_provision(point_label="g)")).auto_accepted is False
    assert _route(_provision(point_label=None, point=None)).auto_accepted is False
    assert _route(_article(), group_b=_failed_group_b()).auto_accepted is False


def test_reason_codes_are_distinct_constants() -> None:
    codes = {
        LOW_OCR_COVERAGE,
        POINT_LABEL_AMBIGUOUS,
        D_D_AMBIGUITY,
        HIERARCHY_VIOLATION,
        DUPLICATE_PROVISION,
        INVALID_POINT_LABEL,
        HEADER_FOOTER_LEAKAGE,
        UNKNOWN_EFFECTIVE_DATE,
        NEEDS_REVIEW,
    }
    assert len(codes) == 9
