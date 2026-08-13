"""Legal hierarchy validation for extracted provisions (VNLRAG-30).

Validates the Điều tree emitted by the Legal Structure Extractor against the
structural rules of ``docs/rulespec/vietnamese-legal-parsing-rules.md`` (§4,
§10) and feeds the structural metrics of ``docs/03-thiet-ke-he-thong.md``
§3.10.5:

- orphan Point count  — POINT provisions whose parent CLAUSE/ARTICLE cannot
  be resolved inside the same document (``document_version_id``);
- orphan Clause count — CLAUSE provisions whose parent ARTICLE is missing;
- duplicate provision count — a ``provision_id`` appearing more than once
  (provision_ids are globally unique by construction, docs/03 §3.8.5);
- Vietnamese point-label detection rate — share of POINT provisions carrying
  a valid canonical Vietnamese point label: the PRIMARY run
  ``a→b→c→d→đ→e`` (rulespec §4.1), with ``đ)`` self-identifying and distinct
  from ``d)`` (bare ``d)`` resolves by ordinal position in the clause's point
  run: 1st d = ``"d)"``, 2nd d = ``"đ)"`` — the extractor's own duplicate-d
  rule, structure_state_parser.py).

Parent resolution uses both the provision_id grammar
(``{slug}__dieu-{n}(__khoan-{m})?(__diem-{x})?``, docs/03 §3.8.5) and the
hierarchy label fields (``article``/``clause``), scoped to one document.
Gold-tree comparison is provided by :func:`validate_against_gold`.

``HierarchyViolation.type`` also admits ``"missing_parent"`` — reserved for
future parent-resolution checks (e.g. non-tree node kinds); it is not emitted
by the current implementation.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.ingestion.metadata_normalizer import canonical_point_label
from app.ingestion.structure_extractor import ExtractedLegalProvision

#: PRIMARY Vietnamese point-run alphabet (rulespec §4.1: ``a→b→c→d→đ→e``,
#: d = 4th, đ = 5th letter).  Mirrors ``metadata_normalizer._POINT_RUN_ALPHABET``;
#: letters beyond ``e`` (e.g. ``g)`` … ``x)``) are flagged for review rather
#: than silently accepted.
_POINT_RUN_ALPHABET = "abcdđe"

#: Tree node kinds participating in the Điều hierarchy (docs/03 §3.8.1).
_TREE_KINDS = frozenset({"ARTICLE", "CLAUSE", "POINT"})

#: provision_id segment prefixes (docs/03 §3.8.5): ``{slug}__dieu-{n}``,
#: ``{slug}__dieu-{n}__khoan-{m}``, ``{slug}__dieu-{n}__khoan-{m}__diem-{x}``.
_KHOAN_SEGMENT = "khoan-"
_DIEM_SEGMENT = "diem-"

#: Bare d)/đ) label form — optional ``Điểm`` prefix, one point letter, then a
#: close paren (ASCII or full-width).  Recognizes the ambiguous d label that
#: needs ordinal context (rulespec §4.1).
_D_LABEL_RE = re.compile(r"^\s*(?:điểm\s+)?([a-zđ])[)）]", re.IGNORECASE)


class HierarchyViolation(BaseModel):
    """One structural defect found by :func:`validate_hierarchy`."""

    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "orphan_point",
        "orphan_clause",
        "duplicate_provision",
        "invalid_label",
        "missing_parent",
    ]
    provision_id: str
    detail: str


class HierarchyValidationResult(BaseModel):
    """Validated hierarchy: violations plus aggregate metrics.

    ``metrics`` always carries the contract keys ``orphan_point_count``,
    ``orphan_clause_count``, ``duplicate_count`` and
    ``point_label_detection_rate``; later tickets may add extra keys.
    """

    model_config = ConfigDict(extra="forbid")

    violations: list[HierarchyViolation]
    metrics: dict[str, float | int]


def _provision_kind(provision: ExtractedLegalProvision) -> str | None:
    """Effective tree kind: ``node_kind`` is authoritative, else field inference.

    Non-tree kinds (APPENDIX/TABLE/TRANSITIONAL/HEADING live outside the Điều
    tree, docs/03 §3.9.4) fall back to their hierarchy fields when those are
    populated; a provision with no hierarchy fields returns ``None``.
    """

    if provision.node_kind in _TREE_KINDS:
        return provision.node_kind
    if provision.point is not None:
        return "POINT"
    if provision.clause is not None:
        return "CLAUSE"
    if provision.article is not None:
        return "ARTICLE"
    return None


def _id_parent(provision_id: str, segment: str) -> str | None:
    """Parent provision_id by grammar: strip the last ``__{segment}`` part."""

    head, sep, tail = provision_id.rpartition("__")
    if sep and tail.startswith(segment):
        return head
    return None


def _point_parent_resolved(
    point: ExtractedLegalProvision,
    doc_ids: set[str],
    article_labels: set[str],
    clause_labels: set[tuple[str, str]],
) -> bool:
    """True when the point's parent CLAUSE/ARTICLE exists in the document.

    Resolution order: provision_id grammar (``__diem-{x}`` stripped), then
    hierarchy-label match — clause labels when the point names a clause,
    article labels for points hanging directly off an article (§10 fallback).
    """

    parent_id = _id_parent(point.provision_id, _DIEM_SEGMENT)
    if parent_id is not None and parent_id in doc_ids:
        return True
    if point.clause:
        return (point.article, point.clause) in clause_labels
    return point.article in article_labels


def _clause_parent_resolved(
    clause: ExtractedLegalProvision,
    doc_ids: set[str],
    article_labels: set[str],
) -> bool:
    """True when the clause's parent ARTICLE exists in the document."""

    parent_id = _id_parent(clause.provision_id, _KHOAN_SEGMENT)
    if parent_id is not None and parent_id in doc_ids:
        return True
    return clause.article in article_labels


def _label_source(provision: ExtractedLegalProvision) -> str | None:
    """Point label to validate: the dedicated ``point_label`` field, else ``point``."""

    return provision.point_label or provision.point


def _is_d_label(label: str) -> bool:
    """Bare ``d)`` form needing ordinal context (rulespec §4.1 PRIMARY rule)."""

    match = _D_LABEL_RE.match(label)
    return match is not None and match.group(1).casefold() == "d"


def _orphan_point_detail(point: ExtractedLegalProvision) -> str:
    expected = (
        f"clause ({point.article!r}, {point.clause!r})"
        if point.clause
        else f"article {point.article!r}"
    )
    return f"no {expected} provision in document {point.document_version_id!r}"


def _orphan_clause_detail(clause: ExtractedLegalProvision) -> str:
    return f"no article {clause.article!r} provision in document {clause.document_version_id!r}"


def validate_hierarchy(
    provisions: list[ExtractedLegalProvision],
) -> HierarchyValidationResult:
    """Validate the Điều tree of extracted provisions.

    Emits ``orphan_point`` / ``orphan_clause`` violations for provisions whose
    parent cannot be resolved within the same document, ``duplicate_provision``
    for repeated provision_ids, and ``invalid_label`` for POINT provisions
    without a valid canonical Vietnamese point label.  Metrics always contain
    ``orphan_point_count``, ``orphan_clause_count``, ``duplicate_count`` and
    ``point_label_detection_rate`` (0.0 when the list is empty or contains no
    POINT provisions).
    """

    violations: list[HierarchyViolation] = []

    # Duplicate provision_ids (globally unique by construction, docs/03 §3.8.5).
    counts: dict[str, int] = {}
    first_index: dict[str, int] = {}
    for index, provision in enumerate(provisions):
        counts[provision.provision_id] = counts.get(provision.provision_id, 0) + 1
        first_index.setdefault(provision.provision_id, index)
    duplicated = sorted(
        (pid for pid, count in counts.items() if count > 1),
        key=first_index.__getitem__,
    )
    for pid in duplicated:
        violations.append(
            HierarchyViolation(
                type="duplicate_provision",
                provision_id=pid,
                detail=f"provision_id {pid!r} appears {counts[pid]} times; expected exactly once",
            )
        )

    # Orphan checks are scoped per document (parent must be in the same list).
    by_document: dict[str, list[ExtractedLegalProvision]] = {}
    for provision in provisions:
        by_document.setdefault(provision.document_version_id, []).append(provision)

    orphan_point_count = 0
    orphan_clause_count = 0
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

    # Point-label detection — POINT kind only (rulespec §4).  Ordinal context
    # for a bare d) comes from its position among d-labels in the clause's
    # point run (1st d → "d)", 2nd d → "đ)"), mirroring the extractor.
    points = [p for p in provisions if _provision_kind(p) == "POINT"]
    point_groups: dict[tuple[str, str | None, str | None], list[ExtractedLegalProvision]] = {}
    for point in points:
        point_groups.setdefault(
            (point.document_version_id, point.article, point.clause), []
        ).append(point)

    valid_point_count = 0
    for group in point_groups.values():
        d_seen = 0
        for point in group:
            label = _label_source(point)
            canonical = canonical_point_label(label) if label is not None else None
            if canonical is not None:
                if canonical[0] in _POINT_RUN_ALPHABET:
                    valid_point_count += 1
                    continue
            elif label is not None and _is_d_label(label):
                d_seen += 1
                canonical = canonical_point_label(label, ordinal=3 + d_seen)
                if canonical is not None:
                    valid_point_count += 1
                    continue
            violations.append(
                HierarchyViolation(
                    type="invalid_label",
                    provision_id=point.provision_id,
                    detail=(
                        f"point label {label!r} is not a valid Vietnamese point "
                        f"label (canonical {canonical!r} outside PRIMARY run "
                        "a→b→c→d→đ→e)"
                    ),
                )
            )

    point_count = len(points)
    metrics: dict[str, float | int] = {
        "orphan_point_count": orphan_point_count,
        "orphan_clause_count": orphan_clause_count,
        "duplicate_count": len(duplicated),
        "point_label_detection_rate": (valid_point_count / point_count if point_count else 0.0),
    }
    return HierarchyValidationResult(violations=violations, metrics=metrics)


def _gold_kind(entry: dict) -> str:
    """Gold fixture node kind inferred from its hierarchy fields."""

    if entry.get("point"):
        return "POINT"
    if entry.get("clause"):
        return "CLAUSE"
    if entry.get("article"):
        return "ARTICLE"
    return "OTHER"


def validate_against_gold(provisions: list[ExtractedLegalProvision], gold: dict) -> dict:
    """Compare extracted node kinds against a gold fixture tree.

    ``gold`` follows the parser-benchmark format
    (``backend/tests/fixtures/parser_benchmark/gold/*-gold.json``):
    ``{"provisions": [{provision_id, article, clause, point, retained, ...}]}``.
    The gold node kind is inferred from its hierarchy fields (point → POINT,
    clause → CLAUSE, article → ARTICLE); entries with ``retained: false`` are
    excluded (they are not provisions).

    Returns ``{"completeness": float, "missing": list[str], "mismatched":
    list[str]}`` — ``missing`` are gold provision_ids absent from the
    extracted set, ``mismatched`` are ids whose node kind differs, and
    ``completeness`` is the fraction of gold provisions matched exactly
    (1.0 for an empty gold — nothing expected is vacuously complete).
    """

    expected: dict[str, str] = {}
    for entry in gold.get("provisions", []):
        if not isinstance(entry, dict):
            continue
        if entry.get("retained", True) is False:
            continue
        pid = entry.get("provision_id")
        if isinstance(pid, str):
            expected[pid] = _gold_kind(entry)

    extracted = {p.provision_id: _provision_kind(p) for p in provisions}
    missing = [pid for pid in expected if pid not in extracted]
    mismatched = [pid for pid in expected if pid in extracted and extracted[pid] != expected[pid]]
    total = len(expected)
    matched = total - len(missing) - len(mismatched)
    return {
        "completeness": matched / total if total else 1.0,
        "missing": missing,
        "mismatched": mismatched,
    }


__all__ = [
    "HierarchyValidationResult",
    "HierarchyViolation",
    "validate_against_gold",
    "validate_hierarchy",
]
