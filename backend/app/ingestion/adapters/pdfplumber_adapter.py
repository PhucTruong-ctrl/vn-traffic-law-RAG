"""Offline searchable-PDF adapter based on pdfplumber.

This is intentionally a text-layer parser: it never performs OCR.  Table regions
are removed from text extraction and emitted once as Markdown, while every IR
element retains page, reading order, bbox, and raw pdfplumber provenance.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypeAlias

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage

IR_SCHEMA_VERSION = "document-ir-v2"
PARSER_NAME = "PDFPLUMBER"

_VIET_LOWER = (
    "abcdefghijklmnopqrstuvwxyzáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵđ"
)
_HEADING_RE = re.compile(r"^(?:Chương|Phần|Mục|Điều|Khoản|Phụ\s+lục)\b|^\d+\.\s+[A-ZĐÀÁẠẢÃ]")
_PAGE_RE = re.compile(r"^(?:trang\s+)?\d+(?:\s*/\s*\d+)?$", re.I)
_NOISE_RE = re.compile(r"about:blank|thư viện pháp luật|mã tra cứu", re.I)
_DATE_RE = re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4},.*about:blank$", re.I)
_END_RE = re.compile(r"[A-Za-zÀ-ỹĐđ,;]$")
BBox: TypeAlias = tuple[float, float, float, float]
LineEntry: TypeAlias = tuple[str, BBox | None]


class SearchableTextRequiredError(RuntimeError):
    """Raised when a PDF has no searchable text layer; this adapter does no OCR."""


def _norm(value: str) -> str:
    return " ".join(unicodedata.normalize("NFC", value).strip().split())


def _is_noise(line: str) -> bool:
    return bool(_PAGE_RE.fullmatch(line) or _NOISE_RE.search(line) or _DATE_RE.fullmatch(line))


def _clean_line_entries(
    entries: list[LineEntry], repeated: Counter[str] | None = None
) -> list[LineEntry]:
    """Clean text entries without losing the bbox paired with each line."""
    repeated = repeated or Counter()
    kept: list[LineEntry] = []
    for raw, raw_box in entries:
        line = _norm(raw)
        if not line or _is_noise(line) or repeated[line.casefold()] > 1:
            continue
        line = re.sub(r"(\.{5,}|_{5,})", " [Cần điền thông tin] ", line)
        if line == "[Cần điền thông tin]":
            continue
        kept.append((line, raw_box))
    merged: list[LineEntry] = []
    for line, raw_box in kept:
        if (
            merged
            and _END_RE.search(merged[-1][0][-1:])
            and line[0] in _VIET_LOWER
            and not _HEADING_RE.match(line)
        ):
            previous, previous_box = merged[-1]
            if previous_box and raw_box:
                raw_box = (
                    min(previous_box[0], raw_box[0]),
                    min(previous_box[1], raw_box[1]),
                    max(previous_box[2], raw_box[2]),
                    max(previous_box[3], raw_box[3]),
                )
            else:
                raw_box = previous_box or raw_box
            merged[-1] = (previous + " " + line, raw_box)
        else:
            merged.append((line, raw_box))
    return merged


def clean_lines(lines: list[str], repeated: Counter[str] | None = None) -> list[str]:
    """Clean extracted lines, preserving headings and joining only continuations."""
    return [line for line, _ in _clean_line_entries([(line, None) for line in lines], repeated)]


def table_to_markdown(table: list[list[Any]] | None) -> str:
    """Render a pdfplumber table without dropping merged-cell values."""
    rows = [
        list(row)
        for row in (table or [])
        if any(cell is not None and str(cell).strip() for cell in row)
    ]
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    previous = [""] * width
    rendered: list[str] = []
    for row in rows:
        cells: list[str] = []
        for index, cell in enumerate(row):
            value = _norm(str(cell or "")).replace("|", r"\|")
            if not value:
                value = previous[index]
            else:
                previous[index] = value
            cells.append(value)
        rendered.append("| " + " | ".join(cells) + " |")
    rendered.insert(1, "|" + "|".join(["---"] * width) + "|")
    return "\n".join(rendered)


def _bbox(
    x0: float, top: float, x1: float, bottom: float, width: float, height: float
) -> BoundingBox | None:
    if width <= 0 or height <= 0:
        return None
    return BoundingBox(
        left=max(0.0, min(1.0, x0 / width)),
        top=max(0.0, min(1.0, top / height)),
        right=max(0.0, min(1.0, x1 / width)),
        bottom=max(0.0, min(1.0, bottom / height)),
        page_width=width,
        page_height=height,
    )


def _words_lines(
    words: list[dict[str, Any]],
) -> list[LineEntry]:
    groups: list[list[dict[str, Any]]] = []
    for word in sorted(
        words, key=lambda item: (float(item.get("top", 0)), float(item.get("x0", 0)))
    ):
        if groups and abs(float(word.get("top", 0)) - float(groups[-1][0].get("top", 0))) <= 2:
            groups[-1].append(word)
        else:
            groups.append([word])
    result: list[LineEntry] = []
    for group in groups:
        text = " ".join(str(item.get("text", "")) for item in group)
        result.append(
            (
                text,
                (
                    min(float(x.get("x0", 0)) for x in group),
                    min(float(x.get("top", 0)) for x in group),
                    max(float(x.get("x1", 0)) for x in group),
                    max(float(x.get("bottom", 0)) for x in group),
                ),
            )
        )
    return result


class PdfPlumberAdapter:
    """Map a searchable PDF directly into the canonical Document IR."""

    def parse(
        self,
        pdf_path: str | Path,
        *,
        source_object_key: str,
        parsed_document_id: str,
        document_id: str,
        parser_version: str = "pdfplumber-0",
    ) -> ParsedDocument:
        try:
            import pdfplumber
        except ImportError as exc:
            raise RuntimeError("pdfplumber is required for the PDFPLUMBER adapter") from exc
        started = datetime.now(UTC)
        path = Path(pdf_path)
        page_data: list[
            tuple[
                Any,
                list[tuple[str, tuple[float, float, float, float] | None]],
                list[tuple[str, tuple[float, float, float, float]]],
            ]
        ] = []
        searchable = False
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                tables = list(page.find_tables())
                boxes: list[BBox] = [
                    (
                        float(table.bbox[0]),
                        float(table.bbox[1]),
                        float(table.bbox[2]),
                        float(table.bbox[3]),
                    )
                    for table in tables
                ]

                def outside_table(obj: dict[str, Any], table_boxes: list[BBox] = boxes) -> bool:
                    return not any(
                        x0 - 2 <= obj.get("x0", 0) <= x1 + 2
                        and top - 2 <= obj.get("top", 0) <= bottom + 2
                        for x0, top, x1, bottom in table_boxes
                    )

                filtered = page.filter(outside_table) if boxes else page
                words = filtered.extract_words() if hasattr(filtered, "extract_words") else []
                if words:
                    searchable = True
                    lines = _words_lines(words)
                else:
                    text = filtered.extract_text() or ""
                    searchable = searchable or bool(text.strip())
                    lines = [(line, None) for line in text.splitlines()]
                table_rows: list[tuple[str, BBox]] = []
                for table in tables:
                    md = table_to_markdown(table.extract())
                    if md:
                        table_rows.append(
                            (
                                md,
                                (
                                    float(table.bbox[0]),
                                    float(table.bbox[1]),
                                    float(table.bbox[2]),
                                    float(table.bbox[3]),
                                ),
                            )
                        )
                page_data.append((page, lines, table_rows))
        if not searchable:
            raise SearchableTextRequiredError(
                f"no searchable text layer in {path}; quarantined, OCR is not performed"
            )
        counts = Counter(
            _norm(line).casefold()
            for page, lines, _ in page_data
            for line, raw_box in lines
            if _norm(line)
            and raw_box
            and (raw_box[1] <= float(page.height) * 0.15 or raw_box[3] >= float(page.height) * 0.85)
        )
        pages: list[ParsedPage] = []
        order = 0
        for page_number, (page, lines, table_rows) in enumerate(page_data, 1):
            width, height = float(page.width), float(page.height)
            records: list[tuple[float, str, str, tuple[float, float, float, float] | None]] = []
            cleaned = _clean_line_entries(lines, counts)
            for index, (text, raw_box) in enumerate(cleaned):
                records.append(
                    ((raw_box[1] if raw_box else float(index)), text, "paragraph", raw_box)
                )
            for md, raw_box in table_rows:
                records.append((raw_box[1], md, "table", raw_box))
            records.sort(key=lambda item: item[0])
            elements: list[DocumentElement] = []
            for _, text, kind, raw_box in records:
                box = _bbox(*raw_box, width, height) if raw_box else None
                elements.append(
                    DocumentElement(
                        element_id=f"p{page_number}-e{order}",
                        element_type=kind,
                        text=text,
                        page_number=page_number,
                        bbox=box,
                        reading_order=order,
                        parent_element_id=None,
                        table_html=text if kind == "table" else None,
                        source_parser=PARSER_NAME,
                        parser_version=parser_version,
                        parser_confidence=None,
                        raw_reference={
                            "pdfplumber_page": page_number,
                            "bbox_points": list(raw_box) if raw_box else None,
                        },
                    )
                )
                order += 1
            page_text = "\n".join(element.text for element in elements) or None
            pages.append(
                ParsedPage(
                    page_number=page_number,
                    width=width,
                    height=height,
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
            parse_started_at=started,
            parse_completed_at=datetime.now(UTC),
            quality_report={
                "conversion_status": "SUCCESS",
                "text_layer": True,
                "tables": sum(
                    1
                    for page in pages
                    for element in page.elements
                    if element.element_type == "table"
                ),
            },
        )


__all__ = ["PdfPlumberAdapter", "SearchableTextRequiredError", "clean_lines", "table_to_markdown"]
