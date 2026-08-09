"""Tests for the production Docling -> canonical Document IR adapter (VNLRAG-129).

Integration tests run the real docling converter on the born-digital parser
benchmark fixtures; unit tests exercise the mapping on synthetic
DoclingDocuments (no converter/model load). Docling runs CPU-only
(``CUDA_VISIBLE_DEVICES=""``), matching the suite_a bench convention.
"""

import os

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # CPU-only docling (suite_a convention)

import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from app.ingestion.adapters.docling_adapter import (
    DEFAULT_OCR_CMD,
    DEFAULT_TESSDATA_DIR,
    DOCLING_LABEL_TO_IR_TYPE,
    DoclingAdapter,
    _build_pipeline_options,
    _item_bbox,
    check_ocr_readiness,
    docling_document_to_ir,
    map_label_to_ir_type,
)
from app.ingestion.document_ir import DocumentElement, ParsedDocument

FIXTURES_DIR = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "parser_benchmark" / "documents"
)
FIXTURE_FILES: dict[str, Path] = {
    "luat": FIXTURES_DIR / "luat" / "luat-traffic-2024-fixture.pdf",
    "nd": FIXTURES_DIR / "nd" / "nd-168-2024-fixture.pdf",
    "tt": FIXTURES_DIR / "tt" / "tt-traffic-2024-fixture.pdf",
}
ELEMENT_ID_PATTERN = re.compile(r"^p\d+-e\d+$")


# ────────────────────────────────────────────────────────────────────────────
# Fixtures & helpers
# ────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def parsed_fixtures() -> dict[str, ParsedDocument]:
    """Parse all three born-digital fixtures once per test session.

    Each ``parse`` builds its own docling converter (model load), so the
    session scope keeps the integration cost to a single run of three parses.
    """
    adapter = DoclingAdapter()
    parsed: dict[str, ParsedDocument] = {}
    for name, path in FIXTURE_FILES.items():
        parsed[name] = adapter.parse(
            pdf_path=str(path),
            source_object_key=f"documents/{name}/source/{path.name}",
            parsed_document_id=str(uuid.uuid4()),
            document_id=f"{name}-document",
        )
    return parsed


def _elements(doc: ParsedDocument) -> list[DocumentElement]:
    return [element for page in doc.pages for element in page.elements]


def _synthetic_doc(*, table_label: str = "table") -> Any:
    """Minimal synthetic DoclingDocument: one page, one table (+ optional caption).

    Built with docling's own API so no converter/model load is involved; used
    to exercise the table_html HTML export and the DOCUMENT_INDEX mapping.
    """
    from docling.datamodel.document import DoclingDocument
    from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
    from docling_core.types.doc.common.reference import ProvenanceItem
    from docling_core.types.doc.document import DocItemLabel
    from docling_core.types.doc.items.table.table_data import TableCell, TableData

    def _cell(text: str, row: int, col: int) -> TableCell:
        return TableCell(
            text=text,
            row_span=1,
            col_span=1,
            start_row_offset_idx=row,
            end_row_offset_idx=row + 1,
            start_col_offset_idx=col,
            end_col_offset_idx=col + 1,
        )

    data = TableData(
        num_rows=2,
        num_cols=2,
        table_cells=[
            _cell("a", 0, 0),
            _cell("b", 0, 1),
            _cell("c", 1, 0),
            _cell("d", 1, 1),
        ],
    )
    doc = DoclingDocument(name="synthetic-table")
    doc.add_page(page_no=1, size=Size(width=595.28, height=841.89))
    prov = ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(l=50.0, t=700.0, r=550.0, b=800.0, coord_origin=CoordOrigin.TOPLEFT),
        charspan=(0, 0),
    )
    doc.add_table(data=data, prov=prov, label=DocItemLabel(table_label))
    return doc


# ────────────────────────────────────────────────────────────────────────────
# Label -> element_type mapping (VNLRAG-21 spike gap #2)
# ────────────────────────────────────────────────────────────────────────────


def test_label_mapping_table_contents() -> None:
    assert DOCLING_LABEL_TO_IR_TYPE == {
        "section_header": "heading",
        "title": "title",
        "picture": "figure",
        "caption": "caption",
        "footnote": "footnote",
        "page_header": "page_header",
        "page_footer": "page_footer",
        "document_index": "table",
    }


def test_label_mapping_pass_through_verbatim() -> None:
    """text/list_item/table pass through verbatim — no lossy text->paragraph."""
    for label in ("text", "list_item", "table"):
        assert map_label_to_ir_type(label) == label


def test_label_mapping_documented_labels() -> None:
    assert map_label_to_ir_type("section_header") == "heading"
    assert map_label_to_ir_type("title") == "title"
    assert map_label_to_ir_type("picture") == "figure"
    assert map_label_to_ir_type("caption") == "caption"
    assert map_label_to_ir_type("footnote") == "footnote"
    assert map_label_to_ir_type("page_header") == "page_header"
    assert map_label_to_ir_type("page_footer") == "page_footer"


def test_label_mapping_document_index_only_for_table_items() -> None:
    assert map_label_to_ir_type("document_index", is_table_item=True) == "table"
    assert map_label_to_ir_type("document_index", is_table_item=False) == "document_index"


def test_unknown_label_passes_through() -> None:
    assert map_label_to_ir_type("list") == "list"
    assert map_label_to_ir_type("unspecified") == "unspecified"


# ────────────────────────────────────────────────────────────────────────────
# Full-parse contract on the nd fixture (multi-page, born-digital)
# ────────────────────────────────────────────────────────────────────────────


def test_nd_full_parse_contract(parsed_fixtures: dict[str, ParsedDocument]) -> None:
    doc = parsed_fixtures["nd"]
    assert doc.parser == "DOCLING"
    assert doc.parser_version == "docling-2.118.1"
    assert doc.ir_schema_version == "document-ir-v2"
    assert doc.source_object_key.startswith("documents/nd/")
    assert doc.quality_report == {}
    assert doc.parse_started_at < doc.parse_completed_at

    assert [page.page_number for page in doc.pages] == [1, 2]  # 1-based, no 0
    elements = _elements(doc)
    assert elements, "fixture must yield at least one element"
    for element in elements:
        assert ELEMENT_ID_PATTERN.fullmatch(element.element_id)
        assert element.source_parser == "DOCLING"
        assert element.parser_version == "docling-2.118.1"
        assert "docling_self_ref" in element.raw_reference
        assert element.raw_reference["docling_self_ref"].startswith("#/")
        assert element.page_number in (1, 2)

    orders = [element.reading_order for element in elements]
    assert orders == list(range(len(elements)))  # contiguous, 0-based


def test_source_object_key_is_injected_not_local_path(
    parsed_fixtures: dict[str, ParsedDocument],
) -> None:
    """Gap #8: the IR records the injected MinIO object key, never str(pdf_path)."""
    doc = parsed_fixtures["nd"]
    assert doc.source_object_key == "documents/nd/source/nd-168-2024-fixture.pdf"
    assert "fixtures/parser_benchmark" not in doc.source_object_key


def test_round_trip_json_equality(parsed_fixtures: dict[str, ParsedDocument]) -> None:
    """model_dump_json -> model_validate_json reproduces an equal document."""
    for doc in parsed_fixtures.values():
        assert doc.model_validate_json(doc.model_dump_json()) == doc


# ────────────────────────────────────────────────────────────────────────────
# bbox normalization (VNLRAG-21 spike gap #1 + v2 NORMALIZED_PAGE)
# ────────────────────────────────────────────────────────────────────────────


def test_bbox_normalized_to_top_left_and_unit_interval(
    parsed_fixtures: dict[str, ParsedDocument],
) -> None:
    """v2 empirical check: EVERY bbox is NORMALIZED_PAGE (0..1, TOPLEFT origin),
    so ``top < bottom`` and ``0 <= left/right/top/bottom <= 1``; the raw
    PDF-point box is preserved under ``raw_reference["bbox_points"]``."""
    checked = 0
    for doc in parsed_fixtures.values():
        for element in _elements(doc):
            if element.bbox is None:
                continue
            checked += 1
            box = element.bbox
            assert box.coordinate_space == "NORMALIZED_PAGE"
            assert 0.0 <= box.left <= 1.0, (
                f"{doc.document_id} {element.element_id}: left={box.left} not in [0, 1]"
            )
            assert 0.0 <= box.right <= 1.0
            assert 0.0 <= box.top <= 1.0
            assert 0.0 <= box.bottom <= 1.0
            assert box.top < box.bottom, (
                f"{doc.document_id} {element.element_id}: top={box.top} !< bottom={box.bottom}"
            )
            assert box.left < box.right
            assert box.page_height is not None
            assert box.page_width is not None
            # v2: raw PDF-point coordinates preserved for provenance. The raw
            # y-axis may be BOTTOMLEFT (born-digital text layer); applying
            # to_top_left_origin (page_height - y) back-projects the normalized
            # box to the raw values, so either raw or its flip must match.
            raw_l, raw_t, raw_r, raw_b = element.raw_reference["bbox_points"]
            assert raw_l == pytest.approx(box.left * box.page_width, rel=1e-3)
            assert raw_r == pytest.approx(box.right * box.page_width, rel=1e-3)
            assert box.top * box.page_height in (
                pytest.approx(raw_t),
                pytest.approx(box.page_height - raw_t),
            )
            assert box.bottom * box.page_height in (
                pytest.approx(raw_b),
                pytest.approx(box.page_height - raw_b),
            )
    assert checked > 0, "fixtures must carry bbox provenance"


# ────────────────────────────────────────────────────────────────────────────
# parent_element_id (VNLRAG-21 spike gap #4)
# ────────────────────────────────────────────────────────────────────────────


def test_parent_element_id_populated(parsed_fixtures: dict[str, ParsedDocument]) -> None:
    """luat is list-heavy: list items must point at their 'list' container."""
    doc = parsed_fixtures["luat"]
    elements = _elements(doc)
    by_id = {element.element_id: element for element in elements}
    non_null = [element for element in elements if element.parent_element_id is not None]
    assert non_null, "luat hierarchy must yield at least one non-null parent"
    # Referential integrity: every parent resolves to an existing element.
    for element in non_null:
        assert element.parent_element_id in by_id
    # List items sit under a 'list' container element (ListGroup).
    list_items = [element for element in elements if element.element_type == "list_item"]
    assert list_items, "luat is list-heavy by fixture design"
    for element in list_items:
        assert element.parent_element_id is not None
        assert by_id[element.parent_element_id].element_type == "list"


# ────────────────────────────────────────────────────────────────────────────
# table_html (VNLRAG-21 spike gap #5) — synthetic table, no converter
# ────────────────────────────────────────────────────────────────────────────


def test_table_html_uses_html_export() -> None:
    doc = _synthetic_doc(table_label="table")
    parsed = docling_document_to_ir(
        doc=doc,
        source_object_key="documents/synthetic/source/t.pdf",
        parsed_document_id=str(uuid.uuid4()),
        document_id="synthetic-table",
        parse_started_at=datetime.now(UTC),
    )
    table = [el for el in _elements(parsed) if el.element_type == "table"]
    assert len(table) == 1
    assert table[0].table_html is not None
    assert table[0].table_html.startswith("<table>")
    assert "<td>a</td>" in table[0].table_html


def test_table_html_for_document_index_label() -> None:
    """A DOCUMENT_INDEX-labelled TableItem maps to element_type 'table' with HTML."""
    doc = _synthetic_doc(table_label="document_index")
    parsed = docling_document_to_ir(
        doc=doc,
        source_object_key="documents/synthetic/source/t.pdf",
        parsed_document_id=str(uuid.uuid4()),
        document_id="synthetic-toc-table",
        parse_started_at=datetime.now(UTC),
    )
    table = [el for el in _elements(parsed) if el.element_type == "table"]
    assert len(table) == 1
    assert table[0].table_html is not None
    assert table[0].table_html.startswith("<table>")


def test_table_export_failure_raises_with_item_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-parse policy: a detected table whose HTML export fails aborts the parse."""
    from docling_core.types.doc.items.table.table import TableItem

    def _explode(self: Any, doc: Any = None, **kwargs: Any) -> str:
        raise ValueError("synthetic table export failure")

    monkeypatch.setattr(TableItem, "export_to_html", _explode)
    with pytest.raises(RuntimeError, match=r"#/tables/0"):
        docling_document_to_ir(
            doc=_synthetic_doc(table_label="table"),
            source_object_key="documents/synthetic/source/t.pdf",
            parsed_document_id=str(uuid.uuid4()),
            document_id="synthetic-table",
            parse_started_at=datetime.now(UTC),
        )


def test_non_table_elements_have_null_table_html(
    parsed_fixtures: dict[str, ParsedDocument],
) -> None:
    for doc in parsed_fixtures.values():
        for element in _elements(doc):
            if element.element_type != "table":
                assert element.table_html is None


# ────────────────────────────────────────────────────────────────────────────
# OCR route (VNLRAG-21 spike gap #7)
# ────────────────────────────────────────────────────────────────────────────


def test_ocr_readiness_check_returns_list() -> None:
    problems = check_ocr_readiness()
    assert isinstance(problems, list)
    assert all(isinstance(problem, str) for problem in problems)


def test_ocr_readiness_reports_missing_configured_absolute_cmd() -> None:
    """The EXACT configured tesseract_cmd is validated, not a PATH fallback."""
    problems = check_ocr_readiness(tesseract_cmd="/definitely/not/a/tesseract")
    assert any("executable not found" in problem for problem in problems)


def test_ocr_readiness_reports_missing_bare_name_cmd() -> None:
    problems = check_ocr_readiness(tesseract_cmd="definitely-not-a-real-tesseract-binary-xyz")
    assert any("executable not found" in problem for problem in problems)


def test_ocr_readiness_resolves_valid_custom_cmd() -> None:
    resolved = shutil.which("tesseract")
    if resolved is None:
        pytest.skip("tesseract not installed in this environment")
    assert resolved is not None
    problems = check_ocr_readiness(tesseract_cmd=resolved)
    assert not any("executable not found" in problem for problem in problems)


def test_ocr_readiness_parses_first_token_of_arg_cmd() -> None:
    """A tesseract_cmd carrying args (\"<bin> -l vie --psm 3\") still resolves."""
    resolved = shutil.which("tesseract")
    if resolved is None:
        pytest.skip("tesseract not installed in this environment")
    assert resolved is not None
    problems = check_ocr_readiness(tesseract_cmd=f"{resolved} -l vie --psm 3")
    assert not any("executable not found" in problem for problem in problems)


def test_pipeline_options_wire_dpi_to_images_scale() -> None:
    """dpi takes effect: docling 2.118.1 rasterizes at 72 * images_scale DPI."""
    options = _build_pipeline_options(
        ocr_enabled=False,
        dpi=300,
        tesseract_cmd=DEFAULT_OCR_CMD,
        tessdata_dir=DEFAULT_TESSDATA_DIR,
        lang=["vie"],
    )
    assert options.images_scale == pytest.approx(300 / 72.0)
    assert options.do_table_structure is True
    assert options.do_ocr is False

    ocr_options = _build_pipeline_options(
        ocr_enabled=True,
        dpi=300,
        tesseract_cmd=DEFAULT_OCR_CMD,
        tessdata_dir=DEFAULT_TESSDATA_DIR,
        lang=["vie"],
    )
    assert ocr_options.images_scale == pytest.approx(300 / 72.0)
    assert ocr_options.do_ocr is True
    assert ocr_options.ocr_options.psm == 3
    assert ocr_options.ocr_options.lang == ["vie"]


def test_ocr_fail_fast_raises_before_convert(monkeypatch: pytest.MonkeyPatch) -> None:
    """ocr_enabled=True must fail fast on readiness problems (no converter run)."""

    def _not_ready(*args: Any, **kwargs: Any) -> list[str]:
        return ["tesseract executable not found (PATH or /usr/bin/tesseract)"]

    monkeypatch.setattr("app.ingestion.adapters.docling_adapter.check_ocr_readiness", _not_ready)
    with pytest.raises(RuntimeError, match="docling OCR not ready"):
        DoclingAdapter().parse(
            pdf_path=str(FIXTURE_FILES["nd"]),
            source_object_key="documents/nd/source/x.pdf",
            parsed_document_id=str(uuid.uuid4()),
            document_id="nd-document",
            ocr_enabled=True,
        )


@pytest.mark.skipif(
    bool(check_ocr_readiness()),
    reason="tesseract not ready in this environment (scan-route OCR needs vie traineddata)",
)
def test_ocr_enabled_runs_tesseract_route() -> None:
    """Scan route end-to-end when tesseract is available (skipped otherwise)."""
    doc = DoclingAdapter().parse(
        pdf_path=str(FIXTURE_FILES["nd"]),
        source_object_key="documents/nd/source/ocr.pdf",
        parsed_document_id=str(uuid.uuid4()),
        document_id="nd-document",
        ocr_enabled=True,
    )
    assert doc.parser == "DOCLING"
    assert _elements(doc)


# ────────────────────────────────────────────────────────────────────────────
# ConversionStatus PARTIAL_SUCCESS / FAILURE (finding #4)
# ────────────────────────────────────────────────────────────────────────────


class _FakeConversionResult:
    """Minimal docling convert() result (status/document/errors) for adapter tests."""

    def __init__(self, document: Any, status: Any, errors: list[Any]) -> None:
        self.document = document
        self.status = status
        self.errors = errors


class _FakeConverter:
    """Stand-in for ``docling.document_converter.DocumentConverter``."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def convert(self, source: Any, **kwargs: Any) -> _FakeConversionResult:
        return self._result

    def with_result(self, result: _FakeConversionResult) -> "_FakeConverter":
        self._result = result
        return self


def test_docling_partial_success_yields_doc_with_conversion_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Finding #4: PARTIAL_SUCCESS must yield a ParsedDocument (not raise) with
    the conversion status + errors recorded on quality_report so the router can
    force the gate to failed instead of silently accepting partial output."""
    from docling.datamodel.base_models import ConversionStatus

    result = _FakeConversionResult(
        document=_synthetic_doc(),
        status=ConversionStatus.PARTIAL_SUCCESS,
        errors=["page 2 conversion timed out", "OCR backend failure on page 3"],
    )
    converter = _FakeConverter().with_result(result)
    monkeypatch.setattr("docling.document_converter.DocumentConverter", lambda **_: converter)

    parsed = DoclingAdapter().parse(
        pdf_path=str(FIXTURE_FILES["nd"]),
        source_object_key="documents/nd/source/partial.pdf",
        parsed_document_id=str(uuid.uuid4()),
        document_id="nd-document",
    )
    # Usable-but-incomplete output is normalized, not discarded.
    assert parsed.pages
    assert parsed.quality_report["conversion_status"] == "PARTIAL_SUCCESS"
    assert parsed.quality_report["conversion_errors"] == [
        "page 2 conversion timed out",
        "OCR backend failure on page 3",
    ]


def test_docling_conversion_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """FAILURE keeps the hard-fail contract: the parse raises (no partial IR)."""
    from docling.datamodel.base_models import ConversionStatus

    result = _FakeConversionResult(
        document=_synthetic_doc(),
        status=ConversionStatus.FAILURE,
        errors=["backend crashed before any output"],
    )
    converter = _FakeConverter().with_result(result)
    monkeypatch.setattr("docling.document_converter.DocumentConverter", lambda **_: converter)

    with pytest.raises(RuntimeError, match="docling conversion failed"):
        DoclingAdapter().parse(
            pdf_path=str(FIXTURE_FILES["nd"]),
            source_object_key="documents/nd/source/failure.pdf",
            parsed_document_id=str(uuid.uuid4()),
            document_id="nd-document",
        )


# ────────────────────────────────────────────────────────────────────────────
# Stability (spike §5 rec 8) + integration
# ────────────────────────────────────────────────────────────────────────────


def test_element_id_stable_across_parses() -> None:
    """Same PDF + same docling version -> identical element_id sequences."""
    adapter = DoclingAdapter()
    first = adapter.parse(
        pdf_path=str(FIXTURE_FILES["nd"]),
        source_object_key="documents/nd/source/stable.pdf",
        parsed_document_id=str(uuid.uuid4()),
        document_id="nd-document",
    )
    second = adapter.parse(
        pdf_path=str(FIXTURE_FILES["nd"]),
        source_object_key="documents/nd/source/stable.pdf",
        parsed_document_id=str(uuid.uuid4()),
        document_id="nd-document",
    )
    first_ids = [element.element_id for element in _elements(first)]
    second_ids = [element.element_id for element in _elements(second)]
    assert first_ids == second_ids
    assert first_ids, "fixture must yield elements"


def test_all_fixtures_validate_as_parsed_document(
    parsed_fixtures: dict[str, ParsedDocument],
) -> None:
    """Integration: all three fixtures re-validate (extra=forbid) as ParsedDocument."""
    for doc in parsed_fixtures.values():
        restored = ParsedDocument.model_validate(doc.model_dump())
        assert restored == doc
        assert all(element.source_parser == "DOCLING" for element in _elements(doc))
        # every element belongs to a page carrying its page_number
        for page in doc.pages:
            assert all(element.page_number == page.page_number for element in page.elements)


# ────────────────────────────────────────────────────────────────────────────
# MISSING_PAGE_DIMS (oracle blocker 2) — raw coords must never become the
# canonical bbox
# ────────────────────────────────────────────────────────────────────────────


class _FakeSize:
    def __init__(self, width: float, height: float) -> None:
        self.width = width
        self.height = height


class _FakePageModel:
    def __init__(self, width: float, height: float) -> None:
        self.size = _FakeSize(width, height)


class _FakeDoc:
    def __init__(self, pages: dict[int, Any]) -> None:
        self.pages = pages


class _FakeProv:
    def __init__(self, bbox: Any) -> None:
        self.bbox = bbox


class _FakeItem:
    def __init__(self, prov: list[Any]) -> None:
        self.prov = prov


def _raw_pdf_point_box() -> Any:
    """Real docling BoundingBox with PDF-point coords ALL outside [0, 1] (the
    case that previously raised ValidationError when emitted as the canonical
    bbox)."""
    from docling_core.types.doc.base import BoundingBox, CoordOrigin

    return BoundingBox(l=50.0, t=700.0, r=550.0, b=800.0, coord_origin=CoordOrigin.TOPLEFT)


@pytest.mark.parametrize(
    "doc",
    [
        _FakeDoc({}),  # page absent from doc.pages -> dims missing
        _FakeDoc({1: _FakePageModel(0.0, 0.0)}),  # zero dims
        _FakeDoc({1: _FakePageModel(-5.0, -5.0)}),  # negative dims
        _FakeDoc({1: _FakePageModel(595.0, 0.0)}),  # height zero
        _FakeDoc({1: _FakePageModel(0.0, 842.0)}),  # width zero
    ],
)
def test_bbox_invalid_page_dims_yields_null_bbox(doc: _FakeDoc) -> None:
    """Oracle blocker 2: with missing/zero/negative page dims, _item_bbox must
    NOT emit the raw PDF-point box as the canonical bbox (it is outside [0,1]
    and would raise ValidationError). The element keeps a null bbox; the raw
    points + MISSING_PAGE_DIMS flag are returned for raw_reference."""
    item = _FakeItem([_FakeProv(_raw_pdf_point_box())])
    bbox, raw_points, normalization_flag = _item_bbox(item, doc, 1)
    assert bbox is None  # raw coords never enter the canonical bbox
    assert raw_points == [50.0, 700.0, 550.0, 800.0]
    assert normalization_flag == "MISSING_PAGE_DIMS"


def test_document_to_ir_invalid_page_dims_keeps_null_bbox_and_flags() -> None:
    """Oracle blocker 2 end-to-end: a synthetic doc with zero/negative page
    dimensions parses WITHOUT ValidationError; the text element keeps a null
    bbox while raw_reference preserves bbox_points + the MISSING_PAGE_DIMS
    flag."""
    for width, height in ((0.0, 0.0), (-5.0, -5.0), (595.0, 0.0)):
        doc = _synthetic_doc_with_page_size(width=width, height=height)
        parsed = docling_document_to_ir(
            doc=doc,
            source_object_key="documents/synthetic/source/x.pdf",
            parsed_document_id=str(uuid.uuid4()),
            document_id="dims-doc",
            parse_started_at=datetime.now(UTC),
        )
        text_element = next(
            element for element in _elements(parsed) if "bbox_points" in element.raw_reference
        )
        assert text_element.bbox is None
        assert text_element.raw_reference["bbox_points"] == [50.0, 700.0, 550.0, 800.0]
        assert text_element.raw_reference["bbox_normalization"] == "MISSING_PAGE_DIMS"


def _synthetic_doc_with_page_size(*, width: float, height: float) -> Any:
    """Minimal synthetic DoclingDocument: one page (custom size) + one text item."""
    from docling.datamodel.document import DoclingDocument
    from docling_core.types.doc.base import BoundingBox, CoordOrigin, Size
    from docling_core.types.doc.common.reference import ProvenanceItem
    from docling_core.types.doc.document import DocItemLabel

    doc = DoclingDocument(name="dims-test")
    doc.add_page(page_no=1, size=Size(width=width, height=height))
    prov = ProvenanceItem(
        page_no=1,
        bbox=BoundingBox(l=50.0, t=700.0, r=550.0, b=800.0, coord_origin=CoordOrigin.TOPLEFT),
        charspan=(0, 5),
    )
    doc.add_text(label=DocItemLabel.TEXT, text="abcde", prov=prov)
    return doc
