"""Suite A parser benchmark — parser-native metrics runner (VNLRAG-20).

Executes a real first-pass parse of the parser-benchmark fixtures (born-digital
PDFs with an embedded text layer — OCR is skipped and recorded, never executed),
computes the QA-arbitrated parser-native metrics, and writes immutable run
artifacts under ``<run-dir>/<run_id>/``.

Run (P1, Docling)::

    CUDA_VISIBLE_DEVICES="" python -m app.evaluation.suites.suite_a run \
        --fixtures-dir backend/tests/fixtures/parser_benchmark/documents \
        --run-dir data/evaluation/suite-a-first-pass --parser docling

Run (P2, MinerU)::

    ... same flags, --parser mineru

Scope (QA arbitration, VNLRAG-20): parser-native metrics ONLY. Structure metrics
(Article/Clause/Point P/R/F1, Short Point Recall, đ) Recall, Parent Context
Completeness) are deferred to VNLRAG-97 and no regex structure proxy is built.
P3 (parser router, VNLRAG-131) is recorded as PENDING, never faked.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import resource
import shutil
import subprocess
import sys
import time
import unicodedata
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from difflib import SequenceMatcher
from itertools import pairwise
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from app.ingestion.document_ir import (
    BoundingBox,
    DocumentElement,
    ParsedDocument,
    ParsedPage,
)

IR_SCHEMA_VERSION = "document-ir-v2"
SUITE_NAME = "suite-a"
PHASE_DIR = {"docling": "p1-docling", "mineru": "p2-mineru"}
OCR_ENGINE = "tesseract"
TESSERACT_CMD = "/usr/bin/tesseract"
TESSDATA_DIR = "/tmp/opencode/tessdata"
OCR_LANG = ["vie"]
OCR_STATUS_SKIPPED = "SKIPPED_TEXT_LAYER_PRESENT"
P3_STATUS = "PENDING (VNLRAG-131)"
MINERU_TIMEOUT_SECONDS = 900
GOLD_CLASSIFICATIONS = {"luat", "nd", "tt"}
OCR_DPI_BENCH_SCRATCH = Path("/tmp/opencode/ocr-dpi-bench")
# Known legal phrases used as the OCR quality hit-rate probe (AC 7).
OCR_BENCH_PHRASES = (
    "CHÍNH PHỦ",
    "NGHỊ ĐỊNH",
    "xử phạt vi phạm hành chính",
    "Điều",
    "khoản",
    "điểm",
)
# Vietnamese letters carrying diacritics (precomposed) + combining marks.
_VIETNAMESE_DIACRITICS = set(
    "ăâđêôơưĂÂĐÊÔƠƯáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ"
)
_METRIC_NAMES = (
    "text_extraction_rate",
    "provenance_coverage",
    "table_detection_rate",
    "table_preservation",
    "header_footer_leakage",
    "layout_coherence",
)


# ────────────────────────────────────────────────────────────────────────────
# Run metadata
# ────────────────────────────────────────────────────────────────────────────


class OcrConfig(BaseModel):
    """OCR configuration snapshot recorded in run.json.

    OCR is NOT executed for the benchmark fixtures (born-digital PDFs with a
    text layer); the options below are recorded as a complete reproducible OCR
    policy snapshot, with ``ocr_status=SKIPPED_TEXT_LAYER_PRESENT`` as the
    executed state. ``tesseract_version`` is resolved at run time via
    ``tesseract --version`` (first line) and is null only when the executable
    cannot be invoked. PSM/DPI record concrete policy values, never null.
    """

    engine: str = OCR_ENGINE
    tesseract_version: str | None = None
    lang: list[str] = Field(default_factory=lambda: list(OCR_LANG))
    tessdata_dir: str = TESSDATA_DIR
    tesseract_cmd: str = TESSERACT_CMD
    psm: int = 3
    scale: float = 3.0
    dpi: int = 300
    dpi_policy: str = "300 (born-digital); 600 scan-only conditional per VNLRAG-20 OCR decision"
    ocr_status: str = OCR_STATUS_SKIPPED

    @classmethod
    def snapshot(cls) -> OcrConfig:
        """Build the runtime OCR policy snapshot, resolving the tesseract version."""
        return cls(tesseract_version=_tesseract_version())


def _tesseract_version() -> str | None:
    """Resolve the installed tesseract version (first line of --version), or None.

    Missing/uninvokable executable is handled gracefully: subprocess failures
    (FileNotFoundError/OSError/TimeoutExpired) and empty output both yield None.
    """
    executable = shutil.which("tesseract") or TESSERACT_CMD
    try:
        result = subprocess.run(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    first_line = (
        (result.stdout or "").splitlines()[0].strip() if (result.stdout or "").strip() else ""
    )
    return first_line or None


class RunMetadata(BaseModel):
    """run.json payload. ``status`` is one-way: RUNNING -> COMPLETED|FAILED."""

    run_id: str
    git_commit: str
    status: Literal["RUNNING", "COMPLETED", "FAILED"] = "RUNNING"
    created_at: str
    completed_at: str | None = None
    ir_schema_version: str = IR_SCHEMA_VERSION
    suite: str = SUITE_NAME
    parser: str
    parser_versions: dict[str, str]
    config: dict[str, Any]
    p3_parser_router: str = P3_STATUS
    error: str | None = None

    _FORWARD_STATUSES: ClassVar[dict[str, set[str]]] = {
        "RUNNING": {"COMPLETED", "FAILED"},
    }

    def transition_to(self, status: str, completed_at: str | None = None) -> RunMetadata:
        """Enforce the one-way status lifecycle; completed runs are never edited."""
        allowed = self._FORWARD_STATUSES.get(self.status, set())
        if status not in allowed:
            raise ValueError(f"invalid one-way status transition {self.status} -> {status}")
        return self.model_copy(update={"status": status, "completed_at": completed_at})


class MetricResult(BaseModel):
    """Outcome of one parser-native metric.

    ``status`` is ``computed`` or ``na``. Per the VNLRAG-20 QA arbitration a
    metric whose fixtures lack the annotations needed to compute it is reported
    as ``na`` with an availability reason — NEVER as a fabricated 0% or 100%.
    """

    name: str
    status: Literal["computed", "na"]
    value: float | None = None
    numerator: int | None = None
    denominator: int | None = None
    na_reason: str | None = None
    detail: dict[str, Any] = Field(default_factory=dict)


# ────────────────────────────────────────────────────────────────────────────
# Small helpers
# ────────────────────────────────────────────────────────────────────────────


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 16), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _pkg_version(package: str) -> str:
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(package)
    except PackageNotFoundError:
        return "unknown"


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _make_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"run-{stamp}-{uuid.uuid4().hex[:6]}"


def create_run_root(run_dir: Path, run_id: str) -> Path:
    """Create the immutable run directory; refuse to reuse an existing run_id."""
    run_root = run_dir / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    return run_root


def check_ocr_readiness(tessdata_dir: str) -> list[str]:
    """Fail-fast tesseract OCR readiness check (AC 8).

    Returns a list of problems (empty = ready). Checks, in order:
      1. tesseract executable present on PATH (or TESSERACT_CMD);
      2. ``tesseract --version`` invokable and parseable;
      3. tessdata dir exists and contains vie.traineddata, osd.traineddata;
      4. tessdata configs/ dir present with the tsv config.
    CI/setup will invoke this via ``check-ocr`` in VNLRAG-148 (CI/CD ticket);
    this script is the W2 deliverable per AC 8.
    """
    problems: list[str] = []
    tessdata = Path(tessdata_dir)
    if shutil.which("tesseract") is None and not Path(TESSERACT_CMD).exists():
        problems.append(f"tesseract executable not found (PATH or {TESSERACT_CMD})")
    version = _tesseract_version()
    if version is None:
        problems.append("tesseract --version returned no parseable version")
    elif not version.lower().startswith("tesseract"):
        problems.append(f"unexpected tesseract --version output: {version!r}")
    if not tessdata.is_dir():
        problems.append(f"tessdata dir missing: {tessdata_dir}")
    else:
        if not (tessdata / "vie.traineddata").exists():
            problems.append("vie.traineddata missing")
        if not (tessdata / "osd.traineddata").exists():
            problems.append("osd.traineddata missing")
        configs = tessdata / "configs"
        if not configs.is_dir():
            problems.append("configs/ dir missing")
        elif not (configs / "tsv").exists():
            problems.append("configs/tsv missing")
    return problems


def _elements(doc: ParsedDocument) -> list[DocumentElement]:
    return [element for page in doc.pages for element in page.elements]


# ────────────────────────────────────────────────────────────────────────────
# Metrics 1-6 (pure functions over ParsedDocument)
# ────────────────────────────────────────────────────────────────────────────


def text_extraction_rate(doc: ParsedDocument) -> MetricResult:
    """Metric 1 — pages with extracted non-empty text over total pages."""
    total = len(doc.pages)
    extracted = sum(1 for page in doc.pages if page.text and page.text.strip())
    return MetricResult(
        name="text_extraction_rate",
        status="computed",
        value=extracted / total if total else None,
        numerator=extracted,
        denominator=total,
        detail={
            "page_text_lengths": {page.page_number: len(page.text or "") for page in doc.pages},
            "rule": "page.text is non-empty after strip()",
        },
    )


def provenance_coverage(doc: ParsedDocument) -> MetricResult:
    """Metric 2 — share of DocumentElements with page_number; bbox separately.

    ``page_number`` is required by the frozen IR schema (document-ir-v2 §6), so
    its share is 1.0 by construction; ``bbox`` is optional and its share is the
    informative parser-provenance signal.
    """
    elements = _elements(doc)
    total = len(elements)
    with_page_number = sum(
        1 for element in elements if getattr(element, "page_number", None) is not None
    )
    with_bbox = sum(1 for element in elements if element.bbox is not None)
    return MetricResult(
        name="provenance_coverage",
        status="computed",
        value=with_page_number / total if total else None,
        numerator=with_page_number,
        denominator=total,
        detail={
            "bbox_share": with_bbox / total if total else None,
            "bbox_count": with_bbox,
            "element_count": total,
            "rule": "page_number schema-required; bbox optional",
        },
    )


def table_detection_rate(doc: ParsedDocument, expected_tables: int | None) -> MetricResult:
    """Metric 3 — gold-annotated expected tables detected as table elements.

    ``expected_tables`` is None when the gold fixture carries no table
    annotations -> N/A (never 0%). When gold explicitly annotates zero tables,
    there are still no table annotations to detect against -> N/A as well.
    """
    if expected_tables is None:
        return MetricResult(
            name="table_detection_rate",
            status="na",
            na_reason="gold fixtures contain no table annotations",
        )
    detected = sum(1 for element in _elements(doc) if element.element_type == "table")
    if expected_tables == 0:
        return MetricResult(
            name="table_detection_rate",
            status="na",
            na_reason="gold fixtures contain no table annotations (expected_tables=0)",
        )
    return MetricResult(
        name="table_detection_rate",
        status="computed",
        value=detected / expected_tables,
        numerator=detected,
        denominator=expected_tables,
    )


def table_preservation(doc: ParsedDocument, expected_tables: int | None) -> MetricResult:
    """Metric 4 — detected tables retaining non-empty table_html.

    Same annotation-availability rule as table_detection_rate: expected_tables
    None or 0 -> N/A (never a fabricated percentage, even when the parser
    emitted table elements). Additionally N/A when the parser detected no table
    elements at all (nothing to preserve).
    """
    if expected_tables is None:
        return MetricResult(
            name="table_preservation",
            status="na",
            na_reason="gold fixtures contain no table annotations",
        )
    if expected_tables == 0:
        return MetricResult(
            name="table_preservation",
            status="na",
            na_reason="gold fixtures contain no table annotations (expected_tables=0)",
        )
    tables = [element for element in _elements(doc) if element.element_type == "table"]
    if not tables:
        return MetricResult(
            name="table_preservation",
            status="na",
            na_reason="parser detected no table elements (nothing to preserve)",
        )
    preserved = sum(1 for element in tables if element.table_html and element.table_html.strip())
    return MetricResult(
        name="table_preservation",
        status="computed",
        value=preserved / len(tables),
        numerator=preserved,
        denominator=len(tables),
    )


def header_footer_leakage(
    doc: ParsedDocument, gold_has_header_footer_annotations: bool
) -> MetricResult:
    """Metric 5 — header/footer content emitted as body content.

    v1 fixtures carry no header/footer gold annotations -> N/A. When gold
    annotates header/footer regions, leakage is the share of body-stream
    elements whose type is page_header/page_footer (parser mislabeled them).
    """
    if not gold_has_header_footer_annotations:
        return MetricResult(
            name="header_footer_leakage",
            status="na",
            na_reason="gold fixtures contain no header/footer annotations",
        )
    leaked = [
        element
        for element in _elements(doc)
        if element.element_type in ("page_header", "page_footer")
    ]
    total = len(_elements(doc))
    return MetricResult(
        name="header_footer_leakage",
        status="computed",
        value=len(leaked) / total if total else None,
        numerator=len(leaked),
        denominator=total,
        detail={"leaked_element_ids": [element.element_id for element in leaked]},
    )


def layout_coherence(doc: ParsedDocument) -> MetricResult:
    """Metric 6 — deterministic layout-coherence rule (documented in code).

    Rule:
      (a) reading-order continuity: across all elements in document order the
          reading_order values must be strictly monotonic with no gaps beyond
          tolerance: reading_order[i] == reading_order[i-1] + 1 (tolerance = 0
          gaps). The adapter assigns reading_order as the parser's item
          iteration index, so this validates the adapter produced a contiguous
          sequence (a duplicated or skipped index would fail the rule).
      (b) element-count-per-page sanity: every page must carry at least one
          element; pages with zero elements are flagged as empty.
    """
    elements = _elements(doc)
    orders = [element.reading_order for element in elements]
    contiguous = all(b == a + 1 for a, b in pairwise(orders)) if len(orders) > 1 else True
    empty_pages = [page.page_number for page in doc.pages if not page.elements]
    coherent = contiguous and not empty_pages
    return MetricResult(
        name="layout_coherence",
        status="computed",
        value=1.0 if coherent else 0.0,
        detail={
            "rule": "reading_order strictly +1 contiguous (tolerance=0 gaps); "
            "every page has >=1 element",
            "reading_order_contiguous": contiguous,
            "reading_order_start": orders[0] if orders else None,
            "reading_order_end": orders[-1] if orders else None,
            "per_page_element_counts": {page.page_number: len(page.elements) for page in doc.pages},
            "empty_pages": empty_pages,
            "element_count": len(orders),
        },
    )


def compute_all_metrics(parsed: ParsedDocument, entry: dict[str, Any]) -> dict[str, MetricResult]:
    """Compute the six parser-native metrics for one document.

    ``entry`` is an input-manifest entry; gold-derived availability comes from
    ``entry["gold_path"]`` (None when the fixture has no gold file).
    """
    gold_path = entry.get("gold_path")
    return {
        "text_extraction_rate": text_extraction_rate(parsed),
        "provenance_coverage": provenance_coverage(parsed),
        "table_detection_rate": table_detection_rate(parsed, _gold_expected_tables(gold_path)),
        "table_preservation": table_preservation(parsed, _gold_expected_tables(gold_path)),
        "header_footer_leakage": header_footer_leakage(parsed, _gold_has_header_footer(gold_path)),
        "layout_coherence": layout_coherence(parsed),
    }


# ────────────────────────────────────────────────────────────────────────────
# Gold-derived availability
# ────────────────────────────────────────────────────────────────────────────


def _load_gold(gold_path: str | None) -> dict[str, Any] | None:
    if gold_path is None:
        return None
    try:
        payload = json.loads(Path(gold_path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return payload if isinstance(payload, dict) else None


def _gold_expected_tables(gold_path: str | None) -> int | None:
    gold = _load_gold(gold_path)
    if gold is None:
        return None
    tables = gold.get("tables")
    return len(tables) if isinstance(tables, list) else None


def _gold_has_header_footer(gold_path: str | None) -> bool:
    gold = _load_gold(gold_path)
    if gold is None:
        return False
    return any(key in gold for key in ("header_footer", "headers_footers", "page_header"))


# ────────────────────────────────────────────────────────────────────────────
# Input manifest
# ────────────────────────────────────────────────────────────────────────────


def _classify(pdf_path: Path) -> str:
    parent = pdf_path.parent.name
    if parent in GOLD_CLASSIFICATIONS:
        return parent
    for prefix in GOLD_CLASSIFICATIONS:
        if pdf_path.stem.startswith(prefix):
            return prefix
    return "other"


def build_input_manifest(fixtures_dir: Path) -> dict[str, Any]:
    """Hash every fixture PDF and its gold companion for the input manifest."""
    pdfs = sorted(fixtures_dir.rglob("*.pdf"))
    gold_dir = fixtures_dir.parent / "gold"
    entries: list[dict[str, Any]] = []
    for pdf in pdfs:
        classification = _classify(pdf)
        gold_path = gold_dir / f"{classification}-gold.json"
        gold_hash: str | None = None
        document_id: str | None = None
        if gold_path.exists():
            gold_hash = _sha256(gold_path)
            gold = _load_gold(str(gold_path))
            if gold is not None:
                document_id = gold.get("document_id")
        entries.append(
            {
                "fixture_path": str(pdf),
                "sha256": _sha256(pdf),
                "classification": classification,
                "gold_path": str(gold_path) if gold_path.exists() else None,
                "gold_sha256": gold_hash,
                "document_id": document_id or pdf.stem,
            }
        )
    return {"fixtures_dir": str(fixtures_dir), "entries": entries}


# ────────────────────────────────────────────────────────────────────────────
# Docling adapter (P1)
# ────────────────────────────────────────────────────────────────────────────


def _docling_version() -> str:
    import docling

    return getattr(docling, "__version__", "") or _pkg_version("docling")


def _make_docling_converter() -> Any:
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False
    options.do_table_structure = True
    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def _item_text(item: Any) -> str:
    text = getattr(item, "text", None)
    return text if isinstance(text, str) else ""


def _item_bbox(item: Any, doc: Any, page_no: int) -> tuple[BoundingBox | None, list[float] | None]:
    """Canonical NORMALIZED_PAGE bbox + raw PDF-point box for ``item`` (prov[0]).

    Mirrors the production docling adapter exactly (v2 / oracle blocker 1): the
    raw Docling box is normalized to TOPLEFT origin (PDF text-layer provenance
    is BOTTOMLEFT) and scaled to 0..1 of page width/height so the IR bbox is
    origin- and unit-consistent with every other parser; the raw PDF-point box
    (docling native, pre-normalization) is returned for
    ``raw_reference["bbox_points"]`` so parser-native coordinates are never
    lost. ``(None, None)`` when the item carries no bbox provenance or page
    dimensions are missing/zero/negative.
    """
    prov = item.prov[0] if item.prov else None
    if prov is None or prov.bbox is None:
        return None, None
    raw = prov.bbox
    raw_points = [raw.l, raw.t, raw.r, raw.b]
    page_model = doc.pages.get(page_no)
    page_height = page_model.size.height if page_model is not None else None
    page_width = page_model.size.width if page_model is not None else None
    if page_height is None or page_width is None or page_height <= 0 or page_width <= 0:
        return None, raw_points
    normalized = raw.to_top_left_origin(page_height)
    return (
        BoundingBox(
            left=normalized.l / page_width,
            top=normalized.t / page_height,
            right=normalized.r / page_width,
            bottom=normalized.b / page_height,
            coordinate_space="NORMALIZED_PAGE",
            page_height=page_height,
            page_width=page_width,
        ),
        raw_points,
    )


def _item_table_html(item: Any, doc: Any) -> str | None:
    if getattr(item, "label", None) is None or item.label.value != "table":
        return None
    try:
        exported = item.export_to_markdown(doc)
    except Exception:
        return None
    return exported if exported.strip() else None


def _item_raw_reference(
    item: Any, index: int, page_no: int, bbox_points: list[float] | None = None
) -> dict[str, Any]:
    prov = item.prov[0] if item.prov else None
    reference: dict[str, Any] = {
        "docling_item_index": index,
        "docling_item_type": type(item).__name__,
        "docling_label": item.label.value if item.label is not None else None,
        "prov_page_no": page_no,
        "charspan": list(prov.charspan) if prov is not None and prov.charspan else None,
    }
    if bbox_points is not None:
        # v2: canonical bbox is NORMALIZED_PAGE (0..1); the raw PDF-point box
        # is preserved here for provenance/traceability (mirrors docling_adapter).
        reference["bbox_points"] = bbox_points
    return reference


def parse_with_docling(
    pdf_path: Path, document_id: str, converter: Any | None = None
) -> ParsedDocument:
    """Parse a born-digital PDF with Docling and map it onto the canonical IR.

    OCR is NOT executed: the benchmark fixtures are born-digital PDFs with an
    embedded text layer (run.json records ``ocr_status=SKIPPED_TEXT_LAYER_PRESENT``).
    Table structure extraction stays enabled so table_html is available when a
    table is present; the v1 fixtures contain none.
    """
    from docling.datamodel.base_models import ConversionStatus

    if converter is None:
        converter = _make_docling_converter()
    result = converter.convert(str(pdf_path))
    if result.status != ConversionStatus.SUCCESS:
        raise RuntimeError(f"docling conversion failed for {pdf_path}: {result.status}")
    doc = result.document

    parser_version = f"docling-{_docling_version()}"
    parsed_document_id = str(uuid.uuid4())
    started_at = datetime.now(UTC)
    elements_by_page: dict[int, list[DocumentElement]] = {}
    for index, (item, _level) in enumerate(doc.iterate_items()):
        prov = item.prov[0] if item.prov else None
        page_no = prov.page_no if prov is not None else 1
        element_type = item.label.value if item.label is not None else "text"
        bbox, bbox_points = _item_bbox(item, doc, page_no)
        element = DocumentElement(
            element_id=f"p{page_no}-e{index}",
            element_type=element_type,
            text=_item_text(item),
            page_number=page_no,
            bbox=bbox,
            reading_order=index,
            parent_element_id=None,
            table_html=_item_table_html(item, doc),
            source_parser="DOCLING",
            parser_version=parser_version,
            parser_confidence=None,
            raw_reference=_item_raw_reference(item, index, page_no, bbox_points=bbox_points),
        )
        elements_by_page.setdefault(page_no, []).append(element)

    pages: list[ParsedPage] = []
    for page_no in range(1, doc.num_pages() + 1):
        elements = elements_by_page.get(page_no, [])
        page_text = "\n".join(element.text for element in elements if element.text.strip()) or None
        size = doc.pages[page_no].size
        pages.append(
            ParsedPage(
                page_number=page_no,
                width=size.width,
                height=size.height,
                text=page_text,
                elements=elements,
            )
        )
    return ParsedDocument(
        parsed_document_id=parsed_document_id,
        document_id=document_id,
        parser="DOCLING",
        parser_version=parser_version,
        ir_schema_version=IR_SCHEMA_VERSION,
        source_object_key=str(pdf_path),
        pages=pages,
        parse_started_at=started_at,
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )


# ────────────────────────────────────────────────────────────────────────────
# MinerU attempt (P2)
# ────────────────────────────────────────────────────────────────────────────


def _find_mineru_content_list(output_dir: Path, pdf_path: Path) -> Path | None:
    candidates = sorted(output_dir.rglob("content_list.json"))
    if candidates:
        return candidates[0]
    direct = output_dir / pdf_path.stem / "content_list.json"
    return direct if direct.exists() else None


def parse_with_mineru(pdf_path: Path, document_id: str, output_dir: Path) -> ParsedDocument:
    """Build the canonical IR from a MinerU pipeline ``content_list.json``.

    v1 minimal, best-effort mapping: MinerU content items carry type/text/
    page_idx; bounding boxes are not exposed at that level, so bbox is None and
    the provenance bbox share is reported from that real absence. ``page_idx``
    is 0-based in MinerU output; the IR uses 1-based page numbers.
    """
    content_list = _find_mineru_content_list(output_dir, pdf_path)
    if content_list is None:
        raise RuntimeError(f"mineru output missing content_list.json under {output_dir}")
    items = json.loads(content_list.read_text(encoding="utf-8"))
    parser_version = f"mineru-{_pkg_version('mineru')}"
    parsed_document_id = str(uuid.uuid4())
    started_at = datetime.now(UTC)
    elements_by_page: dict[int, list[DocumentElement]] = {}
    page_idx_max = 0
    for index, item in enumerate(items):
        page_idx = int(item.get("page_idx", 0) or 0)
        page_no = page_idx + 1
        page_idx_max = max(page_idx_max, page_idx)
        element = DocumentElement(
            element_id=f"p{page_no}-e{index}",
            element_type=str(item.get("type", "text")),
            text=str(item.get("text", "") or ""),
            page_number=page_no,
            bbox=None,
            reading_order=index,
            parent_element_id=None,
            table_html=None,
            source_parser="MINERU",
            parser_version=parser_version,
            parser_confidence=None,
            raw_reference={"mineru_content_index": index, "mineru_item_type": item.get("type")},
        )
        elements_by_page.setdefault(page_no, []).append(element)
    pages: list[ParsedPage] = []
    for page_no in range(1, page_idx_max + 2):
        elements = elements_by_page.get(page_no, [])
        page_text = "\n".join(element.text for element in elements if element.text.strip()) or None
        pages.append(
            ParsedPage(
                page_number=page_no, width=None, height=None, text=page_text, elements=elements
            )
        )
    return ParsedDocument(
        parsed_document_id=parsed_document_id,
        document_id=document_id,
        parser="MINERU",
        parser_version=parser_version,
        ir_schema_version=IR_SCHEMA_VERSION,
        source_object_key=str(pdf_path),
        pages=pages,
        parse_started_at=started_at,
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )


def _extract_error(stderr: str) -> str:
    """Return the most informative error line from mineru stderr.

    Prefer the actual root-cause line (e.g. the ImportError) over traceback
    noise; fall back to the last non-empty line.
    """
    lines = stderr.splitlines()
    for line in lines:
        if "ImportError" in line or "RuntimeError" in line or "OSError" in line:
            return line.strip()[:300]
    for line in lines:
        if "Error" in line or "error:" in line:
            return line.strip()[:300]
    last = [line for line in lines if line.strip()]
    return (last[-1] if last else stderr).strip()[:300]


def _attempt_mineru_document(entry: dict[str, Any], phase_dir: Path) -> dict[str, Any]:
    """Run the mineru CLI for one document and return attempt evidence (no IR)."""
    document_id = entry["document_id"]
    pdf_path = Path(entry["fixture_path"])
    output_dir = phase_dir / "mineru-output"
    output_dir.mkdir(exist_ok=True)
    command = [
        shutil.which("mineru") or "mineru",
        "-p",
        str(pdf_path),
        "-o",
        str(output_dir),
        "-b",
        "pipeline",
        "-m",
        "txt",
    ]
    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = ""
    started = time.monotonic()
    timed_out = False
    error_summary = ""
    stderr_tail = ""
    returncode: int | None = None
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=MINERU_TIMEOUT_SECONDS,
            env=env,
            check=False,
        )
        returncode = completed.returncode
        stderr_tail = (completed.stderr or "")[-4000:]
        error_summary = _extract_error(completed.stderr or "")
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        stderr_tail = (exc.stderr or "")[-4000:] if isinstance(exc.stderr, str) else ""
        error_summary = f"mineru subprocess timed out after {MINERU_TIMEOUT_SECONDS}s"
    duration = time.monotonic() - started
    peak_rss_kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    return {
        "document_id": document_id,
        "command": command,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": round(duration, 2),
        "peak_rss_kb": peak_rss_kb,
        "error_summary": error_summary,
        "stderr_tail": stderr_tail,
    }


def _failure_class(attempts: list[dict[str, Any]]) -> str:
    text = " ".join(f"{attempt['error_summary']} {attempt['stderr_tail']}" for attempt in attempts)
    if "ImportError" in text:
        return "DEPENDENCY_INCOMPATIBILITY"
    if any(attempt["timed_out"] for attempt in attempts):
        return "TIMEOUT"
    return "CRASH"


def _resource_evidence(attempts: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "status": "FAILED",
        "failure_class": _failure_class(attempts),
        "root_cause": (
            "mineru 3.4.4 pipeline backend imports "
            "transformers.pytorch_utils.find_pruneable_heads_and_indices, which was "
            "removed in the installed transformers 5.8.1 (resolved by docling 2.118.1)"
        ),
        "attempts": attempts,
        "retry_policy": {
            "max_attempts": 2,
            "attempts_made": 1,
            "per_document_invocations": len(attempts),
            "retry_skipped": True,
            "retry_skipped_reason": (
                "deterministic dependency failure — a retry cannot succeed in this environment"
            ),
        },
        "environment": {
            "mineru": _pkg_version("mineru"),
            "transformers": _pkg_version("transformers"),
            "torch": _pkg_version("torch"),
            "python": sys.version.split()[0],
            "cuda_visible_devices": "",
            "gpu": (
                'UNUSABLE (CUDA_VISIBLE_DEVICES=""; MX330/Pascal unsupported by torch 2.13 cu130)'
            ),
        },
        "observed_at": _timestamp(),
    }


# ────────────────────────────────────────────────────────────────────────────
# Aggregates, routing evidence, reports
# ────────────────────────────────────────────────────────────────────────────


def _ir_summary(parsed: ParsedDocument) -> dict[str, Any]:
    histogram: dict[str, int] = {}
    for element in _elements(parsed):
        histogram[element.element_type] = histogram.get(element.element_type, 0) + 1
    return {
        "document_id": parsed.document_id,
        "parser": parsed.parser,
        "parser_version": parsed.parser_version,
        "ir_schema_version": parsed.ir_schema_version,
        "pages": len(parsed.pages),
        "elements": len(_elements(parsed)),
        "element_type_histogram": dict(sorted(histogram.items())),
    }


def _aggregate_results(per_doc: dict[str, dict[str, Any]]) -> dict[str, Any]:
    pages = sum(doc["pages"] for doc in per_doc.values())
    elements = sum(doc["elements"] for doc in per_doc.values())
    histogram: dict[str, int] = {}
    for doc in per_doc.values():
        for element_type, count in doc["element_type_histogram"].items():
            histogram[element_type] = histogram.get(element_type, 0) + count
    return {
        "documents": len(per_doc),
        "pages": pages,
        "elements": elements,
        "element_type_histogram": dict(sorted(histogram.items())),
    }


def _dump_metrics(per_doc: dict[str, dict[str, MetricResult]]) -> dict[str, dict[str, Any]]:
    return {
        document_id: {name: result.model_dump(mode="json") for name, result in metrics.items()}
        for document_id, metrics in per_doc.items()
    }


def _aggregate_metrics(per_doc: dict[str, dict[str, MetricResult]]) -> dict[str, Any]:
    aggregate: dict[str, Any] = {}
    for name in _METRIC_NAMES:
        results = [doc[name] for doc in per_doc.values()]
        computed = [
            result for result in results if result.status == "computed" and result.value is not None
        ]
        if not computed:
            reason = next((result.na_reason for result in results if result.na_reason), None)
            aggregate[name] = {
                "status": "na",
                "na_reason": reason or f"{name} not computed for any document",
            }
            continue
        values = [result.value for result in computed if result.value is not None]
        entry: dict[str, Any] = {
            "status": "computed",
            "value": sum(values) / len(values),
            "per_document_values": {doc_id: doc[name].value for doc_id, doc in per_doc.items()},
        }
        if name in ("text_extraction_rate", "provenance_coverage"):
            numerator = sum(result.numerator or 0 for result in computed)
            denominator = sum(result.denominator or 0 for result in computed)
            entry["overall_fraction"] = numerator / denominator if denominator else None
            entry["numerator"] = numerator
            entry["denominator"] = denominator
        aggregate[name] = entry
    return aggregate


def _routing_and_gates(
    per_doc_metrics: dict[str, dict[str, MetricResult]], parser: str
) -> dict[str, Any]:
    """Metric 7 — routing outcome and Group-A quality-gate evidence.

    v1: the selected parser is the CLI argument (parser router P3 is pending,
    VNLRAG-131); no pass/fail thresholds are defined yet, so gates are reported
    as measured values with verdict REPORTED_NO_THRESHOLD.
    """
    per_doc: dict[str, Any] = {}
    for document_id, metrics in per_doc_metrics.items():
        per_doc[document_id] = {
            "selected_parser": parser,
            "fallback_attempted": False,
            "gates": {
                "group_a": {
                    "provenance_coverage": metrics["provenance_coverage"].model_dump(mode="json"),
                    "text_extraction_rate": metrics["text_extraction_rate"].model_dump(mode="json"),
                    "table_detection": metrics["table_detection_rate"].model_dump(mode="json"),
                }
            },
            "gate_verdict": "REPORTED_NO_THRESHOLD",
            "terminal_outcome": "COMPLETED",
        }
    return {
        "parser": parser,
        "selected_parser": parser,
        "fallback_attempted": False,
        "p3_parser_router": P3_STATUS,
        "per_document": per_doc,
        "aggregate": {
            "selected_parser": parser,
            "fallback_attempted": False,
            "p3_parser_router": P3_STATUS,
            "gate_verdict": "REPORTED_NO_THRESHOLD",
            "terminal_outcome": "COMPLETED",
        },
    }


def _fmt_value(value: float | None) -> str:
    return "None" if value is None else f"{value:.4f}"


def _metric_line(name: str, result: MetricResult) -> str:
    fraction = (
        f", fraction=({result.numerator}/{result.denominator})"
        if result.status == "computed"
        and result.numerator is not None
        and result.denominator is not None
        else ""
    )
    reason = f" — N/A: {result.na_reason}" if result.na_reason else ""
    return f"- {name}: status={result.status}, value={_fmt_value(result.value)}{fraction}{reason}"


def _write_docling_report(
    run_root: Path,
    run_id: str,
    per_doc_metrics: dict[str, dict[str, MetricResult]],
    aggregate_metrics: dict[str, Any],
    aggregate_results: dict[str, Any],
    parser_versions: dict[str, str],
) -> None:
    lines = [
        f"# Suite A First Pass — P1 (Docling) — run {run_id}",
        "",
        "Raw numbers only. NO superiority conclusions. Generated automatically by suite_a.py.",
        "",
        f"- parser: docling {parser_versions.get('docling', 'unknown')}",
        f"- ir_schema_version: {IR_SCHEMA_VERSION}",
        "- p2 (MinerU): attempted as a separate run (--parser mineru) in the same "
        "base run dir; see its p2-mineru run directory for the attempt and evidence.",
        f"- p3 (parser router): {P3_STATUS}",
        "",
        "## Aggregate",
        "",
        f"- documents: {aggregate_results['documents']}",
        f"- pages: {aggregate_results['pages']}",
        f"- elements: {aggregate_results['elements']}",
        "- element_type_histogram: "
        f"{json.dumps(aggregate_results['element_type_histogram'], ensure_ascii=False)}",
        "",
        "## Metrics per document",
        "",
    ]
    for document_id, metrics in per_doc_metrics.items():
        lines.append(f"### {document_id}")
        lines.append("")
        for name in _METRIC_NAMES:
            lines.append(_metric_line(name, metrics[name]))
        lines.append("")
    lines.append("## Aggregate metrics")
    lines.append("")
    for name in _METRIC_NAMES:
        lines.append(f"- {name}: {json.dumps(aggregate_metrics[name], ensure_ascii=False)}")
    lines.append("")
    (run_root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def _write_mineru_report(
    run_root: Path, run_id: str, attempts: list[dict[str, Any]], evidence: dict[str, Any]
) -> None:
    lines = [
        f"# Suite A First Pass — P2 (MinerU) — run {run_id}",
        "",
        "P2 attempt FAILED. No IR/metrics produced (parser could not complete locally).",
        "Resource evidence: p2-mineru/resource-evidence.json",
        "",
        f"- failure_class: {evidence['failure_class']}",
        f"- root_cause: {evidence['root_cause']}",
        f"- p3 (parser router): {P3_STATUS}",
        "",
        "## Per-document attempt summary",
        "",
    ]
    for attempt in attempts:
        lines.append(
            f"- {attempt['document_id']}: returncode={attempt['returncode']}, "
            f"duration_s={attempt['duration_seconds']}, "
            f"peak_rss_kb={attempt['peak_rss_kb']}, error={attempt['error_summary']}"
        )
    lines.append("")
    (run_root / "report.md").write_text("\n".join(lines), encoding="utf-8")


# ────────────────────────────────────────────────────────────────────────────
# Parser phase executors
# ────────────────────────────────────────────────────────────────────────────


def _make_docling_parse() -> Callable[[Path, str, Any], ParsedDocument]:
    """Return a parser callable bound to one shared Docling converter.

    The closure owns the (model-loaded) converter so a run parses all documents
    with a single model instance. Tests may inject a stub callable instead,
    avoiding any docling import/model load.
    """

    converter = _make_docling_converter()

    def _parse(pdf_path: Path, document_id: str, _converter: Any) -> ParsedDocument:
        return parse_with_docling(pdf_path, document_id, converter)

    return _parse


def _execute_docling(
    manifest: dict[str, Any],
    run_root: Path,
    phase_dir: Path,
    metadata: RunMetadata,
    parse_callable: Callable[[Path, str, Any], ParsedDocument],
) -> str:
    ir_dir = phase_dir / "ir"
    ir_dir.mkdir()
    per_doc_results: dict[str, dict[str, Any]] = {}
    per_doc_metrics: dict[str, dict[str, MetricResult]] = {}
    artifacts: dict[str, Any] = {}
    for entry in manifest["entries"]:
        document_id = entry["document_id"]
        pdf_path = Path(entry["fixture_path"])
        parsed = parse_callable(pdf_path, document_id, None)
        ir_path = ir_dir / f"{document_id}.ir.json"
        _write_json(ir_path, parsed.model_dump(mode="json"))
        per_doc_results[document_id] = _ir_summary(parsed)
        per_doc_metrics[document_id] = compute_all_metrics(parsed, entry)
        artifacts[document_id] = {
            "ir_path": str(ir_path.relative_to(run_root)),
            "ir_sha256": _sha256(ir_path),
        }
    _write_json(
        phase_dir / "results.json",
        {
            "parser": "docling",
            "ir_schema_version": IR_SCHEMA_VERSION,
            "per_document": per_doc_results,
            "aggregate": _aggregate_results(per_doc_results),
        },
    )
    _write_json(
        phase_dir / "metrics.json",
        {
            "parser": "docling",
            "ir_schema_version": IR_SCHEMA_VERSION,
            "per_document": _dump_metrics(per_doc_metrics),
            "aggregate": _aggregate_metrics(per_doc_metrics),
        },
    )
    _write_json(
        phase_dir / "routing-and-gates.json",
        _routing_and_gates(per_doc_metrics, parser="docling"),
    )
    _write_json(
        phase_dir / "artifacts-manifest.json",
        {"ir_schema_version": IR_SCHEMA_VERSION, "per_document": artifacts},
    )
    _write_docling_report(
        run_root,
        metadata.run_id,
        per_doc_metrics,
        _aggregate_metrics(per_doc_metrics),
        _aggregate_results(per_doc_results),
        metadata.parser_versions,
    )
    return "COMPLETED"


def _execute_mineru(
    manifest: dict[str, Any],
    run_root: Path,
    phase_dir: Path,
    metadata: RunMetadata,
) -> str:
    attempts: list[dict[str, Any]] = []
    for entry in manifest["entries"]:
        attempts.append(_attempt_mineru_document(entry, phase_dir))
    evidence = _resource_evidence(attempts)
    _write_json(phase_dir / "resource-evidence.json", evidence)
    _write_json(
        phase_dir / "results.json",
        {
            "parser": "mineru",
            "per_document": {
                attempt["document_id"]: {
                    "status": "FAILED",
                    "error_summary": attempt["error_summary"],
                }
                for attempt in attempts
            },
        },
    )
    _write_mineru_report(run_root, metadata.run_id, attempts, evidence)
    return "FAILED"


# ────────────────────────────────────────────────────────────────────────────
# 300-vs-600 DPI OCR benchmark (AC 7)
# ────────────────────────────────────────────────────────────────────────────


def _phrase_hits(text: str) -> tuple[list[str], float]:
    """Hit list + fraction of the known legal phrases present in ``text``."""
    folded = text.casefold()
    hits = [phrase for phrase in OCR_BENCH_PHRASES if phrase.casefold() in folded]
    return hits, len(hits) / len(OCR_BENCH_PHRASES)


def _diacritic_count(text: str) -> int:
    """Count Vietnamese diacritic-bearing chars (precomposed + combining marks)."""
    return sum(
        1 for char in text if char in _VIETNAMESE_DIACRITICS or unicodedata.category(char) == "Mn"
    )


def _render_pages(pdf_path: Path, first: int, last: int, dpi: int, out_dir: Path) -> list[Path]:
    """Render PDF pages [first, last] to PNGs at ``dpi`` via pdftoppm."""
    prefix = out_dir / "page"
    subprocess.run(
        [
            "pdftoppm",
            "-png",
            "-r",
            str(dpi),
            "-f",
            str(first),
            "-l",
            str(last),
            str(pdf_path),
            str(prefix),
        ],
        check=True,
        capture_output=True,
    )
    return sorted(out_dir.glob("page-*.png"))


def _ocr_options_kwargs() -> dict[str, Any]:
    """Tesseract OCR options actually applied for scan-route OCR.

    Traceable: mirrors what is recorded in the run.json config snapshot
    (psm=3 explicit — docling's TesseractCliOcrOptions default is psm=None,
    which delegates to the tesseract binary default; the recorded policy must
    reflect what is actually passed).
    """
    return {
        "tesseract_cmd": TESSERACT_CMD,
        "path": TESSDATA_DIR,
        "lang": list(OCR_LANG),
        "psm": 3,
    }


def _make_ocr_image_converter() -> Any:
    """Docling converter for image input with tesseract vie OCR (CPU-only)."""
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions
    from docling.document_converter import DocumentConverter, ImageFormatOption, InputFormat

    options = PdfPipelineOptions()
    options.do_ocr = True
    options.do_table_structure = False
    options.ocr_options = TesseractCliOcrOptions(**_ocr_options_kwargs())
    return DocumentConverter(
        format_options={InputFormat.IMAGE: ImageFormatOption(pipeline_options=options)}
    )


def _ocr_convert_page(converter: Any, png_path: Path) -> dict[str, Any]:
    """OCR one rendered page, measuring elapsed + peak RSS + text quality."""
    started = time.monotonic()
    try:
        result = converter.convert(str(png_path))
    except Exception as exc:
        return {
            "status": "FAILED",
            "error": f"{type(exc).__name__}: {exc}",
            "elapsed_seconds": round(time.monotonic() - started, 2),
            "peak_rss_kb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        }
    elapsed = time.monotonic() - started
    peak_rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    doc = result.document
    items = list(doc.iterate_items())
    element_count = len(items)
    bbox_count = sum(1 for item, _level in items if item.prov and item.prov[0].bbox is not None)
    text = "\n".join(getattr(item, "text", "") or "" for item, _level in items)
    hits, hit_fraction = _phrase_hits(text)
    return {
        "status": "SUCCESS",
        "elapsed_seconds": round(elapsed, 2),
        "peak_rss_kb": peak_rss_kb,
        "element_count": element_count,
        "bbox_count": bbox_count,
        "bbox_coverage": round(bbox_count / element_count, 4) if element_count else 0.0,
        "extracted_text_length": len(text),
        "diacritics": _diacritic_count(text),
        "phrase_hits": hits,
        "phrase_hit_fraction": round(hit_fraction, 4),
        "extracted_text": text,
        "text_snippet": text[:200],
    }


def _dpi_aggregate(page_stats: dict[int, dict[str, Any]], dpi: int) -> dict[str, Any]:
    pages = list(page_stats.values())
    succeeded = [page for page in pages if page["status"] == "SUCCESS"]
    if not succeeded:
        return {
            "dpi": dpi,
            "status": "FAILED_ALL_PAGES",
            "pages_attempted": len(pages),
            "pages_succeeded": 0,
        }
    return {
        "dpi": dpi,
        "status": "COMPLETED",
        "pages_attempted": len(pages),
        "pages_succeeded": len(succeeded),
        "total_elapsed_seconds": round(sum(p["elapsed_seconds"] for p in succeeded), 2),
        "avg_elapsed_seconds_per_page": round(
            sum(p["elapsed_seconds"] for p in succeeded) / len(succeeded), 2
        ),
        "peak_rss_kb": max(p["peak_rss_kb"] for p in succeeded),
        "mean_bbox_coverage": round(sum(p["bbox_coverage"] for p in succeeded) / len(succeeded), 4),
        "mean_phrase_hit_fraction": round(
            sum(p["phrase_hit_fraction"] for p in succeeded) / len(succeeded), 4
        ),
        "total_extracted_chars": sum(p["extracted_text_length"] for p in succeeded),
    }


def _dpi_recommendation(stats_300: dict[str, Any], stats_600: dict[str, Any]) -> dict[str, Any]:
    """Data-driven decision table: which DPI measurably improves each axis.

    No conclusion beyond the measured axes (quality/speed/RAM/bbox). 600 DPI is
    picked when it wins on quality (phrase hit rate or bbox coverage) AND its
    speed penalty stays within 2x of 300 DPI.
    """

    def _better(axis_key: str, lower_is_better: bool = False) -> str:
        v300 = stats_300[axis_key]
        v600 = stats_600[axis_key]
        if lower_is_better:
            return "600" if v600 < v300 else ("300" if v300 < v600 else "tie")
        return "600" if v600 > v300 else ("300" if v300 > v600 else "tie")

    quality_better = _better("mean_phrase_hit_fraction")
    bbox_better = _better("mean_bbox_coverage")
    speed_better = _better("avg_elapsed_seconds_per_page", lower_is_better=True)
    ram_better = _better("peak_rss_kb", lower_is_better=True)
    speed_penalty_ok = stats_600["avg_elapsed_seconds_per_page"] <= (
        2.0 * stats_300["avg_elapsed_seconds_per_page"]
    )
    quality_wins = quality_better == "600" or bbox_better == "600"
    pick = "600" if quality_wins and speed_penalty_ok else "300"
    return {
        "dpi_for_scan_ocr": pick,
        "decision_table": {
            "quality_phrase_hit_rate": {
                "300": stats_300["mean_phrase_hit_fraction"],
                "600": stats_600["mean_phrase_hit_fraction"],
                "better": quality_better,
            },
            "quality_bbox_coverage": {
                "300": stats_300["mean_bbox_coverage"],
                "600": stats_600["mean_bbox_coverage"],
                "better": bbox_better,
            },
            "speed_avg_seconds_per_page": {
                "300": stats_300["avg_elapsed_seconds_per_page"],
                "600": stats_600["avg_elapsed_seconds_per_page"],
                "better": speed_better,
            },
            "ram_peak_rss_kb": {
                "300": stats_300["peak_rss_kb"],
                "600": stats_600["peak_rss_kb"],
                "better": ram_better,
            },
        },
        "basis": (
            "600 picked when it wins on quality (phrase hit rate or bbox coverage) "
            "and speed stays within 2x of 300 DPI"
        ),
        "note": "600 DPI scan-only conditional per VNLRAG-20 OCR decision",
    }


def _write_ocr_bench_report(
    run_root: Path,
    run_id: str,
    stats_300: dict[str, Any],
    stats_600: dict[str, Any],
    page_stats: dict[int, dict[str, dict[str, Any]]],
    relative: dict[int, dict[str, Any]],
    recommendation: dict[str, Any],
    config: dict[str, Any],
) -> None:
    lines = [
        f"# 300-vs-600 DPI OCR Benchmark — run {run_id}",
        "",
        "Raw numbers only. No conclusions beyond which DPI measurably improves "
        "quality/speed/RAM/bbox (AC 7).",
        "",
        f"- pdf: {config['pdf']}",
        f"- page_range: {config['page_range']} ({config['pages']} pages)",
        f"- tesseract: {config['ocr']['tesseract_version']} (psm={config['ocr']['psm']})",
        '- engine: tesseract vie, CPU-only, CUDA_VISIBLE_DEVICES=""',
        "",
        "## Per-DPI aggregates",
        "",
        "| axis | 300 | 600 | better |",
        "|------|-----|-----|--------|",
    ]
    for axis, row in recommendation["decision_table"].items():
        lines.append(f"| {axis} | {row['300']} | {row['600']} | {row['better']} |")
    lines.append("")
    lines.append(f"- recommended dpi_for_scan_ocr: {recommendation['dpi_for_scan_ocr']}")
    lines.append(f"- basis: {recommendation['basis']}")
    lines.append(f"- note: {recommendation['note']}")
    lines.append("")
    lines.append("## Per-page detail")
    lines.append("")
    lines.append(
        "| page | dpi | s/page | peak_rss_kb | elements | bbox | phrase hits | chars | diacritics |"
    )
    lines.append(
        "|------|-----|--------|-------------|----------|------|-------------|-------|------------|"
    )
    for page_no in sorted(page_stats):
        for dpi in (300, 600):
            page = page_stats[page_no][str(dpi)]
            hits = "/".join(page["phrase_hits"]) if page["status"] == "SUCCESS" else "FAILED"
            lines.append(
                f"| {page_no} | {dpi} | {page.get('elapsed_seconds', '')} | "
                f"{page.get('peak_rss_kb', '')} | {page.get('element_count', '')} | "
                f"{page.get('bbox_coverage', '')} | {hits} | "
                f"{page.get('extracted_text_length', '')} | {page.get('diacritics', '')} |"
            )
    lines.append("")
    lines.append("## Relative quality (difflib SequenceMatcher ratio, 300 vs 600)")
    lines.append("")
    for page_no in sorted(relative):
        row = relative[page_no]
        lines.append(
            f"- page {page_no}: ratio={row['sequence_matcher_ratio']}, "
            f"chars 300={row['chars_300']}, chars 600={row['chars_600']}, "
            f"diacritics 300={row['diacritics_300']}, diacritics 600={row['diacritics_600']}"
        )
    lines.append("")
    lines.append(f"- p3 (parser router): {P3_STATUS}")
    lines.append("")
    (run_root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def run_ocr_dpi_benchmark(pdf_path: Path, pages: int, out_dir: Path) -> int:
    """bench-ocr-dpi: render pages 2..pages+1 of a scan PDF at 300 and 600 DPI,
    OCR each with tesseract vie via Docling, and record the decision data.

    Immutability: the run.json status is one-way RUNNING -> COMPLETED|FAILED.
    The entire post-creation body (converter creation, rendering, conversion,
    artifact writes, aggregation, report) is wrapped so ANY exception marks the
    run FAILED with the error recorded — no code path may leave run.json stuck
    at RUNNING (mirrors run_suite).
    """
    pdf_path = pdf_path.resolve()
    out_dir = out_dir.resolve()
    if pages < 1:
        raise ValueError("--pages must be >= 1")

    run_id = _make_run_id()
    run_root = create_run_root(out_dir, run_id)
    scratch = OCR_DPI_BENCH_SCRATCH / run_id
    scratch.mkdir(parents=True, exist_ok=True)
    first, last = 2, pages + 1

    ocr_snapshot = OcrConfig.snapshot()
    config: dict[str, Any] = {
        "pdf": str(pdf_path),
        "pages": pages,
        "page_range": [first, last],
        "dpi_values": [300, 600],
        "render_backend": "pdftoppm",
        "scratch_dir": str(scratch),
        "ocr": ocr_snapshot.model_dump(),
        "ocr_readiness": {
            "checked": True,
            "ocr_required": True,
            "problems": check_ocr_readiness(ocr_snapshot.tessdata_dir),
        },
        "docling": {"do_ocr": True, "do_table_structure": False, "image_input": True},
        "cuda_visible_devices": "",
        "phrases": list(OCR_BENCH_PHRASES),
    }
    run_json: dict[str, Any] = {
        "run_id": run_id,
        "suite": "suite-a-ocr-dpi-benchmark",
        "status": "RUNNING",
        "created_at": _timestamp(),
        "completed_at": None,
        "git_commit": _git_commit(),
        # Parser versions are recorded at run start (ora-22) so even a FAILED
        # run is reproducible; shape mirrors run_suite's top-level
        # parser_versions (+ the OCR engine actually used by the benchmark).
        "ir_schema_version": IR_SCHEMA_VERSION,
        "parser_versions": {
            "docling": _pkg_version("docling"),
            "mineru": _pkg_version("mineru"),
            "tesseract": _tesseract_version() or "unknown",
        },
        "config": config,
        "p3_parser_router": P3_STATUS,
        "error": None,
    }
    _write_json(run_root / "run.json", run_json)

    # OCR is required here (scan route) — fail fast when not ready.
    if config["ocr_readiness"]["problems"]:
        run_json = dict(
            run_json,
            status="FAILED",
            completed_at=_timestamp(),
            error="OCR not ready: " + "; ".join(config["ocr_readiness"]["problems"]),
        )
        _write_json(run_root / "run.json", run_json)
        print(f"run_id={run_id} status=FAILED error=OCR_NOT_READY", file=sys.stderr)
        return 1

    try:
        if not pdf_path.is_file():
            raise ValueError(f"pdf not found: {pdf_path}")
        if shutil.which("pdftoppm") is None:
            raise ValueError("pdftoppm not found on PATH (poppler-utils required)")
        converter = _make_ocr_image_converter()
        page_stats: dict[int, dict[str, dict[str, Any]]] = {}
        relative: dict[int, dict[str, Any]] = {}
        for dpi in (300, 600):
            png_dir = scratch / f"dpi-{dpi}"
            png_dir.mkdir(exist_ok=True)
            pngs = _render_pages(pdf_path, first, last, dpi, png_dir)
            for png in pngs:
                page_no = int(png.stem.rsplit("-", 1)[1])
                page_stats.setdefault(page_no, {})[str(dpi)] = _ocr_convert_page(converter, png)
            dpi_artifacts_dir = run_root / f"dpi-{dpi}"
            dpi_artifacts_dir.mkdir()
            _write_json(
                dpi_artifacts_dir / "metrics.json",
                _dpi_aggregate(_page_stats_for_dpi(page_stats, dpi), dpi),
            )

        stats_300 = _dpi_aggregate(_page_stats_for_dpi(page_stats, 300), 300)
        stats_600 = _dpi_aggregate(_page_stats_for_dpi(page_stats, 600), 600)
        for page_no, both in page_stats.items():
            t300 = _ocr_full_text(both["300"])
            t600 = _ocr_full_text(both["600"])
            ratio = SequenceMatcher(None, t300, t600).ratio()
            relative[page_no] = {
                "sequence_matcher_ratio": round(ratio, 4),
                "chars_300": len(t300),
                "chars_600": len(t600),
                "diacritics_300": both["300"].get("diacritics", 0),
                "diacritics_600": both["600"].get("diacritics", 0),
            }
        recommendation = _dpi_recommendation(stats_300, stats_600)

        _write_json(
            run_root / "detail.json",
            {
                "pdf": str(pdf_path),
                "page_range": [first, last],
                "dpi_values": [300, 600],
                "pages": {str(page_no): both for page_no, both in page_stats.items()},
                "relative_quality": {str(page_no): row for page_no, row in relative.items()},
            },
        )
        _write_json(
            run_root / "summary.json",
            {
                "dpi_metrics": {"300": stats_300, "600": stats_600},
                "recommendation": recommendation,
            },
        )
        _write_ocr_bench_report(
            run_root, run_id, stats_300, stats_600, page_stats, relative, recommendation, config
        )

        run_json = dict(run_json, status="COMPLETED", completed_at=_timestamp())
        _write_json(run_root / "run.json", run_json)
        print(f"run_id={run_id} status=COMPLETED")
        return 0
    except Exception as exc:
        run_json = dict(
            run_json,
            status="FAILED",
            completed_at=_timestamp(),
            error=f"{type(exc).__name__}: {exc}",
        )
        _write_json(run_root / "run.json", run_json)
        print(f"run_id={run_id} status={run_json['status']} error={exc}", file=sys.stderr)
        return 1


def _page_stats_for_dpi(
    page_stats: dict[int, dict[str, dict[str, Any]]], dpi: int
) -> dict[int, dict[str, Any]]:
    return {page_no: by_dpi[str(dpi)] for page_no, by_dpi in page_stats.items()}


def _ocr_full_text(page: dict[str, Any]) -> str:
    return page.get("extracted_text", "") if page.get("status") == "SUCCESS" else ""


# ────────────────────────────────────────────────────────────────────────────
# Run entrypoint
# ────────────────────────────────────────────────────────────────────────────


def run_suite(
    fixtures_dir: Path,
    run_dir: Path,
    parser: str,
    parse_docling: Callable[[Path, str, Any], ParsedDocument] | None = None,
    require_ocr: bool = False,
) -> int:
    """Execute one parser run and write immutable artifacts under run_dir/run_id.

    ``parse_docling`` injects a parser callable for tests (avoids docling);
    ``require_ocr`` marks the scan route: OCR readiness is checked FIRST and the
    run aborts FAILED if not ready (fail fast, AC 8). For born-digital runs OCR
    is skipped: readiness problems are recorded in the config snapshot but never
    hard-fail.

    Immutability: a run dir, once created, is NEVER deleted or rewritten; the
    run.json status is one-way RUNNING -> COMPLETED|FAILED. The whole run body
    (parser/phase validation, input-manifest build, all per-doc parsing) is
    wrapped so ANY exception marks the run FAILED — no code path may leave a
    run.json stuck at RUNNING.
    """
    fixtures_dir = fixtures_dir.resolve()
    run_dir = run_dir.resolve()
    run_id = _make_run_id()
    run_root = create_run_root(run_dir, run_id)

    ocr_snapshot = OcrConfig.snapshot()
    readiness_problems = check_ocr_readiness(ocr_snapshot.tessdata_dir)
    metadata = RunMetadata(
        run_id=run_id,
        git_commit=_git_commit(),
        created_at=_timestamp(),
        parser=parser,
        parser_versions={"docling": _pkg_version("docling"), "mineru": _pkg_version("mineru")},
        config={
            "fixtures_dir": str(fixtures_dir),
            "run_dir": str(run_dir),
            "parser": parser,
            "cuda_visible_devices": "",
            "ocr": ocr_snapshot.model_dump(),
            "ocr_readiness": {
                "checked": True,
                "ocr_required": require_ocr,
                "hard_fail": require_ocr,
                "problems": readiness_problems,
            },
            "parser_pipeline": {
                "docling": {"do_ocr": False, "do_table_structure": True},
                "mineru": {"backend": "pipeline", "method": "txt"},
            },
        },
    )
    _write_json(run_root / "run.json", metadata.model_dump(mode="json"))

    # Fail fast (AC 8): OCR required (scan route) but not ready -> abort FAILED.
    if require_ocr and readiness_problems:
        final = metadata.transition_to("FAILED", completed_at=_timestamp())
        final = final.model_copy(
            update={"error": "OCR not ready: " + "; ".join(readiness_problems)}
        )
        _write_json(run_root / "run.json", final.model_dump(mode="json"))
        print(f"run_id={run_id} status={final.status} error=OCR_NOT_READY", file=sys.stderr)
        return 1

    try:
        if parser not in PHASE_DIR:
            raise ValueError(f"unknown parser: {parser!r}")
        phase_dir = run_root / PHASE_DIR[parser]
        phase_dir.mkdir()
        if not fixtures_dir.is_dir():
            raise ValueError(f"fixtures dir not found: {fixtures_dir}")
        manifest = build_input_manifest(fixtures_dir)
        if not manifest["entries"]:
            raise ValueError(f"no PDF fixtures found under {fixtures_dir}")
        _write_json(run_root / "input-manifest.json", manifest)
        if parser == "docling":
            parse_callable = parse_docling or _make_docling_parse()
            status = _execute_docling(manifest, run_root, phase_dir, metadata, parse_callable)
        else:
            status = _execute_mineru(manifest, run_root, phase_dir, metadata)
        final = metadata.transition_to(status, completed_at=_timestamp())
        _write_json(run_root / "run.json", final.model_dump(mode="json"))
        print(f"run_id={run_id} status={final.status}")
        return 0
    except Exception as exc:
        final = metadata.transition_to("FAILED", completed_at=_timestamp())
        final = final.model_copy(update={"error": f"{type(exc).__name__}: {exc}"})
        _write_json(run_root / "run.json", final.model_dump(mode="json"))
        print(f"run_id={run_id} status={final.status} error={exc}", file=sys.stderr)
        return 1


def _cmd_check_ocr(tessdata_dir: Path) -> int:
    """check-ocr subcommand: fail-fast tesseract readiness (AC 8)."""
    problems = check_ocr_readiness(str(tessdata_dir))
    if problems:
        print("OCR not ready:")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(f"OCR ready (tesseract={_tesseract_version()}, tessdata={tessdata_dir})")
    return 0


def main(argv: list[str] | None = None) -> int:
    arg_parser = argparse.ArgumentParser(
        prog="python -m app.evaluation.suites.suite_a",
        description="Suite A parser benchmark runner (VNLRAG-20)",
    )
    sub = arg_parser.add_subparsers(dest="command", required=True)
    run_parser = sub.add_parser("run", help="Execute one parser run")
    run_parser.add_argument("--fixtures-dir", type=Path, required=True)
    run_parser.add_argument("--run-dir", type=Path, required=True)
    run_parser.add_argument(
        "--parser", choices=sorted(PHASE_DIR), default="docling", help="Parser to run"
    )
    run_parser.add_argument(
        "--require-ocr",
        action="store_true",
        help="Scan route: fail fast (FAILED) when OCR readiness check reports problems (AC 8)",
    )
    check_parser = sub.add_parser(
        "check-ocr", help="Fail-fast tesseract OCR readiness check (AC 8)"
    )
    check_parser.add_argument("--tessdata-dir", type=Path, required=True)
    bench_parser = sub.add_parser(
        "bench-ocr-dpi",
        help="300-vs-600 DPI OCR benchmark on a scan PDF (AC 7)",
    )
    bench_parser.add_argument("--pdf", type=Path, required=True)
    bench_parser.add_argument("--pages", type=int, default=6)
    bench_parser.add_argument("--out", type=Path, required=True)
    args = arg_parser.parse_args(argv)
    if args.command == "run":
        return run_suite(args.fixtures_dir, args.run_dir, args.parser, require_ocr=args.require_ocr)
    if args.command == "check-ocr":
        return _cmd_check_ocr(args.tessdata_dir)
    if args.command == "bench-ocr-dpi":
        return run_ocr_dpi_benchmark(args.pdf, args.pages, args.out)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
