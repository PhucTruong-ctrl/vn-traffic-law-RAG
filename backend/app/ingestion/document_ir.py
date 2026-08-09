"""Canonical Document IR schema (VNLRAG-128).

Parser-neutral intermediate representation owned by the project (FR-02).
The contract is frozen at ``docs/canonical-document-ir-design.md`` (M0 scope
baseline; doc 03 §3.6.1-3.6.6): consumers (Legal Structure Extractor, quality
gates, embedding, index) read only this IR — never raw Docling/MinerU output.

All models reject undeclared fields (``extra="forbid"``) so parser-specific
fields cannot leak into the IR artifact. The schema is deliberately
parser-neutral: ``parser``/``source_parser`` are plain strings ("DOCLING" |
"MINERU" today — a future parser must not be rejected), and every element
carries parser provenance (``source_parser``/``parser_version``/
``raw_reference``). Invariants such as bbox ordering or value ranges belong
to quality gates and adapters, not the frozen canonical schema.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class BoundingBox(BaseModel):
    """Axis-aligned box in PDF points (frozen contract §5).

    ``page_height``/``page_width`` are optional page dimensions recorded when
    the parser provides them.
    """

    model_config = ConfigDict(extra="forbid")

    left: float
    top: float
    right: float
    bottom: float
    page_height: float | None = None
    page_width: float | None = None


class DocumentElement(BaseModel):
    """A single layout/content unit on a page (frozen contract §6).

    ``element_type`` is intentionally a free string per the frozen contract —
    expected values include title, heading, paragraph, table, list_item,
    figure, page_header, page_footer, ... Do not narrow it to a Literal.
    ``source_parser`` is likewise a free string ("DOCLING" | "MINERU" today).
    """

    model_config = ConfigDict(extra="forbid")

    element_id: str
    element_type: str
    text: str
    page_number: int
    bbox: BoundingBox | None = None
    reading_order: int
    parent_element_id: str | None
    table_html: str | None = None
    source_parser: str
    parser_version: str
    parser_confidence: float | None
    raw_reference: dict[str, Any]


class ParsedPage(BaseModel):
    """Physical page of a parsed document (frozen contract §4).

    ``width``/``height``/``text`` are required keys but may be null when the
    parser does not provide them.
    """

    model_config = ConfigDict(extra="forbid")

    page_number: int
    width: float | None
    height: float | None
    text: str | None
    elements: list[DocumentElement]


class ParsedDocument(BaseModel):
    """Document-level IR artifact (frozen contract §3)."""

    model_config = ConfigDict(extra="forbid")

    parsed_document_id: str  # UUID of the parse, NOT the legal document_id
    document_id: str  # legal document_id from the manifest
    parser: str
    parser_version: str
    ir_schema_version: str
    source_object_key: str
    pages: list[ParsedPage]
    parse_started_at: datetime
    parse_completed_at: datetime
    quality_report: dict[str, Any]
