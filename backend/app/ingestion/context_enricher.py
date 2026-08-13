"""Legal Context Enricher (VNLRAG-132, FR-04).

Parent-context enrichment: ``retrieval_text`` of a Point may inherit the
parent clause lead-in (and that of a Clause the parent article heading) so the
provision stays self-contained when retrieved on its own, while ``source_text``
keeps the verbatim legal text of the provision and citations keep pointing at
the actual provision (docs/00 §4.4, §8.3:394-410; docs/03 §3.8.6).

The exact expected format is defined by
``backend/tests/fixtures/parser_benchmark/gold/parent_context_annotation.json``:

- POINT  -> canonical clause lead-in + point ``source_text``
  e.g. ``"Khoản 4. Phạt tiền từ 14.000.000 đồng đến 16.000.000 đồng ... sau
  đây: a) Điều khiển xe lạng lách, đánh võng trên đường bộ"``
- CLAUSE -> article heading + clause ``source_text``
- ARTICLE and other node kinds -> the provision's own ``source_text`` (identity)

The clause lead-in is the parent clause's text with its leading raw number
replaced by the canonical ``Khoản {n}.`` label (from the clause's structural
``clause`` field); the article heading is never included in a Point's
retrieval_text.  When the parent chain cannot be resolved, a POINT derives a
clause-only lead-in from ``provision.parent_context`` (the trailing clause
segment after the last article boundary) and a CLAUSE derives the article
heading only — the full ``parent_context`` concatenation (chapter+section+
article[+clause]) is never used — and the enrichment finally falls back to
the unmodified ``source_text`` (never raises, never fabricates content).
"""

from __future__ import annotations

import re
from collections.abc import Mapping

from app.ingestion.structure_extractor import ExtractedLegalProvision

#: Node kinds whose retrieval_text may inherit parent context.
_ENRICHABLE_KINDS = frozenset({"POINT", "CLAUSE"})

_ARTICLE_NUMBER_RE = re.compile(r"^Điều\s+(\d+)", re.IGNORECASE)
_CLAUSE_NUMBER_RE = re.compile(r"^Khoản\s+(\d+)", re.IGNORECASE)
#: Leading marker of a clause text: either the raw number ("4. Phạt tiền ...") or
#: an already-canonical label ("Khoản 4. Phạt tiền ...").  The number is
#: captured so a derived lead-in can be canonicalized without a structural label.
_CLAUSE_LEAD_IN_RE = re.compile(r"^(?:(\d+)|Khoản\s+(\d+))\s*\.\s*")
#: Article heading boundary anywhere in a concatenated ``parent_context``
#: (``"Điều 7. Xử phạt ..."``, preceded by start-of-text or whitespace).  The
#: required space after the dot keeps cross-references like ``"tại Điều 5 của"``
#: from being mistaken for a heading boundary.
_ARTICLE_HEADING_RE = re.compile(r"(?:^|\s)Điều\s+\d+\.\s")
#: Clause-level marker anywhere in text: a raw number ("4. ") or an
#: already-canonical label ("Khoản 4. "), preceded by start-of-text or
#: whitespace, with the trailing space required so thousands separators
#: (``"14.000.000 đồng"``) are never treated as clause boundaries.
_CLAUSE_SEGMENT_RE = re.compile(r"(?:^|\s)(?:\d+|Khoản\s+\d+)\s*\.\s")


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


def _clause_lead_in(number: str, text: str) -> str:
    """Canonical clause lead-in ``Khoản {number}. {body}`` from a clause ``text``.

    ``{body}`` is ``text`` with its leading raw number (``"4. "``) or existing
    ``Khoản {n}.`` label removed, e.g. ``"4. Phạt tiền từ ..."`` ->
    ``"Khoản 4. Phạt tiền từ ..."``.
    """

    body = _CLAUSE_LEAD_IN_RE.sub("", text.strip(), count=1)
    return f"Khoản {number}. {body}" if body else f"Khoản {number}."


def _canonical_clause_lead_in(clause: ExtractedLegalProvision) -> str:
    """Canonical clause lead-in text for a parent CLAUSE provision.

    Returns ``Khoản {n}. {body}`` where ``{n}`` comes from the clause's
    structural ``clause`` label and ``{body}`` is the clause source_text with
    its leading raw number (``"4. "``) or existing ``Khoản {n}.`` label
    removed, e.g. ``"4. Phạt tiền từ ..."`` -> ``"Khoản 4. Phạt tiền từ ..."``.
    Returns an empty string when the clause number is unknown.
    """

    number = _clause_number(clause)
    if not number:
        return ""
    return _clause_lead_in(number, clause.source_text)


def _extract_clause_lead_in(provision: ExtractedLegalProvision) -> str:
    """Extract the canonical clause lead-in from ``provision.parent_context``.

    The structure extractor records ``parent_context`` of a POINT as the
    concatenation ``[chapter] [section] [article] [clause]``, so the clause
    text is the trailing segment starting with its raw number.  The last
    ``{clause number}.``-preceded-by-whitespace occurrence is the clause start
    (clause bodies only contain ``{n}.`` without a following space, e.g.
    thousands separators like ``14.000.000``).  Returns an empty string when
    the clause cannot be located (``parent_context`` missing or malformed).
    """

    parent = provision.parent_context
    if not parent:
        return ""
    number = _clause_number(provision)
    if not number:
        return ""
    pattern = re.compile(rf"(?:^|\s){re.escape(number)}\.\s")
    matches = list(pattern.finditer(parent))
    if not matches:
        return ""
    clause_text = parent[matches[-1].start() :].strip()
    return _clause_lead_in(number, clause_text)


def _derive_clause_lead_in(parent_context: str | None) -> str:
    """Derive a clause-only lead-in from a full ``parent_context``.

    Best-effort fallback for a POINT whose parent clause cannot be located by
    the structural clause number (missing or mismatched label, marker-stripped
    or reconstructed clause text): the trailing clause segment is the text from
    the last clause-level marker (raw ``"4. "`` or ``"Khoản 4. "``) after the
    last article boundary, canonicalized to ``Khoản {n}. ...``.  The chapter,
    section and article-heading prefix is never returned — when no clause
    segment can be located the fallback is an empty string (the caller then
    falls back to ``source_text`` alone).
    """

    if not parent_context:
        return ""
    search_from = 0
    article_matches = list(_ARTICLE_HEADING_RE.finditer(parent_context))
    if article_matches:
        match = article_matches[-1]
        # Skip the article's own "Điều {n}. " label; step one char back so a
        # clause marker directly abutting the heading is still found.
        search_from = match.start() + len(match.group(0).lstrip()) - 1
    clause_matches = list(_CLAUSE_SEGMENT_RE.finditer(parent_context, max(search_from, 0)))
    if not clause_matches:
        return ""
    segment = parent_context[clause_matches[-1].start() :].strip()
    lead_in_match = _CLAUSE_LEAD_IN_RE.match(segment)
    if not lead_in_match:
        return ""
    number = lead_in_match.group(1) or lead_in_match.group(2)
    return _clause_lead_in(number, segment)


def _derive_article_heading(parent_context: str | None) -> str:
    """Derive the parent article heading from a full ``parent_context``.

    Best-effort fallback for a CLAUSE enriched without sibling documents: the
    heading is the text from the last article boundary (``Điều {n}. ...``) cut
    off at the first clause-level marker, so chapter/section text (and any
    trailing clause text) is never included.  Returns an empty string when no
    article heading can be located.
    """

    if not parent_context:
        return ""
    article_matches = list(_ARTICLE_HEADING_RE.finditer(parent_context))
    if not article_matches:
        return ""
    match = article_matches[-1]
    heading = parent_context[match.start() :].strip()
    label_len = len(match.group(0).lstrip())
    clause_match = _CLAUSE_SEGMENT_RE.search(heading, max(label_len - 1, 0))
    if clause_match:
        heading = heading[: clause_match.start()].strip()
    return heading


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

    For a POINT this is the canonical clause lead-in (``Khoản {n}. ...``,
    without the article heading); for a CLAUSE the parent article heading.
    When ``documents`` is provided, the parent provision is looked up among
    the sibling provisions of the same document (matched by provision_id
    prefix or article/clause labels); otherwise, or when the parent cannot be
    found, the clause lead-in is extracted from ``provision.parent_context``
    (for POINTs) or derived from it as a clause-only segment; a CLAUSE derives
    the article heading only.  The full ``parent_context`` (chapter+section+
    article[+clause] concatenation) is never returned — when nothing can be
    resolved the result is an empty string and :func:`enrich_retrieval_text`
    falls back to the unmodified ``source_text``.
    """

    if documents is not None:
        document_key, siblings = _document_provisions(provision, documents)
        if provision.node_kind == "POINT":
            parent = _find_clause_parent(provision, siblings, document_key)
            if parent is not None:
                return _canonical_clause_lead_in(parent)
        elif provision.node_kind == "CLAUSE":
            parent = _find_article_parent(provision, siblings, document_key)
            if parent is not None:
                return parent.source_text.strip()
    if provision.node_kind == "POINT":
        clause_lead_in = _extract_clause_lead_in(provision)
        if clause_lead_in:
            return clause_lead_in
        return _derive_clause_lead_in(provision.parent_context)
    if provision.node_kind == "CLAUSE":
        return _derive_article_heading(provision.parent_context)
    if provision.parent_context:
        return provision.parent_context.strip()
    return ""


def enrich_retrieval_text(provision: ExtractedLegalProvision) -> str:
    """Return the enriched ``retrieval_text`` for a provision.

    POINT/CLAUSE provisions inherit the resolved parent context; ARTICLE and
    every other node kind keep their own ``source_text`` (identity).  When the
    parent chain cannot be resolved, the provision falls back to the derived
    clause-only lead-in / article heading and finally to the unmodified
    ``source_text`` — the full ``parent_context`` concatenation is never
    prepended.  This function never mutates ``source_text`` or
    ``content_hash``.
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
