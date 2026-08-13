"""State-machine parsing for Vietnamese legal document structure.

The parser consumes only the canonical :mod:`document_ir` models.  It does not
inspect Docling/MinerU objects or infer legal content from parser-specific
fields.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument


class StructureKind(StrEnum):
    """Legal hierarchy and non-tree node kinds emitted by the state parser."""

    CHAPTER = "CHAPTER"
    SECTION = "SECTION"
    ARTICLE = "ARTICLE"
    CLAUSE = "CLAUSE"
    POINT = "POINT"
    APPENDIX = "APPENDIX"
    TABLE = "TABLE"
    TRANSITIONAL = "TRANSITIONAL"
    HEADING = "HEADING"


class StructureNode(BaseModel):
    """One recognized structure boundary and its source IR provenance."""

    model_config = ConfigDict(extra="forbid")

    kind: StructureKind
    text: str
    label: str | None = None
    number: str | None = None
    page_number: int
    bbox: BoundingBox | None = None
    source_element_ids: list[str]
    ambiguity: str | None = None
    needs_review: bool = False


@dataclass
class StructureState:
    """Current hierarchy while walking elements in reading order."""

    chapter: StructureNode | None = None
    section: StructureNode | None = None
    article: StructureNode | None = None
    clause: StructureNode | None = None
    point: StructureNode | None = None
    appendix: StructureNode | None = None
    point_labels: list[str] = field(default_factory=list)
    _clause_number: int = field(default=0, repr=False)
    _heading_number: int = field(default=0, repr=False)
    _appendix_number: int = field(default=0, repr=False)
    _transitional_number: int = field(default=0, repr=False)

    def reset_below(self, kind: StructureKind) -> None:
        if kind == StructureKind.CHAPTER:
            self.section = self.article = self.clause = self.point = None
            self.point_labels.clear()
        elif kind == StructureKind.SECTION:
            self.article = self.clause = self.point = None
            self.point_labels.clear()
        elif kind == StructureKind.ARTICLE:
            self.clause = self.point = None
            self.point_labels.clear()
        elif kind == StructureKind.CLAUSE:
            self.point = None
            self.point_labels.clear()


_CHAPTER_RE = re.compile(r"^Chương\s+([IVXLCDM]+|\d+)\s*[.:-]?\s*(.*)$", re.IGNORECASE)
_SECTION_RE = re.compile(r"^Mục\s+([IVXLCDM]+|\d+)\s*[.:-]?\s*(.*)$", re.IGNORECASE)
_ARTICLE_RE = re.compile(r"^Điều\s+(\d+[A-Za-z]?)\s*[.:-]?\s*(.*)$", re.IGNORECASE)
_CLAUSE_RE = re.compile(r"^(\d+)\s*[.]\s*(.*)$")
_VIETNAMESE_POINT_LABELS = "aăâbcdđeêghiklmnoôơpqrstuưvxy"
_POINT_RE = re.compile(rf"^([{_VIETNAMESE_POINT_LABELS}])\s*[)]\s*(.*)$", re.IGNORECASE)
_POINT_FALLBACK_LABELS = "abcdđeghiklmnoôơpqrstuưvxy"
_APPENDIX_RE = re.compile(r"^Phụ\s+lục(?:\s+([IVXLCDM]+|\d+))?\s*[.:-]?\s*(.*)$", re.IGNORECASE)
_TRANSITIONAL_RE = re.compile(
    r"^(?:Điều\s+khoản\s+)?chuyển\s+tiếp\b(?:\s*[.:-]?\s*(.*))?$", re.IGNORECASE
)


def _clean_text(text: str) -> str:
    """Normalize OCR whitespace without changing legal characters."""

    return " ".join(unicodedata.normalize("NFC", text).strip().split())


def _nonempty(text: str) -> str | None:
    value = _clean_text(text)
    return value or None


def _roman_to_int(value: str) -> int | None:
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    previous = 0
    for character in reversed(value.upper()):
        current = values.get(character)
        if current is None:
            return None
        if current < previous:
            total -= current
        else:
            total += current
            previous = current
    return total


def _is_page_chrome(element: DocumentElement) -> bool:
    return element.element_type.casefold() in {"page_header", "page_footer", "header", "footer"}


def _node(
    kind: StructureKind,
    element: DocumentElement,
    *,
    label: str | None = None,
    number: str | None = None,
    ambiguity: str | None = None,
    needs_review: bool = False,
) -> StructureNode:
    return StructureNode(
        kind=kind,
        text=element.text.strip(),
        label=label,
        number=number,
        page_number=element.page_number,
        bbox=element.bbox,
        source_element_ids=[element.element_id],
        ambiguity=ambiguity,
        needs_review=needs_review,
    )


class LegalStructureStateParser:
    """Recognize Vietnamese legal boundaries and maintain hierarchy state."""

    def __init__(self) -> None:
        self.state = StructureState()

    @staticmethod
    def _elements(document: ParsedDocument) -> list[DocumentElement]:
        elements = [element for page in document.pages for element in page.elements]
        return sorted(elements, key=lambda element: (element.page_number, element.reading_order))

    @staticmethod
    def _looks_repeated_chrome(
        element: DocumentElement,
        counts: dict[str, int],
        pages_by_text: dict[str, set[int]],
    ) -> bool:
        if _is_page_chrome(element):
            return True
        if element.bbox is None:
            return False
        text = _clean_text(element.text).casefold()
        at_page_edge = element.bbox.top <= 0.15 or element.bbox.bottom >= 0.85
        return at_page_edge and counts.get(text, 0) > 1 and len(pages_by_text.get(text, set())) > 1

    @staticmethod
    def _text_locations(
        elements: list[DocumentElement],
    ) -> tuple[dict[str, int], dict[str, set[int]]]:
        counts: dict[str, int] = {}
        pages_by_text: dict[str, set[int]] = {}
        for element in elements:
            text = _clean_text(element.text).casefold()
            counts[text] = counts.get(text, 0) + 1
            pages_by_text.setdefault(text, set()).add(element.page_number)
        return counts, pages_by_text

    def parse(self, document: ParsedDocument) -> list[StructureNode]:
        """Return recognized nodes in canonical reading order.

        Page header/footer elements are always excluded.  Repeated chrome is
        excluded even when an adapter labels it as a generic paragraph.
        """

        self.state = StructureState()
        elements = self._elements(document)
        counts, pages_by_text = self._text_locations(elements)

        nodes: list[StructureNode] = []
        for element in elements:
            text = _clean_text(element.text)
            if not text or self._looks_repeated_chrome(element, counts, pages_by_text):
                continue
            node = self._recognize(element, text)
            if node is None:
                continue
            self._transition(node)
            nodes.append(node)
        return nodes

    def _next_point_label(self) -> str:
        used = {label.removesuffix(")") for label in self.state.point_labels}
        for label in _POINT_FALLBACK_LABELS:
            if label not in used:
                return f"{label})"
        return "a)"

    def _recognize(self, element: DocumentElement, text: str) -> StructureNode | None:
        match = _CHAPTER_RE.match(text)
        if match:
            return _node(
                StructureKind.CHAPTER,
                element,
                number=match.group(1),
                label=_nonempty(match.group(2)),
            )
        match = _SECTION_RE.match(text)
        if match:
            return _node(
                StructureKind.SECTION,
                element,
                number=match.group(1),
                label=_nonempty(match.group(2)),
            )
        match = _ARTICLE_RE.match(text)
        if match:
            number = match.group(1)
            needs_review = not number.isdigit()
            return _node(
                StructureKind.ARTICLE,
                element,
                number=number,
                label=_nonempty(match.group(2)),
                ambiguity="non-numeric article suffix" if needs_review else None,
                needs_review=needs_review,
            )
        match = _APPENDIX_RE.match(text)
        if match:
            raw_number = match.group(1)
            number = (
                str(_roman_to_int(raw_number))
                if raw_number and not raw_number.isdigit()
                else raw_number
            )
            if number is None:
                self.state._appendix_number += 1
                number = str(self.state._appendix_number)
            else:
                self.state._appendix_number = max(self.state._appendix_number, int(number))
            return _node(
                StructureKind.APPENDIX, element, number=number, label=_nonempty(match.group(2))
            )
        match = _TRANSITIONAL_RE.match(text)
        if match:
            return _node(StructureKind.TRANSITIONAL, element, label=_nonempty(match.group(1)))
        if element.element_type.casefold() == "table" or re.match(
            r"^Bảng\s+\d+", text, re.IGNORECASE
        ):
            number_match = re.search(r"\d+", text)
            return _node(
                StructureKind.TABLE, element, number=number_match.group(0) if number_match else None
            )
        match = _POINT_RE.match(text)
        if match:
            label = match.group(1).lower() + ")"
            return _node(StructureKind.POINT, element, label=label)
        match = _CLAUSE_RE.match(text)
        if match:
            return _node(StructureKind.CLAUSE, element, number=match.group(1))
        if element.element_type.casefold() == "list_item" and self.state.article is not None:
            if self.state.clause is None or text.casefold().endswith(
                ("gồm:", "như sau:", "sau đây:")
            ):
                self.state._clause_number += 1
                return _node(
                    StructureKind.CLAUSE,
                    element,
                    number=str(self.state._clause_number),
                    needs_review=True,
                    ambiguity="clause number reconstructed from marker-stripped list item",
                )
            return _node(
                StructureKind.POINT,
                element,
                label=self._next_point_label(),
                needs_review=True,
                ambiguity="point label reconstructed from marker-stripped list item",
            )
        if element.element_type.casefold() in {"heading", "title"}:
            self.state._heading_number += 1
            return _node(StructureKind.HEADING, element, number=str(self.state._heading_number))
        return None

    def _transition(self, node: StructureNode) -> None:
        kind = node.kind
        if kind == StructureKind.CHAPTER:
            self.state.chapter = node
            self.state.section = self.state.article = self.state.clause = self.state.point = None
            self.state.appendix = None
            self.state.point_labels.clear()
            self.state._clause_number = 0
        elif kind == StructureKind.SECTION:
            self.state.section = node
            self.state.article = self.state.clause = self.state.point = None
            self.state.appendix = None
            self.state.point_labels.clear()
            self.state._clause_number = 0
        elif kind == StructureKind.ARTICLE:
            self.state.article = node
            self.state.clause = self.state.point = None
            self.state.appendix = None
            self.state.point_labels.clear()
            self.state._clause_number = 0
        elif kind == StructureKind.CLAUSE:
            self.state.clause = node
            if node.number and node.number.isdigit():
                self.state._clause_number = max(self.state._clause_number, int(node.number))
            self.state.point_labels.clear()
            if self.state.article is None:
                node.needs_review = True
                node.ambiguity = "orphan clause without article"
        elif kind == StructureKind.POINT:
            if node.label == "d)" and "d)" in self.state.point_labels:
                if "đ)" not in self.state.point_labels:
                    node.label = "đ)"
                    node.needs_review = True
                    node.ambiguity = "OCR d/đ ambiguity normalized from duplicate d)"
                else:
                    node.needs_review = True
                    node.ambiguity = "duplicate d) point label"
            self.state.point = node
            self.state.point_labels.append(node.label or "")
            if self.state.article is None or self.state.clause is None:
                node.needs_review = True
                node.ambiguity = node.ambiguity or "orphan point without article/clause"
        elif kind == StructureKind.APPENDIX:
            self.state.appendix = node
            self.state.article = self.state.clause = self.state.point = None
            self.state.point_labels.clear()
        elif kind == StructureKind.TRANSITIONAL:
            self.state._transitional_number += 1
            node.number = str(self.state._transitional_number)
        elif (
            kind == StructureKind.TABLE
            and self.state.article is None
            and self.state.appendix is None
        ):
            node.needs_review = True
            node.ambiguity = "table without article or appendix"


def parse_structure_state(document: ParsedDocument) -> list[StructureNode]:
    """Convenience wrapper around :class:`LegalStructureStateParser`."""

    return LegalStructureStateParser().parse(document)


__all__ = [
    "LegalStructureStateParser",
    "StructureKind",
    "StructureNode",
    "StructureState",
    "parse_structure_state",
]
