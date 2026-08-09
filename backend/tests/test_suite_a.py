"""Unit tests for the Suite A parser-native metrics runner (VNLRAG-20).

Synthetic ParsedDocument fixtures only — docling/mineru are NOT imported at
module level (metrics are pure functions over the canonical IR, so the unit
tests run without either parser installed).
"""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.evaluation.suites.suite_a import (
    IR_SCHEMA_VERSION,
    OCR_LANG,
    TESSDATA_DIR,
    TESSERACT_CMD,
    OcrConfig,
    RunMetadata,
    _cmd_generate_report,
    _discover_variant_runs,
    _make_run_id,
    _ocr_options_kwargs,
    check_ocr_readiness,
    compute_all_metrics,
    create_run_root,
    generate_first_pass_report,
    header_footer_leakage,
    layout_coherence,
    parse_with_docling,
    provenance_coverage,
    run_ocr_dpi_benchmark,
    run_suite,
    table_detection_rate,
    table_preservation,
    text_extraction_rate,
)
from app.ingestion.document_ir import ParsedDocument, ParsedPage


def _element(**overrides: Any) -> dict[str, Any]:
    element: dict[str, Any] = {
        "element_id": "e0",
        "element_type": "paragraph",
        "text": "Nội dung đoạn văn.",
        "page_number": 1,
        "bbox": {"left": 0.1, "top": 0.2, "right": 0.3, "bottom": 0.4},
        "reading_order": 0,
        "parent_element_id": None,
        "table_html": None,
        "source_parser": "DOCLING",
        "parser_version": "docling-2.118.1",
        "parser_confidence": None,
        "raw_reference": {"docling_item_type": "TextItem", "docling_item_index": 0},
    }
    element.update(overrides)
    return element


def _page(page_number: int, elements: list[dict[str, Any]], text: str | None = None) -> ParsedPage:
    page_text = (
        text
        if text is not None
        else ("\n".join(e["text"] for e in elements if e["text"].strip()) or None)
    )
    # v2: element.page_number must equal the page's number (cross-level check).
    for element in elements:
        element["page_number"] = page_number
    return ParsedPage(
        page_number=page_number,
        width=595.0,
        height=842.0,
        text=page_text,
        elements=elements,
    )


def _document(pages: list[ParsedPage]) -> ParsedDocument:
    started_at = datetime.now(UTC)
    return ParsedDocument(
        parsed_document_id="9f1c2e0a-4b3c-4d5e-8f90-1234567890ab",
        document_id="luat-36-2024-qh15",
        parser="DOCLING",
        parser_version="docling-2.118.1",
        ir_schema_version=IR_SCHEMA_VERSION,
        source_object_key="fixtures/luat.pdf",
        pages=pages,
        parse_started_at=started_at,
        parse_completed_at=started_at,  # v2: completed >= started
        quality_report={},
    )


# ────────────────────────────────────────────────────────────────────────────
# Metric 1 — text extraction rate
# ────────────────────────────────────────────────────────────────────────────


def test_text_extraction_rate_all_pages_have_text() -> None:
    doc = _document([_page(1, [_element()]), _page(2, [_element(element_id="e1", page_number=2)])])
    result = text_extraction_rate(doc)
    assert result.status == "computed"
    assert result.value == 1.0
    assert result.numerator == 2
    assert result.denominator == 2


def test_text_extraction_rate_mixed_pages() -> None:
    doc = _document(
        [
            _page(1, [_element()], text="non-empty text"),
            _page(2, [_element(element_id="e1", text="")], text="   "),  # whitespace-only page
            _page(3, [], text=None),  # no extracted text at all
        ]
    )
    result = text_extraction_rate(doc)
    assert result.status == "computed"
    assert result.value == pytest.approx(1 / 3)
    assert result.numerator == 1
    assert result.denominator == 3


# ────────────────────────────────────────────────────────────────────────────
# Metric 2 — provenance coverage
# ────────────────────────────────────────────────────────────────────────────


def test_provenance_coverage_page_number_schema_guaranteed() -> None:
    doc = _document([_page(1, [_element(), _element(element_id="e1", reading_order=1)])])
    result = provenance_coverage(doc)
    assert result.status == "computed"
    # page_number is schema-required in document-ir-v2 §6 -> always present
    assert result.value == 1.0
    assert result.detail["bbox_share"] == 1.0


def test_provenance_coverage_bbox_partial() -> None:
    doc = _document(
        [
            _page(
                1,
                [
                    _element(),
                    _element(element_id="e1", reading_order=1, bbox=None),
                ],
            )
        ]
    )
    result = provenance_coverage(doc)
    assert result.value == 1.0  # page_number present for every element
    assert result.detail["bbox_share"] == 0.5
    assert result.detail["bbox_count"] == 1


# ────────────────────────────────────────────────────────────────────────────
# N/A rule (CRITICAL: never fabricate 0%/100% when annotations are missing)
# ────────────────────────────────────────────────────────────────────────────


def test_table_detection_rate_na_when_no_gold_annotations() -> None:
    doc = _document([_page(1, [_element()])])
    result = table_detection_rate(doc, expected_tables=None)
    assert result.status == "na"
    assert result.value is None  # NOT 0% — availability reason only
    assert result.na_reason


def test_table_detection_rate_na_when_gold_has_zero_tables() -> None:
    doc = _document([_page(1, [_element()])])
    result = table_detection_rate(doc, expected_tables=0)
    assert result.status == "na"
    assert result.value is None
    assert result.na_reason


def test_table_preservation_na_when_no_tables_detected() -> None:
    doc = _document([_page(1, [_element()])])
    result = table_preservation(doc, expected_tables=1)
    assert result.status == "na"
    assert result.value is None
    assert result.na_reason


def test_table_preservation_na_when_gold_has_zero_tables_even_with_parser_tables() -> None:
    """Regression (QA finding): expected_tables=0 must be N/A — never a percentage,
    even when the parser emitted table elements (no-fabricated-percent rule)."""
    doc = _document(
        [
            _page(
                1,
                [
                    _element(
                        element_id="t0",
                        element_type="table",
                        text="",
                        table_html="<table><tr><td>a</td></tr></table>",
                    )
                ],
            )
        ]
    )
    result = table_preservation(doc, expected_tables=0)
    assert result.status == "na"
    assert result.value is None  # NOT 100% — no annotations to preserve against
    assert result.na_reason


def test_table_preservation_computed_positive_path() -> None:
    doc = _document(
        [
            _page(
                1,
                [
                    _element(
                        element_id="t0",
                        element_type="table",
                        text="",
                        table_html="<table><tr><td>a</td></tr></table>",
                    ),
                    _element(
                        element_id="t1",
                        element_type="table",
                        text="",
                        table_html=None,
                        reading_order=1,
                    ),
                ],
            )
        ]
    )
    result = table_preservation(doc, expected_tables=2)
    assert result.status == "computed"
    assert result.value == 0.5  # 1 of 2 detected tables retained table_html
    assert result.numerator == 1
    assert result.denominator == 2


def test_header_footer_leakage_na_without_annotations() -> None:
    doc = _document([_page(1, [_element()])])
    result = header_footer_leakage(doc, gold_has_header_footer_annotations=False)
    assert result.status == "na"
    assert result.value is None
    assert result.na_reason


def test_header_footer_leakage_computed_branch() -> None:
    doc = _document(
        [
            _page(
                1,
                [
                    _element(),  # body paragraph
                    _element(
                        element_id="h0",
                        element_type="page_header",
                        text="Header",
                        reading_order=1,
                    ),
                ],
            )
        ]
    )
    result = header_footer_leakage(doc, gold_has_header_footer_annotations=True)
    assert result.status == "computed"
    assert result.value == 0.5  # 1 of 2 body-stream elements leaked
    assert result.numerator == 1
    assert result.denominator == 2
    assert result.detail["leaked_element_ids"] == ["h0"]


def test_compute_all_metrics_bundle_applies_na_rules() -> None:
    doc = _document([_page(1, [_element()])])
    entry: dict[str, Any] = {"gold_path": None, "document_id": "x"}
    metrics = compute_all_metrics(doc, entry)
    assert metrics["text_extraction_rate"].value == 1.0
    assert metrics["provenance_coverage"].status == "computed"
    assert metrics["table_detection_rate"].status == "na"
    assert metrics["table_preservation"].status == "na"
    assert metrics["header_footer_leakage"].status == "na"
    assert metrics["layout_coherence"].status == "computed"


# ────────────────────────────────────────────────────────────────────────────
# Metric 6 — layout coherence (spatial-progression rule, user finding #7)
# ────────────────────────────────────────────────────────────────────────────


def _spatial_element(
    reading_order: int, top: float, left: float = 0.1, **overrides: Any
) -> dict[str, Any]:
    return _element(
        element_id=f"s{reading_order}",
        reading_order=reading_order,
        bbox={"left": left, "top": top, "right": left + 0.2, "bottom": top + 0.1},
        **overrides,
    )


def test_layout_coherence_in_order_rows_is_1() -> None:
    doc = _document(
        [_page(1, [_spatial_element(0, 0.1), _spatial_element(1, 0.4), _spatial_element(2, 0.7)])]
    )
    result = layout_coherence(doc)
    assert result.status == "computed"
    assert result.value == 1.0
    assert result.detail["per_page_scores"] == {1: 1.0}
    assert result.detail["empty_pages"] == []


def test_layout_coherence_bottom_before_top_scores_zero() -> None:
    # Adapter-contiguous reading_order (0,1,2,3) but spatial path is bottom-up
    # -> every pair is spatially inverted -> 0.0 (the old tautological rule
    # would have reported 1.0).
    doc = _document(
        [
            _page(
                1,
                [
                    _spatial_element(0, 0.9),
                    _spatial_element(1, 0.7),
                    _spatial_element(2, 0.4),
                    _spatial_element(3, 0.2),
                ],
            )
        ]
    )
    result = layout_coherence(doc)
    assert result.value == 0.0
    assert result.detail["per_page_scores"] == {1: 0.0}


def test_layout_coherence_bottom_to_top_pair_scores_zero() -> None:
    # Minimal non-tautology proof: contiguous reading_order 0,1 with the second
    # element physically ABOVE the first -> 0.0, never 1.0.
    doc = _document([_page(1, [_spatial_element(0, 0.8), _spatial_element(1, 0.2)])])
    result = layout_coherence(doc)
    assert result.value == 0.0


def test_layout_coherence_single_element_is_1() -> None:
    doc = _document([_page(1, [_spatial_element(0, 0.2)])])
    result = layout_coherence(doc)
    assert result.value == 1.0
    assert result.detail["per_page_scores"] == {1: 1.0}


def test_layout_coherence_empty_document_vacuously_coherent() -> None:
    doc = _document([_page(1, [])])
    result = layout_coherence(doc)
    assert result.status == "computed"
    assert result.value == 1.0
    assert result.detail["per_page_scores"] == {}
    assert result.detail["empty_pages"] == [1]


def test_layout_coherence_no_bbox_signal_is_none() -> None:
    doc = _document(
        [
            _page(
                1,
                [_element(bbox=None), _element(element_id="e1", reading_order=1, bbox=None)],
            )
        ]
    )
    result = layout_coherence(doc)
    assert result.status == "computed"
    assert result.value is None  # never a fabricated 0.0/1.0 without spatial signal
    assert result.detail["per_page_scores"] == {}


def test_layout_coherence_multi_row_mixed_partial_agreement() -> None:
    # Three rows top/mid/bottom; reading_order swaps the bottom two rows ->
    # one of three pairs disagrees -> 2/3.
    doc = _document(
        [_page(1, [_spatial_element(0, 0.1), _spatial_element(2, 0.4), _spatial_element(1, 0.7)])]
    )
    result = layout_coherence(doc)
    assert result.value == pytest.approx(2 / 3)
    assert result.detail["per_page_scores"] == {1: pytest.approx(2 / 3)}


def test_layout_coherence_within_row_left_to_right_disorder_scores_zero() -> None:
    # Two-column-ish page: same row band, right column read before left — a
    # multi-column layout bug row-band monotonicity alone would NOT catch.
    doc = _document(
        [_page(1, [_spatial_element(0, 0.1, left=0.6), _spatial_element(1, 0.1, left=0.1)])]
    )
    result = layout_coherence(doc)
    assert result.value == 0.0


def test_layout_coherence_identical_boxes_no_spatial_signal_is_1() -> None:
    # All elements share one bbox (fixture artifact): every pair is
    # non-comparable (identical spatial keys) -> trivially coherent.
    doc = _document([_page(1, [_element(), _element(element_id="e1", reading_order=1)])])
    result = layout_coherence(doc)
    assert result.status == "computed"
    assert result.value == 1.0
    assert result.detail["per_page_scores"] == {1: 1.0}


# ────────────────────────────────────────────────────────────────────────────
# Run-metadata immutability shape
# ────────────────────────────────────────────────────────────────────────────


def test_ocr_config_snapshot_records_concrete_policy() -> None:
    """QA finding: OCR policy snapshot must carry concrete PSM/DPI (never null),
    a dpi_policy note, and a runtime-resolved tesseract_version."""
    config = OcrConfig.snapshot()
    assert config.psm == 3
    assert config.dpi == 300
    assert config.dpi_policy.startswith("300 (born-digital)")
    assert config.ocr_status == "SKIPPED_TEXT_LAYER_PRESENT"
    assert config.engine == "tesseract"
    # tesseract_version resolved at run time; null only if executable missing
    assert config.tesseract_version is None or config.tesseract_version.startswith("tesseract")


def test_run_id_unique() -> None:
    assert _make_run_id() != _make_run_id()


def test_create_run_root_rejects_existing_run_id(tmp_path: Path) -> None:
    run_id = _make_run_id()
    create_run_root(tmp_path, run_id)
    with pytest.raises(FileExistsError):
        create_run_root(tmp_path, run_id)


def test_run_metadata_status_transition_one_way() -> None:
    metadata = RunMetadata(
        run_id="run-x",
        git_commit="abc",
        created_at="t0",
        parser="docling",
        parser_versions={},
        config={},
    )
    completed = metadata.transition_to("COMPLETED", completed_at="t1")
    assert completed.status == "COMPLETED"
    assert completed.completed_at == "t1"
    with pytest.raises(ValueError):
        completed.transition_to("FAILED")  # COMPLETED is terminal
    with pytest.raises(ValueError):
        completed.transition_to("RUNNING")  # no backward transition
    with pytest.raises(ValueError):
        metadata.transition_to("RUNNING")  # no self-transition either


def test_run_metadata_json_shape() -> None:
    metadata = RunMetadata(
        run_id="run-x",
        git_commit="abc",
        created_at="t0",
        parser="docling",
        parser_versions={"docling": "2.118.1"},
        config={"ocr": {}},
    )
    dumped = metadata.model_dump(mode="json")
    assert dumped["status"] == "RUNNING"
    assert dumped["ir_schema_version"] == IR_SCHEMA_VERSION
    assert dumped["suite"] == "suite-a"
    assert dumped["p3_parser_router"].startswith("OPERATIONAL")


# ────────────────────────────────────────────────────────────────────────────
# Blocker 1 — OCR readiness check (AC 8)
# ────────────────────────────────────────────────────────────────────────────


def test_check_ocr_readiness_detects_missing_vie(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    problems = check_ocr_readiness(str(tmp_path))
    assert any("vie.traineddata" in problem for problem in problems)


def test_check_ocr_readiness_real_environment_ready() -> None:
    tessdata = Path("/tmp/opencode/tessdata")
    tesseract_present = shutil.which("tesseract") is not None or Path(TESSERACT_CMD).exists()
    if not (tessdata.is_dir() and tesseract_present):
        pytest.skip("tesseract + real tessdata dir unavailable in this environment")
    assert check_ocr_readiness(str(tessdata)) == []


# ────────────────────────────────────────────────────────────────────────────
# Blocker 5 — artifact-level test: run_suite with injected stub parser
# ────────────────────────────────────────────────────────────────────────────


def _stub_parse(pdf_path: Path, document_id: str, converter: Any) -> ParsedDocument:
    """Parser stub: no docling import/model load; returns a minimal IR doc."""
    del converter
    return ParsedDocument(
        parsed_document_id="stub-00000000-0000-0000-0000-000000000000",
        document_id=document_id,
        parser="DOCLING",
        parser_version="stub-0.0.0",
        ir_schema_version=IR_SCHEMA_VERSION,
        source_object_key=str(pdf_path),
        pages=[
            ParsedPage(
                page_number=1,
                width=10.0,
                height=10.0,
                text="hello",
                elements=[],
            )
        ],
        parse_started_at=datetime.now(UTC),
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )


def test_run_suite_require_ocr_fails_fast(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Blocker 1 wiring: OCR-required (scan route) + not ready -> run aborts FAILED
    with the readiness problems recorded, before any parsing."""
    fixtures = tmp_path / "documents"
    (fixtures / "luat").mkdir(parents=True)
    (fixtures / "luat" / "luat-fixture.pdf").write_bytes(b"x")
    out = tmp_path / "out"
    monkeypatch.setattr(
        "app.evaluation.suites.suite_a.check_ocr_readiness",
        lambda _tessdata_dir: ["simulated OCR problem"],
    )
    rc = run_suite(fixtures, out, "docling", parse_docling=_stub_parse, require_ocr=True)
    assert rc == 1
    run_dirs = list(out.iterdir())
    assert len(run_dirs) == 1
    run_json = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "FAILED"
    assert run_json["error"] is not None
    assert "simulated OCR problem" in run_json["error"]
    assert run_json["config"]["ocr_readiness"]["hard_fail"] is True


def test_run_suite_artifact_includes_full_ocr_snapshot(tmp_path: Path) -> None:
    """Oracle blocker 5: run.json must carry the complete OCR policy snapshot
    (tesseract_version str-or-null, psm==3, dpi==300, dpi_policy)."""
    fixtures = tmp_path / "documents"
    (fixtures / "luat").mkdir(parents=True)
    (fixtures / "luat" / "luat-fixture.pdf").write_bytes(b"not a real pdf - stub parse")
    out = tmp_path / "out"
    rc = run_suite(fixtures, out, "docling", parse_docling=_stub_parse)
    assert rc == 0
    run_dirs = list(out.iterdir())
    assert len(run_dirs) == 1
    run_json = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "COMPLETED"
    ocr = run_json["config"]["ocr"]
    assert ocr["psm"] == 3
    assert ocr["dpi"] == 300
    assert ocr["dpi_policy"].startswith("300 (born-digital)")
    assert ocr["ocr_status"] == "SKIPPED_TEXT_LAYER_PRESENT"
    assert ocr["tesseract_version"] is None or ocr["tesseract_version"].startswith("tesseract")
    readiness = run_json["config"]["ocr_readiness"]
    assert readiness["checked"] is True
    assert readiness["ocr_required"] is False  # born-digital: never hard-fails
    assert isinstance(readiness["problems"], list)


# ────────────────────────────────────────────────────────────────────────────
# Finding 1 — PSM traceability (OCR options construction)
# ────────────────────────────────────────────────────────────────────────────


def test_ocr_options_kwargs_include_psm3() -> None:
    """Finding 1: the OCR options applied for scan-route OCR must pass psm=3
    explicitly (docling's TesseractCliOcrOptions default is psm=None)."""
    kwargs = _ocr_options_kwargs()
    assert kwargs["psm"] == 3
    assert kwargs["tesseract_cmd"] == TESSERACT_CMD
    assert kwargs["path"] == TESSDATA_DIR
    assert kwargs["lang"] == list(OCR_LANG)


def test_tesseract_cli_ocr_options_supports_psm_field() -> None:
    """Finding 1: confirm the installed docling exposes `psm` on
    TesseractCliOcrOptions and that psm=3 round-trips through construction."""
    pytest.importorskip("docling")
    from docling.datamodel.pipeline_options import TesseractCliOcrOptions

    assert "psm" in TesseractCliOcrOptions.model_fields
    options = TesseractCliOcrOptions(**_ocr_options_kwargs())
    assert options.psm == 3


# ────────────────────────────────────────────────────────────────────────────
# Finding 2(a) — no code path may leave run.json at RUNNING
# ────────────────────────────────────────────────────────────────────────────


def test_run_suite_empty_fixtures_dir_marks_failed(tmp_path: Path) -> None:
    """Finding 2(a): empty fixtures dir (build_input_manifest raises) must still
    produce a run dir whose run.json is FAILED, never RUNNING."""
    fixtures = tmp_path / "documents"
    fixtures.mkdir(parents=True)  # exists but contains no PDFs
    out = tmp_path / "out"
    rc = run_suite(fixtures, out, "docling", parse_docling=_stub_parse)
    assert rc == 1
    run_dirs = list(out.iterdir())
    assert len(run_dirs) == 1
    run_json = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "FAILED"
    assert run_json["completed_at"] is not None
    assert run_json["error"] is not None
    assert "no PDF fixtures found" in run_json["error"]


def test_run_suite_missing_fixtures_dir_marks_failed(tmp_path: Path) -> None:
    """Finding 2(a): missing fixtures dir must produce FAILED (run dir exists),
    not an unrecorded exception and not a RUNNING-stuck run.json."""
    fixtures = tmp_path / "does-not-exist"
    out = tmp_path / "out"
    rc = run_suite(fixtures, out, "docling", parse_docling=_stub_parse)
    assert rc == 1
    run_dirs = list(out.iterdir())
    assert len(run_dirs) == 1
    run_json = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "FAILED"
    assert "fixtures dir not found" in run_json["error"]


# ────────────────────────────────────────────────────────────────────────────
# ora-21 — benchmark run must also guarantee terminal status
# ────────────────────────────────────────────────────────────────────────────


def test_bench_ocr_dpi_failure_marks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ora-21: a failure anywhere in the OCR benchmark body must mark run.json
    FAILED (never RUNNING), with the error recorded — mirroring run_suite.

    Failure is forced deterministically by monkeypatching the converter factory
    to raise; no real OCR, rendering, or tesseract is executed.
    """

    def _boom() -> Any:
        raise RuntimeError("simulated converter failure")

    monkeypatch.setattr("app.evaluation.suites.suite_a._make_ocr_image_converter", _boom)
    # Deterministic regardless of environment: readiness passes and pdftoppm
    # appears available so the failure comes from the converter factory.
    monkeypatch.setattr("app.evaluation.suites.suite_a.check_ocr_readiness", lambda _d: [])
    monkeypatch.setattr(
        "app.evaluation.suites.suite_a.shutil.which", lambda name: f"/usr/bin/{name}"
    )

    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"dummy scan pdf")
    out = tmp_path / "out"
    rc = run_ocr_dpi_benchmark(pdf, pages=6, out_dir=out)
    assert rc == 1
    run_dirs = list(out.iterdir())
    assert len(run_dirs) == 1
    run_json = json.loads((run_dirs[0] / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "FAILED"  # never RUNNING
    assert run_json["completed_at"] is not None
    assert run_json["error"] is not None
    assert "simulated converter failure" in run_json["error"]
    # ora-22: parser versions are recorded at run start, so even a FAILED
    # benchmark run is reproducible.
    assert run_json["ir_schema_version"] == IR_SCHEMA_VERSION
    assert set(run_json["parser_versions"]) >= {"docling", "mineru", "tesseract"}


# ────────────────────────────────────────────────────────────────────────────
# Oracle blocker 1 — suite_a docling→IR mapping must persist raw bbox points
# ────────────────────────────────────────────────────────────────────────────


def test_parse_with_docling_persists_raw_bbox_points() -> None:
    """Oracle blocker 1: the suite_a docling→IR mapping (parse_with_docling)
    must persist the raw PDF-point box under raw_reference["bbox_points"]
    alongside the normalized NORMALIZED_PAGE canonical bbox — mirroring the
    production docling_adapter so parser-native coordinates are never lost in
    the P1 benchmark artifacts."""
    pytest.importorskip("docling")
    from docling.datamodel.base_models import ConversionStatus
    from docling.datamodel.document import DoclingDocument
    from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
    from docling_core.types.doc.common.reference import ProvenanceItem
    from docling_core.types.doc.document import DocItemLabel

    doc = DoclingDocument(name="suite-a-bbox-provenance")
    doc.add_page(page_no=1, size=Size(width=595.28, height=841.89))
    prov = ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(l=50.0, t=700.0, r=550.0, b=800.0, coord_origin=CoordOrigin.TOPLEFT),
        charspan=(0, 5),
    )
    doc.add_text(label=DocItemLabel.TEXT, text="abcde", prov=prov)

    class _FakeResult:
        status = ConversionStatus.SUCCESS
        document = doc

    class _FakeConverter:
        def convert(self, pdf_path: str) -> _FakeResult:
            del pdf_path  # converter stub ignores the path
            return _FakeResult()

    parsed = parse_with_docling(
        Path("/tmp/nonexistent-suite-a.pdf"), "fixture-doc", _FakeConverter()
    )

    # The text item carries both the normalized canonical bbox and the raw
    # PDF-point box.
    text_element = parsed.pages[0].elements[-1]
    assert text_element.bbox is not None
    assert text_element.bbox.coordinate_space == "NORMALIZED_PAGE"
    assert 0.0 <= text_element.bbox.left <= 1.0
    assert 0.0 <= text_element.bbox.top <= 1.0
    assert 0.0 <= text_element.bbox.right <= 1.0
    assert 0.0 <= text_element.bbox.bottom <= 1.0
    points = text_element.raw_reference["bbox_points"]
    assert len(points) == 4
    assert all(isinstance(value, (int, float)) for value in points)
    assert points == [50.0, 700.0, 550.0, 800.0]
    # The parser-native keys are preserved alongside bbox_points.
    assert text_element.raw_reference["docling_item_type"] == "TextItem"
    assert text_element.raw_reference["prov_page_no"] == 1


# ────────────────────────────────────────────────────────────────────────────
# P3 (parser router, VNLRAG-131) wiring — route_and_gate with stubbed runners
# ────────────────────────────────────────────────────────────────────────────


def _routed_document(
    document_id: str, parser: str = "DOCLING", *, elements: list[dict[str, Any]] | None = None
) -> ParsedDocument:
    """Valid v2 ParsedDocument for the router stubs (never touches docling/mineru)."""
    started_at = datetime.now(UTC)
    els = elements if elements is not None else [_element()]
    return ParsedDocument(
        parsed_document_id="stub-00000000-0000-0000-0000-000000000000",
        document_id=document_id,
        parser=parser,
        parser_version="docling-2.118.1" if parser == "DOCLING" else "mineru-3.4.4",
        ir_schema_version=IR_SCHEMA_VERSION,
        source_object_key=f"fixtures/{document_id}.pdf",
        pages=[_page(1, els)],
        parse_started_at=started_at,
        parse_completed_at=started_at,  # v2: completed >= started
        quality_report={},
    )


def _stub_docling_pass(pdf_path: Path, document_id: str, converter: Any) -> ParsedDocument:
    """Docling stub passing Group A (bbox'd element, non-empty text)."""
    del pdf_path, converter
    return _routed_document(document_id, "DOCLING")


def _stub_docling_fail(pdf_path: Path, document_id: str, converter: Any) -> ParsedDocument:
    """Docling stub failing Group A (no bbox -> provenance 0.0 < 0.9)."""
    del pdf_path, converter
    return _routed_document(document_id, "DOCLING", elements=[_element(bbox=None)])


def _stub_mineru_pass(pdf_path: Path, document_id: str) -> ParsedDocument:
    """MinerU stub passing Group A (genuine MINERU provenance)."""
    del pdf_path
    return _routed_document(document_id, "MINERU", elements=[_element(source_parser="MINERU")])


def _stub_mineru_fail(pdf_path: Path, document_id: str) -> ParsedDocument:
    """MinerU stub failing Group A (no bbox -> provenance 0.0 < 0.9)."""
    del pdf_path
    return _routed_document(
        document_id, "MINERU", elements=[_element(source_parser="MINERU", bbox=None)]
    )


def _p3_fixtures(tmp_path: Path) -> Path:
    """Three born-digital fixture PDFs (one per document type, as in the real corpus)."""
    fixtures = tmp_path / "documents"
    for folder, name in (
        ("luat", "luat-fixture.pdf"),
        ("nd", "nd-fixture.pdf"),
        ("tt", "tt-fixture.pdf"),
    ):
        (fixtures / folder).mkdir(parents=True)
        (fixtures / folder / name).write_bytes(b"stub born-digital pdf bytes")
    return fixtures


def test_run_suite_p3_writes_routing_records(tmp_path: Path) -> None:
    """P3 (VNLRAG-131) wiring: run_suite p3 routes each fixture through
    ParserRouter.decide + route_and_gate with stubbed lazy runners and writes
    the per-document parser_routing records (selected parser + gate verdicts)."""
    fixtures = _p3_fixtures(tmp_path)
    out = tmp_path / "out"
    rc = run_suite(
        fixtures,
        out,
        "p3",
        parse_docling=_stub_docling_pass,
        parse_mineru=_stub_mineru_pass,
    )
    assert rc == 0
    run_dirs = list(out.iterdir())
    assert len(run_dirs) == 1
    run_root = run_dirs[0]
    run_json = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "COMPLETED"
    assert run_json["parser"] == "p3-parser-router"
    assert run_json["p3_parser_router"].startswith("OPERATIONAL")

    phase = run_root / "p3-parser-router"
    routing = json.loads((phase / "routing-and-gates.json").read_text(encoding="utf-8"))
    assert routing["parser"] == "p3-parser-router"
    assert routing["router"] == "ParserRouter (VNLRAG-131)"
    records = routing["per_document"]
    # No gold files in the test fixtures -> document_id falls back to the PDF stem.
    assert set(records) == {"luat-fixture", "nd-fixture", "tt-fixture"}
    for _document_id, record in records.items():
        # Routing: born-digital -> docling_text, Docling selected, accepted.
        assert record["schema_version"] == "parser_routing-v1"
        assert record["decision"]["route"] == "docling_text"
        assert record["inputs"]["has_text_layer"] is True
        assert record["selected_parser"] == "docling"
        assert record["source_parser"] == "docling"
        assert record["fallback_attempted"] is False
        assert record["gate_verdict"] == "passed"
        assert record["terminal_outcome"] == "accepted"
        assert record["executed"] is True
        assert record["gates"]["group_a"]["provenance_coverage"]["status"] == "passed"
        assert record["gates"]["group_a"]["text_extraction_rate"]["status"] == "passed"
    aggregate = routing["aggregate"]
    assert aggregate["documents"] == 3
    assert aggregate["accepted"] == 3
    assert aggregate["selected_parsers"] == {"docling": 3}
    assert aggregate["gate_verdicts"] == {"passed": 3}
    assert aggregate["terminal_outcomes"] == {"accepted": 3}
    assert aggregate["fallback_attempted_documents"] == 0

    # Metrics computed on the accepted (Docling) doc.
    metrics = json.loads((phase / "metrics.json").read_text(encoding="utf-8"))
    assert set(metrics["per_document"]) == set(records)
    for doc_metrics in metrics["per_document"].values():
        assert doc_metrics["text_extraction_rate"]["status"] == "computed"
        assert doc_metrics["text_extraction_rate"]["value"] == 1.0
        assert doc_metrics["provenance_coverage"]["status"] == "computed"

    # IR artifacts are recorded for every accepted doc.
    manifest = json.loads((phase / "artifacts-manifest.json").read_text(encoding="utf-8"))
    assert set(manifest["per_document"]) == set(records)
    results = json.loads((phase / "results.json").read_text(encoding="utf-8"))
    assert results["aggregate"]["accepted"] == 3


def test_run_suite_p3_primary_gate_fail_falls_back_to_mineru(tmp_path: Path) -> None:
    """P3 wiring: a Docling parse failing Group A triggers the REAL alternate
    runner path — MinerU supersedes (single source_parser) and the routing
    record captures fallback_attempted with the alternate's gate verdict."""
    fixtures = _p3_fixtures(tmp_path)
    out = tmp_path / "out"
    rc = run_suite(
        fixtures,
        out,
        "p3",
        parse_docling=_stub_docling_fail,
        parse_mineru=_stub_mineru_pass,
    )
    assert rc == 0
    run_root = next(iter(out.iterdir()))
    run_json = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "COMPLETED"

    routing = json.loads(
        (run_root / "p3-parser-router" / "routing-and-gates.json").read_text(encoding="utf-8")
    )
    records = routing["per_document"]
    assert len(records) == 3
    for _document_id, record in records.items():
        # Primary (Docling) failed Group A -> MinerU ran as the alternate and
        # superseded; every artifact is attributed to a single parser.
        assert record["selected_parser"] == "docling"
        assert record["gate_verdict"] == "failed"  # primary Group A verdict
        assert record["fallback_attempted"] is True
        assert record["fallback_parser"] == "mineru"
        assert record["source_parser"] == "mineru"
        assert record["terminal_outcome"] == "accepted"
        assert record["gates"]["group_a"]["provenance_coverage"]["status"] == "failed"
    assert routing["aggregate"]["fallback_attempted_documents"] == 3
    assert routing["aggregate"]["source_parsers"] == {"mineru": 3}

    # The alternate parser's Group A evidence is recorded on the run results.
    results = json.loads(
        (run_root / "p3-parser-router" / "results.json").read_text(encoding="utf-8")
    )
    for _document_id, entry in results["per_document"].items():
        assert entry["fallback_attempted"] is True
        assert entry["fallback_parser"] == "mineru"
        assert entry["source_parser"] == "mineru"
        assert entry["fallback_group_a"]["provenance_coverage"]["status"] == "passed"

    # Metrics are computed on the ACCEPTED (MinerU) doc — provenance 1.0.
    metrics = json.loads(
        (run_root / "p3-parser-router" / "metrics.json").read_text(encoding="utf-8")
    )
    for doc_metrics in metrics["per_document"].values():
        assert doc_metrics["provenance_coverage"]["status"] == "computed"
        assert doc_metrics["provenance_coverage"]["value"] == 1.0
        assert doc_metrics["text_extraction_rate"]["value"] == 1.0


def test_run_suite_p3_no_accepted_doc_still_completes(tmp_path: Path) -> None:
    """ora-5 #1 regression: when NO parser output is accepted (primary and
    alternate BOTH fail Group A), the P3 run still COMPLETES — routing records
    carry the needs_review outcome per doc, metrics are N/A (never fabricated),
    no IR artifact is written, and the aggregate never hits a KeyError."""
    fixtures = _p3_fixtures(tmp_path)
    out = tmp_path / "out"
    rc = run_suite(
        fixtures,
        out,
        "p3",
        parse_docling=_stub_docling_fail,
        parse_mineru=_stub_mineru_fail,
    )
    assert rc == 0
    run_root = next(iter(out.iterdir()))
    run_json = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    assert run_json["status"] == "COMPLETED"  # not FAILED by the aggregate KeyError

    routing = json.loads(
        (run_root / "p3-parser-router" / "routing-and-gates.json").read_text(encoding="utf-8")
    )
    records = routing["per_document"]
    assert len(records) == 3  # every doc's routing outcome is recorded, none dropped
    for _document_id, record in records.items():
        assert record["source_parser"] is None
        assert record["terminal_outcome"] == "needs_review"
        assert record["routed_to_review"] is True
        assert record["fallback_attempted"] is True
        assert record["gate_verdict"] == "failed"  # primary's Group A verdict
    aggregate = routing["aggregate"]
    assert aggregate["accepted"] == 0
    assert aggregate["terminal_outcomes"] == {"needs_review": 3}
    assert aggregate["fallback_attempted_documents"] == 3
    assert aggregate["pages"] == 0
    assert aggregate["elements"] == 0
    assert aggregate["element_type_histogram"] == {}

    # Metrics are N/A with the availability reason — never fabricated values.
    metrics = json.loads(
        (run_root / "p3-parser-router" / "metrics.json").read_text(encoding="utf-8")
    )
    assert set(metrics["per_document"]) == set(records)
    for doc_metrics in metrics["per_document"].values():
        for metric in doc_metrics.values():
            assert metric["status"] == "na"
            assert metric["value"] is None
            assert "no accepted parser output" in metric["na_reason"]

    # No accepted doc -> no IR artifact is written for any document.
    manifest = json.loads(
        (run_root / "p3-parser-router" / "artifacts-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["per_document"] == {}

    # results.json per-doc entries carry the routing outcome + fallback evidence.
    results = json.loads(
        (run_root / "p3-parser-router" / "results.json").read_text(encoding="utf-8")
    )
    for _document_id, entry in results["per_document"].items():
        assert "ir_summary" not in entry
        assert entry["source_parser"] is None
        assert entry["terminal_outcome"] == "needs_review"
        assert entry["fallback_group_a"]["provenance_coverage"]["status"] == "failed"


# ────────────────────────────────────────────────────────────────────────────
# ora-5 #2 — reproducible committed report (`suite_a report` subcommand)
# ────────────────────────────────────────────────────────────────────────────

_DOC_IDS = ("luat-36-2024-qh15", "nd-168-2024", "tt-24-2024-tt-bgtvt")


def _fake_metric(name: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Minimal computed metric dict consumed by the report generator cells."""
    return {
        "name": name,
        "status": "computed",
        "value": 1.0,
        "numerator": 1,
        "denominator": 1,
        "na_reason": None,
        "detail": detail or {},
    }


def _write_synthetic_run(
    base: Path, run_id: str, parser_label: str, doc_ids: tuple[str, ...] | None = None
) -> None:
    """Write a COMPLETED run dir with minimal artifacts for report generation.

    ``doc_ids`` varies the input-manifest content (hence its sha256) so tests
    can build multiple trios with DIFFERENT manifest hashes.
    """
    doc_ids = doc_ids or _DOC_IDS
    run_root = base / run_id
    run_root.mkdir(parents=True)
    phase = {
        "docling": "p1-docling",
        "mineru": "p2-mineru",
        "p3-parser-router": "p3-parser-router",
    }[parser_label]
    (run_root / phase).mkdir()
    (run_root / "input-manifest.json").write_text(
        json.dumps({"fixtures_dir": str(base), "entries": [{"document_id": d} for d in doc_ids]}),
        encoding="utf-8",
    )
    (run_root / "run.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "COMPLETED",
                "parser": parser_label,
                "git_commit": "abc123",
                "ir_schema_version": "document-ir-v2",
                "parser_versions": {"docling": "2.118.1", "mineru": "3.4.4"},
                "p3_parser_router": "OPERATIONAL (VNLRAG-131)",
                "created_at": "2026-08-09T00:00:00+00:00",
                "completed_at": "2026-08-09T00:01:00+00:00",
                "config": {
                    "ocr": {
                        "engine": "tesseract",
                        "tesseract_version": "tesseract 5.5.3",
                        "lang": ["vie"],
                        "tessdata_dir": "/tmp/opencode/tessdata",
                        "tesseract_cmd": "/usr/bin/tesseract",
                        "psm": 3,
                        "scale": 3.0,
                        "dpi": 300,
                        "dpi_policy": "300 (born-digital)",
                        "ocr_status": "SKIPPED_TEXT_LAYER_PRESENT",
                    },
                    "ocr_readiness": {"checked": True, "problems": []},
                },
            }
        ),
        encoding="utf-8",
    )
    per_doc_metrics = {
        doc: {
            name: _fake_metric(name, {"bbox_share": 1.0, "bbox_count": 1, "element_count": 1})
            for name in (
                "text_extraction_rate",
                "provenance_coverage",
                "table_detection_rate",
                "table_preservation",
                "header_footer_leakage",
                "layout_coherence",
            )
        }
        for doc in _DOC_IDS
    }
    per_doc_results = {
        doc: {"pages": 1, "elements": 3, "element_type_histogram": {"paragraph": 3}}
        for doc in _DOC_IDS
    }
    (run_root / phase / "metrics.json").write_text(
        json.dumps({"per_document": per_doc_metrics, "aggregate": {}}), encoding="utf-8"
    )
    (run_root / phase / "results.json").write_text(
        json.dumps(
            {
                "per_document": per_doc_results,
                "aggregate": {
                    "documents": 3,
                    "pages": 3,
                    "elements": 9,
                    "element_type_histogram": {"paragraph": 9},
                },
            }
        ),
        encoding="utf-8",
    )
    (run_root / phase / "artifacts-manifest.json").write_text(
        json.dumps({"per_document": {}}), encoding="utf-8"
    )
    if parser_label == "p3-parser-router":
        routing = {
            "per_document": {
                doc: {
                    "schema_version": "parser_routing-v1",
                    "decision": {"route": "docling_text"},
                    "selected_parser": "docling",
                    "source_parser": "docling",
                    "fallback_attempted": False,
                    "gate_verdict": "passed",
                    "terminal_outcome": "accepted",
                }
                for doc in _DOC_IDS
            },
            "aggregate": {
                "documents": 3,
                "accepted": 3,
                "routes": {"docling_text": 3},
                "selected_parsers": {"docling": 3},
                "source_parsers": {"docling": 3},
                "gate_verdicts": {"passed": 3},
                "terminal_outcomes": {"accepted": 3},
                "fallback_attempted_documents": 0,
                "pages": 3,
                "elements": 9,
                "element_type_histogram": {"paragraph": 9},
            },
        }
        (run_root / phase / "routing-and-gates.json").write_text(
            json.dumps(routing), encoding="utf-8"
        )
    else:
        (run_root / phase / "routing-and-gates.json").write_text(
            json.dumps({"per_document": {}}), encoding="utf-8"
        )


def test_generate_first_pass_report_from_artifacts(tmp_path: Path) -> None:
    """ora-5 #2: `suite_a report` discovers the p1/p2/p3 run trio sharing one
    input-manifest hash and generates the committed report from the run
    artifacts (run_ids + numbered sections), never from hand-edited numbers."""
    base = tmp_path / "runs"
    _write_synthetic_run(base, "run-20260809-000000-aaaaaa", "docling")
    _write_synthetic_run(base, "run-20260809-000001-bbbbbb", "mineru")
    _write_synthetic_run(base, "run-20260809-000002-cccccc", "p3-parser-router")

    runs = _discover_variant_runs(base)
    assert set(runs) == {"p1", "p2", "p3"}
    assert runs["p1"].name == "run-20260809-000000-aaaaaa"
    assert runs["p2"].name == "run-20260809-000001-bbbbbb"
    assert runs["p3"].name == "run-20260809-000002-cccccc"

    text = generate_first_pass_report(runs)
    assert "## 1. P1 (Docling) — run run-20260809-000000-aaaaaa" in text
    assert "## 2. P2 (MinerU) — run run-20260809-000001-bbbbbb" in text
    assert "## 3. P3 (Parser Router) — run run-20260809-000002-cccccc" in text
    assert "## 4. OCR configuration snapshot" in text
    assert "## 5. 300-vs-600 DPI OCR benchmark" in text
    assert "## 6. Immutable artifact paths + hashes" in text
    assert "## 7. Routing recommendation" in text
    assert "## 8. M1 status" in text
    assert "## 9. Immutability contract note" in text
    assert "tesseract 5.5.3" in text
    assert "docling_text" in text
    assert "parser_routing-v1" in text

    # The CLI command writes the committed report file.
    out = tmp_path / "suite-a-first-pass-report.md"
    rc = _cmd_generate_report(base, out)
    assert rc == 0
    assert out.is_file()
    regenerated = out.read_text(encoding="utf-8")
    assert "## 1. P1 (Docling) — run run-20260809-000000-aaaaaa" in regenerated


def test_discover_variant_runs_requires_full_trio(tmp_path: Path) -> None:
    """Discovery refuses an incomplete trio (missing variant)."""
    base = tmp_path / "runs"
    _write_synthetic_run(base, "run-20260809-000000-aaaaaa", "docling")
    _write_synthetic_run(base, "run-20260809-000001-bbbbbb", "mineru")
    with pytest.raises(ValueError, match="no COMPLETED p1/p2/p3 run trio"):
        _discover_variant_runs(base)


def test_discover_variant_runs_prefers_newest_trio(tmp_path: Path) -> None:
    """ora-6 #A: with TWO complete trios (different manifest hashes, different
    timestamps), discovery returns the NEWER trio — not the first complete one
    found in an oldest-first walk."""
    base = tmp_path / "runs"
    # Older trio (hash differs from the newer trio's manifest content).
    old_docs: tuple[str, ...] = ("old-a", "old-b", "old-c")
    _write_synthetic_run(base, "run-20260809-000000-aaaaaa", "docling", doc_ids=old_docs)
    _write_synthetic_run(base, "run-20260809-000001-bbbbbb", "mineru", doc_ids=old_docs)
    _write_synthetic_run(base, "run-20260809-000002-cccccc", "p3-parser-router", doc_ids=old_docs)
    # Newer trio (later timestamps, DIFFERENT manifest content -> different hash).
    new_docs: tuple[str, ...] = ("new-a", "new-b", "new-c")
    _write_synthetic_run(base, "run-20260809-000003-dddddd", "docling", doc_ids=new_docs)
    _write_synthetic_run(base, "run-20260809-000004-eeeeee", "mineru", doc_ids=new_docs)
    _write_synthetic_run(base, "run-20260809-000005-ffffff", "p3-parser-router", doc_ids=new_docs)

    runs = _discover_variant_runs(base)
    assert set(runs) == {"p1", "p2", "p3"}
    assert runs["p1"].name == "run-20260809-000003-dddddd"
    assert runs["p2"].name == "run-20260809-000004-eeeeee"
    assert runs["p3"].name == "run-20260809-000005-ffffff"


def test_report_uses_recorded_git_commit_not_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ora-6 #B: report generation reads run.json.git_commit from the artifact,
    so regenerating after a later checkout commit does NOT change the report —
    even when the live checkout reports a different HEAD."""
    base = tmp_path / "runs"
    _write_synthetic_run(base, "run-20260809-000000-aaaaaa", "docling")  # git_commit "abc123"
    _write_synthetic_run(base, "run-20260809-000001-bbbbbb", "mineru")
    _write_synthetic_run(base, "run-20260809-000002-cccccc", "p3-parser-router")
    monkeypatch.setattr("app.evaluation.suites.suite_a._git_commit", lambda: "fake-checkout-HEAD")

    runs = _discover_variant_runs(base)
    text = generate_first_pass_report(runs)
    # The artifact's recorded commit wins over the checkout's.
    assert "`abc123`" in text
    assert "fake-checkout-HEAD" not in text

    # The CLI path behaves identically.
    out = tmp_path / "suite-a-first-pass-report.md"
    rc = _cmd_generate_report(base, out)
    assert rc == 0
    regenerated = out.read_text(encoding="utf-8")
    assert "`abc123`" in regenerated
    assert "fake-checkout-HEAD" not in regenerated
