"""Legal Structure Extractor for the canonical Vietnamese-law IR.

The extractor turns state-parser nodes into deterministic, provenance-bearing
LegalProvision-shaped Pydantic records.  It deliberately has no dependency on
Docling, MinerU, or persistence sessions.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from pydantic import BaseModel, ConfigDict, Field

from app.ingestion.document_ir import ParsedDocument
from app.ingestion.structure_state_parser import (
    LegalStructureStateParser,
    StructureKind,
    StructureNode,
)


class ExtractedLegalProvision(BaseModel):
    """Pydantic representation matching the LegalProvision storage contract."""

    model_config = ConfigDict(extra="forbid")

    provision_id: str
    document_version_id: str
    chapter: str | None
    section: str | None
    article: str | None
    clause: str | None
    point: str | None
    heading: str | None
    source_text: str
    retrieval_text: str
    parent_context: str | None
    effective_from: str | None = None
    effective_to: str | None = None
    status: str = "UNKNOWN"
    page_number: int
    bbox: dict[str, float] | None
    source_element_ids: list[str] = Field(min_length=1)
    content_hash: str
    version: int = Field(default=1, ge=1)
    review_status: str = "PENDING"

    # Structural metadata used before persistence.  They map directly to the
    # optional node_kind field in the JSON template and QA annotations.
    node_kind: str = "ARTICLE"
    point_label: str | None = None
    short_point: bool = False
    needs_review: bool = False
    ambiguity: str | None = None

    def to_schema_dict(self) -> dict[str, object]:
        """Return only fields accepted by ``templates/legal-provision.schema.json``."""

        data = self.model_dump(exclude={"point_label", "short_point", "needs_review", "ambiguity"})
        return data


# Compatibility-friendly short name for callers of the extractor module.
LegalProvision = ExtractedLegalProvision


def _slug_document_id(document_id: str) -> str:
    normalized = unicodedata.normalize("NFC", document_id).strip().lower()
    normalized = "".join(
        char
        for char in unicodedata.normalize("NFD", normalized)
        if unicodedata.category(char) != "Mn"
    )
    normalized = re.sub(r"(-qh\d+|-tt-[a-z0-9-]+)$", "", normalized)
    # Keep Vietnamese đ distinct from d; it does not decompose under NFD.
    return re.sub(r"[^a-z0-9đ]+", "-", normalized).strip("-")


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _node_label(node: StructureNode | None, prefix: str) -> str | None:
    if node is None or node.number is None:
        return None
    return f"{prefix} {node.number}"


def _point_id_label(label: str) -> str:
    """Normalize Vietnamese point letters to the stable ASCII/đ ID alphabet."""

    normalized = unicodedata.normalize("NFD", label.removesuffix(")"))
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").lower()


def _bbox(node: StructureNode) -> dict[str, float] | None:
    if node.bbox is None:
        return None
    return {
        key: value
        for key, value in node.bbox.model_dump(exclude_none=True).items()
        if key != "coordinate_space"
    }


class LegalStructureExtractor:
    """Extract stable LegalProvision records from one ParsedDocument."""

    def __init__(
        self,
        *,
        document_version_id: str | None = None,
        document_slug: str | None = None,
    ) -> None:
        self.document_version_id = document_version_id
        self.document_slug = document_slug

    def extract(
        self,
        document: ParsedDocument,
        *,
        document_version_id: str | None = None,
        document_slug: str | None = None,
    ) -> list[ExtractedLegalProvision]:
        """Extract all recognized legal nodes in reading order.

        ``document_slug`` is the manifest-derived stable slug.  The fallback
        strips known authority suffixes from legacy IR document IDs.
        """

        version_id = document_version_id or self.document_version_id or document.parsed_document_id
        document_slug = (
            document_slug or self.document_slug or _slug_document_id(document.document_id)
        )
        nodes = LegalStructureStateParser().parse(document)
        current_chapter: StructureNode | None = None
        current_section: StructureNode | None = None
        current_article: StructureNode | None = None
        current_clause: StructureNode | None = None
        current_appendix: StructureNode | None = None
        heading_number = 0
        transitional_number = 0
        table_ordinals: dict[str, int] = {}
        used_ids: set[str] = set()
        provisions: list[ExtractedLegalProvision] = []

        for node in nodes:
            if node.kind == StructureKind.CHAPTER:
                current_chapter = node
                current_section = current_article = current_clause = None
                current_appendix = None
                continue
            if node.kind == StructureKind.SECTION:
                current_section = node
                current_article = current_clause = None
                current_appendix = None
                continue
            if node.kind == StructureKind.ARTICLE:
                current_article = node
                current_clause = None
                current_appendix = None
                if not node.number or not node.number.isdigit():
                    continue
                provision = self._provision(
                    document_slug,
                    version_id,
                    node,
                    node_id=f"{document_slug}__dieu-{node.number}",
                    chapter=current_chapter,
                    section=current_section,
                    article=node,
                    clause=None,
                    point=None,
                    parent_context=self._context(current_chapter, current_section),
                    heading=node.label,
                )
                provisions.append(provision)
                used_ids.add(provision.provision_id)
                continue
            if node.kind == StructureKind.CLAUSE:
                current_clause = node
                if current_article is None or not (current_article.number or "").isdigit():
                    node.needs_review = True
                    continue
                provision = self._provision(
                    document_slug,
                    version_id,
                    node,
                    node_id=f"{document_slug}__dieu-{current_article.number}__khoan-{node.number}",
                    chapter=current_chapter,
                    section=current_section,
                    article=current_article,
                    clause=node,
                    point=None,
                    parent_context=self._context(current_chapter, current_section, current_article),
                )
                provisions.append(provision)
                used_ids.add(provision.provision_id)
                continue
            if node.kind == StructureKind.POINT:
                if (
                    current_article is None
                    or current_clause is None
                    or not (current_article.number or "").isdigit()
                ):
                    node.needs_review = True
                    continue
                label = node.label or ""
                label_slug = _point_id_label(label)
                node_id = (
                    f"{document_slug}__dieu-{current_article.number}"
                    f"__khoan-{current_clause.number}__diem-{label_slug}"
                )
                if node_id in used_ids:
                    node.needs_review = True
                    node.ambiguity = node.ambiguity or "duplicate stable provision ID"
                    continue
                provision = self._provision(
                    document_slug,
                    version_id,
                    node,
                    node_id=node_id,
                    chapter=current_chapter,
                    section=current_section,
                    article=current_article,
                    clause=current_clause,
                    point=node,
                    parent_context=self._context(
                        current_chapter, current_section, current_article, current_clause
                    ),
                )
                provisions.append(provision)
                used_ids.add(provision.provision_id)
                continue
            if node.kind == StructureKind.APPENDIX:
                current_appendix = node
                current_article = current_clause = None
                provision = self._provision(
                    document_slug,
                    version_id,
                    node,
                    node_id=f"{document_slug}__phu-luc-{node.number}",
                    chapter=current_chapter,
                    section=current_section,
                    article=None,
                    clause=None,
                    point=None,
                    parent_context=self._context(current_chapter, current_section),
                    node_kind="APPENDIX",
                )
                provisions.append(provision)
                used_ids.add(provision.provision_id)
                continue
            if node.kind == StructureKind.TABLE:
                if current_appendix is not None:
                    parent_key = f"phu-luc-{current_appendix.number}"
                    prefix = f"{document_slug}__{parent_key}__bang-"
                    article = None
                elif current_article is not None and (current_article.number or "").isdigit():
                    parent_key = f"dieu-{current_article.number}"
                    prefix = f"{document_slug}__{parent_key}__bang-"
                    article = current_article
                else:
                    node.needs_review = True
                    continue
                ordinal = table_ordinals.get(parent_key, 0) + 1
                requested = int(node.number) if node.number and node.number.isdigit() else ordinal
                node_id = f"{prefix}{requested}"
                while node_id in used_ids:
                    requested += 1
                    node_id = f"{prefix}{requested}"
                table_ordinals[parent_key] = requested
                provision = self._provision(
                    document_slug,
                    version_id,
                    node,
                    node_id=node_id,
                    chapter=current_chapter,
                    section=current_section,
                    article=article,
                    clause=current_clause if article else None,
                    point=None,
                    parent_context=self._context(
                        current_chapter,
                        current_section,
                        article,
                        current_clause if article else None,
                    ),
                    node_kind="TABLE",
                )
                provisions.append(provision)
                used_ids.add(provision.provision_id)
                continue
            if node.kind == StructureKind.TRANSITIONAL:
                transitional_number += 1
                node_id = f"{document_slug}__chuyen-tiep-{transitional_number}"
                provision = self._provision(
                    document_slug,
                    version_id,
                    node,
                    node_id=node_id,
                    chapter=current_chapter,
                    section=current_section,
                    article=None,
                    clause=None,
                    point=None,
                    parent_context=self._context(current_chapter, current_section),
                    node_kind="TRANSITIONAL",
                )
                provisions.append(provision)
                used_ids.add(provision.provision_id)
                current_article = current_clause = None
                current_appendix = None
                continue
            if node.kind == StructureKind.HEADING:
                heading_number += 1
                provisions.append(
                    self._provision(
                        document_slug,
                        version_id,
                        node,
                        node_id=f"{document_slug}__tieu-de-{node.number or heading_number}",
                        chapter=current_chapter,
                        section=current_section,
                        article=current_article,
                        clause=current_clause,
                        point=None,
                        parent_context=self._context(
                            current_chapter, current_section, current_article, current_clause
                        ),
                        node_kind="HEADING",
                    )
                )

        return provisions

    @staticmethod
    def _context(*nodes: StructureNode | None) -> str | None:
        values = [node.text.strip() for node in nodes if node is not None and node.text.strip()]
        return " ".join(values) or None

    @classmethod
    def _provision(
        cls,
        document_slug: str,
        version_id: str,
        node: StructureNode,
        *,
        node_id: str,
        chapter: StructureNode | None,
        section: StructureNode | None,
        article: StructureNode | None,
        clause: StructureNode | None,
        point: StructureNode | None,
        parent_context: str | None,
        heading: str | None = None,
        node_kind: str | None = None,
    ) -> ExtractedLegalProvision:
        source_text = node.text.strip()
        retrieval_text = f"{parent_context} {source_text}" if parent_context else source_text
        article_value = _node_label(article, "Điều")
        clause_value = _node_label(clause, "Khoản")
        point_value = f"Điểm {point.label}" if point and point.label else None
        return ExtractedLegalProvision(
            provision_id=node_id,
            document_version_id=version_id,
            chapter=chapter.text.strip() if chapter else None,
            section=section.text.strip() if section else None,
            article=article_value,
            clause=clause_value,
            point=point_value,
            heading=heading,
            source_text=source_text,
            retrieval_text=retrieval_text,
            parent_context=parent_context,
            status="UNKNOWN",
            page_number=node.page_number,
            bbox=_bbox(node),
            source_element_ids=list(node.source_element_ids),
            content_hash=_hash_text(source_text),
            version=1,
            review_status="PENDING",
            node_kind=node_kind or node.kind.value,
            point_label=point.label if point else None,
            short_point=point is not None and len(source_text.split()) <= 3,
            needs_review=node.needs_review,
            ambiguity=node.ambiguity,
        )


def extract_legal_provisions(
    document: ParsedDocument,
    *,
    document_version_id: str | None = None,
    document_slug: str | None = None,
) -> list[ExtractedLegalProvision]:
    """Convenience wrapper for one-document extraction."""

    return LegalStructureExtractor(
        document_version_id=document_version_id, document_slug=document_slug
    ).extract(document)


__all__ = [
    "ExtractedLegalProvision",
    "LegalProvision",
    "LegalStructureExtractor",
    "extract_legal_provisions",
]
