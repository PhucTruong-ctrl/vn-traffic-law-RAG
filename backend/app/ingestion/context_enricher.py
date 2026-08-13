"""Legal Context Enricher (VNLRAG-132, FR-04).

Parent-context enrichment: ``retrieval_text`` of a Point may inherit the
parent clause lead-in (and that of a Clause the parent article heading) so the
provision stays self-contained when retrieved on its own, while ``source_text``
keeps the verbatim legal text of the provision and citations keep pointing at
the actual provision (docs/00 §4.4, §8.3:394-410; docs/03 §3.8.6).

The exact expected format is defined by
``backend/tests/fixtures/parser_benchmark/gold/parent_context_annotation.json``:

- POINT  -> clause lead-in + point ``source_text``
  e.g. ``"Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng ... sau
  đây: a) Điều khiển xe lạng lách, đánh võng trên đường bộ"``
- CLAUSE -> article heading + clause ``source_text``
- ARTICLE and other node kinds -> the provision's own ``source_text`` (identity)

The module never mutates ``source_text`` or ``content_hash``; if a parent chain
cannot be resolved it falls back to ``provision.parent_context`` and finally to
the unmodified ``source_text`` (never raises, never fabricates).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.ingestion.structure_extractor import ExtractedLegalProvision

#: Node kinds whose retrieval_text may inherit parent context.
_ENRICHABLE_KINDS = frozenset({"POINT", "CLAUSE"})

_ARTICLE_NUMBER_RE = re.compile(r"^Điều\s+(\d+)", re.IGNORECASE)
_CLAUSE_NUMBER_RE = re.compile(r"^Khoản\s+(\d+)", re.IGNORECASE)


def _label_number(label: str | None, pattern: re.Pattern[str]) -> str | None:
    """Extract the trailing number from a label such as ``Điều 7`` or ``Khoản 4``."""

    if not label:
        return None
    match = pattern.match(label)
    return match.group(1) if match else None


def _article_number(provision: ExtractedLegalProvision) -> str | None:
    return _label_number(provision.article, _ARTICLE_NUMBER_RE)


def _clause_number(provision: ExtractedLegalProvision) -> str | None:
    return _label_number(provision.clause, _CLAUSE_NUMBER_RE)


def _document_provisions(
    provision: ExtractedLegalProvision,
    documents: Mapping[str, list[ExtractedLegalProvision]],
) -> tuple[str | None, list[ExtractedLegalProvision]]:
    """Return ``(document key, sibling provisions)`` for the provision.

    The document is located either by the exact ``document_version_id`` key or
    by any key that is a prefix of the provision_id (``doc_id__dieu-...``).
    """

    direct = documents.get(provision.document_version_id)
    if direct is not None:
        return provision.document_version_id, direct
    for document_id, provisions in documents.items():
        if document_id and provision.provision_id.startswith(f"{document_id}__"):
            return document_id, provisions
    return None, []


def _find_clause_parent(
    provision: ExtractedLegalProvision,
    siblings: list[ExtractedLegalProvision],
    document_key: str | None,
) -> ExtractedLegalProvision | None:
    """Locate the parent CLAUSE provision of a POINT.

    Matches first on the stable provision_id prefix
    (``{document}__dieu-{n}__khoan-{m}``) and then on the article/clause labels.
    """

    article_number = _article_number(provision)
    clause_number = _clause_number(provision)
    if document_key and article_number and clause_number:
        expected_id = f"{document_key}__dieu-{article_number}__khoan-{clause_number}"
        for sibling in siblings:
            if sibling.node_kind == "CLAUSE" and sibling.provision_id == expected_id:
                return sibling
    for sibling in siblings:
        if (
            sibling.node_kind == "CLAUSE"
            and sibling.article == provision.article
            and sibling.clause == provision.clause
        ):
            return sibling
    return None


def _find_article_parent(
    provision: ExtractedLegalProvision,
    siblings: list[ExtractedLegalProvision],
    document_key: str | None,
) -> ExtractedLegalProvision | None:
    """Locate the parent ARTICLE provision of a CLAUSE.

    Matches first on the stable provision_id prefix (``{document}__dieu-{n}``)
    and then on the article label.
    """

    article_number = _article_number(provision)
    if document_key and article_number:
        expected_id = f"{document_key}__dieu-{article_number}"
        for sibling in siblings:
            if sibling.node_kind == "ARTICLE" and sibling.provision_id == expected_id:
                return sibling
    for sibling in siblings:
        if sibling.node_kind == "ARTICLE" and sibling.article == provision.article:
            return sibling
    return None


def build_parent_context(
    provision: ExtractedLegalProvision,
    *,
    documents: Mapping[str, list[ExtractedLegalProvision]] | None = None,
) -> str:
    """Resolve the parent-chain text used to enrich ``retrieval_text``.

    For a POINT this is the parent clause lead-in; for a CLAUSE the parent
    article heading.  When ``documents`` is provided, the parent provision is
    looked up among the sibling provisions of the same document (matched by
    provision_id prefix or article/clause labels); otherwise, or when the
    parent cannot be found, ``provision.parent_context`` is used.  Returns an
    empty string when nothing can be resolved.
    """

    if documents is not None and provision.node_kind in _ENRICHABLE_KINDS:
        document_key, siblings = _document_provisions(provision, documents)
        parent = (
            _find_clause_parent(provision, siblings, document_key)
            if provision.node_kind == "POINT"
            else _find_article_parent(provision, siblings, document_key)
        )
        if parent is not None:
            return parent.source_text.strip()
    if provision.parent_context:
        return provision.parent_context.strip()
    return ""


def enrich_retrieval_text(provision: ExtractedLegalProvision) -> str:
    """Return the enriched ``retrieval_text`` for a provision.

    POINT/CLAUSE provisions inherit the resolved parent context; ARTICLE and
    every other node kind keep their own ``source_text`` (identity).  When the
    parent chain cannot be resolved the provision falls back to its
    ``parent_context`` and finally to the unmodified ``source_text``.  This
    function never mutates ``source_text`` or ``content_hash``.
    """

    if provision.node_kind not in _ENRICHABLE_KINDS:
        return provision.source_text
    context = build_parent_context(provision)
    if not context:
        return provision.source_text
    return f"{context} {provision.source_text}"


def enrich_provision(provision: ExtractedLegalProvision) -> ExtractedLegalProvision:
    """Return a copy of the provision with enriched retrieval fields.

    The copy has ``retrieval_text`` set to :func:`enrich_retrieval_text` and
    ``parent_context`` populated with the resolved parent chain (``None`` when
    nothing can be resolved).  ``source_text`` and ``content_hash`` are kept
    byte-identical to the input.
    """

    context = build_parent_context(provision)
    return provision.model_copy(
        update={
            "retrieval_text": enrich_retrieval_text(provision),
            "parent_context": context or None,
        }
    )


def parent_context_completeness(provisions: list[ExtractedLegalProvision]) -> float:
    """Parent Context Completeness metric (docs/06 §6.4.1, FR-04).

    Fraction of POINT/CLAUSE provisions whose enriched ``retrieval_text``
    inherits parent context, i.e. whose resolved parent chain (see
    :func:`build_parent_context`) is non-empty.  Returns ``0.0`` when there are
    no POINT/CLAUSE provisions.
    """

    eligible = [provision for provision in provisions if provision.node_kind in _ENRICHABLE_KINDS]
    if not eligible:
        return 0.0
    with_context = sum(1 for provision in eligible if build_parent_context(provision))
    return with_context / len(eligible)


__all__ = [
    "enrich_retrieval_text",
    "build_parent_context",
    "enrich_provision",
    "parent_context_completeness",
]
