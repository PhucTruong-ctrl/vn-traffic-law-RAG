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
contract (:mod:`app.ingestion.quality_gates`). MinerU execution is
environment-blocked (``mineru_adapter.MINERU_ENV_ERROR_MESSAGE``), so parses
are injected lazily at the :meth:`ParserRouter.route_and_gate` boundary as
``primary_runner`` / ``alternate_runner`` callables — the ingestion pipeline
(another ticket) wires the real adapters. No parser mixing: a single
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
        """
        thresholds = group_a_thresholds or self._default_group_a_thresholds()

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
                reason=(
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
                reason=(
                    f"Group A {primary_result.verdict}; policy "
                    f"{self.config.fallback_policy.on_parser_gate_fail!r} does not rerun "
                    "the alternate parser -> route to review"
                ),
                source_parser=selected_parser,
                routed_to_review=True,
            )

        if fallback_runner is None:
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
                reason=f"FALLBACK_PARSE_FAILED: {exc}",
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
                reason="PROVENANCE_MISMATCH: " + "; ".join(alternate_problems),
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
                reason=(
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
            reason=(
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
          * both pass -> accept the better parser (tie-break: higher
            provenance_coverage, then higher text_extraction_rate; equal ->
            primary preferred), superseding the losing parser's artifacts;
          * one passes -> accept it (``superseded_old_artifacts`` per config —
            the losing parser's artifacts were produced);
          * both fail / alternate unavailable and primary fails -> needs_review
            (never auto-index partial output).
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

        comparison: dict[str, Any] = {
            "mode": "compare_complex_tables",
            "primary_parser": primary_parser,
            "alternate_parser": alternate_parser,
            "primary_group_a": primary_result.model_dump(mode="json"),
            "alternate_group_a": (
                alternate_result.model_dump(mode="json") if alternate_result is not None else None
            ),
            "alternate_error": alternate_error,
            "alternate_provenance_problems": alternate_problems or None,
            "pick": None,
            "pick_rule": None,
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
                reason=(
                    "compare mode: alternate unavailable and primary failed Group A -> "
                    "route to review"
                ),
                source_parser=None,
                routed_to_review=True,
                comparison=comparison,
            )

        if primary_passed and alternate_passed:
            pick, rule = self._pick_better(
                primary_result, alternate_result, primary_parser, alternate_parser
            )
            comparison["pick"] = pick
            comparison["pick_rule"] = rule
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
                reason="compare mode: only primary passed Group A -> accepted",
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
                reason="compare mode: only alternate passed Group A -> accepted",
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
            reason="compare mode: BOTH_PARSERS_FAILED -> route to review (doc 03 §3.7.1)",
            source_parser=None,
            routed_to_review=True,
            comparison=comparison,
        )

    @staticmethod
    def _pick_better(
        primary_result: GroupAResult,
        alternate_result: GroupAResult,
        primary_parser: str,
        alternate_parser: str,
    ) -> tuple[str, str]:
        """Tie-break when both parsers pass Group A.

        Rule (documented): higher ``provenance_coverage`` wins; on a tie,
        higher ``text_extraction_rate``; still equal -> primary preferred
        (Docling is the primary parser; no evidence either is superior).
        """
        primary_score = (
            primary_result.provenance_coverage.value or 0.0,
            primary_result.text_extraction_rate.value or 0.0,
        )
        alternate_score = (
            alternate_result.provenance_coverage.value or 0.0,
            alternate_result.text_extraction_rate.value or 0.0,
        )
        rule = "both passed; tie-break provenance_coverage then text_extraction_rate -> "
        if alternate_score > primary_score:
            return alternate_parser, rule + "alternate higher"
        if primary_score > alternate_score:
            return primary_parser, rule + "primary higher"
        return primary_parser, rule + "equal, primary preferred"

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
        document. Both are invoked ONLY after the OCR fail-fast guard passes,
        so a scan whose OCR is not ready never triggers any parse.

        (a) ``decide(inputs)`` — pure routing (side-effect-free);
        (b) if the route requires OCR (scan) -> ``ensure_ocr_ready()`` FIRST
            and, on problems, return the terminal ``failed``/``OCR_NOT_READY``
            outcome WITHOUT invoking ``primary_runner`` or ``alternate_runner``;
        (c) otherwise invoke ``primary_runner()`` and dispatch:
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
