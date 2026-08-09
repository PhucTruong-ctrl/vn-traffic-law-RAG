"""Quality gates for the Parser Router (VNLRAG-131).

Two gate groups, run at two different points of the ingestion pipeline
(doc 03 §3.7.3, L948-999; ``docs/parser_router.yaml``):

* **Group A — parser-level gates (OPERATIONAL in W2).** Run AFTER IR
  normalization and BEFORE the Legal Structure Extractor, on
  :class:`~app.ingestion.document_ir.ParsedDocument` /
  :class:`~app.ingestion.document_ir.DocumentElement`.
* **Group B — structural gates (CONTRACT ONLY in W2).** Run AFTER the Legal
  Structure Extractor (VNLRAG-26/28, W3) on ``LegalProvision[]``. This module
  defines the typed contract (:class:`GroupBThresholds`,
  :class:`GroupBContract`) and the stub :func:`evaluate_group_b`; execution
  lands in W3. No extractor logic is implemented here.

Formula decisions (documented, tested):

* ``provenance_coverage`` uses the **bbox share** as the discriminator:
  ``page_number`` is a required, non-optional field of the frozen IR schema
  (``document-ir-v1`` §6), so its coverage is 1.0 by construction and cannot
  separate parser quality; ``bbox`` is optional and is the informative
  parser-provenance signal (same rationale as Suite A metric 2's documented
  ``bbox_share``, ``app/evaluation/suites/suite_a.py``). The yaml comment
  treats "provenance_coverage < 0.9 **hoặc bbox thiếu**" as the same
  low-provenance review trigger.
* ``text_extraction_rate`` counts pages whose ``page.text`` is non-empty after
  ``strip()`` (Suite A metric 1 rule).
* ``table_detection_rate`` is N/A (None, never 0) when no expected table count
  is supplied — a gate cannot assert on expectations it does not have.
* ``layout_coherence`` measures spatial-progression coherence (user finding
  #7): the share of element pairs whose ``reading_order`` agrees with a
  row-major spatial path (``round(bbox.top, 2)`` then ``bbox.left``). The old
  rule asserted the adapter-assigned ``reading_order`` was strictly ``+1``
  contiguous — since both adapters number elements by global iteration index,
  that passed by construction and measured adapter numbering, not parser
  layout quality. Implemented locally — the ingestion package must not import
  the evaluation package (same rule in ``app/evaluation/suites/suite_a.py``).

All fraction-returning functions use ``None`` to mean N/A (cannot compute), so
an empty document never produces a fabricated 0.0 that would spuriously fail a
gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, NoReturn

from pydantic import BaseModel

from app.ingestion.document_ir import DocumentElement, ParsedDocument

GateStatus = Literal["passed", "failed", "na"]

#: Defaults mirror ``docs/parser_router.yaml`` → ``parser_router.quality_gates``.
DEFAULT_MIN_PROVENANCE_COVERAGE = 0.9
DEFAULT_MIN_TEXT_EXTRACTION_RATE = 0.8
DEFAULT_MIN_TABLE_DETECTION_RATE = 0.6

#: Group B defaults mirror ``docs/parser_router.yaml`` →
#: ``parser_router.quality_gates.structural``.
DEFAULT_MIN_POINT_LABEL_DETECTION = 0.9
DEFAULT_MIN_HIERARCHY_COMPLETENESS = 0.9


def _elements(doc: ParsedDocument) -> list[DocumentElement]:
    return [element for page in doc.pages for element in page.elements]


# ────────────────────────────────────────────────────────────────────────────
# Group A — parser-level gates (operational on the canonical IR)
# ────────────────────────────────────────────────────────────────────────────


def provenance_coverage(doc: ParsedDocument) -> float | None:
    """Share of elements carrying parser provenance (bbox), or None (N/A).

    Formula: ``elements with bbox is not None / all elements``.

    ``page_number`` is schema-required (``document-ir-v1`` §6), so its share
    is 1.0 by construction; ``bbox`` is optional and is the discriminating
    parser-provenance signal (mirrors Suite A metric 2's ``bbox_share``). A
    scan/OCR parse that cannot localize elements yields a low score and routes
    to review (never auto-index partial OCR output).
    """
    elements = _elements(doc)
    if not elements:
        return None
    with_bbox = sum(1 for element in elements if element.bbox is not None)
    return with_bbox / len(elements)


def text_extraction_rate(doc: ParsedDocument) -> float | None:
    """Share of pages with non-empty extracted text, or None (N/A).

    Formula: ``pages with non-empty page.text (after strip) / total pages`` —
    Suite A metric 1 rule. Quantity-only: this gate cannot certify legal
    correctness (d/đ labels, hierarchy); that is Group B's role.
    """
    total = len(doc.pages)
    if total == 0:
        return None
    extracted = sum(1 for page in doc.pages if page.text and page.text.strip())
    return extracted / total


def table_detection_rate(doc: ParsedDocument, expected_tables: int | None) -> float | None:
    """Share of expected tables detected as table elements, or None (N/A).

    ``expected_tables`` is the expected table count (from the manifest / gold
    annotations). When it is None or 0 there are no expectations to assert
    against -> N/A (never a fabricated 0.0).
    """
    if expected_tables is None or expected_tables == 0:
        return None
    detected = sum(1 for element in _elements(doc) if element.element_type == "table")
    return detected / expected_tables


def _page_layout_score(elements: list[DocumentElement]) -> float:
    """Share of spatial pairs on one page that agree with ``reading_order``.

    Only elements carrying a bbox participate. A pair is *comparable* when its
    two elements have distinct spatial keys ``(round(top, 2), round(left, 2))``
    AND distinct ``reading_order`` — equal keys mean no spatial discrimination
    (e.g. overlapping/stacked boxes) and equal orders mean no claimed order, so
    neither can be judged. A comparable pair *agrees* when the relative spatial
    order (row-major: top-down, then left-to-right) matches the relative
    ``reading_order``. Pages with <2 bbox'd elements have no pairs and are
    trivially coherent (1.0). Deterministic — no scipy, pure integer/float
    comparisons.
    """
    keys: list[tuple[float, float]] = []
    orders: list[int] = []
    for element in elements:
        bbox = element.bbox
        if bbox is None:
            continue
        keys.append((round(bbox.top, 2), round(bbox.left, 2)))
        orders.append(element.reading_order)
    comparable = 0
    agreeing = 0
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            if keys[i] == keys[j] or orders[i] == orders[j]:
                continue
            comparable += 1
            if (keys[i] < keys[j]) == (orders[i] < orders[j]):
                agreeing += 1
    return 1.0 if comparable == 0 else agreeing / comparable


def layout_coherence(doc: ParsedDocument) -> float | None:
    """Spatial-progression coherence — does the parser read a plausible path?

    Rule (user finding #7; identical to Suite A metric 6, duplicated locally —
    ingestion must not import the evaluation package): for each page, compare
    the adapter-assigned ``reading_order`` against a row-major spatial path
    derived from element bboxes — an element's spatial key is
    ``(round(bbox.top, 2), round(bbox.left, 2))`` (top=0 at the page top, so
    smaller ``top`` is earlier; within a row band, smaller ``left`` is
    earlier). The page score is the fraction of element pairs whose relative
    ``reading_order`` matches their relative spatial order
    (:func:`_page_layout_score`); the document score is the mean across pages
    carrying at least one bbox'd element. A parser that emits an element before
    the element physically above it (bottom-before-top, wrong column order in a
    multi-column layout) scores < 1.0.

    Pages with no bbox'd element contribute no spatial signal and are excluded
    from the mean (``provenance_coverage`` is the gate that asserts bbox
    presence). Returns ``None`` (N/A) when no page carries a bbox'd element —
    layout plausibility cannot be measured without any spatial signal — and
    1.0 vacuously for an empty document.
    """
    page_scores: list[float] = []
    for page in doc.pages:
        bboxed = [element for element in page.elements if element.bbox is not None]
        if bboxed:
            page_scores.append(_page_layout_score(bboxed))
    if not page_scores:
        if not _elements(doc):
            return 1.0  # no elements at all -> vacuously coherent
        return None  # elements exist but no bbox anywhere -> N/A (no signal)
    return sum(page_scores) / len(page_scores)


class GroupAThresholds(BaseModel):
    """Group A threshold set (defaults from ``docs/parser_router.yaml``).

    ``min_layout_coherence`` defaults to None because the yaml config does not
    set a layout threshold ("tùy loại văn bản", doc 03 §3.7.3) — when None the
    layout gate is reported N/A unless a caller supplies a threshold.
    """

    min_provenance_coverage: float = DEFAULT_MIN_PROVENANCE_COVERAGE
    min_text_extraction_rate: float = DEFAULT_MIN_TEXT_EXTRACTION_RATE
    min_table_detection_rate: float = DEFAULT_MIN_TABLE_DETECTION_RATE
    min_layout_coherence: float | None = None


class GateResult(BaseModel):
    """One gate's evaluation: measured value vs threshold, passed/failed/na."""

    gate: str
    value: float | None = None
    threshold: float | None = None
    status: GateStatus = "na"
    detail: dict[str, Any] = {}


class GroupAResult(BaseModel):
    """Group A verdict: per-gate results plus the overall verdict.

    Overall verdict: ``failed`` when any gate failed; otherwise ``passed`` when
    at least one gate was computed and all computed gates passed; ``na`` when
    every gate is N/A (nothing was computable to assert on).
    """

    provenance_coverage: GateResult
    text_extraction_rate: GateResult
    table_detection_rate: GateResult
    layout_coherence: GateResult
    verdict: GateStatus

    @property
    def gates(self) -> list[GateResult]:
        return [
            self.provenance_coverage,
            self.text_extraction_rate,
            self.table_detection_rate,
            self.layout_coherence,
        ]


def _verdict(results: list[GateResult]) -> GateStatus:
    if any(result.status == "failed" for result in results):
        return "failed"
    if any(result.status == "passed" for result in results):
        return "passed"
    return "na"


def _gate(
    gate: str, value: float | None, threshold: float | None, detail: dict[str, Any] | None = None
) -> GateResult:
    if value is None or threshold is None:
        return GateResult(
            gate=gate, value=value, threshold=threshold, status="na", detail=detail or {}
        )
    passed = value >= threshold
    return GateResult(
        gate=gate,
        value=value,
        threshold=threshold,
        status="passed" if passed else "failed",
        detail=detail or {},
    )


def evaluate_group_a(
    doc: ParsedDocument,
    thresholds: GroupAThresholds | None = None,
    expected_tables: int | None = None,
) -> GroupAResult:
    """Evaluate all Group A gates on ``doc`` -> per-gate + overall verdict.

    ``expected_tables`` is optional: table detection is N/A when no expected
    table count is supplied (the IR carries no table expectations).
    """
    config = thresholds or GroupAThresholds()
    provenance = provenance_coverage(doc)
    extraction = text_extraction_rate(doc)
    table = table_detection_rate(doc, expected_tables)
    layout = layout_coherence(doc)

    results = [
        _gate(
            "provenance_coverage",
            provenance,
            config.min_provenance_coverage,
            {
                "formula": (
                    "elements with bbox is not None / all elements; page_number schema-required"
                )
            },
        ),
        _gate(
            "text_extraction_rate",
            extraction,
            config.min_text_extraction_rate,
            {"formula": "pages with non-empty page.text / total pages"},
        ),
        _gate(
            "table_detection_rate",
            table,
            config.min_table_detection_rate,
            {"formula": "table elements / expected_tables; N/A when no expectations"},
        ),
        _gate(
            "layout_coherence",
            layout,
            config.min_layout_coherence,
            {
                "formula": (
                    "share of pairs whose reading_order matches row-major bbox "
                    "order (round(top,2), left); N/A without bbox"
                )
            },
        ),
    ]
    return GroupAResult(
        provenance_coverage=results[0],
        text_extraction_rate=results[1],
        table_detection_rate=results[2],
        layout_coherence=results[3],
        verdict=_verdict(results),
    )


# ────────────────────────────────────────────────────────────────────────────
# Group B — structural gates (CONTRACT ONLY in W2; execution in W3)
# ────────────────────────────────────────────────────────────────────────────


class GroupBThresholds(BaseModel):
    """Group B threshold set (defaults from ``docs/parser_router.yaml``).

    Contract for W3: execution happens after the Legal Structure Extractor
    (VNLRAG-26/28) on ``LegalProvision[]``.
    """

    min_point_label_detection: float = DEFAULT_MIN_POINT_LABEL_DETECTION
    min_hierarchy_completeness: float = DEFAULT_MIN_HIERARCHY_COMPLETENESS


@dataclass(frozen=True)
class GroupBContract:
    """Group B (structural) gates — typed CONTRACT in W2 (VNLRAG-131).

    These gates run AFTER the Legal Structure Extractor because they need its
    output (``LegalProvision[]``, not the parser IR). In W2 this is a contract
    + config only: :func:`evaluate_group_b` raises ``NotImplementedError``.
    Execution lands in W3 (VNLRAG-26/28 extractor + VNLRAG-131 W3).
    """

    name: str = "group_b_structural"
    gates: tuple[str, ...] = ("point_label_detection", "hierarchy_completeness")
    thresholds: GroupBThresholds = field(default_factory=GroupBThresholds)
    runs_on: str = "LegalProvision[]"
    executes_after: str = "Legal Structure Extractor (VNLRAG-26/28)"
    implemented_in: str = "VNLRAG-131 W3"
    # Rulespec §5: short-point retention has NO token-length threshold — a
    # short-but-valid point is retained. Not a numeric gate; documented for W3.
    short_point_retention: str = "no token-length threshold (rulespec §5)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "gates": list(self.gates),
            "thresholds": self.thresholds.model_dump(mode="json"),
            "runs_on": self.runs_on,
            "executes_after": self.executes_after,
            "implemented_in": self.implemented_in,
            "short_point_retention": self.short_point_retention,
        }


def evaluate_group_b(provisions: list[Any], thresholds: GroupBThresholds | None = None) -> NoReturn:
    """Group B structural gate evaluation — stub, CONTRACT ONLY in W2.

    Implemented in W3 (VNLRAG-131 W3) once the Legal Structure Extractor
    (VNLRAG-26/28) produces ``LegalProvision[]``. Execution requires
    structural-recognition output the parser IR does not carry (d/đ point
    labels, article/clause/point hierarchy, short-point retention).
    """
    del provisions, thresholds  # contract-only stub; inputs land in W3
    raise NotImplementedError(
        "Group B structural gates are contract-only in W2 (VNLRAG-131). Execution "
        "lands in W3 after the Legal Structure Extractor (VNLRAG-26/28) produces "
        "LegalProvision[] (min_point_label_detection, min_hierarchy_completeness)."
    )
