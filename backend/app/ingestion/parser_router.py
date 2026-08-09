"""Parser Router — selects Docling or MinerU per document + quality gates (VNLRAG-131).

Implements doc 03 §3.7 (L926-1019), ``docs/parser_router.yaml`` (authoritative
config), and Suite A §7's routing recommendation
(``docs/evaluation/suite-a-first-pass-report.md``).

Routing rules (doc 03 §3.7.1 table + Suite A §7):

| Input class | Route | OCR | Fallback |
|---|---|---|---|
| non-PDF (DOCX/HTML/EPUB) | ``docling_other_mime`` | no | none (P0) |
| PDF searchable (std layout) | ``docling_text`` | no | mineru |
| PDF scan (no text layer) | ``docling_ocr`` | yes | mineru |
| PDF complex tables | ``compare_complex_tables`` | per scan | gate/review |

Complex tables = ``compare_on_complex_tables`` (yaml) AND
``layout_complexity >= COMPLEX_TABLE_COUNT_THRESHOLD`` (layout_complexity is a
table-count estimate; threshold is a W2 heuristic, documented in
:data:`COMPLEX_TABLE_COUNT_THRESHOLD`).

W2 scope: routing + Group A gates are OPERATIONAL; Group B gates are a typed
contract (:mod:`app.ingestion.quality_gates`). Parses are injected lazily at the
:meth:`ParserRouter.route_and_gate` boundary as ``primary_runner`` /
``alternate_runner`` callables — the ingestion pipeline (another ticket) wires
the real adapters (:mod:`app.ingestion.adapters.docling_adapter`,
:mod:`app.ingestion.adapters.mineru_adapter`, the latter running the real
MinerU pipeline via ``mineru.cli.client``). No parser mixing: a single
``source_parser`` per document in every outcome.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import yaml  # type: ignore[import-untyped]  # PyYAML ships no stubs (mypy)
from pydantic import BaseModel

from app.ingestion.adapters.docling_adapter import (
    DEFAULT_OCR_CMD,
    DEFAULT_TESSDATA_DIR,
    OCR_DPI,
    OCR_PSM,
    check_ocr_readiness,
)
from app.ingestion.document_ir import ParsedDocument
from app.ingestion.quality_gates import (
    GateResult,
    GroupAResult,
    GroupAThresholds,
    evaluate_group_a,
)

#: W2 heuristic: a document is "complex tables" when its estimated table count
#: reaches this. Not in the yaml config; configurable in W3 if the corpus shows
#: a better boundary (doc 03 §3.7.1 "Bảng phức tạp").
COMPLEX_TABLE_COUNT_THRESHOLD = 3

#: Resolved against the repo root (``backend/app/ingestion/parser_router.py``
#: -> parents[3] = repo root). Falls back to defaults when absent.
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "docs" / "parser_router.yaml"

#: Schema tag for the ``ingestion_runs.parser_routing`` record (doc 03 §3.7.4).
PARSER_ROUTING_RECORD_SCHEMA = "parser_routing-v1"

#: Terminal outcomes (doc 03 §3.7.5 / task): accepted, needs_review, failed.
TerminalOutcome = Literal["accepted", "needs_review", "failed"]

OCR_SNAPSHOT_POLICY = (
    "scan-only OCR route: tesseract vie CPU-only; 300 DPI measured for 1-bit CCITT, "
    "600 DPI scan-only conditional; no force_backend_text (parser_router.yaml "
    "comments / Suite A §7)"
)

#: Sentinel distinguishing "not probed yet" from a probed-but-None version.
_UNSET = object()
_TESSERACT_VERSION: str | None | object = _UNSET


@dataclass(frozen=True)
class RoutingInputs:
    """Document characteristics driving the routing decision (doc 03 §3.7.2).

    ``layout_complexity`` is a layout-complexity estimate, e.g. the number of
    tables found in a cheap pre-scan (None = unknown / not evaluated).
    """

    document_id: str
    file_mime: str
    has_text_layer: bool
    page_count: int
    file_size_bytes: int
    layout_complexity: int | None = None
    document_type: str = "OTHER"


# ────────────────────────────────────────────────────────────────────────────
# Config (mirrors docs/parser_router.yaml exactly)
# ────────────────────────────────────────────────────────────────────────────


class ParserLevelGates(BaseModel):
    """Group A thresholds — ``parser_router.quality_gates.parser_level``."""

    min_provenance_coverage: float = 0.9
    min_text_extraction_rate: float = 0.8
    min_table_detection_rate: float = 0.6


class StructuralGates(BaseModel):
    """Group B thresholds — ``parser_router.quality_gates.structural``."""

    min_point_label_detection: float = 0.9
    min_hierarchy_completeness: float = 0.9


class QualityGates(BaseModel):
    """``parser_router.quality_gates`` (Group A + Group B)."""

    parser_level: ParserLevelGates = ParserLevelGates()
    structural: StructuralGates = StructuralGates()


class FallbackPolicy(BaseModel):
    """``parser_router.fallback_policy`` (doc 03 §3.7.3)."""

    on_parser_gate_fail: Literal["rerun_alternate_parser", "none"] = "rerun_alternate_parser"
    on_structural_gate_fail: Literal["full_rerun_alternate"] = "full_rerun_alternate"
    supersede_old_artifacts: bool = True


class RouterConfig(BaseModel):
    """Parser Router config mirroring ``docs/parser_router.yaml``.

    Defaults equal the committed yaml values, so an absent config file still
    yields the authoritative behavior.
    """

    primary: str = "docling"
    fallback: str = "mineru"
    compare_on_complex_tables: bool = True
    quality_gates: QualityGates = QualityGates()
    fallback_policy: FallbackPolicy = FallbackPolicy()
    decision_record: bool = True


def load_router_config(path: Path | None = None) -> RouterConfig:
    """Parse ``docs/parser_router.yaml`` into :class:`RouterConfig`.

    The yaml file carries a top-level ``parser_router:`` key which is
    unwrapped. When ``path`` is None the committed config path is used; a
    missing file falls back to :class:`RouterConfig` defaults (equal to the
    committed values). Malformed yaml raises (never silently defaulted).
    """
    config_path = path or DEFAULT_CONFIG_PATH
    if not Path(config_path).is_file():
        return RouterConfig()
    with Path(config_path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if data is None:
        return RouterConfig()
    router = data.get("parser_router", data) if isinstance(data, dict) else data
    if not isinstance(router, dict):
        raise ValueError(f"parser_router config in {config_path} must be a mapping")
    return RouterConfig(**router)


# ────────────────────────────────────────────────────────────────────────────
# Decision / outcome models
# ────────────────────────────────────────────────────────────────────────────


class RoutingDecision(BaseModel):
    """Pure routing decision for one document (no side effects, no OCR probe).

    ``route`` is one of ``docling_text`` / ``docling_ocr`` /
    ``compare_complex_tables`` / ``docling_other_mime``. ``inputs`` is embedded
    so decision records are self-contained and auditable.
    """

    inputs: RoutingInputs
    route: Literal["docling_text", "docling_ocr", "compare_complex_tables", "docling_other_mime"]
    selected_parser: str
    ocr_required: bool
    compare_parsers: bool
    expected_fallback: str | None
    reason: str


class GateOutcome(BaseModel):
    """Group A evaluation + optional alternate-parse outcome for one document.

    Invariant: ``source_parser`` is a single value (never a mix of parsers)
    per doc 03 §3.7.3 — when the alternate supersedes, every artifact of the
    document is attributed to the alternate parser. ``comparison`` carries the
    both-parser evidence when the route is ``compare_complex_tables``.
    """

    document_id: str
    selected_parser: str
    group_a: GroupAResult
    fallback_attempted: bool = False
    fallback_parser: str | None = None
    fallback_result: GroupAResult | None = None
    terminal_outcome: TerminalOutcome
    reason: str | None = None
    source_parser: str | None = None
    routed_to_review: bool = False
    superseded_old_artifacts: bool = False
    comparison: dict[str, Any] | None = None


def _na_group_a_result() -> GroupAResult:
    """A not-applicable GroupA result (outcomes with no parse / no gating)."""
    return GroupAResult(
        provenance_coverage=GateResult(gate="provenance_coverage", status="na"),
        text_extraction_rate=GateResult(gate="text_extraction_rate", status="na"),
        table_detection_rate=GateResult(gate="table_detection_rate", status="na"),
        layout_coherence=GateResult(gate="layout_coherence", status="na"),
        verdict="na",
    )


# ────────────────────────────────────────────────────────────────────────────
# Parser Router
# ────────────────────────────────────────────────────────────────────────────


def _table_element_share(doc: ParsedDocument) -> float | None:
    """Share of ``table`` elements among all elements; None for an empty doc.

    Derived from the canonical IR (``element_type == "table"``) — the fallback
    table-quality signal when no expected table count is available (finding #8).
    """
    elements = [element for page in doc.pages for element in page.elements]
    if not elements:
        return None
    tables = sum(1 for element in elements if element.element_type == "table")
    return tables / len(elements)


def _table_quality_signal(
    result: GroupAResult, doc: ParsedDocument
) -> tuple[str | None, float | None]:
    """Table-quality signal for one parser, or ``(None, None)`` when N/A.

    ``table_detection_rate`` (detected/expected) is the signal when an expected
    table count exists; otherwise the doc-derived table-element share. ``None``
    only when neither is computable (no tables at all / empty doc).
    """
    detection = result.table_detection_rate.value
    if detection is not None:
        return "table_detection_rate", detection
    share = _table_element_share(doc)
    if share is not None:
        return "table_element_share", share
    return None, None


def _dimension_winner(
    primary_value: float | None,
    alternate_value: float | None,
    primary_parser: str,
    alternate_parser: str,
) -> str:
    """Parser winning one comparison dimension, or ``"tie"``.

    A present value beats an absent (N/A) one; equal or both-N/A -> ``"tie"``.
    """
    if primary_value is not None and (alternate_value is None or primary_value > alternate_value):
        return primary_parser
    if alternate_value is not None and (primary_value is None or alternate_value > primary_value):
        return alternate_parser
    return "tie"


class ParserRouter:
    """Selects the parser for a document and gates its output (VNLRAG-131).

    Docling is the primary parser and MinerU the fallback/challenger (doc 03
    §3.7). The class never runs adapters itself in W2: parses are injected
    lazily at the :meth:`route_and_gate` boundary — ``primary_runner`` wraps
    the selected parser's parse (including any OCR) and ``alternate_runner``
    wraps the alternate's. :meth:`compare_and_pick` executes the complex-table
    "compare both parsers" policy on already-parsed docs.
    """

    def __init__(
        self,
        config: RouterConfig | None = None,
        *,
        config_path: Path | None = None,
    ) -> None:
        """``config`` wins when given; else load from ``config_path`` (default
        committed path); a missing file yields :class:`RouterConfig` defaults."""
        if config is not None:
            self.config = config
        else:
            self.config = load_router_config(config_path)

    # ── routing ─────────────────────────────────────────────────────────────

    def decide(self, inputs: RoutingInputs) -> RoutingDecision:
        """Route ``inputs`` per doc 03 §3.7.1 (pure decision, no OCR probe).

        Precedence: non-PDF (P0 scope, ``docling_other_mime``) wins over
        complex-tables — a DOCX/HTML/EPUB never routes to the compare path or
        gets a MinerU fallback.
        """
        is_pdf = _is_pdf_mime(inputs.file_mime)
        ocr_required = is_pdf and not inputs.has_text_layer
        complex_tables = (
            self.config.compare_on_complex_tables
            and inputs.layout_complexity is not None
            and inputs.layout_complexity >= COMPLEX_TABLE_COUNT_THRESHOLD
        )

        if not is_pdf:
            return RoutingDecision(
                inputs=inputs,
                route="docling_other_mime",
                selected_parser=self.config.primary,
                ocr_required=False,
                compare_parsers=False,
                expected_fallback=None,
                reason=(
                    f"mime={inputs.file_mime!r} is outside P0 PDF scope: Docling, no "
                    "active support / no fallback (doc 03 §3.7.1 row 4)"
                ),
            )
        if complex_tables:
            return RoutingDecision(
                inputs=inputs,
                route="compare_complex_tables",
                selected_parser=self.config.primary,
                ocr_required=ocr_required,
                compare_parsers=True,
                expected_fallback=self.config.fallback,
                reason=(
                    f"layout_complexity={inputs.layout_complexity} >= "
                    f"{COMPLEX_TABLE_COUNT_THRESHOLD} and compare_on_complex_tables=true: "
                    "compare both parsers, pick by quality gate or route to review "
                    "(doc 03 §3.7.1)"
                ),
            )
        if inputs.has_text_layer:
            return RoutingDecision(
                inputs=inputs,
                route="docling_text",
                selected_parser=self.config.primary,
                ocr_required=False,
                compare_parsers=False,
                expected_fallback=self.config.fallback,
                reason=(
                    "PDF searchable (text layer present), standard layout: Docling "
                    "first, no fallback unless a Group A gate fails (doc 03 §3.7.1)"
                ),
            )
        return RoutingDecision(
            inputs=inputs,
            route="docling_ocr",
            selected_parser=self.config.primary,
            ocr_required=True,
            compare_parsers=False,
            expected_fallback=self.config.fallback,
            reason=(
                "PDF scan (no text layer): Docling first with tesseract-vie CPU OCR; "
                "MinerU if a Group A gate fails (doc 03 §3.7.1, Suite A §7)"
            ),
        )

    # ── OCR fail-fast ────────────────────────────────────────────────────────

    def ensure_ocr_ready(self) -> list[str]:
        """Fail-fast tesseract readiness for the scan/OCR route.

        Reuses :func:`app.ingestion.adapters.docling_adapter.check_ocr_readiness`
        (no duplicated logic). Returns a list of problems (empty = ready).
        """
        return check_ocr_readiness(tessdata_dir=DEFAULT_TESSDATA_DIR, tesseract_cmd=DEFAULT_OCR_CMD)

    def ocr_route_terminal_outcome(self, inputs: RoutingInputs, problems: list[str]) -> GateOutcome:
        """Terminal ``failed`` outcome for the scan route when OCR is not ready."""
        return GateOutcome(
            document_id=inputs.document_id,
            selected_parser=self.config.primary,
            group_a=_na_group_a_result(),
            terminal_outcome="failed",
            reason="OCR_NOT_READY: " + "; ".join(problems),
            source_parser=None,
        )

    # ── gate + fallback execution ────────────────────────────────────────────

    def execute_and_gate(
        self,
        doc: ParsedDocument,
        selected_parser: str,
        fallback_parser: str,
        group_a_thresholds: GroupAThresholds | None = None,
        *,
        expected_tables: int | None = None,
        fallback_runner: Callable[[], ParsedDocument] | None = None,
        fallback_enabled: bool = True,
    ) -> GateOutcome:
        """Gate ``doc`` with Group A; rerun the alternate parser on failure.

        ``doc`` is the selected parser's already-parsed IR. Provenance
        invariants are enforced first: ``doc.parser`` and every element's
        ``source_parser`` must match ``selected_parser`` (exactly one source
        parser per document, no mixing) — otherwise the outcome is ``failed``
        with reason ``PROVENANCE_MISMATCH``.

        When Group A fails and ``fallback_policy.on_parser_gate_fail ==
        "rerun_alternate_parser"`` (and ``fallback_enabled``), the alternate
        parse is obtained from ``fallback_runner`` (a closure the ingestion
        pipeline builds with the source path — the router cannot re-parse from
        IR alone), its provenance is validated against ``fallback_parser``, and
        it is re-gated. If the alternate passes, its artifacts supersede the
        primary's (single ``source_parser``, no mixing); if both fail, the
        document routes to review — never auto-index partial output
        (doc 03 §3.7.3, Suite A §7).

        A document whose ``quality_report["conversion_status"] ==
        "PARTIAL_SUCCESS"`` (docling page-timeout) is never accepted: the Group
        A verdict is forced to ``failed`` so the alternate fallback decides;
        with no alternate available the document routes to review — partial
        legal output is never silently accepted nor discarded (finding #4).
        """
        thresholds = group_a_thresholds or self._default_group_a_thresholds()

        # Docling PARTIAL_SUCCESS (e.g. page-timeout) means usable-but-incomplete
        # output: never accept it silently. The adapter records the conversion
        # status on quality_report; here we force the Group A verdict to failed so
        # the alternate fallback (or review) decides (finding #4).
        partial_conversion = doc.quality_report.get("conversion_status") == "PARTIAL_SUCCESS"
        partial_note = "PARTIAL_SUCCESS: " if partial_conversion else ""

        def reason(message: str) -> str:
            return partial_note + message if partial_conversion else message

        primary_problems = self._validate_single_source_parser(doc, selected_parser)
        if primary_problems:
            return GateOutcome(
                document_id=doc.document_id,
                selected_parser=selected_parser,
                group_a=_na_group_a_result(),
                terminal_outcome="failed",
                reason="PROVENANCE_MISMATCH: " + "; ".join(primary_problems),
                source_parser=None,
            )

        primary_result = evaluate_group_a(
            doc, thresholds=thresholds, expected_tables=expected_tables
        )
        if partial_conversion:
            primary_result = primary_result.model_copy(update={"verdict": "failed"})

        if primary_result.verdict == "passed":
            return GateOutcome(
                document_id=doc.document_id,
                selected_parser=selected_parser,
                group_a=primary_result,
                terminal_outcome="accepted",
                reason="Group A passed on the selected parser",
                source_parser=selected_parser,
            )

        if not fallback_enabled:
            return GateOutcome(
                document_id=doc.document_id,
                selected_parser=selected_parser,
                group_a=primary_result,
                terminal_outcome="needs_review",
                reason=reason(
                    f"Group A {primary_result.verdict}; fallback disabled for this route "
                    "(expected_fallback=None, e.g. P0 non-PDF) -> route to review"
                ),
                source_parser=selected_parser,
                routed_to_review=True,
            )

        if self.config.fallback_policy.on_parser_gate_fail != "rerun_alternate_parser":
            return GateOutcome(
                document_id=doc.document_id,
                selected_parser=selected_parser,
                group_a=primary_result,
                terminal_outcome="needs_review",
                reason=reason(
                    f"Group A {primary_result.verdict}; policy "
                    f"{self.config.fallback_policy.on_parser_gate_fail!r} does not rerun "
                    "the alternate parser -> route to review"
                ),
                source_parser=selected_parser,
                routed_to_review=True,
            )

        if fallback_runner is None:
            if partial_conversion:
                # PARTIAL_SUCCESS with no alternate: never silently accept nor
                # discard partial output — the review decides (finding #4).
                return GateOutcome(
                    document_id=doc.document_id,
                    selected_parser=selected_parser,
                    group_a=primary_result,
                    terminal_outcome="needs_review",
                    reason=reason(
                        "docling reported a partial conversion (usable-but-incomplete "
                        "output) and no alternate fallback is available -> route to review"
                    ),
                    source_parser=None,
                    routed_to_review=True,
                )
            return GateOutcome(
                document_id=doc.document_id,
                selected_parser=selected_parser,
                group_a=primary_result,
                terminal_outcome="failed",
                reason=(
                    "FALLBACK_NOT_AVAILABLE: Group A failed and no fallback_runner was "
                    "supplied to re-parse with the alternate parser"
                ),
                source_parser=None,
            )

        try:
            alternate_doc = fallback_runner()
        except Exception as exc:  # noqa: BLE001 - alternate-parse failures become terminal
            return GateOutcome(
                document_id=doc.document_id,
                selected_parser=selected_parser,
                group_a=primary_result,
                fallback_attempted=True,
                fallback_parser=fallback_parser,
                terminal_outcome="failed",
                reason=reason(f"FALLBACK_PARSE_FAILED: {exc}"),
                source_parser=None,
            )

        alternate_problems = self._validate_single_source_parser(alternate_doc, fallback_parser)
        if alternate_problems:
            return GateOutcome(
                document_id=doc.document_id,
                selected_parser=selected_parser,
                group_a=primary_result,
                fallback_attempted=True,
                fallback_parser=fallback_parser,
                terminal_outcome="needs_review",
                reason=reason("PROVENANCE_MISMATCH: " + "; ".join(alternate_problems)),
                source_parser=None,
                routed_to_review=True,
            )

        fallback_result = evaluate_group_a(
            alternate_doc, thresholds=thresholds, expected_tables=expected_tables
        )
        if fallback_result.verdict == "passed":
            return GateOutcome(
                document_id=doc.document_id,
                selected_parser=selected_parser,
                group_a=primary_result,
                fallback_attempted=True,
                fallback_parser=fallback_parser,
                fallback_result=fallback_result,
                terminal_outcome="accepted",
                reason=reason(
                    "alternate parser passed Group A and supersedes the primary's "
                    "artifacts (no parser mixing)"
                ),
                source_parser=fallback_parser,
                superseded_old_artifacts=self.config.fallback_policy.supersede_old_artifacts,
            )
        return GateOutcome(
            document_id=doc.document_id,
            selected_parser=selected_parser,
            group_a=primary_result,
            fallback_attempted=True,
            fallback_parser=fallback_parser,
            fallback_result=fallback_result,
            terminal_outcome="needs_review",
            reason=reason(
                "BOTH_PARSERS_FAILED: primary and alternate both failed Group A -> "
                "route to review, never auto-index partial output (doc 03 §3.7.3)"
            ),
            source_parser=None,
            routed_to_review=True,
        )

    # ── provenance invariants ────────────────────────────────────────────────

    @staticmethod
    def _validate_single_source_parser(doc: ParsedDocument, expected_parser: str) -> list[str]:
        """Provenance-invariant problems for ``doc`` vs the expected parser.

        The router uses lowercase labels ("docling"/"mineru") while the IR
        records uppercase parser names ("DOCLING"/"MINERU"), so the comparison
        is case-insensitive. Checks (a) ``doc.parser`` matches
        ``expected_parser`` and (b) when the document has elements, every
        ``DocumentElement.source_parser`` matches too — exactly one source
        parser per document (no mixing, doc 03 §3.7.3). Returns [] when the
        invariants hold.
        """
        problems: list[str] = []
        expected = expected_parser.upper()
        if doc.parser.upper() != expected:
            problems.append(f"doc.parser={doc.parser!r} != expected parser {expected_parser!r}")
        element_parsers = {
            element.source_parser.upper() for page in doc.pages for element in page.elements
        }
        if len(element_parsers) > 1:
            problems.append(
                f"document mixes source_parser values {sorted(element_parsers)} "
                "(no parser mixing allowed)"
            )
        if element_parsers and element_parsers != {expected}:
            problems.append(
                f"document elements source_parser={sorted(element_parsers)} != "
                f"expected parser {expected_parser!r}"
            )
        return problems

    # ── compare mode (complex tables: run both parsers, pick per policy) ─────

    def compare_and_pick(
        self,
        primary_doc: ParsedDocument,
        alternate_doc: ParsedDocument | None,
        primary_parser: str,
        alternate_parser: str,
        group_a_thresholds: GroupAThresholds | None = None,
        *,
        expected_tables: int | None = None,
        alternate_error: str | None = None,
    ) -> GateOutcome:
        """Compare both parsers' Group A results and pick per doc 03 §3.7.1.

        ``alternate_doc`` is None when the alternate parse failed/unavailable
        (``alternate_error`` records why). Picking policy:
          * both pass -> accept the better parser (finding #8: table quality
            leads — higher table quality wins, then higher
            provenance_coverage, then higher text_extraction_rate; equal ->
            primary preferred), superseding the losing parser's artifacts;
          * one passes -> accept it (``superseded_old_artifacts`` per config —
            the losing parser's artifacts were produced);
          * both fail / alternate unavailable and primary fails -> needs_review
            (never auto-index partial output).
        A doc carrying ``quality_report["conversion_status"] ==
        "PARTIAL_SUCCESS"`` (finding #4, ora-3) is never accepted as a winner:
        its Group A verdict is forced to ``failed``, so a partial primary lets
        the alternate's result decide (or routes to review when the alternate
        fails/is unavailable) and a partial alternate can never win — if it
        would have won by default the comparison routes to review. The partial
        flags are recorded on ``outcome.comparison`` (``primary_partial`` /
        ``alternate_partial``).
        The full comparison (both Group A results, pick + rule) is recorded in
        ``outcome.comparison`` for the ``parser_routing`` record.
        """
        thresholds = group_a_thresholds or self._default_group_a_thresholds()

        primary_problems = self._validate_single_source_parser(primary_doc, primary_parser)
        if primary_problems:
            return GateOutcome(
                document_id=primary_doc.document_id,
                selected_parser=primary_parser,
                group_a=_na_group_a_result(),
                terminal_outcome="failed",
                reason="PROVENANCE_MISMATCH: " + "; ".join(primary_problems),
                source_parser=None,
            )

        primary_result = evaluate_group_a(
            primary_doc, thresholds=thresholds, expected_tables=expected_tables
        )
        # Finding #4 (ora-3): a PARTIAL_SUCCESS doc is usable-but-incomplete and
        # must never win a comparison. Force the primary's Group A verdict to
        # failed so the alternate's result decides (or review when it fails or
        # is unavailable) — same treatment execute_and_gate applies on the
        # normal path.
        primary_partial = primary_doc.quality_report.get("conversion_status") == "PARTIAL_SUCCESS"
        if primary_partial:
            primary_result = primary_result.model_copy(update={"verdict": "failed"})

        alternate_result: GroupAResult | None = None
        alternate_problems: list[str] = []
        if alternate_doc is not None:
            alternate_problems = self._validate_single_source_parser(
                alternate_doc, alternate_parser
            )
            if not alternate_problems:
                alternate_result = evaluate_group_a(
                    alternate_doc, thresholds=thresholds, expected_tables=expected_tables
                )
        # Symmetric: a partial alternate never wins; if it would win by default
        # (healthy primary failed), the comparison routes to review instead.
        alternate_partial = bool(
            alternate_doc is not None
            and alternate_doc.quality_report.get("conversion_status") == "PARTIAL_SUCCESS"
        )
        if alternate_result is not None and alternate_partial:
            alternate_result = alternate_result.model_copy(update={"verdict": "failed"})
        partial_note = "PARTIAL_SUCCESS: " if (primary_partial or alternate_partial) else ""

        def reason(message: str) -> str:
            return partial_note + message if (primary_partial or alternate_partial) else message

        comparison: dict[str, Any] = {
            "mode": "compare_complex_tables",
            "primary_parser": primary_parser,
            "alternate_parser": alternate_parser,
            "primary_group_a": primary_result.model_dump(mode="json"),
            "alternate_group_a": (
                alternate_result.model_dump(mode="json") if alternate_result is not None else None
            ),
            "primary_partial": primary_partial,
            "alternate_partial": alternate_partial,
            "alternate_error": alternate_error,
            "alternate_provenance_problems": alternate_problems or None,
            "pick": None,
            "pick_rule": None,
            "tiebreak": None,
        }

        primary_passed = primary_result.verdict == "passed"
        alternate_passed = alternate_result is not None and alternate_result.verdict == "passed"

        if alternate_result is None:
            if primary_passed:
                comparison["pick"] = primary_parser
                comparison["pick_rule"] = "alternate unavailable; primary passed Group A"
                return GateOutcome(
                    document_id=primary_doc.document_id,
                    selected_parser=primary_parser,
                    group_a=primary_result,
                    terminal_outcome="accepted",
                    reason=(
                        "compare mode: alternate unavailable, primary passed Group A -> accepted"
                    ),
                    source_parser=primary_parser,
                    comparison=comparison,
                )
            return GateOutcome(
                document_id=primary_doc.document_id,
                selected_parser=primary_parser,
                group_a=primary_result,
                terminal_outcome="needs_review",
                reason=reason(
                    "compare mode: alternate unavailable and primary failed Group A -> "
                    "route to review"
                ),
                source_parser=None,
                routed_to_review=True,
                comparison=comparison,
            )

        if primary_passed and alternate_passed:
            assert alternate_doc is not None  # alternate passed -> its parse exists
            pick, rule, tiebreak = self._pick_better(
                primary_result,
                alternate_result,
                primary_doc,
                alternate_doc,
                primary_parser,
                alternate_parser,
            )
            comparison["pick"] = pick
            comparison["pick_rule"] = rule
            comparison["tiebreak"] = tiebreak
            return GateOutcome(
                document_id=primary_doc.document_id,
                selected_parser=primary_parser,
                group_a=alternate_result if pick == alternate_parser else primary_result,
                terminal_outcome="accepted",
                reason=f"compare mode: both parsers passed; picked {pick} ({rule})",
                source_parser=pick,
                superseded_old_artifacts=self.config.fallback_policy.supersede_old_artifacts,
                comparison=comparison,
            )
        if primary_passed:
            comparison["pick"] = primary_parser
            comparison["pick_rule"] = "only primary passed Group A"
            return GateOutcome(
                document_id=primary_doc.document_id,
                selected_parser=primary_parser,
                group_a=primary_result,
                terminal_outcome="accepted",
                reason=reason("compare mode: only primary passed Group A -> accepted"),
                source_parser=primary_parser,
                superseded_old_artifacts=self.config.fallback_policy.supersede_old_artifacts,
                comparison=comparison,
            )
        if alternate_passed:
            comparison["pick"] = alternate_parser
            comparison["pick_rule"] = "only alternate passed Group A"
            return GateOutcome(
                document_id=primary_doc.document_id,
                selected_parser=primary_parser,
                group_a=alternate_result,
                terminal_outcome="accepted",
                reason=reason("compare mode: only alternate passed Group A -> accepted"),
                source_parser=alternate_parser,
                superseded_old_artifacts=self.config.fallback_policy.supersede_old_artifacts,
                comparison=comparison,
            )
        comparison["pick_rule"] = "both parsers failed Group A"
        return GateOutcome(
            document_id=primary_doc.document_id,
            selected_parser=primary_parser,
            group_a=primary_result,
            terminal_outcome="needs_review",
            reason=reason("compare mode: BOTH_PARSERS_FAILED -> route to review (doc 03 §3.7.1)"),
            source_parser=None,
            routed_to_review=True,
            comparison=comparison,
        )

    @staticmethod
    def _pick_better(
        primary_result: GroupAResult,
        alternate_result: GroupAResult,
        primary_doc: ParsedDocument,
        alternate_doc: ParsedDocument,
        primary_parser: str,
        alternate_parser: str,
    ) -> tuple[str, str, dict[str, Any]]:
        """Tie-break when both parsers pass Group A (finding #8).

        The complex-table route exists because of complex tables, so TABLE
        QUALITY leads the pick: higher table quality wins (detection rate when
        an expected count exists, else the doc-derived table-element share); on
        a tie, higher ``provenance_coverage``; then ``text_extraction_rate``;
        still equal -> primary preferred. When neither parser has a computable
        table-quality signal (e.g. no tables at all) the comparison falls back
        to the pre-finding provenance -> text -> primary order. Returns the
        pick, the rule, and the per-dimension tie-break metrics recorded on
        ``comparison["tiebreak"]`` (auditable decision).
        """
        primary_table = _table_quality_signal(primary_result, primary_doc)
        alternate_table = _table_quality_signal(alternate_result, alternate_doc)
        provenance = (
            primary_result.provenance_coverage.value or 0.0,
            alternate_result.provenance_coverage.value or 0.0,
        )
        text = (
            primary_result.text_extraction_rate.value or 0.0,
            alternate_result.text_extraction_rate.value or 0.0,
        )
        tiebreak: dict[str, Any] = {
            "table_quality": {
                "signal": primary_table[0] or alternate_table[0],
                "primary": primary_table[1],
                "alternate": alternate_table[1],
                "winner": _dimension_winner(
                    primary_table[1], alternate_table[1], primary_parser, alternate_parser
                ),
            },
            "provenance": {
                "primary": provenance[0],
                "alternate": provenance[1],
                "winner": _dimension_winner(
                    provenance[0], provenance[1], primary_parser, alternate_parser
                ),
            },
            "text": {
                "primary": text[0],
                "alternate": text[1],
                "winner": _dimension_winner(text[0], text[1], primary_parser, alternate_parser),
            },
        }
        rule = (
            "both passed; tie-break table quality -> provenance_coverage -> "
            "text_extraction_rate -> primary preference -> "
        )
        table_winner = tiebreak["table_quality"]["winner"]
        if table_winner != "tie":
            return table_winner, rule + f"{table_winner} higher table quality", tiebreak
        provenance_winner = tiebreak["provenance"]["winner"]
        if provenance_winner != "tie":
            return (
                provenance_winner,
                rule + f"{provenance_winner} higher provenance_coverage",
                tiebreak,
            )
        text_winner = tiebreak["text"]["winner"]
        if text_winner != "tie":
            return text_winner, rule + f"{text_winner} higher text_extraction_rate", tiebreak
        return primary_parser, rule + "equal, primary preferred", tiebreak

    # ── orchestration (routing + OCR fail-fast + gate/fallback/compare) ──────

    def route_and_gate(
        self,
        inputs: RoutingInputs,
        primary_runner: Callable[[], ParsedDocument],
        *,
        alternate_runner: Callable[[], ParsedDocument] | None = None,
        group_a_thresholds: GroupAThresholds | None = None,
        expected_tables: int | None = None,
    ) -> tuple[RoutingDecision, GateOutcome]:
        """Orchestrate routing + Group A gating for one document (lazy parses).

        ``primary_runner`` lazily produces the selected parser's
        :class:`ParsedDocument` (wrapping the adapter parse, including any
        OCR); ``alternate_runner`` lazily produces the alternate parser's
        document. A scan whose OCR is not ready never triggers the primary
        parse, and a crashing primary never yields a hard ``failed`` while an
        alternate is available (finding #4).

        (a) ``decide(inputs)`` — pure routing (side-effect-free);
        (b) if the route requires OCR (scan) -> ``ensure_ocr_ready()`` FIRST
            and, on problems, when an alternate is a real option for this route
            (``alternate_runner`` given AND ``expected_fallback`` set) run and
            gate the alternate instead of failing (reason ``OCR_NOT_READY``);
            with no alternate -> the terminal ``failed``/``OCR_NOT_READY``
            outcome WITHOUT invoking any runner;
        (c) otherwise invoke ``primary_runner()``: if it raises and an
            alternate is available, run and gate the alternate (reason
            ``PRIMARY_PARSE_FAILED``); only with no alternate -> the terminal
            ``failed``/``PRIMARY_PARSE_FAILED`` outcome. Dispatch on success:
            ``compare_complex_tables`` -> :meth:`compare_and_pick` (also
            invokes ``alternate_runner()``); every other route ->
            :meth:`execute_and_gate` (``alternate_runner`` is passed through
            as the lazy fallback, used only after a Group A failure, honouring
            the decision's ``expected_fallback``).
        """
        decision = self.decide(inputs)

        if decision.ocr_required:
            problems = self.ensure_ocr_ready()
            if problems:
                if alternate_runner is not None and decision.expected_fallback is not None:
                    # OCR is not ready but the alternate parser is a real option for
                    # this route: run the alternate (lazy) and gate it — the alternate
                    # is most valuable exactly when the OCR primary cannot run
                    # (finding #4). Never accept a doc whose provenance fails.
                    return decision, self._primary_failure_fallback_outcome(
                        inputs,
                        decision,
                        decision.expected_fallback,
                        alternate_runner,
                        primary_failure="OCR_NOT_READY: " + "; ".join(problems),
                        group_a_thresholds=group_a_thresholds,
                        expected_tables=expected_tables,
                    )
                return decision, self.ocr_route_terminal_outcome(inputs, problems)

        fallback_parser = decision.expected_fallback or self.config.fallback

        if decision.compare_parsers:
            if alternate_runner is None:
                return decision, GateOutcome(
                    document_id=inputs.document_id,
                    selected_parser=decision.selected_parser,
                    group_a=_na_group_a_result(),
                    terminal_outcome="failed",
                    reason=(
                        "COMPARE_NOT_AVAILABLE: compare_complex_tables route requires "
                        "an alternate_runner to parse with the alternate parser"
                    ),
                    source_parser=None,
                )
            try:
                primary_doc = primary_runner()
            except Exception as exc:  # noqa: BLE001 - parse failures become terminal
                if alternate_runner is not None and decision.expected_fallback is not None:
                    # The primary (Docling) crashed: fall back to the alternate and
                    # gate its output instead of failing hard (finding #4).
                    return decision, self._primary_failure_fallback_outcome(
                        inputs,
                        decision,
                        fallback_parser,
                        alternate_runner,
                        primary_failure=f"PRIMARY_PARSE_FAILED: {exc}",
                        group_a_thresholds=group_a_thresholds,
                        expected_tables=expected_tables,
                    )
                return decision, self._primary_parse_failed_outcome(inputs, decision, exc)
            alternate_error: str | None
            try:
                alternate_doc = alternate_runner()
            except Exception as exc:  # noqa: BLE001 - alternate-parse failures become terminal
                alternate_doc = None
                alternate_error = str(exc)
            else:
                alternate_error = None
            outcome = self.compare_and_pick(
                primary_doc,
                alternate_doc,
                decision.selected_parser,
                fallback_parser,
                group_a_thresholds=group_a_thresholds,
                expected_tables=expected_tables,
                alternate_error=alternate_error,
            )
            return decision, outcome

        try:
            primary_doc = primary_runner()
        except Exception as exc:  # noqa: BLE001 - parse failures become terminal
            if alternate_runner is not None and decision.expected_fallback is not None:
                # The primary (Docling) crashed: fall back to the alternate and
                # gate its output instead of failing hard (finding #4).
                return decision, self._primary_failure_fallback_outcome(
                    inputs,
                    decision,
                    fallback_parser,
                    alternate_runner,
                    primary_failure=f"PRIMARY_PARSE_FAILED: {exc}",
                    group_a_thresholds=group_a_thresholds,
                    expected_tables=expected_tables,
                )
            return decision, self._primary_parse_failed_outcome(inputs, decision, exc)

        return decision, self.execute_and_gate(
            primary_doc,
            decision.selected_parser,
            fallback_parser,
            group_a_thresholds=group_a_thresholds,
            expected_tables=expected_tables,
            fallback_runner=alternate_runner,
            fallback_enabled=decision.expected_fallback is not None,
        )

    def _primary_parse_failed_outcome(
        self, inputs: RoutingInputs, decision: RoutingDecision, exc: Exception
    ) -> GateOutcome:
        """Terminal ``failed`` outcome when the selected parser's parse raises."""
        return GateOutcome(
            document_id=inputs.document_id,
            selected_parser=decision.selected_parser,
            group_a=_na_group_a_result(),
            terminal_outcome="failed",
            reason=f"PRIMARY_PARSE_FAILED: {exc}",
            source_parser=None,
        )

    def _primary_failure_fallback_outcome(
        self,
        inputs: RoutingInputs,
        decision: RoutingDecision,
        fallback_parser: str,
        alternate_runner: Callable[[], ParsedDocument],
        *,
        primary_failure: str,
        group_a_thresholds: GroupAThresholds | None = None,
        expected_tables: int | None = None,
    ) -> GateOutcome:
        """Gate the alternate parser's output when the primary could not run.

        Used when OCR is not ready or ``primary_runner`` raises: the alternate
        is most valuable exactly when the primary CANNOT run (finding #4). The
        alternate doc is gated with Group A — accepted (``source_parser`` =
        alternate, superseding) when it passes, needs_review when it fails
        Group A or its provenance is wrong, failed when the alternate itself
        raises. ``primary_failure`` records why the primary did not run (e.g.
        ``"OCR_NOT_READY: ..."`` / ``"PRIMARY_PARSE_FAILED: ..."``) on the
        outcome reason and is never dropped.
        """
        thresholds = group_a_thresholds or self._default_group_a_thresholds()

        try:
            alternate_doc = alternate_runner()
        except Exception as exc:  # noqa: BLE001 - alternate-parse failures become terminal
            return GateOutcome(
                document_id=inputs.document_id,
                selected_parser=decision.selected_parser,
                group_a=_na_group_a_result(),
                fallback_attempted=True,
                fallback_parser=fallback_parser,
                terminal_outcome="failed",
                reason=f"{primary_failure}; ALTERNATE_PARSE_FAILED: {exc}",
                source_parser=None,
            )

        # Never accept a doc whose provenance fails the single-source invariant
        # (the alternate output must be genuine alternate-parser IR).
        alternate_problems = self._validate_single_source_parser(alternate_doc, fallback_parser)
        if alternate_problems:
            return GateOutcome(
                document_id=inputs.document_id,
                selected_parser=decision.selected_parser,
                group_a=_na_group_a_result(),
                fallback_attempted=True,
                fallback_parser=fallback_parser,
                terminal_outcome="needs_review",
                reason=f"{primary_failure}; PROVENANCE_MISMATCH: " + "; ".join(alternate_problems),
                source_parser=None,
                routed_to_review=True,
            )

        alternate_result = evaluate_group_a(
            alternate_doc, thresholds=thresholds, expected_tables=expected_tables
        )
        if alternate_result.verdict == "passed":
            return GateOutcome(
                document_id=inputs.document_id,
                selected_parser=decision.selected_parser,
                group_a=alternate_result,
                fallback_attempted=True,
                fallback_parser=fallback_parser,
                fallback_result=alternate_result,
                terminal_outcome="accepted",
                reason=(
                    f"{primary_failure}; alternate parser passed Group A and supersedes "
                    "the primary's artifacts (no parser mixing)"
                ),
                source_parser=fallback_parser,
                superseded_old_artifacts=self.config.fallback_policy.supersede_old_artifacts,
            )
        return GateOutcome(
            document_id=inputs.document_id,
            selected_parser=decision.selected_parser,
            group_a=alternate_result,
            fallback_attempted=True,
            fallback_parser=fallback_parser,
            fallback_result=alternate_result,
            terminal_outcome="needs_review",
            reason=(
                f"{primary_failure}; alternate parser failed Group A -> route to review, "
                "never auto-index partial output (doc 03 §3.7.3)"
            ),
            source_parser=None,
            routed_to_review=True,
        )

    # ── decision record ──────────────────────────────────────────────────────

    def record_decision(
        self,
        decision: RoutingDecision,
        outcome: GateOutcome | None = None,
        *,
        ocr_config: dict[str, Any] | None = None,
        expected_tables: int | None = None,
    ) -> dict[str, Any]:
        """Build the jsonable ``parser_routing`` record for this decision.

        Persistence to ``ingestion_runs`` is another ticket; here the record
        builder (:func:`build_parser_routing_record`) is the deliverable.
        """
        return build_parser_routing_record(
            inputs=decision.inputs,
            decision=decision,
            outcome=outcome,
            config=self.config,
            ocr_config=ocr_config,
            expected_tables=expected_tables,
        )

    def _default_group_a_thresholds(self) -> GroupAThresholds:
        parser_level = self.config.quality_gates.parser_level
        return GroupAThresholds(
            min_provenance_coverage=parser_level.min_provenance_coverage,
            min_text_extraction_rate=parser_level.min_text_extraction_rate,
            min_table_detection_rate=parser_level.min_table_detection_rate,
        )


# ────────────────────────────────────────────────────────────────────────────
# Record builder (jsonable, for ingestion_runs.parser_routing)
# ────────────────────────────────────────────────────────────────────────────


def build_parser_routing_record(
    *,
    inputs: RoutingInputs,
    decision: RoutingDecision,
    outcome: GateOutcome | None = None,
    config: RouterConfig | None = None,
    group_a_thresholds: GroupAThresholds | None = None,
    ocr_config: dict[str, Any] | None = None,
    expected_tables: int | None = None,
) -> dict[str, Any]:
    """Build the jsonable ``ingestion_runs.parser_routing`` record.

    Shape (doc 03 §3.7.4 / NFR-09): ``inputs``, ``selected``, gating results
    (Group A), terminal outcome, OCR config snapshot, and the single
    ``source_parser`` per document. When ``outcome`` is None the record is a
    decision-only record (``terminal_outcome=None``, ``executed=false``).
    """
    thresholds = group_a_thresholds
    if thresholds is None and config is not None:
        parser_level = config.quality_gates.parser_level
        thresholds = GroupAThresholds(
            min_provenance_coverage=parser_level.min_provenance_coverage,
            min_text_extraction_rate=parser_level.min_text_extraction_rate,
            min_table_detection_rate=parser_level.min_table_detection_rate,
        )
    thresholds_snapshot = thresholds.model_dump(mode="json") if thresholds is not None else None

    gates: dict[str, Any] | None = None
    if outcome is not None:
        gates = {"group_a": outcome.group_a.model_dump(mode="json")}

    return {
        "schema_version": PARSER_ROUTING_RECORD_SCHEMA,
        "document_id": inputs.document_id,
        "inputs": asdict(inputs),
        "decision": decision.model_dump(mode="json"),
        "selected_parser": decision.selected_parser,
        "source_parser": outcome.source_parser if outcome is not None else None,
        "fallback_attempted": bool(outcome is not None and outcome.fallback_attempted),
        "fallback_parser": outcome.fallback_parser if outcome is not None else None,
        "gates": gates,
        "gate_verdict": outcome.group_a.verdict if outcome is not None else None,
        "terminal_outcome": outcome.terminal_outcome if outcome is not None else None,
        "executed": outcome is not None,
        "reason": outcome.reason if outcome is not None else None,
        "routed_to_review": bool(outcome is not None and outcome.routed_to_review),
        "superseded_old_artifacts": bool(outcome is not None and outcome.superseded_old_artifacts),
        "comparison": outcome.comparison if outcome is not None else None,
        "group_a_thresholds": thresholds_snapshot,
        "expected_tables": expected_tables,
        "ocr_config": ocr_config if ocr_config is not None else build_ocr_config_snapshot(),
        "decision_record_enabled": config.decision_record if config is not None else True,
        "config_snapshot": config.model_dump(mode="json") if config is not None else None,
    }


def build_ocr_config_snapshot(
    *,
    tesseract_version: str | None = None,
    tesseract_cmd: str = DEFAULT_OCR_CMD,
    tessdata_dir: str = DEFAULT_TESSDATA_DIR,
    dpi: int = OCR_DPI,
) -> dict[str, Any]:
    """OCR configuration snapshot for the routing record (Suite A §7).

    ``tesseract_version`` is probed once (best-effort) when not supplied, so
    records carry the engine snapshot even in environments without tesseract.
    """
    return {
        "engine": "tesseract",
        "lang": ["vie"],
        "psm": OCR_PSM,
        "dpi": dpi,
        "tesseract_cmd": tesseract_cmd,
        "tessdata_dir": tessdata_dir,
        "tesseract_version": tesseract_version
        if tesseract_version is not None
        else _tesseract_version(),
        "cuda_visible_devices": "",
        "policy": OCR_SNAPSHOT_POLICY,
    }


def _is_pdf_mime(mime: str) -> bool:
    return mime.lower() in ("application/pdf", "application/x-pdf", "pdf") or mime.lower().endswith(
        "/pdf"
    )


def _tesseract_version() -> str | None:
    """Best-effort installed tesseract version (probed once, then cached)."""
    global _TESSERACT_VERSION
    if _TESSERACT_VERSION is _UNSET:
        _TESSERACT_VERSION = _probe_tesseract_version()
    return _TESSERACT_VERSION  # type: ignore[return-value]


def _probe_tesseract_version() -> str | None:
    executable = shutil.which("tesseract")
    if (
        executable is None
        and os.path.isfile(DEFAULT_OCR_CMD)
        and os.access(DEFAULT_OCR_CMD, os.X_OK)
    ):
        executable = DEFAULT_OCR_CMD
    if executable is None:
        return None
    try:
        result = subprocess.run(
            [executable, "--version"], capture_output=True, text=True, timeout=5, check=False
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    first_line = (result.stdout or "").splitlines()[0].strip() if result.stdout else ""
    return first_line or None
