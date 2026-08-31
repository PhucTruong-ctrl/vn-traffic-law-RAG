"""Corpus QA — the 16 FR-10 metrics over an extracted corpus (VNLRAG-127).

Computes the corpus quality report defined in doc 00 §10.3 and
doc 03 §3.10.5 (FR-10, UC-12) from a list of
:class:`~app.ingestion.structure_extractor.ExtractedLegalProvision` records
plus optional corpus manifests:

    document count, article count, clause count, point count,
    Point coverage, short-Point retention, Vietnamese đ) detection rate,
    orphan Point count, orphan Clause count, duplicate provision count,
    parent-context coverage, provenance coverage, table coverage,
    unresolved cross-reference count, unknown effective date count,
    temporal conflict count.

Semantics follow ``docs/rulespec/vietnamese-legal-parsing-rules.md``
(§5 short-Point retention without a token-length threshold, §7 REFERS_TO
cross-reference patterns, §8 half-open ``[effective_from, effective_to)``
temporal intervals, §10 hierarchy) and doc 03 §3.14.1.

Two metrics come from cross-module contracts developed in parallel worktrees
and monkeypatched in tests:

- ``provenance_coverage`` (VNLRAG-29, ``app.ingestion.provenance``) — the
  share of provisions with ≥1 ``source_element_id`` AND a non-null
  ``page_number`` (0.0 for an empty list);
- ``validate_hierarchy`` (VNLRAG-30, ``app.ingestion.hierarchy_validation``)
  — supplies ``orphan_point_count``, ``orphan_clause_count`` and
  ``duplicate_count`` from its ``.metrics`` dict (keys fixed by the
  cross-ticket contract).  ``d_point_detection_rate`` is NOT sourced from
  hierarchy validation: it is the đ)-specific rate computed locally by
  ``vietnamese_d_detection_rate`` (rulespec §4).

The two modules may not exist yet (parallel development), so they are loaded
lazily at call time via ``importlib``; ``run_corpus_qa`` raises a clear
``ImportError`` when a real call is attempted before they are merged.  Tests
monkeypatch the module-level ``provenance_coverage`` / ``validate_hierarchy``
wrapper names; the orchestrator verifies the real integration after merge.

The module is deterministic, side-effect free and parser-neutral; it never
modifies the provisions it is given.
"""

from __future__ import annotations

import importlib
import json
import re
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.ingestion.metadata_normalizer import canonical_point_label
from app.ingestion.structure_extractor import ExtractedLegalProvision

#: Corpus QA report schema version (bump on incompatible metric changes).
CORPUS_QA_VERSION = "corpus-qa-v1"

#: ``corpus_qa_reports.metrics`` is JSONB; pydantic serializes exactly these
#: 16 keys via ``model_dump()``.


# ────────────────────────────────────────────────────────────────────────────
# Cross-module contracts (VNLRAG-29 provenance, VNLRAG-30 hierarchy
# validation).  Developed in parallel worktrees: the modules may be absent,
# so both functions are lazy wrappers over ``importlib`` — the names below
# always exist, which keeps the monkeypatch surface stable in tests.
# ────────────────────────────────────────────────────────────────────────────
def _load_contract(module_name: str, attribute: str) -> Any:
    """Lazily load one cross-module contract function.

    ``importlib`` keeps mypy clean both before and after the VNLRAG-29/30
    modules land (no static import of a possibly-missing module).  A missing
    module raises ``ImportError`` with a clear message.
    """

    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ImportError(
            f"{module_name}.{attribute} is not available yet "
            "(parallel VNLRAG-29/30 development); "
            "integration runs after the modules are merged."
        ) from exc
    return getattr(module, attribute)


def provenance_coverage(provisions: list[ExtractedLegalProvision]) -> float:
    """Provenance coverage per the VNLRAG-29 contract: fraction of provisions
    with ≥1 ``source_element_id`` and a non-null ``page_number`` (0.0 for an
    empty list).  Tests monkeypatch this module-level name.
    """

    return float(_load_contract("app.ingestion.provenance", "provenance_coverage")(provisions))


def validate_hierarchy(provisions: list[ExtractedLegalProvision]) -> Any:
    """Hierarchy validation per the VNLRAG-30 contract: the result has
    ``.violations`` and ``.metrics`` with the fixed keys ``orphan_point_count``
    / ``orphan_clause_count`` / ``duplicate_count``.  Tests monkeypatch this
    module-level name.
    """

    return _load_contract("app.ingestion.hierarchy_validation", "validate_hierarchy")(provisions)


# ────────────────────────────────────────────────────────────────────────────
# Per-metric helpers
# ────────────────────────────────────────────────────────────────────────────


class CorpusQaMetrics(BaseModel):
    """The EXACT 16 corpus QA metrics (doc 00 §10.3, doc 03 §3.10.5)."""

    model_config = ConfigDict(extra="forbid")

    #: Distinct documents represented by the provision list.
    document_count: int
    #: Provisions whose ``node_kind`` is ``ARTICLE``.
    article_count: int
    #: Provisions whose ``node_kind`` is ``CLAUSE``.
    clause_count: int
    #: Provisions whose ``node_kind`` is ``POINT``.
    point_count: int
    #: ``POINT`` provisions / expected points (manifest ``expected_points``
    #: declaration first, gold fixture fallback, else 0 baseline).
    point_coverage: float
    #: Retained short points / short points flagged by the extractor
    #: (rulespec §5 — no token-length threshold; retained = present and not
    #: DROPPED/REJECTED).
    short_point_retention: float
    #: Vietnamese đ) detection rate — Point labels detected as ``đ)``,
    #: distinct from ``d)`` (rulespec §4).  Computed locally by
    #: ``vietnamese_d_detection_rate``, NOT from hierarchy validation's
    #: generic point-label rate.
    d_point_detection_rate: float
    #: Orphan Points without a parent Clause/Article (validate_hierarchy).
    orphan_point_count: int
    #: Orphan Clauses without a parent Article (validate_hierarchy).
    orphan_clause_count: int
    #: Duplicate provisions detected (validate_hierarchy ``duplicate_count``).
    duplicate_provision_count: int
    #: Share of provisions with a non-empty ``parent_context``.
    parent_context_coverage: float
    #: Share of provisions with ≥1 ``source_element_id`` and a non-null
    #: ``page_number`` (VNLRAG-29 provenance contract).
    provenance_coverage: float
    #: ``TABLE`` provisions / expected tables (manifest ``expected_tables``;
    #: else 0 baseline with a note).
    table_coverage: float
    #: REFERS_TO citations (rulespec §7) that resolve to no provision_id in
    #: the corpus.
    unresolved_cross_reference_count: int
    #: ACCEPTED provisions with ``effective_from`` None + provisions of
    #: documents whose manifest ``status`` is ``UNKNOWN``.
    unknown_effective_date_count: int
    #: Provisions with ``effective_to < effective_from`` (half-open
    #: ``[from, to)`` interval, rulespec §8).
    temporal_conflict_count: int


class CorpusQaReportShape(BaseModel):
    """Report shape matching the ``CorpusQaReport`` persistence fields.

    ``id`` (DB-generated UUID) and DB server defaults are intentionally
    absent; the repository maps this shape onto the ORM row.
    """

    model_config = ConfigDict(extra="forbid")

    report_id: str
    corpus_version: str
    corpus_hash: str
    metrics: CorpusQaMetrics
    documents_analyzed: list[dict[str, Any]] | None = None
    notes: str | None = None
    generated_at: datetime


# ────────────────────────────────────────────────────────────────────────────
# REFERS_TO cross-reference patterns (rulespec §7, doc 03 §3.14.1)
# ────────────────────────────────────────────────────────────────────────────

#: Optional trailing document mention, e.g. " Nghị định 168/2024/NĐ-CP"
#: ("của" for "Điều 7 của Nghị định 168/2024/NĐ-CP").
_DOC_MENTION = (
    r"(?:\s+(?:của\s+)?(?:nghị\s+định|luật|thông\s+tư|nghị\s+quyết|quyết\s+định)"
    r"\s*(?:số\s+)?\d+(?:/\d+)*(?:/[a-zđ]+(?:-[a-z]+)*)?)?"
)

#: REFERS_TO citation patterns, most specific first.  ``Điểm`` letters are
#: followed by ``)`` or whitespace only, so "điểm của" is not a false
#: positive (rulespec §7: "khoảng cách" style false positives guarded by the
#: mandatory number / letter-position constraints).
_REFERS_TO_PATTERNS: tuple[re.Pattern[str], ...] = (
    # "theo quy định tại (Điều|Khoản|Điểm) X" with chained forms.
    re.compile(
        r"theo\s+quy\s+định\s+tại\s+"
        r"(?:Điểm\s*[a-zđ](?=\s|\))\s+)?"
        r"(?:Khoản\s*\d+\s+)?"
        r"(?:Điều\s*\d+|Khoản\s*\d+|Điểm\s*[a-zđ](?=\s|\)))" + _DOC_MENTION,
        re.IGNORECASE,
    ),
    # "quy định tại (Điều|Khoản|Điểm) X" with chained forms.
    re.compile(
        r"quy\s+định\s+tại\s+"
        r"(?:Điểm\s*[a-zđ](?=\s|\))\s+)?"
        r"(?:Khoản\s*\d+\s+)?"
        r"(?:Điều\s*\d+|Khoản\s*\d+|Điểm\s*[a-zđ](?=\s|\)))" + _DOC_MENTION,
        re.IGNORECASE,
    ),
    # doc 03 §3.14.1 light form: "theo Khoản Y" / "theo Điều Z".
    re.compile(
        r"theo\s+"
        r"(?:Điểm\s*[a-zđ](?=\s|\))\s+)?"
        r"(?:Khoản\s*\d+\s+)?"
        r"(?:Điều\s*\d+|Khoản\s*\d+|Điểm\s*[a-zđ](?=\s|\)))" + _DOC_MENTION,
        re.IGNORECASE,
    ),
    # rulespec §7 chained form: "Khoản 4 Điều 6", "Điểm a Khoản 4 Điều 7".
    re.compile(
        r"(?:Điểm\s*[a-zđ](?=\s|\))\s+)?"
        r"Khoản\s*\d+\s+Điều\s*\d+" + _DOC_MENTION,
        re.IGNORECASE,
    ),
)

#: Document-type keyword → provision_id document slug prefix.
_DOC_TYPE_PREFIX: dict[str, str] = {
    "nghị định": "nd",
    "luật": "luat",
    "thông tư": "tt",
    "nghị quyết": "nq",
    "quyết định": "qd",
}

_DOC_IN_CITATION_RE = re.compile(
    r"(?P<kind>nghị\s+định|luật|thông\s+tư|nghị\s+quyết|quyết\s+định)"
    r"\s*(?:số\s+)?(?P<number>\d+)(?:/(?P<year>\d+))?",
    re.IGNORECASE,
)
_POINT_IN_CITATION_RE = re.compile(r"Điểm\s*([a-zđ])(?=\s|\))", re.IGNORECASE)
_CLAUSE_IN_CITATION_RE = re.compile(r"Khoản\s*(\d+)", re.IGNORECASE)
_ARTICLE_IN_CITATION_RE = re.compile(r"Điều\s*(\d+)", re.IGNORECASE)

#: Gold annotation dir (doc 06 §6.13.4) — human-reviewed reference structure
#: shared by Suite A; used as the "expected points" fallback for
#: ``point_coverage`` when a manifest does not declare ``expected_points``.
_GOLD_DIR = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "parser_benchmark" / "gold"

#: Review states that keep a provision "retained" for short-Point retention.
_RETAINED_REVIEW_STATES = frozenset({"PENDING", "ACCEPTED"})


# ────────────────────────────────────────────────────────────────────────────
# Cross-reference extraction and resolution
# ────────────────────────────────────────────────────────────────────────────


def find_cross_references(
    text: str,
    *,
    patterns: tuple[re.Pattern[str], ...] | None = None,
) -> list[str]:
    """Return the REFERS_TO citations found in ``text`` (rulespec §7).

    Each citation is a normalized, non-overlapping match of the cross
    reference patterns (``"quy định tại (Điều|Khoản|Điểm) X"``,
    ``"theo quy định tại …"``, ``"theo Khoản Y"`` and chained forms such as
    ``"Khoản 4 Điều 6"`` / ``"Điểm a Khoản 4 Điều 7"``).  A bare ``Điều`` /
    ``Khoản`` without a trigger keyword is NOT a citation, so article
    headings like ``"Điều 5. …"`` are never false positives.
    """

    patterns = patterns or _REFERS_TO_PATTERNS
    spans: list[tuple[int, int]] = []
    for pattern in patterns:
        for match in pattern.finditer(text):
            spans.append(match.span())
    # Longest-first at each start position; drop spans inside kept ones so one
    # citation is never counted twice ("quy định tại Khoản 4 Điều 6" matches
    # both the "quy định tại" form and the chained form).
    spans.sort(key=lambda span: (span[0], -span[1]))
    citations: list[str] = []
    last_end = -1
    for start, end in spans:
        if start < last_end:
            continue
        citations.append(" ".join(text[start:end].split()))
        last_end = end
    return citations


def resolve_cross_reference(
    citation: str,
    *,
    citing_provision_id: str,
    known_provision_ids: Sequence[str],
) -> str | None:
    """Resolve one ``find_cross_references`` citation to a provision_id.

    The citation's explicit components (Điều/Khoản/Điểm, optional document
    mention) are turned into the deterministic provision_id form
    ``{doc}__dieu-N__khoan-M__diem-X``; the citation resolves iff that exact
    id exists in ``known_provision_ids``.  When the citation omits the Điều
    (e.g. PENALTY_COMPANION ``"quy định tại Khoản 13"``), the citing
    provision's own article/clause context is used.  Returns ``None`` when
    the target provision (or cited document) is not in the corpus.
    """

    known = set(known_provision_ids)
    citing_parts = citing_provision_id.split("__")
    citing_document = citing_parts[0]
    citing_ctx: dict[str, str] = {}
    for part in citing_parts[1:]:
        if part.startswith("dieu-"):
            citing_ctx["article"] = part.removeprefix("dieu-")
        elif part.startswith("khoan-"):
            citing_ctx["clause"] = part.removeprefix("khoan-")
        elif part.startswith("diem-"):
            citing_ctx["point"] = part.removeprefix("diem-")

    doc_slug = _cited_document_slug(citation, citing_document=citing_document, known=known)
    if doc_slug is None:
        return None

    point = _first_match(_POINT_IN_CITATION_RE, citation)
    clause = _first_match(_CLAUSE_IN_CITATION_RE, citation)
    article = _first_match(_ARTICLE_IN_CITATION_RE, citation)

    if article is not None:
        if point is not None and clause is None:
            # A Điểm under a Điều without a Khoản has no provision_id form.
            return None
        candidate = f"{doc_slug}__dieu-{article}"
        if clause is not None:
            candidate += f"__khoan-{clause}"
            if point is not None:
                candidate += f"__diem-{point}"
    elif point is not None and citing_ctx.get("article") and citing_ctx.get("clause"):
        candidate = (
            f"{doc_slug}__dieu-{citing_ctx['article']}__khoan-{citing_ctx['clause']}__diem-{point}"
        )
    elif clause is not None and citing_ctx.get("article"):
        candidate = f"{doc_slug}__dieu-{citing_ctx['article']}__khoan-{clause}"
    else:
        return None
    return candidate if candidate in known else None


def _first_match(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).casefold() if match else None


def _cited_document_slug(citation: str, *, citing_document: str, known: set[str]) -> str | None:
    """Document slug the citation points at; the citing document by default.

    Returns ``None`` when the citation names a document that is not in the
    corpus (an out-of-corpus citation is unresolvable by construction).
    """

    match = _DOC_IN_CITATION_RE.search(citation)
    if match is None:
        return citing_document
    prefix = _DOC_TYPE_PREFIX[" ".join(match.group("kind").split()).casefold()]
    number = match.group("number")
    year = match.group("year")
    known_slugs = {provision_id.split("__", 1)[0] for provision_id in known}
    for slug in known_slugs:
        if slug.startswith(f"{prefix}-{number}-") and (year is None or year in slug.split("-")):
            return slug
    return None


# ────────────────────────────────────────────────────────────────────────────
# Per-metric helpers
# ────────────────────────────────────────────────────────────────────────────


def vietnamese_d_detection_rate(provisions: Sequence[ExtractedLegalProvision]) -> float:
    """Rate of detected Point labels that are correctly ``đ)`` (rulespec §4).

    A Point whose canonical label is ``"đ)"`` (the đ character preserved,
    distinct from ``d)``) counts as correctly detected; the denominator is
    every POINT provision with a detected label.  0.0 when no label is
    detected.  This is the source of the report's ``d_point_detection_rate``
    metric (FR-10) — it is NOT taken from hierarchy validation.
    """

    labeled = 0
    d_da = 0
    for provision in provisions:
        if provision.node_kind != "POINT" or not provision.point_label:
            continue
        labeled += 1
        if canonical_point_label(provision.point_label) == "đ)":
            d_da += 1
    return d_da / labeled if labeled else 0.0


def structural_qa_report(
    provisions: Sequence[ExtractedLegalProvision], document_id: str
) -> dict[str, Any]:
    """Targeted structural QA for one key document (e.g. nd-168-2024).

    Reuses ``validate_hierarchy`` (VNLRAG-30) and returns a compact dict with
    the per-document provision count, the hierarchy violations and the
    hierarchy metrics (orphan/duplicate counts, point-label detection rate).
    """

    result = validate_hierarchy(list(provisions))
    return {
        "document_id": document_id,
        "provision_count": len(provisions),
        "hierarchy_violations": [_dump_model(violation) for violation in result.violations],
        "hierarchy_metrics": dict(result.metrics),
    }


def _dump_model(value: Any) -> Any:
    dump = getattr(value, "model_dump", None)
    return dump() if callable(dump) else value


def _document_id(provision: ExtractedLegalProvision) -> str:
    """Stable document slug for a provision (provision_id prefix)."""

    if "__" in provision.provision_id:
        return provision.provision_id.split("__", 1)[0]
    return provision.document_version_id


def _provenance_coverage(provisions: Sequence[ExtractedLegalProvision]) -> float:
    return provenance_coverage(list(provisions))


def _hierarchy_metrics(provisions: Sequence[ExtractedLegalProvision]) -> dict[str, float | int]:
    return dict(validate_hierarchy(list(provisions)).metrics)


def _expected_points(
    provisions: Sequence[ExtractedLegalProvision], manifests: dict[str, dict] | None
) -> tuple[int, str | None]:
    """Expected POINT count: manifest ``expected_points`` first, gold fallback."""

    per_document: dict[str, int] = {}
    for document_id, manifest in (manifests or {}).items():
        declared = manifest.get("expected_points")
        if isinstance(declared, int) and declared >= 0:
            per_document[document_id] = declared
    gold_used: list[str] = []
    for document_id in {_document_id(p) for p in provisions}:
        if document_id in per_document:
            continue
        count = _gold_point_count(document_id)
        if count is not None:
            per_document[document_id] = count
            gold_used.append(document_id)
    total = sum(per_document.values())
    note: str | None = None
    if gold_used:
        note = f"expected point counts from gold fixtures: {', '.join(sorted(gold_used))}"
    if total == 0:
        note = (
            "no expected point counts declared in manifests/gold; "
            f"point coverage computed against 0 baseline{f'; {note}' if note else ''}"
        )
    return total, note


def _gold_point_count(document_id: str) -> int | None:
    """Human-reviewed POINT count for ``document_id`` from the gold fixtures."""

    try:
        for path in _GOLD_DIR.glob("*-gold.json"):
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("document_id") != document_id:
                continue
            return sum(
                1 for provision in data.get("provisions", []) if provision.get("point") is not None
            )
    except (OSError, json.JSONDecodeError):  # pragma: no cover - fixture IO
        return None
    return None


def _expected_tables(manifests: dict[str, dict] | None) -> tuple[int, str | None]:
    """Expected TABLE count from manifest ``expected_tables`` declarations."""

    total = 0
    for manifest in (manifests or {}).values():
        declared = manifest.get("expected_tables")
        if isinstance(declared, int) and declared >= 0:
            total += declared
    note = None
    if total == 0:
        note = (
            "no expected_tables declared in manifests; table coverage computed against 0 baseline"
        )
    return total, note


def _temporal_conflict_count(provisions: Sequence[ExtractedLegalProvision]) -> int:
    """Provisions whose ``effective_to < effective_from`` (half-open interval)."""

    count = 0
    for provision in provisions:
        effective_from = _parse_date(provision.effective_from)
        effective_to = _parse_date(provision.effective_to)
        if (
            effective_from is not None
            and effective_to is not None
            and effective_to < effective_from
        ):
            count += 1
    return count


def _parse_date(value: str | None) -> Any:
    """``date`` for an ISO 8601 value, or None when unparseable."""

    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.date() if isinstance(parsed, datetime) else parsed


def _unknown_effective_date_count(
    provisions: Sequence[ExtractedLegalProvision], manifests: dict[str, dict] | None
) -> int:
    """ACCEPTED provisions without ``effective_from`` + UNKNOWN-status documents."""

    unknown_status_documents = {
        document_id
        for document_id, manifest in (manifests or {}).items()
        if manifest.get("status") == "UNKNOWN"
    }
    count = 0
    for provision in provisions:
        if provision.review_status == "ACCEPTED" and provision.effective_from is None:
            count += 1
            continue
        if _document_id(provision) in unknown_status_documents:
            count += 1
    return count


def _unresolved_cross_reference_count(
    provisions: Sequence[ExtractedLegalProvision],
    *,
    patterns: tuple[re.Pattern[str], ...] | None,
) -> int:
    """Citations (rulespec §7) that resolve to no corpus provision_id."""

    known_ids = [provision.provision_id for provision in provisions]
    count = 0
    for provision in provisions:
        for citation in find_cross_references(provision.source_text, patterns=patterns):
            if (
                resolve_cross_reference(
                    citation,
                    citing_provision_id=provision.provision_id,
                    known_provision_ids=known_ids,
                )
                is None
            ):
                count += 1
    return count


# ────────────────────────────────────────────────────────────────────────────
# Report entry points
# ────────────────────────────────────────────────────────────────────────────


def run_corpus_qa(
    provisions: list[ExtractedLegalProvision],
    *,
    corpus_version: str,
    corpus_hash: str,
    manifests: dict[str, dict] | None = None,
    cross_reference_patterns: tuple[re.Pattern[str], ...] | None = None,
) -> CorpusQaReportShape:
    """Compute the full FR-10 corpus QA report for ``provisions``.

    ``manifests`` maps document_id → manifest dict (``expected_points`` /
    ``expected_tables`` declarations, document ``status``).  The report never
    modifies the input provisions; with an empty corpus every metric is 0.
    """

    notes: list[str] = []
    total = len(provisions)
    document_ids = sorted({_document_id(provision) for provision in provisions})
    document_count = len(document_ids)
    article_count = sum(1 for p in provisions if p.node_kind == "ARTICLE")
    clause_count = sum(1 for p in provisions if p.node_kind == "CLAUSE")
    point_count = sum(1 for p in provisions if p.node_kind == "POINT")

    expected_points, point_note = _expected_points(provisions, manifests)
    point_coverage = point_count / expected_points if expected_points > 0 else 0.0
    if point_note:
        notes.append(point_note)

    flagged_short = [p for p in provisions if p.short_point]
    retained_short = [p for p in flagged_short if p.review_status in _RETAINED_REVIEW_STATES]
    short_point_retention = len(retained_short) / len(flagged_short) if flagged_short else 0.0

    hierarchy_metrics = _hierarchy_metrics(provisions)
    orphan_point_count = int(hierarchy_metrics["orphan_point_count"])
    orphan_clause_count = int(hierarchy_metrics["orphan_clause_count"])
    duplicate_provision_count = int(hierarchy_metrics["duplicate_count"])
    d_point_detection_rate = vietnamese_d_detection_rate(provisions)

    parent_context_count = sum(
        1 for p in provisions if p.parent_context is not None and p.parent_context.strip() != ""
    )
    parent_context_coverage = parent_context_count / total if total else 0.0

    provenance = _provenance_coverage(provisions)

    table_count = sum(1 for p in provisions if p.node_kind == "TABLE")
    expected_tables, table_note = _expected_tables(manifests)
    table_coverage = table_count / expected_tables if expected_tables > 0 else 0.0
    if table_note:
        notes.append(table_note)

    unresolved_cross_reference_count = _unresolved_cross_reference_count(
        provisions, patterns=cross_reference_patterns
    )
    unknown_effective_date_count = _unknown_effective_date_count(provisions, manifests)
    temporal_conflict_count = _temporal_conflict_count(provisions)

    metrics = CorpusQaMetrics(
        document_count=document_count,
        article_count=article_count,
        clause_count=clause_count,
        point_count=point_count,
        point_coverage=point_coverage,
        short_point_retention=short_point_retention,
        d_point_detection_rate=d_point_detection_rate,
        orphan_point_count=orphan_point_count,
        orphan_clause_count=orphan_clause_count,
        duplicate_provision_count=duplicate_provision_count,
        parent_context_coverage=parent_context_coverage,
        provenance_coverage=provenance,
        table_coverage=table_coverage,
        unresolved_cross_reference_count=unresolved_cross_reference_count,
        unknown_effective_date_count=unknown_effective_date_count,
        temporal_conflict_count=temporal_conflict_count,
    )

    documents_analyzed: list[dict[str, Any]] = []
    for document_id in document_ids:
        document_provisions = [p for p in provisions if _document_id(p) == document_id]
        documents_analyzed.append(
            {
                "document_id": document_id,
                "provision_count": len(document_provisions),
                "structural_qa": structural_qa_report(document_provisions, document_id),
            }
        )

    notes.append(
        f"corpus QA version {CORPUS_QA_VERSION}; computed over {total} provisions "
        f"across {document_count} documents"
    )

    generated_at = datetime.now(UTC)
    return CorpusQaReportShape(
        report_id=f"corpus-qa-{generated_at:%Y-%m-%d}-{uuid4().hex[:8]}",
        corpus_version=corpus_version,
        corpus_hash=corpus_hash,
        metrics=metrics,
        documents_analyzed=documents_analyzed,
        notes=". ".join(notes),
        generated_at=generated_at,
    )


def run_corpus_qa_from_manifests(
    manifests_dir: str,
    *,
    corpus_version: str,
    corpus_hash: str,
) -> CorpusQaReportShape:
    """Run corpus QA over every manifest under ``manifests_dir``.

    Loads ``*.manifest.json`` recursively (e.g. ``data/manifests`` holding
    ``batch-01/`` and ``batch-02/``) and any extraction output found next to
    the manifests (``data/<document_id>/provisions.json``,
    ``data/extracted/<document_id>.json`` …).  When extraction output is not
    yet available for a document, the report is computed over the provisions
    that could be built and the gap is recorded in ``notes``.
    """

    root = Path(manifests_dir)
    manifests: dict[str, dict] = {}
    for path in sorted(root.rglob("*.manifest.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        document_id = data.get("document_id")
        if isinstance(document_id, str) and document_id:
            manifests[document_id] = data

    provisions: list[ExtractedLegalProvision] = []
    loaded_documents: list[str] = []
    for document_id in sorted(manifests):
        loaded = _load_provision_output(root, document_id)
        if loaded is not None:
            provisions.extend(loaded)
            loaded_documents.append(document_id)

    report = run_corpus_qa(
        provisions,
        corpus_version=corpus_version,
        corpus_hash=corpus_hash,
        manifests=manifests,
    )
    coverage_note = (
        f"manifests loaded: {len(manifests)} documents; "
        f"provisions loaded for {len(loaded_documents)} documents "
        f"({len(provisions)} provisions)"
    )
    report.notes = f"{coverage_note}. {report.notes}" if report.notes else coverage_note
    return report


def _load_provision_output(
    manifests_root: Path, document_id: str
) -> list[ExtractedLegalProvision] | None:
    """Provisions from any real extraction output under ``data/``, else None.

    Candidate locations mirror the repo layout: ``data/<document_id>/`` and
    ``data/extracted/``.  Only the first hit is used.
    """

    data_root = manifests_root.parent
    candidates = (
        data_root / document_id / "provisions.json",
        data_root / document_id / "extracted" / "provisions.json",
        data_root / "extracted" / f"{document_id}.json",
        data_root / f"{document_id}.provisions.json",
    )
    for path in candidates:
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        records = payload.get("provisions") if isinstance(payload, dict) else payload
        if not isinstance(records, list):
            continue
        return [ExtractedLegalProvision.model_validate(record) for record in records]
    return None


__all__ = [
    "CORPUS_QA_VERSION",
    "CorpusQaMetrics",
    "CorpusQaReportShape",
    "find_cross_references",
    "resolve_cross_reference",
    "run_corpus_qa",
    "run_corpus_qa_from_manifests",
    "structural_qa_report",
    "vietnamese_d_detection_rate",
]
