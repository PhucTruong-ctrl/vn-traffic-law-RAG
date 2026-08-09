"""MinerU → Canonical Document IR adapter (VNLRAG-130, W2).

Maps MinerU pipeline JSON output (``content_list``) onto the frozen canonical
Document IR (``app.ingestion.document_ir``; contract
``docs/canonical-document-ir-design.md``). The mapping layer is pure and
unit-testable: it consumes the JSON artifacts MinerU writes, NOT a PDF. The
real pipeline backend is executed by :func:`run_mineru` (a subprocess call to
``python -m mineru.cli.client`` — the module entrypoint behind the ``mineru``
console script), which returns the produced flat ``*_content_list.json`` path
that :meth:`MinerUAdapter.parse` consumes (VNLRAG-131 finding #5).

Input schema (verified against the installed mineru 3.4.4 sources, 2026-08-09):
  * ``{pdf}_content_list.json`` is a BARE JSON ARRAY of items — the CLI writes
    ``json.dumps(content_list, ...)`` where ``content_list`` is the list built
    by ``union_make`` (``mineru/backend/pipeline/pipeline_middle_json_mkcontent.py``).
    The ticket's ``{"content_list": [...]}`` wrapper form is accepted too.
  * item fields: ``type`` (``text`` | ``image`` | ``table`` | ``chart`` |
    ``equation`` | ``list`` | ``code`` | ``header``/``footer``/...), ``text``
    (text-like items; absent on visual items), ``bbox`` ``[x0, y0, x1, y1]``
    emitted by ``_build_bbox`` as page-PERMILLE (0..1000) coordinates,
    ``page_idx`` (0-based). Tables carry the HTML under ``table_body`` (the
    ``BlockType.TABLE_BODY`` key) plus ``table_caption``/``table_footnote``
    lists; images carry ``img_path`` plus ``image_caption``/``image_footnote``
    lists; lists carry ``list_items``.

  Real MinerU 3.4.4 JSON quirk (verified on real output, 2026-08-09): ``bbox``
  and ``page_idx`` are serialized as STRINGS (``"bbox": "[89, 53, 877, 85]"``,
  ``"page_idx": "0"``). Both the list/tuple form and the string form are
  accepted.

Coordinate-origin and unit assumption (stated): MinerU ``bbox``/``box`` values
are TOPLEFT-origin ``[x0, y0, x1, y1]`` page-PERMILLE (0..1000)
(``top < bottom``) — verified in ``_build_bbox``
(``int(x0*1000/page_width), int(y0*1000/page_height), ...``; layout-model pixel
space is top-left), so the Docling adapter's recommended TOPLEFT normalization
is a no-op here. The v2 canonical IR requires NORMALIZED_PAGE coordinates, so
every bbox is scaled by ``/1000`` into 0..1 and the raw permille values are
preserved under ``raw_reference["bbox_permille"]``. MinerU content_list items
carry no page size, so ``page_height``/``page_width`` are None.

Conventions shared with the Docling adapter (spike VNLRAG-21):
  * ``element_id`` = ``p{page}-e{global-index}``; ``reading_order`` = global
    0-based index.
  * ``parent_element_id`` is always None: content_list is flat (each item is
    one layout paragraph), so no text_span→text hierarchy is derivable in v1.
  * ``page_number`` = ``page_idx + 1`` (MinerU is 0-based, IR is 1-based).
  * ``raw_reference`` carries ``mineru_item_index`` / ``mineru_item_type`` /
    ``mineru_page_idx`` (raw JSON values), plus ``mineru_line_idx`` /
    ``mineru_item_id`` when the JSON carries them — the spike's recommended
    stable-id provenance.
  * ``parser_version`` = ``mineru-<version>``; version resolution:
    ``mineru.__version__`` (absent in 3.4.4) → installed distribution metadata
    → injected ``parser_version`` → ``"mineru-unknown"``.
"""

import ast
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from html import escape
from pathlib import Path
from typing import Any

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage

IR_SCHEMA_VERSION = "document-ir-v2"

# Explicit MinerU content_list type → canonical IR element_type mapping
# (spike VNLRAG-21 §5 rec #3). Unknown types pass through verbatim so a future
# MinerU type is never silently dropped.
_TYPE_MAPPING: dict[str, str] = {
    "text": "paragraph",
    "text_span": "paragraph",
    "abstract": "paragraph",
    "title": "heading",
    "table": "table",
    "simple_table": "table",
    "complex_table": "table",
    "image": "figure",
    "chart": "figure",
    "equation": "equation",
    "interline_equation": "equation",
    "list": "list_item",
    "ref_text": "list_item",
    "code": "code",
    "header": "page_header",
    "page_header": "page_header",
    "footer": "page_footer",
    "page_footer": "page_footer",
    "page_number": "page_number",
    "footnote": "footnote",
    "page_footnote": "footnote",
    "aside_text": "aside_text",
    "page_aside_text": "aside_text",
}

_TABLE_TYPES = {"table", "simple_table", "complex_table"}

_VISUAL_TEXT_KEYS = (
    "image_caption",
    "image_footnote",
    "table_caption",
    "table_footnote",
    "chart_caption",
    "chart_footnote",
)


class MineruExecutionError(RuntimeError):
    """The MinerU pipeline failed to run or produced no IR-consumable output.

    Raised by :func:`run_mineru` when the ``mineru`` package is unavailable in
    this environment, when the CLI subprocess exits nonzero (the message
    carries the stderr tail), when the subprocess times out, or when the run
    succeeded but produced no ``*_content_list.json`` artifact.
    """


class MinerUAdapter:
    """Maps MinerU ``content_list`` JSON onto the canonical ParsedDocument IR.

    The mapping layer never touches a PDF: it reads the ``content_list.json``
    artifact (or the equivalent dict) that the MinerU pipeline writes.
    """

    def parse(
        self,
        mineru_json_path: str | dict[str, Any],
        source_object_key: str,
        parsed_document_id: str,
        document_id: str,
        parser_version: str | None = None,
    ) -> ParsedDocument:
        """Build a :class:`ParsedDocument` from MinerU content_list JSON.

        Args:
            mineru_json_path: Path to a MinerU ``*_content_list.json`` file, a
                ``{"content_list": [...]}`` dict, or the bare content list.
            source_object_key: MinIO object key of the source PDF (injected by
                the pipeline, per spike VNLRAG-21 §5 rec #7).
            parsed_document_id: UUID of this parse (not the legal document_id).
            document_id: Legal document_id from the manifest.
            parser_version: Full ``mineru-<version>`` string override; when
                None the adapter resolves the installed MinerU version.
        """
        items = _load_content_list(mineru_json_path)
        resolved_parser_version = parser_version or f"mineru-{_mineru_version()}"
        started_at = datetime.now(UTC)

        elements_by_page: dict[int, list[DocumentElement]] = {}
        for index, item in enumerate(items):
            page_no = _item_page_number(item)
            element_type = _map_element_type(item)
            bbox, bbox_permille = _item_bbox(item)
            element = DocumentElement(
                element_id=f"p{page_no}-e{index}",
                element_type=element_type,
                text=_item_text(item),
                page_number=page_no,
                bbox=bbox,
                reading_order=index,
                parent_element_id=None,
                table_html=_item_table_html(item),
                source_parser="MINERU",
                parser_version=resolved_parser_version,
                parser_confidence=None,
                raw_reference=_item_raw_reference(item, index, bbox_permille=bbox_permille),
            )
            elements_by_page.setdefault(page_no, []).append(element)

        pages = [
            ParsedPage(
                page_number=page_no,
                width=None,
                height=None,
                text=_page_text(elements),
                elements=elements,
            )
            for page_no, elements in sorted(elements_by_page.items())
        ]
        return ParsedDocument(
            parsed_document_id=parsed_document_id,
            document_id=document_id,
            parser="MINERU",
            parser_version=resolved_parser_version,
            ir_schema_version=IR_SCHEMA_VERSION,
            source_object_key=source_object_key,
            pages=pages,
            parse_started_at=started_at,
            parse_completed_at=datetime.now(UTC),
            quality_report={},
        )

    def parse_pdf(
        self,
        pdf_path: str,
        output_dir: str,
        source_object_key: str,
        parsed_document_id: str,
        document_id: str,
        *,
        method: str = "auto",
        lang: str | None = None,
        start_page: int | None = None,
        end_page: int | None = None,
        parser_version: str | None = None,
    ) -> ParsedDocument:
        """End-to-end convenience: run the pipeline, then map the IR.

        Executes the real MinerU pipeline via :func:`run_mineru`, then maps
        the produced flat ``content_list.json`` through :meth:`parse`
        (``source_parser`` stays ``"MINERU"``, provenance/bbox handling
        unchanged). Used by Suite A P2 / ingestion wiring (VNLRAG-131 #6).
        ``parser_version`` overrides the resolved ``mineru-<version>`` when
        provided; the other kwargs forward to :func:`run_mineru`.
        """
        content_list_path = run_mineru(
            pdf_path,
            output_dir,
            method=method,
            lang=lang,
            start_page=start_page,
            end_page=end_page,
        )
        return self.parse(
            content_list_path,
            source_object_key=source_object_key,
            parsed_document_id=parsed_document_id,
            document_id=document_id,
            parser_version=parser_version,
        )


def run_mineru(
    pdf_path: str,
    output_dir: str,
    *,
    method: str = "auto",
    backend: str = "pipeline",
    lang: str | None = None,
    start_page: int | None = None,
    end_page: int | None = None,
    timeout_seconds: int = 3600,
    env_extra: dict[str, str] | None = None,
) -> str:
    """Run the REAL MinerU pipeline on ``pdf_path`` via the CLI (VNLRAG-131/#5).

    Executes ``python -m mineru.cli.client`` (the same module entrypoint the
    ``mineru`` console script wraps; ``python -m mineru`` itself has no
    ``__main__``) in a subprocess. ``CUDA_VISIBLE_DEVICES=""`` is always set
    (CPU-only pipeline) and merged with ``env_extra``. Returns the path of the
    produced flat ``*_content_list.json`` artifact — the format
    :meth:`MinerUAdapter.parse` consumes.

    The pipeline additionally writes a ``*_content_list_v2.json`` sibling, but
    that file is a per-page NESTED structure (a list of page-lists whose items
    carry ``content.paragraph_content`` spans and no ``page_idx``) which is
    NOT the IR mapping input; the flat ``*_content_list.json`` is returned
    instead.

    Args:
        pdf_path: Local path of the PDF to parse.
        output_dir: Base output directory (the CLI writes
            ``<output_dir>/<docname>/txt/``).
        method: ``auto`` | ``txt`` (born-digital) | ``ocr`` (scans).
        backend: ``pipeline`` (the only backend the VNLRAG-130 mapping is
            verified against).
        lang: Optional document language hint (improves OCR accuracy;
            ``-l``).
        start_page/end_page: Optional 0-based page range (``-s``/``-e``).
        timeout_seconds: Subprocess timeout; the first pipeline run downloads
            models (can take minutes).
        env_extra: Extra environment variables merged over
            ``CUDA_VISIBLE_DEVICES=""`` (caller values win).

    Raises:
        MineruExecutionError: if the ``mineru`` module is not importable, the
            CLI exits nonzero (message includes the stderr tail), the
            subprocess times out, or no ``*_content_list.json`` is produced.
    """
    if not _mineru_module_available():
        raise MineruExecutionError(
            "MinerU is not installed in this environment "
            "(pip install 'mineru[pipeline]>=3.4,<3.5'); cannot run the "
            f"pipeline for {pdf_path!r}"
        )

    command = [
        sys.executable,
        "-m",
        "mineru.cli.client",
        "-p",
        str(pdf_path),
        "-o",
        str(output_dir),
        "-b",
        backend,
        "-m",
        method,
    ]
    if lang:
        command += ["-l", lang]
    if start_page is not None:
        command += ["-s", str(start_page)]
    if end_page is not None:
        command += ["-e", str(end_page)]

    env = dict(os.environ)
    env["CUDA_VISIBLE_DEVICES"] = ""
    if env_extra:
        env.update(env_extra)

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=env,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise MineruExecutionError(
            f"mineru pipeline timed out after {timeout_seconds}s for {pdf_path!r}"
        ) from exc

    if completed.returncode != 0:
        raise MineruExecutionError(
            f"mineru pipeline failed (rc={completed.returncode}): {_stderr_tail(completed.stderr)}"
        )

    content_list = _find_content_list_path(pdf_path, output_dir)
    if content_list is None:
        raise MineruExecutionError(
            f"no content_list JSON produced under {output_dir!r} for {pdf_path!r}"
        )
    return str(content_list)


def _mineru_module_available() -> bool:
    """True when the ``mineru`` package is importable in this environment.

    Lazy import probe so the adapter module still imports (and the pure
    mapping layer stays testable) when MinerU is not installed.
    """
    import importlib.util

    return importlib.util.find_spec("mineru") is not None


def _find_content_list_path(pdf_path: str, output_dir: str) -> Path | None:
    """Resolve the flat ``*_content_list.json`` the CLI wrote for ``pdf_path``.

    MinerU writes ``<output_dir>/<pdf_stem>/txt/<pdf_stem>_content_list.json``
    (verified on the real 3.4.4 pipeline, 2026-08-09), so the artifact is
    resolved from the INPUT PDF STEM — never from a lexicographically-first
    glob, which could return an old or unrelated document's output when the
    output dir is reused or shared with concurrent runs.

    Resolution order:
      1. the exact derived path ``<output_dir>/<pdf_stem>/txt/<pdf_stem>_content_list.json``;
      2. a recursive fallback glob of ``*_content_list.json`` filtered to files
         whose stem matches the input PDF stem (covers a changed docname
         directory layout while still refusing unrelated documents);
      3. None — the caller raises :class:`MineruExecutionError`.

    The ``<stem>_content_list_v2.json`` sibling is a per-page NESTED structure
    (list of page-lists, items carry ``content.*_content`` spans and no
    ``page_idx``) which :meth:`MinerUAdapter.parse` does not consume — it is
    deliberately ignored (and never collides with the ``*_content_list.json``
    glob).
    """
    pdf_stem = Path(pdf_path).stem
    derived = Path(output_dir) / pdf_stem / "txt" / f"{pdf_stem}_content_list.json"
    if derived.is_file():
        return derived
    prefix = f"{pdf_stem}_content_list.json"
    for match in sorted(Path(output_dir).rglob("*_content_list.json")):
        if match.name.startswith(prefix):
            return match
    return None


def _stderr_tail(stderr: str) -> str:
    """Last non-empty stderr lines (diagnostics tail), capped at 2000 chars."""
    lines = [line for line in stderr.splitlines() if line.strip()]
    return "\n".join(lines[-20:])[:2000] or "(no stderr output)"


def _mineru_version() -> str:
    """Resolve the installed MinerU version ('' → 'unknown' fallback).

    ``mineru.__version__`` is absent in 3.4.4, so this falls back to the
    installed distribution metadata — the same convention as the Docling
    adapter (``_pkg_version``). The import is lazy/dynamic so the adapter
    imports without MinerU installed.
    """
    import importlib

    try:
        mineru_module = importlib.import_module("mineru")
    except ImportError:
        mineru_module = None
    version = getattr(mineru_module, "__version__", "") if mineru_module is not None else ""
    if version:
        return version
    try:
        from importlib.metadata import version as pkg_version

        return pkg_version("mineru")
    except Exception:
        return "unknown"


def _load_content_list(payload: Any) -> list[dict[str, Any]]:
    """Normalize a content_list file path / dict / bare list to item dicts."""
    if isinstance(payload, str):
        payload = json.loads(Path(payload).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict):
        content_list = payload.get("content_list")
        if not isinstance(content_list, list):
            raise ValueError(
                "MinerU JSON must be a list of content items or a dict with a "
                f"'content_list' list key (got: {type(content_list).__name__})"
            )
        items = content_list
    else:
        raise ValueError(
            "mineru_json_path must be a JSON file path, a content_list list, or "
            f"a {{'content_list': [...]}} dict (got: {type(payload).__name__})"
        )
    normalized: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError(
                f"MinerU content_list items must be dicts (got: {type(item).__name__})"
            )
        normalized.append(item)
    return normalized


def _item_page_number(item: dict[str, Any]) -> int:
    """1-based IR page number: ``page_idx`` (0-based) + 1, else explicit ``page_number``."""
    page_idx = item.get("page_idx")
    if page_idx is not None:
        return int(page_idx) + 1
    page_number = item.get("page_number")
    if page_number is not None:
        return int(page_number)
    return 1


def _map_element_type(item: dict[str, Any]) -> str:
    mineru_type = str(item.get("type", "text"))
    if mineru_type == "text":
        text_level = item.get("text_level")
        if text_level is not None and int(text_level) > 0:
            # MinerU pipeline emits titles as type="text" + text_level.
            return "heading"
    return _TYPE_MAPPING.get(mineru_type, mineru_type)


def _item_text(item: dict[str, Any]) -> str:
    text = item.get("text")
    if isinstance(text, str):
        return text
    parts: list[str] = []
    for key in _VISUAL_TEXT_KEYS:
        value = item.get(key)
        if isinstance(value, list):
            parts.extend(str(part) for part in value if str(part))
        elif value:
            parts.append(str(value))
    content = item.get("content")
    if isinstance(content, str) and content.strip():
        parts.append(content)
    list_items = item.get("list_items")
    if isinstance(list_items, list):
        parts.extend(str(part) for part in list_items if str(part))
    return "\n".join(parts)


def _parse_bbox_coords(raw: Any) -> list[float] | None:
    """Parse a MinerU ``bbox``/``box`` value into ``[x0, y0, x1, y1]`` floats.

    Real MinerU 3.4.4 JSON serializes ``bbox`` as a STRING
    (``"[89, 53, 877, 85]"``); the list/tuple form is accepted too. Returns
    None for anything unparseable.
    """
    if isinstance(raw, str):
        text = raw.strip()
        if not (text.startswith("[") and text.endswith("]")):
            return None
        try:
            values = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            return None
        if not isinstance(values, (list, tuple)):
            return None
        raw = values
    if not isinstance(raw, (list, tuple)) or len(raw) < 4:
        return None
    try:
        return [float(value) for value in raw[:4]]
    except (TypeError, ValueError):
        return None


def _item_bbox(item: dict[str, Any]) -> tuple[BoundingBox | None, list[float] | None]:
    """Normalized NORMALIZED_PAGE bbox + raw permille coords for ``item``.

    MinerU emits TOPLEFT-origin page-PERMILLE (0..1000) coordinates; v2
    requires NORMALIZED_PAGE (0..1), so each value is scaled by ``/1000``. The
    raw permille ``[x0, y0, x1, y1]`` is returned for
    ``raw_reference["bbox_permille"]``. ``(None, None)`` when the item carries
    no parseable bbox.
    """
    raw = item.get("bbox") if item.get("bbox") is not None else item.get("box")
    coords = _parse_bbox_coords(raw)
    if coords is None:
        return None, None
    left, top, right, bottom = (value / 1000.0 for value in coords)
    return BoundingBox(left=left, top=top, right=right, bottom=bottom), coords


def _item_table_html(item: dict[str, Any]) -> str | None:
    if str(item.get("type", "")).lower() not in _TABLE_TYPES:
        return None
    html = item.get("html")
    if isinstance(html, str) and html.strip():
        return html
    table_body = item.get("table_body")
    if isinstance(table_body, str) and table_body.strip():
        return table_body
    cells = item.get("cells")
    if isinstance(cells, list) and cells:
        return _cells_to_html(cells)
    return None


def _cells_to_html(cells: list[Any]) -> str:
    rows = ["<table>"]
    for row in cells:
        cells_row = "".join(f"<td>{_escape_cell(cell)}</td>" for cell in row)
        rows.append(f"<tr>{cells_row}</tr>")
    rows.append("</table>")
    return "".join(rows)


def _escape_cell(cell: Any) -> str:
    return escape(str(cell), quote=True)


def _item_raw_reference(
    item: dict[str, Any], index: int, bbox_permille: list[float] | None = None
) -> dict[str, Any]:
    reference: dict[str, Any] = {
        "mineru_item_index": index,
        "mineru_item_type": item.get("type"),
        "mineru_page_idx": item.get("page_idx"),
    }
    if bbox_permille is not None:
        # v2: canonical bbox is NORMALIZED_PAGE (0..1); the raw page-permille
        # coordinates are preserved here for provenance/traceability.
        reference["bbox_permille"] = bbox_permille
    line_idx = item.get("line_idx")
    if line_idx is not None:
        reference["mineru_line_idx"] = line_idx
    stable_id = item.get("id") if item.get("id") is not None else item.get("item_id")
    if stable_id is not None:
        reference["mineru_item_id"] = stable_id
    return reference


def _page_text(elements: list[DocumentElement]) -> str | None:
    return "\n".join(element.text for element in elements if element.text.strip()) or None
