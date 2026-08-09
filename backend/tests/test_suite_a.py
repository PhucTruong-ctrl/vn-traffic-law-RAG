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
    _make_run_id,
    _ocr_options_kwargs,
    check_ocr_readiness,
    compute_all_metrics,
    create_run_root,
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
# Metric 6 — layout coherence (deterministic rule)
# ────────────────────────────────────────────────────────────────────────────


def test_layout_coherence_contiguous_reading_order() -> None:
    doc = _document(
        [
            _page(1, [_element(), _element(element_id="e1", reading_order=1)]),
            _page(2, [_element(element_id="e2", page_number=2, reading_order=2)]),
        ]
    )
    result = layout_coherence(doc)
    assert result.status == "computed"
    assert result.value == 1.0
    assert result.detail["reading_order_contiguous"] is True
    assert result.detail["empty_pages"] == []


def test_layout_coherence_gap_in_reading_order_fails() -> None:
    doc = _document(
        [
            _page(
                1,
                [
                    _element(reading_order=0),
                    _element(element_id="e1", reading_order=2),  # gap: order 1 missing
                ],
            )
        ]
    )
    result = layout_coherence(doc)
    assert result.value == 0.0
    assert result.detail["reading_order_contiguous"] is False


def test_layout_coherence_empty_page_fails() -> None:
    doc = _document([_page(1, [_element()]), _page(2, [])])
    result = layout_coherence(doc)
    assert result.value == 0.0
    assert result.detail["empty_pages"] == [2]


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
    assert dumped["p3_parser_router"].startswith("PENDING")


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
