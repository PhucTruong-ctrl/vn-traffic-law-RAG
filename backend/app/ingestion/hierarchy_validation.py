"""Legal hierarchy validation for extracted provisions (VNLRAG-30).

This module validates the Điều → Khoản → Điểm tree and exposes the four
contract metrics consumed by the ingestion quality gates.
"""

from __future__ import annotations

import re
from collections import defaultdict

from pydantic import BaseModel, ConfigDict

from app.ingestion.metadata_normalizer import VIETNAMESE_POINT_ALPHABET, canonical_point_label
from app.ingestion.structure_extractor import ExtractedLegalProvision
from app.ingestion.structure_state_parser import StructureKind

_POINT_RUN_ALPHABET = VIETNAMESE_POINT_ALPHABET
_TREE_KINDS = frozenset({"ARTICLE", "CLAUSE", "POINT"})
_NON_TREE_KINDS = frozenset(
    {
        StructureKind.APPENDIX.value,
        StructureKind.TABLE.value,
        StructureKind.TRANSITIONAL.value,
        StructureKind.HEADING.value,
    }
)
_KHOAN_SEGMENT = "khoan-"
_DIEM_SEGMENT = "diem-"
_D_LABEL_RE = re.compile(r"^\s*(?:điểm\s+)?([a-zđ])[)）]", re.IGNORECASE)


class HierarchyViolation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    provision_id: str
    detail: str


class HierarchyValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    violations: list[HierarchyViolation]
    metrics: dict[str, float | int | None]


def _provision_kind(provision: ExtractedLegalProvision) -> str | None:
    kind = provision.node_kind
    if kind in _NON_TREE_KINDS:
        return None
    if kind in _TREE_KINDS:
        return kind
    if provision.point is not None:
        return "POINT"
    if provision.clause is not None:
        return "CLAUSE"
    if provision.article is not None:
        return "ARTICLE"
    return None


def _id_parent(provision_id: str, segment: str) -> str | None:
    marker = f"__{segment}"
    if marker not in provision_id:
        return None
    return provision_id.rsplit(marker, 1)[0]


def _point_parent_resolved(point, doc_ids, article_labels, clause_labels) -> bool:
    parent_clause = _id_parent(point.provision_id, _DIEM_SEGMENT)
    if parent_clause in doc_ids:
        return True
    if point.article is None:
        return False
    if point.clause is not None and (point.article, point.clause) in clause_labels:
        return True
    return point.article in article_labels


def _clause_parent_resolved(clause, doc_ids, article_labels) -> bool:
    parent_article = _id_parent(clause.provision_id, _KHOAN_SEGMENT)
    if parent_article in doc_ids:
        return True
    return clause.article in article_labels


def _label_source(provision: ExtractedLegalProvision) -> str | None:
    return provision.point_label or provision.point


def _is_d_label(label: str) -> bool:
    match = _D_LABEL_RE.match(label)
    return match is not None and match.group(1).casefold() == "d"


def _orphan_point_detail(point: ExtractedLegalProvision) -> str:
    expected = "clause" if point.clause is not None else "article"
    return f"no {expected} provision in document {point.document_version_id!r}"


def _orphan_clause_detail(clause: ExtractedLegalProvision) -> str:
    return f"no article {clause.article!r} provision in document {clause.document_version_id!r}"


def validate_hierarchy(provisions: list[ExtractedLegalProvision]) -> HierarchyValidationResult:
    violations: list[HierarchyViolation] = []
    counts: dict[str, int] = {}
    first_index: dict[str, int] = {}
    for index, provision in enumerate(provisions):
        counts[provision.provision_id] = counts.get(provision.provision_id, 0) + 1
        first_index.setdefault(provision.provision_id, index)
    duplicated = sorted(
        (pid for pid, count in counts.items() if count > 1), key=first_index.__getitem__
    )
    for pid in duplicated:
        violations.append(
            HierarchyViolation(
                type="duplicate_provision",
                provision_id=pid,
                detail=f"provision_id {pid!r} appears {counts[pid]} times; expected exactly once",
            )
        )

    by_document: dict[str, list[ExtractedLegalProvision]] = defaultdict(list)
    for provision in provisions:
        by_document[provision.document_version_id].append(provision)
    orphan_point_count = orphan_clause_count = 0
    for document_provisions in by_document.values():
        doc_ids = {p.provision_id for p in document_provisions}
        article_labels = {
            p.article
            for p in document_provisions
            if _provision_kind(p) == "ARTICLE" and p.article is not None
        }
        clause_labels = {
            (p.article, p.clause)
            for p in document_provisions
            if _provision_kind(p) == "CLAUSE" and p.article is not None and p.clause is not None
        }
        for provision in document_provisions:
            kind = _provision_kind(provision)
            if kind == "POINT" and not _point_parent_resolved(
                provision, doc_ids, article_labels, clause_labels
            ):
                violations.append(
                    HierarchyViolation(
                        type="orphan_point",
                        provision_id=provision.provision_id,
                        detail=_orphan_point_detail(provision),
                    )
                )
                orphan_point_count += 1
            elif kind == "CLAUSE" and not _clause_parent_resolved(
                provision, doc_ids, article_labels
            ):
                violations.append(
                    HierarchyViolation(
                        type="orphan_clause",
                        provision_id=provision.provision_id,
                        detail=_orphan_clause_detail(provision),
                    )
                )
                orphan_clause_count += 1

    points = [p for p in provisions if _provision_kind(p) == "POINT"]
    point_groups: dict[tuple[str, str | None, str | None], list[ExtractedLegalProvision]] = (
        defaultdict(list)
    )
    for point in points:
        point_groups[(point.document_version_id, point.article, point.clause)].append(point)
    valid_point_count = 0
    misses: list[str] = []
    for group in point_groups.values():
        d_seen = 0
        for point in group:
            label = _label_source(point)
            canonical = canonical_point_label(label) if label is not None else None
            valid = False
            if canonical is not None and label is not None and not _is_d_label(label):
                valid = canonical[0] in _POINT_RUN_ALPHABET and canonical != "x)"
            elif label is not None and _is_d_label(label):
                d_seen += 1
                canonical = canonical_point_label(label, ordinal=3 + d_seen)
                valid = canonical is not None
            if valid:
                valid_point_count += 1
            else:
                misses.append(point.provision_id)
                violations.append(
                    HierarchyViolation(
                        type="invalid_label",
                        provision_id=point.provision_id,
                        detail=(
                            f"point label {label!r} is not a valid Vietnamese point label "
                            f"(canonical {canonical!r} outside PRIMARY run a→b→c→d→đ→e)"
                        ),
                    )
                )
    point_count = len(points)
    return HierarchyValidationResult(
        violations=violations,
        metrics={
            "orphan_point_count": orphan_point_count,
            "orphan_clause_count": orphan_clause_count,
            "duplicate_count": len(duplicated),
            "point_label_detection_rate": valid_point_count / point_count if point_count else 0.0,
        },
    )


def _gold_kind(entry: dict) -> str:
    if entry.get("point"):
        return "POINT"
    if entry.get("clause"):
        return "CLAUSE"
    if entry.get("article"):
        return "ARTICLE"
    return "OTHER"


def validate_against_gold(provisions: list[ExtractedLegalProvision], gold: dict) -> dict:
    expected: dict[str, str] = {}
    for entry in gold.get("provisions", []):
        if (
            isinstance(entry, dict)
            and entry.get("retained", True) is not False
            and isinstance(entry.get("provision_id"), str)
        ):
            expected[entry["provision_id"]] = _gold_kind(entry)
    extracted = {p.provision_id: _provision_kind(p) for p in provisions}
    missing = [pid for pid in expected if pid not in extracted]
    mismatched = [pid for pid in expected if pid in extracted and extracted[pid] != expected[pid]]
    total = len(expected)
    return {
        "completeness": (total - len(missing) - len(mismatched)) / total if total else 1.0,
        "missing": missing,
        "mismatched": mismatched,
    }


__all__ = [
    "HierarchyValidationResult",
    "HierarchyViolation",
    "validate_against_gold",
    "validate_hierarchy",
]
