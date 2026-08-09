"""Canonical Document IR schema (VNLRAG-128).

Parser-neutral intermediate representation owned by the project (FR-02).
The contract is frozen at ``docs/canonical-document-ir-design.md`` (M0 scope
baseline; doc 03 §3.6.1-3.6.6): consumers (Legal Structure Extractor, quality
gates, embedding, index) read only this IR — never raw Docling/MinerU output.

All models reject undeclared fields (``extra="forbid"``) and are immutable
(``frozen=True``) so parser-specific fields cannot leak into the IR artifact.
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ParserEngine(StrEnum):
    """Parser engines supported by the IR (frozen contract §3 / §6)."""

    DOCLING = "DOCLING"
    MINERU = "MINERU"


def _require_non_empty(value: str, *, field_name: str) -> str:
    """Reject empty/whitespace-only values for pinned provenance fields."""
    if not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


class BoundingBox(BaseModel):
    """Axis-aligned box in PDF points (frozen contract §5).

    ``page_height``/``page_width`` are optional page dimensions recorded when
    the parser provides them.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    left: float
    top: float
    right: float
    bottom: float
    page_height: float | None = None
    page_width: float | None = None

    @model_validator(mode="after")
    def _reject_inverted_box(self) -> Self:
        """Reject inverted boxes: require left < right and top < bottom."""
        if self.left >= self.right or self.top >= self.bottom:
            raise ValueError(
                "BoundingBox must satisfy left < right and top < bottom, "
                f"got left={self.left}, top={self.top}, right={self.right}, bottom={self.bottom}"
            )
        return self


class DocumentElement(BaseModel):
    """A single layout/content unit on a page (frozen contract §6).

    ``element_type`` is intentionally a free string per the frozen contract —
    expected values include title, heading, paragraph, table, list_item,
    figure, page_header, page_footer, ... Do not narrow it to a Literal.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    element_id: str
    element_type: str
    text: str
    page_number: Annotated[int, Field(ge=1)]
    bbox: BoundingBox | None = None
    reading_order: Annotated[int, Field(ge=0)]
    parent_element_id: str | None = None
    table_html: str | None = None
    source_parser: ParserEngine
    parser_version: str
    parser_confidence: Annotated[float | None, Field(ge=0.0, le=1.0)] = None
    raw_reference: dict[str, Any]

    @model_validator(mode="after")
    def _require_parser_provenance(self) -> Self:
        """Every element carries parser provenance (source_parser, parser_version).

        ``source_parser`` presence/validity is enforced by the required
        ``ParserEngine`` field; ``parser_version`` must additionally be non-empty.
        """
        _require_non_empty(self.parser_version, field_name="parser_version")
        return self


class ParsedPage(BaseModel):
    """Physical page of a parsed document (frozen contract §4)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    page_number: Annotated[int, Field(ge=1)]
    width: float | None = None
    height: float | None = None
    text: str | None = None
    elements: list[DocumentElement]


class ParsedDocument(BaseModel):
    """Document-level IR artifact (frozen contract §3)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    parsed_document_id: str  # UUID of the parse, NOT the legal document_id
    document_id: str  # legal document_id from the manifest
    parser: ParserEngine
    parser_version: str
    ir_schema_version: str = "document-ir-v1"
    source_object_key: str
    pages: list[ParsedPage]
    parse_started_at: datetime
    parse_completed_at: datetime
    quality_report: dict[str, Any] = Field(default_factory=dict)

    @field_validator("parser_version")
    @classmethod
    def _parser_version_must_be_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, field_name="parser_version")
