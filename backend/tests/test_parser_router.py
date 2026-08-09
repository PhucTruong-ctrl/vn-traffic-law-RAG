"""Tests for the Parser Router (VNLRAG-131).

Routing matrix (doc 03 §3.7.1 + Suite A §7), Group A gating with alternate-
parser fallback, OCR fail-fast, and the jsonable ``parser_routing`` record.
Adapter executions are injected (``fallback_runner``) or monkeypatched — no
parser backend is required.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

import app.ingestion.parser_router as parser_router
from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage
from app.ingestion.parser_router import (
    COMPLEX_TABLE_COUNT_THRESHOLD,
    DEFAULT_CONFIG_PATH,
    FallbackPolicy,
    GateOutcome,
    ParserLevelGates,
    ParserRouter,
    QualityGates,
    RouterConfig,
    RoutingInputs,
    build_ocr_config_snapshot,
    build_parser_routing_record,
    load_router_config,
)
from app.ingestion.quality_gates import GroupAThresholds

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _box() -> BoundingBox:
    # v2: NORMALIZED_PAGE (0..1) — values must stay in the unit interval.
    return BoundingBox(left=0.1, top=0.2, right=0.3, bottom=0.4)


def _element(
    reading_order: int,
    *,
    has_bbox: bool = True,
    text: str = "Nội dung đoạn văn.",
    source_parser: str = "DOCLING",
) -> DocumentElement:
    return DocumentElement(
        element_id=f"e{reading_order}",
        element_type="paragraph",
        text=text,
        page_number=1,
        bbox=_box() if has_bbox else None,
        reading_order=reading_order,
        parent_element_id=None,
        table_html=None,
        source_parser=source_parser,
        parser_version="docling-2.118.1",
        parser_confidence=None,
        raw_reference={"docling_item_index": reading_order},
    )


def _page(page_number: int, elements: list[DocumentElement]) -> ParsedPage:
    page_text = "\n".join(e.text for e in elements if e.text.strip()) or None
    # v2: element.page_number must equal the page's number (cross-level check).
    for element in elements:
        element.page_number = page_number
    return ParsedPage(
        page_number=page_number,
        width=595.0,
        height=842.0,
        text=page_text,
        elements=elements,
    )


def _document(
    pages: list[ParsedPage],
    document_id: str = "nd-168-2024",
    parser: str = "DOCLING",
) -> ParsedDocument:
    started_at = datetime.now(UTC)
    return ParsedDocument(
        parsed_document_id="a1b2c3d4-0000-4000-8000-000000000000",
        document_id=document_id,
        parser=parser,
        parser_version="docling-2.118.1",
        ir_schema_version="document-ir-v2",
        source_object_key="fixtures/nd-168-2024.pdf",
        pages=pages,
        parse_started_at=started_at,
        parse_completed_at=started_at,  # v2: completed >= started
        quality_report={},
    )


def _passing_doc() -> ParsedDocument:
    """Group A passes: all bbox'd, text non-empty, contiguous reading_order."""
    return _document(
        [
            _page(1, [_element(0), _element(1)]),
            _page(2, [_element(2), _element(3)]),
        ]
    )


def _failing_doc() -> ParsedDocument:
    """Group A fails: provenance 0.2 (1 of 5 bbox'd) < 0.9."""
    return _document(
        [
            _page(
                1,
                [
                    _element(0),
                    _element(1, has_bbox=False),
                    _element(2, has_bbox=False),
                    _element(3, has_bbox=False),
                    _element(4, has_bbox=False),
                ],
            )
        ]
    )


def _mineru_passing_doc() -> ParsedDocument:
    """Genuine MINERU-labeled doc that passes Group A (all bbox'd, text, contiguous)."""
    return _document(
        [
            _page(1, [_element(0, source_parser="MINERU"), _element(1, source_parser="MINERU")]),
            _page(2, [_element(2, source_parser="MINERU"), _element(3, source_parser="MINERU")]),
        ],
        parser="MINERU",
    )


def _mineru_failing_doc() -> ParsedDocument:
    """Genuine MINERU-labeled doc that fails Group A (provenance 0.2)."""
    return _document(
        [
            _page(
                1,
                [
                    _element(0, source_parser="MINERU"),
                    _element(1, has_bbox=False, source_parser="MINERU"),
                    _element(2, has_bbox=False, source_parser="MINERU"),
                    _element(3, has_bbox=False, source_parser="MINERU"),
                    _element(4, has_bbox=False, source_parser="MINERU"),
                ],
            )
        ],
        parser="MINERU",
    )


def _mineru_with_bbox(bbox_count: int, total: int = 10) -> ParsedDocument:
    """MINERU doc with ``bbox_count`` of ``total`` bbox'd elements (one page)."""
    elements = [
        _element(i, has_bbox=(i < bbox_count), source_parser="MINERU") for i in range(total)
    ]
    return _document([_page(1, elements)], parser="MINERU")


def _docling_with_bbox(bbox_count: int, total: int = 10) -> ParsedDocument:
    """DOCLING doc with ``bbox_count`` of ``total`` bbox'd elements (one page)."""
    elements = [_element(i, has_bbox=(i < bbox_count)) for i in range(total)]
    return _document([_page(1, elements)])


def _boom_runner() -> ParsedDocument:
    raise RuntimeError("mineru pipeline blocked")


def _raise_runtime(message: str) -> ParsedDocument:
    raise RuntimeError(message)


def _flag_runner(flags: list[str], label: str, doc: ParsedDocument) -> Callable[[], ParsedDocument]:
    """Lazy runner that records ``label`` in ``flags`` when invoked."""

    def runner() -> ParsedDocument:
        flags.append(label)
        return doc

    return runner


def _pdf_inputs(**overrides: Any) -> RoutingInputs:
    defaults: dict[str, Any] = {
        "document_id": "nd-168-2024",
        "file_mime": "application/pdf",
        "has_text_layer": True,
        "page_count": 2,
        "file_size_bytes": 2048,
        "layout_complexity": None,
        "document_type": "DECREE",
    }
    defaults.update(overrides)
    return RoutingInputs(**defaults)


# ────────────────────────────────────────────────────────────────────────────
# Config
# ────────────────────────────────────────────────────────────────────────────


def test_load_router_config_parses_committed_yaml() -> None:
    config = load_router_config()
    assert DEFAULT_CONFIG_PATH.is_file()
    assert config.primary == "docling"
    assert config.fallback == "mineru"
    assert config.compare_on_complex_tables is True
    assert config.quality_gates.parser_level.min_provenance_coverage == 0.9
    assert config.quality_gates.parser_level.min_text_extraction_rate == 0.8
    assert config.quality_gates.parser_level.min_table_detection_rate == 0.6
    assert config.quality_gates.structural.min_point_label_detection == 0.9
    assert config.quality_gates.structural.min_hierarchy_completeness == 0.9
    assert config.fallback_policy.on_parser_gate_fail == "rerun_alternate_parser"
    assert config.fallback_policy.on_structural_gate_fail == "full_rerun_alternate"
    assert config.fallback_policy.supersede_old_artifacts is True
    assert config.decision_record is True


def test_load_router_config_defaults_when_file_absent(tmp_path: Path) -> None:
    config = load_router_config(tmp_path / "missing-parser-router.yaml")
    # Defaults equal the committed yaml values (authoritative behavior retained).
    assert config == RouterConfig()
    assert config.primary == "docling"


def test_router_config_overrides_are_honoured() -> None:
    config = RouterConfig(primary="mineru", fallback="docling")
    router = ParserRouter(config)
    decision = router.decide(_pdf_inputs())
    assert decision.selected_parser == "mineru"
    assert decision.expected_fallback == "docling"


# ────────────────────────────────────────────────────────────────────────────
# Routing decisions (doc 03 §3.7.1)
# ────────────────────────────────────────────────────────────────────────────


def test_route_searchable_pdf_to_docling_text() -> None:
    decision = ParserRouter().decide(_pdf_inputs(has_text_layer=True))
    assert decision.route == "docling_text"
    assert decision.selected_parser == "docling"
    assert decision.ocr_required is False
    assert decision.compare_parsers is False
    assert decision.expected_fallback == "mineru"


def test_route_scan_pdf_to_docling_ocr() -> None:
    decision = ParserRouter().decide(_pdf_inputs(has_text_layer=False))
    assert decision.route == "docling_ocr"
    assert decision.selected_parser == "docling"
    assert decision.ocr_required is True
    assert decision.compare_parsers is False
    assert decision.expected_fallback == "mineru"


def test_route_complex_tables_to_compare() -> None:
    decision = ParserRouter().decide(_pdf_inputs(layout_complexity=COMPLEX_TABLE_COUNT_THRESHOLD))
    assert decision.route == "compare_complex_tables"
    assert decision.compare_parsers is True
    assert decision.selected_parser == "docling"


def test_route_below_complex_threshold_to_normal_route() -> None:
    decision = ParserRouter().decide(_pdf_inputs(layout_complexity=2))
    assert decision.route == "docling_text"
    assert decision.compare_parsers is False


def test_route_scan_with_complex_tables_needs_ocr() -> None:
    decision = ParserRouter().decide(_pdf_inputs(has_text_layer=False, layout_complexity=6))
    assert decision.route == "compare_complex_tables"
    assert decision.ocr_required is True


def test_route_compare_disabled_by_config() -> None:
    config = RouterConfig(compare_on_complex_tables=False)
    decision = ParserRouter(config).decide(_pdf_inputs(layout_complexity=10))
    assert decision.route == "docling_text"
    assert decision.compare_parsers is False


def test_route_non_pdf_to_docling_no_fallback() -> None:
    decision = ParserRouter().decide(
        _pdf_inputs(
            file_mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
    )
    assert decision.route == "docling_other_mime"
    assert decision.ocr_required is False
    assert decision.expected_fallback is None
    assert decision.selected_parser == "docling"


def test_route_non_pdf_complex_tables_stays_other_mime() -> None:
    # Precedence regression (ora-28 blocker 1): non-PDF wins over complex
    # tables — a DOCX with a high table count must NOT route to the compare
    # path nor get a MinerU fallback (P0 = PDF-only).
    decision = ParserRouter().decide(
        _pdf_inputs(
            file_mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            layout_complexity=COMPLEX_TABLE_COUNT_THRESHOLD + 5,
        )
    )
    assert decision.route == "docling_other_mime"
    assert decision.compare_parsers is False
    assert decision.expected_fallback is None
    assert decision.selected_parser == "docling"


def test_route_decision_embeds_inputs() -> None:
    inputs = _pdf_inputs(has_text_layer=False)
    decision = ParserRouter().decide(inputs)
    assert decision.inputs == inputs
    assert decision.inputs.document_id == "nd-168-2024"


# ────────────────────────────────────────────────────────────────────────────
# Fixture routing matrix (AC: "Routing matrix correct on fixtures")
# ────────────────────────────────────────────────────────────────────────────


def test_fixture_routing_matrix() -> None:
    """Routing decisions on VNLRAG-24 fixtures + batch-01 manifests.

    Matrix (text-layer facts from the fixture/README documentation):

    | document                  | source                        | text layer | expected route   |
    |---------------------------|-------------------------------|------------|------------------|
    | luat-traffic-2024-fixture | parser_benchmark/documents    | yes        | docling_text     |
    | nd-168-2024-fixture       | parser_benchmark/documents    | yes        | docling_text     |
    | tt-traffic-2024-fixture   | parser_benchmark/documents    | yes        | docling_text     |
    | luat-36-2024-qh15         | data/manifests/batch-01       | yes        | docling_text     |
    | nd-168-2024               | data/manifests/batch-01       | no (scan)  | docling_ocr      |
    | nd-100-2019               | data/manifests/batch-01       | no (scan)  | docling_ocr      |
    | tt-79-2024                | data/manifests/batch-01       | no (scan)  | docling_ocr      |
    | tt-24-2023                | data/manifests/batch-01       | no (scan)  | docling_ocr      |
    """
    router = ParserRouter()
    fixtures_dir = _REPO_ROOT / "backend" / "tests" / "fixtures" / "parser_benchmark" / "documents"
    for subdir in ("luat", "nd", "tt"):
        pdf = next((fixtures_dir / subdir).glob("*.pdf"))
        decision = router.decide(
            _pdf_inputs(
                document_id=pdf.stem,
                has_text_layer=True,
                page_count=1,
                file_size_bytes=pdf.stat().st_size,
                layout_complexity=0,
                document_type="OTHER",
            )
        )
        assert decision.route == "docling_text", pdf.name

    # batch-01: only luat-36-2024-qh15 is born-digital; the other four are
    # scan-only (data/manifests/batch-01/README.md).
    manifests_dir = _REPO_ROOT / "data" / "manifests" / "batch-01"
    text_layer: dict[str, bool] = {
        "luat-36-2024-qh15": True,
        "nd-168-2024": False,
        "nd-100-2019": False,
        "tt-79-2024": False,
        "tt-24-2023": False,
    }
    for manifest_path in sorted(manifests_dir.glob("*.manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        document_id = manifest["document_id"]
        decision = router.decide(
            _pdf_inputs(
                document_id=document_id,
                has_text_layer=text_layer[document_id],
                page_count=1,
                file_size_bytes=0,
                document_type=manifest.get("document_type", "OTHER"),
            )
        )
        expected = "docling_text" if text_layer[document_id] else "docling_ocr"
        assert decision.route == expected, document_id


# ────────────────────────────────────────────────────────────────────────────
# execute_and_gate — Group A gating + alternate fallback
# ────────────────────────────────────────────────────────────────────────────


def test_execute_and_gate_accepted_when_group_a_passes() -> None:
    outcome = ParserRouter().execute_and_gate(_passing_doc(), "docling", "mineru")
    assert outcome.terminal_outcome == "accepted"
    assert outcome.group_a.verdict == "passed"
    assert outcome.fallback_attempted is False
    assert outcome.source_parser == "docling"  # single parser, no mixing


def test_execute_and_gate_fallback_passes_and_supersedes() -> None:
    router = ParserRouter()
    outcome = router.execute_and_gate(
        _failing_doc(),
        "docling",
        "mineru",
        fallback_runner=lambda: _mineru_passing_doc(),
    )
    assert outcome.terminal_outcome == "accepted"
    assert outcome.fallback_attempted is True
    assert outcome.fallback_parser == "mineru"
    assert outcome.fallback_result is not None
    assert outcome.fallback_result.verdict == "passed"
    # No parser mixing: the document is wholly attributed to the alternate.
    assert outcome.source_parser == "mineru"
    assert outcome.superseded_old_artifacts is True  # fallback_policy.supersede_old_artifacts


def test_execute_and_gate_fallback_fails_routes_to_review() -> None:
    outcome = ParserRouter().execute_and_gate(
        _failing_doc(),
        "docling",
        "mineru",
        fallback_runner=_mineru_failing_doc,
    )
    assert outcome.terminal_outcome == "needs_review"
    assert outcome.routed_to_review is True
    assert outcome.fallback_attempted is True
    assert outcome.source_parser is None  # neither parser accepted


def test_execute_and_gate_primary_provenance_mismatch_fails() -> None:
    # A MINERU-labeled doc presented as the "docling" parse must not be accepted.
    outcome = ParserRouter().execute_and_gate(_mineru_passing_doc(), "docling", "mineru")
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason is not None
    assert outcome.reason.startswith("PROVENANCE_MISMATCH")
    assert outcome.source_parser is None


def test_execute_and_gate_mixed_source_parsers_fail() -> None:
    # One document carrying elements from two parsers violates the no-mixing rule.
    mixed = _document(
        [
            _page(
                1,
                [
                    _element(0, source_parser="DOCLING"),
                    _element(1, source_parser="MINERU"),
                ],
            )
        ]
    )
    outcome = ParserRouter().execute_and_gate(mixed, "docling", "mineru")
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason is not None
    assert outcome.reason.startswith("PROVENANCE_MISMATCH")
    assert "mixes source_parser" in outcome.reason
    assert outcome.source_parser is None


def test_execute_and_gate_fallback_doc_wrong_parser_not_accepted() -> None:
    # The fallback_runner returned a DOCLING doc: it must NOT be accepted as
    # mineru — the outcome routes to review with a provenance reason.
    outcome = ParserRouter().execute_and_gate(
        _failing_doc(),
        "docling",
        "mineru",
        fallback_runner=lambda: _passing_doc(),  # DOCLING-labeled, not MINERU
    )
    assert outcome.terminal_outcome == "needs_review"
    assert outcome.routed_to_review is True
    assert outcome.fallback_attempted is True
    assert outcome.source_parser is None
    assert outcome.reason is not None
    assert outcome.reason.startswith("PROVENANCE_MISMATCH")


def test_execute_and_gate_no_fallback_runner_is_terminal_failure() -> None:
    outcome = ParserRouter().execute_and_gate(_failing_doc(), "docling", "mineru")
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason is not None
    assert outcome.reason.startswith("FALLBACK_NOT_AVAILABLE")
    assert outcome.source_parser is None


def test_execute_and_gate_fallback_runner_raises_is_terminal_failure() -> None:
    def boom() -> ParsedDocument:
        raise RuntimeError("mineru pipeline blocked")

    outcome = ParserRouter().execute_and_gate(
        _failing_doc(), "docling", "mineru", fallback_runner=boom
    )
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason is not None
    assert outcome.reason.startswith("FALLBACK_PARSE_FAILED")


def test_execute_and_gate_no_rerun_policy_routes_to_review() -> None:
    config = RouterConfig(fallback_policy=FallbackPolicy(on_parser_gate_fail="none"))
    outcome = ParserRouter(config).execute_and_gate(_failing_doc(), "docling", "mineru")
    assert outcome.terminal_outcome == "needs_review"
    assert outcome.routed_to_review is True
    assert outcome.fallback_attempted is False
    assert outcome.source_parser == "docling"  # its artifacts exist but are under review


def test_execute_and_gate_uses_config_thresholds_by_default() -> None:
    # A doc with provenance 0.2 passes when the config threshold is 0.0 —
    # proving the router builds its default thresholds from the config.
    config = RouterConfig(
        quality_gates=QualityGates(parser_level=ParserLevelGates(min_provenance_coverage=0.0))
    )
    outcome = ParserRouter(config).execute_and_gate(_failing_doc(), "docling", "mineru")
    assert outcome.group_a.provenance_coverage.value == pytest.approx(0.2)
    assert outcome.group_a.provenance_coverage.status == "passed"
    assert outcome.terminal_outcome == "accepted"
    assert outcome.source_parser == "docling"


def test_execute_and_gate_explicit_thresholds_override_config() -> None:
    router = ParserRouter()
    lenient = GroupAThresholds(min_provenance_coverage=0.0)
    outcome = router.execute_and_gate(_failing_doc(), "docling", "mineru", lenient)
    assert outcome.group_a.provenance_coverage.value == pytest.approx(0.2)
    assert outcome.group_a.provenance_coverage.status == "passed"
    assert outcome.terminal_outcome == "accepted"
    assert outcome.source_parser == "docling"


# ────────────────────────────────────────────────────────────────────────────
# OCR fail-fast
# ────────────────────────────────────────────────────────────────────────────


def test_ensure_ocr_ready_propagates_problems(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    problems = ["tesseract executable not found: '/usr/bin/tesseract'"]
    monkeypatch.setattr(parser_router, "check_ocr_readiness", lambda **kwargs: problems)
    router = ParserRouter()
    assert router.ensure_ocr_ready() == problems


def test_scan_route_ocr_not_ready_terminal_outcome(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    problems = ["tesseract executable not found: '/usr/bin/tesseract'", "vie.traineddata missing"]
    monkeypatch.setattr(parser_router, "check_ocr_readiness", lambda **kwargs: problems)

    router = ParserRouter()
    inputs = _pdf_inputs(has_text_layer=False)
    decision = router.decide(inputs)
    assert decision.route == "docling_ocr"

    outcome = router.ocr_route_terminal_outcome(inputs, problems)
    assert isinstance(outcome, GateOutcome)
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason is not None
    assert outcome.reason.startswith("OCR_NOT_READY")
    assert outcome.source_parser is None  # no parse happened


# ────────────────────────────────────────────────────────────────────────────
# route_and_gate — orchestration (routing + OCR fail-fast + gating)
# ────────────────────────────────────────────────────────────────────────────


def test_route_and_gate_ocr_not_ready_invokes_no_parser(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    problems = ["tesseract executable not found: '/usr/bin/tesseract'"]
    monkeypatch.setattr(parser_router, "check_ocr_readiness", lambda **kwargs: problems)

    router = ParserRouter()
    inputs = _pdf_inputs(has_text_layer=False)
    calls: list[str] = []
    primary_runner = _flag_runner(calls, "primary", _passing_doc())
    alternate_runner = _flag_runner(calls, "alternate", _mineru_passing_doc())

    decision, outcome = router.route_and_gate(
        inputs, primary_runner, alternate_runner=alternate_runner
    )
    assert decision.route == "docling_ocr"
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason is not None
    assert outcome.reason.startswith("OCR_NOT_READY")
    assert outcome.source_parser is None
    # Genuine fail-fast: neither the primary parse nor the alternate ran.
    assert calls == []


def test_route_and_gate_ocr_ready_invokes_primary_runner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(parser_router, "check_ocr_readiness", lambda **kwargs: [])
    router = ParserRouter()
    inputs = _pdf_inputs(has_text_layer=False)
    calls: list[str] = []
    primary_runner = _flag_runner(calls, "primary", _passing_doc())

    decision, outcome = router.route_and_gate(inputs, primary_runner)
    assert decision.route == "docling_ocr"
    assert calls == ["primary"]  # OCR ready -> the primary parse actually ran
    assert outcome.terminal_outcome == "accepted"
    assert outcome.source_parser == "docling"


def test_route_and_gate_primary_runner_raises_terminal_failure() -> None:
    router = ParserRouter()
    decision, outcome = router.route_and_gate(
        _pdf_inputs(), lambda: _raise_runtime("docling pipeline blocked")
    )
    assert decision.route == "docling_text"
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason is not None
    assert outcome.reason.startswith("PRIMARY_PARSE_FAILED")
    assert outcome.source_parser is None


def test_route_and_gate_non_pdf_no_fallback_on_gate_fail() -> None:
    router = ParserRouter()
    inputs = _pdf_inputs(file_mime="application/msword", layout_complexity=10)
    calls: list[str] = []
    primary_runner = _flag_runner(calls, "primary", _failing_doc())
    alternate_runner = _flag_runner(calls, "alternate", _mineru_passing_doc())

    decision, outcome = router.route_and_gate(
        inputs, primary_runner, alternate_runner=alternate_runner
    )
    assert decision.route == "docling_other_mime"
    assert calls == ["primary"]  # primary parsed, alternate never invoked (P0)
    assert outcome.terminal_outcome == "needs_review"
    assert outcome.routed_to_review is True
    assert outcome.fallback_attempted is False


# ────────────────────────────────────────────────────────────────────────────
# compare mode (complex tables: both parsers run, pick per policy)
# ────────────────────────────────────────────────────────────────────────────


def _compare_inputs() -> RoutingInputs:
    return _pdf_inputs(layout_complexity=COMPLEX_TABLE_COUNT_THRESHOLD)


def test_compare_mode_runs_both_parsers() -> None:
    router = ParserRouter()
    calls: list[str] = []
    primary_runner = _flag_runner(calls, "primary", _passing_doc())
    alternate_runner = _flag_runner(calls, "alternate", _mineru_passing_doc())

    decision, outcome = router.route_and_gate(
        _compare_inputs(), primary_runner, alternate_runner=alternate_runner
    )
    assert decision.route == "compare_complex_tables"
    assert calls == ["primary", "alternate"]  # both parsers actually ran
    assert outcome.terminal_outcome == "accepted"
    assert outcome.comparison is not None
    # Both parsers' outputs were produced and evaluated.
    assert outcome.comparison["primary_group_a"] is not None
    assert outcome.comparison["alternate_group_a"] is not None
    assert outcome.comparison["pick"] in ("docling", "mineru")


def test_compare_both_pass_picks_higher_provenance() -> None:
    router = ParserRouter()
    # Primary provenance 1.0; alternate exactly 0.9 (passes) -> primary wins.
    outcome = router.compare_and_pick(
        _docling_with_bbox(10),
        _mineru_with_bbox(9),
        "docling",
        "mineru",
    )
    assert outcome.terminal_outcome == "accepted"
    assert outcome.source_parser == "docling"
    assert outcome.comparison is not None
    assert outcome.comparison["pick"] == "docling"
    assert "tie-break" in outcome.comparison["pick_rule"]

    # Reverse: alternate 1.0 beats primary 0.9 -> alternate wins.
    outcome_rev = router.compare_and_pick(
        _docling_with_bbox(9),
        _mineru_with_bbox(10),
        "docling",
        "mineru",
    )
    assert outcome_rev.terminal_outcome == "accepted"
    assert outcome_rev.source_parser == "mineru"
    assert outcome_rev.comparison is not None
    assert outcome_rev.comparison["pick"] == "mineru"


def test_compare_one_pass_picks_passing_parser() -> None:
    router = ParserRouter()
    # Primary fails, alternate passes -> alternate accepted, primary superseded.
    outcome = router.compare_and_pick(
        _failing_doc(),
        _mineru_passing_doc(),
        "docling",
        "mineru",
    )
    assert outcome.terminal_outcome == "accepted"
    assert outcome.source_parser == "mineru"
    assert outcome.superseded_old_artifacts is True
    assert outcome.comparison is not None
    assert outcome.comparison["pick"] == "mineru"

    # Alternate fails, primary passes -> primary accepted, alternate superseded.
    outcome_primary = router.compare_and_pick(
        _passing_doc(),
        _mineru_failing_doc(),
        "docling",
        "mineru",
    )
    assert outcome_primary.terminal_outcome == "accepted"
    assert outcome_primary.source_parser == "docling"
    assert outcome_primary.superseded_old_artifacts is True


def test_compare_both_fail_routes_to_review() -> None:
    outcome = ParserRouter().compare_and_pick(
        _failing_doc(),
        _mineru_failing_doc(),
        "docling",
        "mineru",
    )
    assert outcome.terminal_outcome == "needs_review"
    assert outcome.routed_to_review is True
    assert outcome.source_parser is None
    assert outcome.comparison is not None
    assert outcome.comparison["pick"] is None


def test_compare_alternate_unavailable_primary_passes() -> None:
    router = ParserRouter()
    calls: list[str] = []
    primary_runner = _flag_runner(calls, "primary", _passing_doc())

    decision, outcome = router.route_and_gate(
        _compare_inputs(), primary_runner, alternate_runner=_boom_runner
    )
    assert decision.route == "compare_complex_tables"
    assert calls == ["primary"]  # alternate crashed, primary still ran
    assert outcome.terminal_outcome == "accepted"
    assert outcome.source_parser == "docling"
    assert outcome.comparison is not None
    assert outcome.comparison["alternate_error"] is not None
    assert outcome.comparison["pick"] == "docling"


def test_compare_alternate_unavailable_primary_fails_routes_to_review() -> None:
    router = ParserRouter()
    calls: list[str] = []
    primary_runner = _flag_runner(calls, "primary", _failing_doc())

    decision, outcome = router.route_and_gate(
        _compare_inputs(), primary_runner, alternate_runner=_boom_runner
    )
    assert decision.route == "compare_complex_tables"
    assert calls == ["primary"]
    assert outcome.terminal_outcome == "needs_review"
    assert outcome.routed_to_review is True
    assert outcome.source_parser is None


def test_compare_not_available_without_runner() -> None:
    router = ParserRouter()
    calls: list[str] = []
    primary_runner = _flag_runner(calls, "primary", _passing_doc())

    decision, outcome = router.route_and_gate(_compare_inputs(), primary_runner)
    assert decision.route == "compare_complex_tables"
    assert calls == []  # fail-fast: no parse before COMPARE_NOT_AVAILABLE
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason is not None
    assert outcome.reason.startswith("COMPARE_NOT_AVAILABLE")


def test_compare_scan_route_ocr_not_ready_blocks_compare(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    problems = ["tesseract executable not found: '/usr/bin/tesseract'"]
    monkeypatch.setattr(parser_router, "check_ocr_readiness", lambda **kwargs: problems)

    router = ParserRouter()
    inputs = _pdf_inputs(has_text_layer=False, layout_complexity=6)  # compare + scan
    calls: list[str] = []
    primary_runner = _flag_runner(calls, "primary", _passing_doc())
    alternate_runner = _flag_runner(calls, "alternate", _mineru_passing_doc())

    decision, outcome = router.route_and_gate(
        inputs, primary_runner, alternate_runner=alternate_runner
    )
    assert decision.route == "compare_complex_tables"
    assert decision.ocr_required is True
    assert outcome.terminal_outcome == "failed"
    assert outcome.reason is not None
    assert outcome.reason.startswith("OCR_NOT_READY")
    assert calls == []  # OCR guard fired before either parser ran


# ────────────────────────────────────────────────────────────────────────────
# parser_routing record (jsonable)
# ────────────────────────────────────────────────────────────────────────────


def test_parser_routing_record_shape_and_jsonable() -> None:
    router = ParserRouter()
    inputs = _pdf_inputs(has_text_layer=False)
    decision = router.decide(inputs)
    outcome = router.execute_and_gate(_passing_doc(), decision.selected_parser, "mineru")
    record = router.record_decision(decision, outcome)

    assert isinstance(json.dumps(record), str)  # jsonable for ingestion_runs

    assert record["schema_version"] == "parser_routing-v1"
    assert record["document_id"] == "nd-168-2024"
    assert record["inputs"]["has_text_layer"] is False
    assert record["inputs"]["file_mime"] == "application/pdf"
    assert record["selected_parser"] == "docling"
    assert record["source_parser"] == "docling"
    assert record["fallback_attempted"] is False
    assert record["fallback_parser"] is None
    assert record["gates"]["group_a"]["provenance_coverage"]["status"] == "passed"
    assert record["gates"]["group_a"]["text_extraction_rate"]["status"] == "passed"
    assert record["gate_verdict"] == "passed"
    assert record["terminal_outcome"] == "accepted"
    assert record["executed"] is True
    assert record["decision_record_enabled"] is True
    assert record["group_a_thresholds"]["min_provenance_coverage"] == 0.9
    assert record["comparison"] is None  # non-compare route carries no comparison

    ocr = record["ocr_config"]
    assert ocr["engine"] == "tesseract"
    assert ocr["lang"] == ["vie"]
    assert ocr["psm"] == 3
    assert ocr["dpi"] == 300
    assert ocr["cuda_visible_devices"] == ""
    assert "tesseract_version" in ocr
    assert "policy" in ocr


def test_parser_routing_record_decision_only_when_no_outcome() -> None:
    router = ParserRouter()
    decision = router.decide(_pdf_inputs())
    record = build_parser_routing_record(inputs=decision.inputs, decision=decision)
    assert record["terminal_outcome"] is None
    assert record["executed"] is False
    assert record["gates"] is None


def test_parser_routing_record_compare_mode_includes_comparison() -> None:
    router = ParserRouter()
    decision, outcome = router.route_and_gate(
        _compare_inputs(),
        lambda: _docling_with_bbox(10),
        alternate_runner=lambda: _mineru_with_bbox(9),
    )
    assert decision.route == "compare_complex_tables"
    record = router.record_decision(decision, outcome)
    assert isinstance(json.dumps(record), str)  # comparison is jsonable
    assert record["comparison"]["mode"] == "compare_complex_tables"
    assert record["comparison"]["pick"] == "docling"
    assert record["comparison"]["primary_group_a"]["provenance_coverage"]["status"] == "passed"
    assert record["comparison"]["alternate_group_a"]["provenance_coverage"]["status"] == "passed"
    assert record["source_parser"] == "docling"  # single parser, no mixing


def test_build_ocr_config_snapshot() -> None:
    snapshot = build_ocr_config_snapshot(tesseract_version="tesseract 5.4.1")
    assert snapshot["tesseract_version"] == "tesseract 5.4.1"
    assert snapshot["engine"] == "tesseract"
    assert snapshot["lang"] == ["vie"]
