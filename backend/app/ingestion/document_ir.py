"""Canonical Document IR schema (VNLRAG-128), v2.

Parser-neutral intermediate representation owned by the project (FR-02).
The contract is frozen at ``docs/canonical-document-ir-design.md`` (M0 scope
baseline; doc 03 §3.6.1-3.6.6; ``ir_schema_version = "document-ir-v2"``):
consumers (Legal Structure Extractor, quality gates, embedding, index) read
only this IR — never raw Docling/MinerU output.

All models reject undeclared fields (``extra="forbid"``) so parser-specific
fields cannot leak into the IR artifact. The schema is deliberately
parser-neutral: ``parser``/``source_parser`` are plain strings ("DOCLING" |
"MINERU" today — a future parser must not be rejected), and every element
carries parser provenance (``source_parser``/``parser_version``/
``raw_reference``).

v2 change (user blocker review #2/#3): ONE canonical bbox coordinate space —
:data:`BoundingBox.coordinate_space` = ``NORMALIZED_PAGE`` (0..1, TOPLEFT
origin). Raw parser coordinates (Docling PDF points, MinerU page-permille)
live in ``raw_reference`` — never in the canonical bbox. v2 also strengthens
parser-independent validation invariants (page_number >= 1, reading_order >= 0,
parser_confidence in [0, 1], non-empty parser_version, bbox bounds/ordering,
unique element_id, element↔page number match, parse time ordering) so malformed
IR is rejected at the schema boundary instead of surfacing downstream.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

#: The single canonical coordinate space for v2 bboxes. Parser-specific
#: coordinates (PDF points, permille, ...) must be converted by the adapters
#: and stored under ``raw_reference``, never emitted here.
COORDINATE_SPACE = Literal["NORMALIZED_PAGE"]


def _validate_parser_version(value: str) -> str:
    if not value.strip():
        raise ValueError("parser_version must not be empty")
    return value


class BoundingBox(BaseModel):
    """Axis-aligned box in NORMALIZED_PAGE coordinates (frozen contract §5, v2).

    v2 semantics: every coordinate is page-normalized to the unit interval —
    ``left``/``right`` in [0, 1] of page width, ``top``/``bottom`` in [0, 1] of
    page height, TOPLEFT origin (``bottom >= top``, ``right >= left``).
    ``coordinate_space`` is fixed to ``NORMALIZED_PAGE`` (the only space in v2);
    a parser introducing another space must bump the IR schema version.

    ``page_height``/``page_width`` are optional informational page dimensions
    recorded when the parser provides them; they are no longer used for
    normalization math (v2 boxes are already normalized).
    """

    model_config = ConfigDict(extra="forbid")

    left: float
    top: float
    right: float
    bottom: float
    coordinate_space: COORDINATE_SPACE = "NORMALIZED_PAGE"
    page_height: float | None = None
    page_width: float | None = None

    @field_validator("left", "right")
    @classmethod
    def _x_in_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("bbox left/right must be in [0, 1] (NORMALIZED_PAGE)")
        return value

    @field_validator("top", "bottom")
    @classmethod
    def _y_in_unit_interval(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("bbox top/bottom must be in [0, 1] (NORMALIZED_PAGE)")
        return value

    @field_validator("page_height", "page_width")
    @classmethod
    def _page_dims_positive(cls, value: float | None) -> float | None:
        if value is not None and value <= 0:
            raise ValueError("page_height/page_width must be > 0 when present")
        return value

    @model_validator(mode="after")
    def _check_ordering(self) -> "BoundingBox":
        if self.right < self.left:
            raise ValueError("bbox right must be >= left")
        if self.bottom < self.top:
            raise ValueError("bbox bottom must be >= top (TOPLEFT origin)")
        return self


class DocumentElement(BaseModel):
    """A single layout/content unit on a page (frozen contract §6).

    ``element_type`` is intentionally a free string per the frozen contract —
    expected values include title, heading, paragraph, table, list_item,
    figure, page_header, page_footer, ... Do not narrow it to a Literal.
    ``source_parser`` is likewise a free string ("DOCLING" | "MINERU" today).

    v2 validation invariants (user review #3): ``page_number >= 1``,
    ``reading_order >= 0``, ``parser_confidence`` in [0, 1] when present, and
    non-empty ``parser_version``.
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

    @field_validator("page_number")
    @classmethod
    def _page_number_ge_1(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page_number must be >= 1 (1-based)")
        return value

    @field_validator("reading_order")
    @classmethod
    def _reading_order_ge_0(cls, value: int) -> int:
        if value < 0:
            raise ValueError("reading_order must be >= 0 (0-based)")
        return value

    @field_validator("parser_version")
    @classmethod
    def _parser_version_non_empty(cls, value: str) -> str:
        return _validate_parser_version(value)

    @field_validator("parser_confidence")
    @classmethod
    def _confidence_in_unit_interval(cls, value: float | None) -> float | None:
        if value is not None and not 0.0 <= value <= 1.0:
            raise ValueError("parser_confidence must be in [0, 1] when present")
        return value


class ParsedPage(BaseModel):
    """Physical page of a parsed document (frozen contract §4).

    ``width``/``height``/``text`` are required keys but may be null when the
    parser does not provide them. v2: ``page_number >= 1`` and every element
    on the page must carry that page's number.
    """

    model_config = ConfigDict(extra="forbid")

    page_number: int
    width: float | None
    height: float | None
    text: str | None
    elements: list[DocumentElement]

    @field_validator("page_number")
    @classmethod
    def _page_number_ge_1(cls, value: int) -> int:
        if value < 1:
            raise ValueError("page_number must be >= 1 (1-based)")
        return value

    @model_validator(mode="after")
    def _element_page_numbers_match(self) -> "ParsedPage":
        for element in self.elements:
            if element.page_number != self.page_number:
                raise ValueError(
                    f"element {element.element_id!r} page_number {element.page_number} "
                    f"!= page page_number {self.page_number}"
                )
        return self


class ParsedDocument(BaseModel):
    """Document-level IR artifact (frozen contract §3), v2."""

    model_config = ConfigDict(extra="forbid")

    parsed_document_id: str  # UUID of the parse, NOT the legal document_id
    document_id: str  # legal document_id from the manifest
    parser: str
    parser_version: str
    ir_schema_version: str  # required — callers pass "document-ir-v2"
    source_object_key: str
    pages: list[ParsedPage]
    parse_started_at: datetime
    parse_completed_at: datetime
    quality_report: dict[str, Any]

    @field_validator("parser_version")
    @classmethod
    def _parser_version_non_empty(cls, value: str) -> str:
        return _validate_parser_version(value)

    @model_validator(mode="after")
    def _time_ordering(self) -> "ParsedDocument":
        if self.parse_completed_at < self.parse_started_at:
            raise ValueError("parse_completed_at must be >= parse_started_at")
        return self

    @model_validator(mode="after")
    def _unique_element_ids_across_pages(self) -> "ParsedDocument":
        seen: set[str] = set()
        for page in self.pages:
            for element in page.elements:
                if element.element_id in seen:
                    raise ValueError(f"duplicate element_id across pages: {element.element_id!r}")
                seen.add(element.element_id)
        return self
