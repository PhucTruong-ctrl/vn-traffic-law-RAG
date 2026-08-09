"""Production Docling → canonical Document IR adapter (VNLRAG-129).

Maps a parsed :class:`docling_core.types.doc.document.DoclingDocument` onto the
frozen canonical IR (``app/ingestion/document_ir.py``, ``document-ir-v1``).
Incorporates all nine VNLRAG-21 spike findings
(``docs/spike-vnlrag-21-ir-provenance-contract.md``) that the VNLRAG-20 bench
adapter (``app/evaluation/suites/suite_a.py``) did not address:

1. bbox coordinate normalization: PDF text-layer provenance is BOTTOMLEFT
   (``top > bottom``); OCR provenance is TOPLEFT. Every bbox is normalized to
   TOPLEFT via ``BoundingBox.to_top_left_origin(page_height)`` so IR
   coordinates are origin-consistent regardless of route.
2. explicit docling label → IR ``element_type`` mapping (module-level dict);
   labels outside the table pass through verbatim.
3. ``raw_reference`` carries the stable ``docling_self_ref`` JSON pointer plus
   the docling item index/type/label and provenance page/charspan.
4. ``parent_element_id`` is populated from ``NodeItem.parent`` (a cref JSON
   pointer) by mapping ``self_ref -> element_id`` over the full node tree
   (container items included, ``with_groups=True``), so list items point to
   their ``list`` container and captions to their parent content item.
5. ``table_html`` uses ``TableItem.export_to_html(doc)`` (HTML, matching the
   field name), including DOCUMENT_INDEX-labelled tables.
6. multi-prov items are not truncated silently: ``prov[0]`` drives page/bbox,
   while ``prov_count``/``prov_pages`` record the full provenance span.
7. ``source_object_key`` is the injected MinIO object key, never the local
   filesystem path.
8. ``parser_version`` is ``f"docling-{docling.__version__}"``.
9. ``element_id`` is ``p{page_no}-e{global_index}`` (stable within a parse,
   per contract §9) and ``reading_order`` is the global 0-based index.
10. OCR route: ``do_ocr=True`` with ``TesseractCliOcrOptions`` (vie, psm=3);
    a fail-fast tesseract readiness check runs before any OCR conversion.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage

IR_SCHEMA_VERSION = "document-ir-v1"
PARSER_NAME = "DOCLING"
OCR_PSM = 3

# Explicit docling label -> IR element_type mapping (VNLRAG-21 spike gap #2).
# Keep docling-native values for v1 EXCEPT where the contract vocabulary is the
# better name. ``text -> paragraph`` is deliberately NOT mapped: it is a lossy
# choice (the PDF route classifies most body prose as ``text``), so the label
# passes through verbatim and consumers must not rely on ``element_type ==
# "heading"`` either (real headings are often classified as ``text``).
# ``document_index -> table`` applies ONLY when the labelled item is a
# TableItem (a TOC rendered as a table); other document_index items (e.g.
# TableOfContentItem) pass through verbatim.
DOCLING_LABEL_TO_IR_TYPE: dict[str, str] = {
    "section_header": "heading",
    "title": "title",
    "picture": "figure",
    "caption": "caption",
    "footnote": "footnote",
    "page_header": "page_header",
    "page_footer": "page_footer",
    "document_index": "table",
}

DEFAULT_OCR_CMD = "/usr/bin/tesseract"
DEFAULT_TESSDATA_DIR = "/tmp/opencode/tessdata"
DEFAULT_OCR_LANG = ["vie"]
OCR_DPI = 300


def map_label_to_ir_type(label: str, is_table_item: bool = False) -> str:
    """Map a docling label to the canonical IR ``element_type``.

    Labels in :data:`DOCLING_LABEL_TO_IR_TYPE` are mapped; everything else
    (``text``, ``list_item``, ``table``, ``list``, ``unspecified``, ...) passes
    through verbatim. ``document_index`` maps to ``table`` only for TableItems.
    """
    if label == "document_index" and not is_table_item:
        return label
    return DOCLING_LABEL_TO_IR_TYPE.get(label, label)


def _resolve_tesseract_cmd(tesseract_cmd: str) -> str | None:
    """Resolve the configured tesseract command to an executable path.

    ``tesseract_cmd`` may be an absolute path (validated for existence +
    executability) or a bare name (resolved via PATH), and may carry trailing
    args (e.g. ``"tesseract -l vie"``) — only the first token is the
    executable. Returns None when no executable is found.
    """
    tokens = tesseract_cmd.strip().split()
    if not tokens:
        return None
    candidate = tokens[0]
    if os.path.isabs(candidate):
        return candidate if os.path.isfile(candidate) and os.access(candidate, os.X_OK) else None
    return shutil.which(candidate)


def check_ocr_readiness(
    tessdata_dir: str = DEFAULT_TESSDATA_DIR, tesseract_cmd: str = DEFAULT_OCR_CMD
) -> list[str]:
    """Fail-fast tesseract OCR readiness check (VNLRAG-21 spike gap #7).

    Validates the EXACT configured ``tesseract_cmd`` — never a PATH fallback:
    resolves it via :func:`_resolve_tesseract_cmd`, probes ``--version`` with
    the same resolved executable, and checks the tessdata layout
    (``vie.traineddata``, ``osd.traineddata``, ``configs/tsv``). Mirrors the
    pattern in ``suite_a.check_ocr_readiness`` but is local to the adapter
    (ingestion must not depend on the evaluation package). Returns a list of
    problems (empty = ready).
    """
    problems: list[str] = []
    executable = _resolve_tesseract_cmd(tesseract_cmd)
    if executable is None:
        problems.append(f"tesseract executable not found: {tesseract_cmd!r}")
    else:
        try:
            result = subprocess.run(
                [executable, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            result = None
        version = (
            (result.stdout or "").splitlines()[0].strip()
            if result is not None and (result.stdout or "").strip()
            else ""
        )
        if not version:
            problems.append("tesseract --version returned no parseable version")
        elif not version.lower().startswith("tesseract"):
            problems.append(f"unexpected tesseract --version output: {version!r}")
    tessdata = Path(tessdata_dir)
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


def _item_text(item: Any) -> str:
    """Text of a content item; empty string for container items (no ``text``)."""
    text = getattr(item, "text", None)
    return text if isinstance(text, str) else ""


def _node_page_no(node: Any, nodes_by_ref: dict[str, Any]) -> int | None:
    """First page number found in ``node``'s provenance, else first descendant's.

    Container items (GroupItem/ListGroup) expose no ``prov``; their page is
    derived from the first descendant that carries provenance.
    """
    prov = getattr(node, "prov", None)
    if prov:
        return prov[0].page_no
    for child in getattr(node, "children", None) or []:
        child_node = nodes_by_ref.get(child.cref)
        if child_node is not None:
            page_no = _node_page_no(child_node, nodes_by_ref)
            if page_no is not None:
                return page_no
    return None


def _item_page_no(item: Any, nodes_by_ref: dict[str, Any]) -> int:
    return _node_page_no(item, nodes_by_ref) or 1


def _item_bbox(item: Any, doc: Any, page_no: int) -> BoundingBox | None:
    """Normalized TOPLEFT bbox for ``item`` (prov[0]), or None.

    Docling PDF text-layer provenance is BOTTOMLEFT (top > bottom); OCR boxes
    are TOPLEFT. ``BoundingBox.to_top_left_origin(page_height)`` normalizes
    both routes to a single TOPLEFT convention (spike gap #1) so the IR
    invariant ``top < bottom`` holds for every element with a bbox.
    """
    prov = getattr(item, "prov", None)
    if not prov or prov[0].bbox is None:
        return None
    page_model = doc.pages.get(page_no)
    page_height = page_model.size.height if page_model is not None else None
    page_width = page_model.size.width if page_model is not None else None
    if page_height is None:
        return None  # cannot normalize without page height
    normalized = prov[0].bbox.to_top_left_origin(page_height)
    return BoundingBox(
        left=normalized.l,
        top=normalized.t,
        right=normalized.r,
        bottom=normalized.b,
        page_height=page_height,
        page_width=page_width,
    )


def _item_table_html(item: Any, doc: Any) -> str | None:
    """HTML export of a table item (gap #5): ``export_to_html`` not markdown.

    Applies to TableItems labelled ``table`` or ``document_index`` (a TOC
    rendered as a table). Non-table items yield None. An export failure is
    FATAL: the parse aborts with a clear item/self_ref context so a detected
    table can never silently lose its HTML (VNLRAG-129 oracle finding 3).
    """
    label = item.label.value if item.label is not None else None
    if label not in ("table", "document_index") or not hasattr(item, "export_to_html"):
        return None
    try:
        exported = item.export_to_html(doc)
    except Exception as exc:
        raise RuntimeError(
            "table HTML export failed for docling item "
            f"{item.self_ref!r} (label={label!r}, type={type(item).__name__}): {exc}"
        ) from exc
    return exported if exported.strip() else None


def _item_raw_reference(
    item: Any, index: int, page_no: int, prov_list: list[Any]
) -> dict[str, Any]:
    """Provenance record for one element (gaps #3 and #6).

    ``docling_self_ref`` is the stable JSON-pointer id; ``prov[0]`` drives the
    IR page/bbox while ``prov_count``/``prov_pages`` record the full
    provenance span so multi-prov items are never silently truncated.
    """
    prov = prov_list[0] if prov_list else None
    return {
        "docling_self_ref": item.self_ref,
        "docling_item_index": index,
        "docling_item_type": type(item).__name__,
        "docling_label": item.label.value if item.label is not None else None,
        "prov_page_no": page_no,
        "charspan": list(prov.charspan) if prov is not None and prov.charspan else None,
        "prov_count": len(prov_list),
        "prov_pages": sorted({p.page_no for p in prov_list}),
    }


def docling_document_to_ir(
    doc: Any,
    source_object_key: str,
    parsed_document_id: str,
    document_id: str,
    parse_started_at: datetime,
) -> ParsedDocument:
    """Map a parsed :class:`DoclingDocument` onto the canonical IR.

    Pure conversion (no PDF/converter involved) so it is unit-testable on
    synthetic DoclingDocuments; :meth:`DoclingAdapter.parse` is the
    PDF-entrypoint that feeds it the converter output.
    """
    import docling as _docling

    parser_version = f"docling-{_docling.__version__}"

    items = list(doc.iterate_items(with_groups=True))
    nodes_by_ref: dict[str, Any] = {item.self_ref: item for item, _level in items}
    # self_ref (JSON pointer) -> IR element_id over the whole node tree so a
    # parent cref resolves even when the parent is a container item.
    element_id_by_ref: dict[str, str] = {}
    for index, (item, _level) in enumerate(items):
        element_id_by_ref[item.self_ref] = f"p{_item_page_no(item, nodes_by_ref)}-e{index}"

    elements_by_page: dict[int, list[DocumentElement]] = {}
    for index, (item, _level) in enumerate(items):
        prov_list = list(getattr(item, "prov", None) or [])
        page_no = _item_page_no(item, nodes_by_ref)
        element_id = f"p{page_no}-e{index}"
        label = item.label.value if item.label is not None else None
        is_table_item = hasattr(item, "export_to_html")
        parent = item.parent
        parent_element_id = element_id_by_ref.get(parent.cref) if parent is not None else None
        element = DocumentElement(
            element_id=element_id,
            element_type=map_label_to_ir_type(label or "text", is_table_item=is_table_item),
            text=_item_text(item),
            page_number=page_no,
            bbox=_item_bbox(item, doc, page_no),
            reading_order=index,
            parent_element_id=parent_element_id,
            table_html=_item_table_html(item, doc),
            source_parser=PARSER_NAME,
            parser_version=parser_version,
            parser_confidence=None,
            raw_reference=_item_raw_reference(item, index, page_no, prov_list),
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
        parser=PARSER_NAME,
        parser_version=parser_version,
        ir_schema_version=IR_SCHEMA_VERSION,
        source_object_key=source_object_key,
        pages=pages,
        parse_started_at=parse_started_at,
        parse_completed_at=datetime.now(UTC),
        quality_report={},
    )


def _build_pipeline_options(
    *,
    ocr_enabled: bool,
    dpi: int,
    tesseract_cmd: str,
    tessdata_dir: str,
    lang: list[str],
) -> Any:
    """Build the docling PDF pipeline options for this parse.

    ``dpi`` is wired to ``PdfPipelineOptions.images_scale`` as ``dpi / 72.0``:
    docling 2.118.1's standard PDF pipeline rasterizes page/table images at
    ``dpi = int(72 * images_scale)`` (``standard_pdf_pipeline.py``), so the
    scale is exactly what the package expects for a requested DPI. Applied on
    both routes (the field governs pipeline image resolution, not just OCR).
    """
    from docling.datamodel.pipeline_options import PdfPipelineOptions, TesseractCliOcrOptions

    options = PdfPipelineOptions()
    options.do_ocr = ocr_enabled
    options.do_table_structure = True
    options.images_scale = dpi / 72.0
    if ocr_enabled:
        options.ocr_options = TesseractCliOcrOptions(
            tesseract_cmd=tesseract_cmd,
            path=tessdata_dir,
            lang=list(lang),
            psm=OCR_PSM,
        )
    return options


class DoclingAdapter:
    """Production Docling → canonical IR adapter (VNLRAG-129).

    A stateless adapter: each :meth:`parse` builds its own converter, so a
    call is fully self-contained (callers wanting a shared, model-loaded
    converter should construct one per ``parse`` via the module helpers).
    """

    def parse(
        self,
        pdf_path: str,
        source_object_key: str,
        parsed_document_id: str,
        document_id: str,
        ocr_enabled: bool = False,
        dpi: int = OCR_DPI,
        tesseract_cmd: str = DEFAULT_OCR_CMD,
        tessdata_dir: str = DEFAULT_TESSDATA_DIR,
        lang: list[str] = DEFAULT_OCR_LANG,  # noqa: B006 - caller-owned mutable default per spec
    ) -> ParsedDocument:
        """Parse ``pdf_path`` into a canonical :class:`ParsedDocument`.

        ``source_object_key`` is the MinIO object key recorded on the IR (gap
        #8) — never derived from the local path. ``dpi`` is wired to docling's
        resolution control (``PdfPipelineOptions.images_scale = dpi / 72.0``;
        docling 2.118.1 rasterizes at ``72 * images_scale`` DPI), so the
        parameter actually takes effect — no caller-side rendering is
        required. When ``ocr_enabled`` (scan route) a tesseract readiness
        check runs first and fails fast on any problem.
        """
        from docling.datamodel.base_models import ConversionStatus
        from docling.document_converter import DocumentConverter, InputFormat, PdfFormatOption

        if ocr_enabled:
            problems = check_ocr_readiness(tessdata_dir=tessdata_dir, tesseract_cmd=tesseract_cmd)
            if problems:
                raise RuntimeError("docling OCR not ready: " + "; ".join(problems))

        options = _build_pipeline_options(
            ocr_enabled=ocr_enabled,
            dpi=dpi,
            tesseract_cmd=tesseract_cmd,
            tessdata_dir=tessdata_dir,
            lang=lang,
        )
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )

        started_at = datetime.now(UTC)
        result = converter.convert(pdf_path)
        if result.status != ConversionStatus.SUCCESS:
            raise RuntimeError(f"docling conversion failed for {pdf_path}: {result.status}")
        return docling_document_to_ir(
            doc=result.document,
            source_object_key=source_object_key,
            parsed_document_id=parsed_document_id,
            document_id=document_id,
            parse_started_at=started_at,
        )
