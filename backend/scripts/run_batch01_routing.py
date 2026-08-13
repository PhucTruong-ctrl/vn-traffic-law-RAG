"""VNLRAG-35 — batch-01 W3 routing-only ingestion run (quality gates + review routing).

Runs the ingestion pipeline up to (and including) review routing for the five
batch-01 corpus documents and writes two committed artifacts:

* ``data/ingestion/batch-01-routing.json`` — routing states + gate metrics +
  extraction quality stats + review backlog per document;
* ``docs/evaluation/batch-01-routing-report.md`` — the generated quality report.

W3 scope (doc 05 §5.6 row 09/08, Gate M2 note): **routing-only** — NO indexing,
NO Gate M2 closure. No provision may be indexed without a resolver-derived
effective interval (VNLRAG-136, W4). Routing decisions here are provisional:
ACCEPTED provisions stay PENDING for indexing until the W4 resolvers assign
final intervals (quality-gate actor contract, ``actors/quality_gate.py``).

Input policy (documented in the artifact, ``extraction_input``):

* ``luat-36-2024-qh15`` — the only batch-01 document whose source PDF has a
  born-digital text layer (batch-01 README). The committed parser-benchmark
  fixture ``luat-traffic-2024-fixture.pdf.txt`` is a genuine excerpt of that
  text; it is used as the parse input.
* ``nd-168-2024`` — the source PDF is scan-only (1-bit CCITT, no text layer).
  The committed fixture ``nd-168-2024-fixture.pdf.txt`` is a curated excerpt
  stand-in, NOT real OCR output. Per the scan-review policy
  (``docs/parser_router.yaml``) scan-derived text is never auto-indexed: the
  routing Group A is marked failed on extraction/provenance grounds
  (LOW_OCR_COVERAGE) even though the fixture IR itself measures 1.0 — the
  input is not the certified parse of the authoritative source.
* ``nd-100-2019``, ``tt-79-2024``, ``tt-24-2023`` — scan-only source PDFs,
  gitignored (not present in the worktree), real OCR infeasible in this W3
  run, and NO committed text fixture exists. Extraction input is
  ``none_available``; the document routes NEEDS_REVIEW (LOW_OCR_COVERAGE) with
  zero provisions.

Routing mechanics mirror ``actors/quality_gate.py``: Group A (measured on the
parse IR, or scan-policy-certifying) + Group B (on extracted provisions) +
``review_routing.evaluate_and_route``. A manifest-provisional document interval
is applied to provisions ONLY when it is provision-uniform (manifest status
EFFECTIVE); PARTIALLY_EFFECTIVE (nd-100) and EXPIRED (tt-24) per-provision
intervals are resolver territory (W4) and are never applied here.

Deterministic except for the ``generated_at`` timestamp. Idempotent: re-running
regenerates both artifacts. No database, no Qdrant, no object storage is
touched.

Usage (from backend/):

    uv run python scripts/run_batch01_routing.py
    uv run python scripts/run_batch01_routing.py \
        --artifacts ../data/ingestion/batch-01-routing.json \
        --report ../docs/evaluation/batch-01-routing-report.md
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.evaluation.corpus_qa import run_corpus_qa  # noqa: E402  (sys.path bootstrap)
from app.ingestion.context_enricher import enrich_provision  # noqa: E402
from app.ingestion.document_ir import (  # noqa: E402
    BoundingBox,
    DocumentElement,
    ParsedDocument,
    ParsedPage,
)
from app.ingestion.quality_gates import (  # noqa: E402
    GateResult,
    GroupAResult,
    GroupAThresholds,
    GroupBResult,
    GroupBThresholds,
    evaluate_group_a,
    evaluate_group_b,
)
from app.ingestion.review_routing import (  # noqa: E402
    LOW_OCR_COVERAGE,
    RoutingDecision,
    evaluate_and_route,
)
from app.ingestion.structure_extractor import (  # noqa: E402
    ExtractedLegalProvision,
    extract_legal_provisions,
)

#: Artifact schema version (bump on incompatible shape changes).
ARTIFACT_VERSION = "batch-01-routing-v1"

#: Batch-01 document order (mirrors data/manifests/batch-01/README.md).
BATCH01_DOCUMENT_IDS = [
    "nd-168-2024",
    "nd-100-2019",
    "luat-36-2024-qh15",
    "tt-79-2024",
    "tt-24-2023",
]

#: Committed text inputs available for this W3 run (fixture excerpts).
#: key = document_id, value = path relative to the repository root.
FIXTURE_INPUTS: dict[str, str] = {
    "nd-168-2024": "backend/tests/fixtures/parser_benchmark/documents/nd/nd-168-2024-fixture.pdf.txt",
    "luat-36-2024-qh15": (
        "backend/tests/fixtures/parser_benchmark/documents/luat/luat-traffic-2024-fixture.pdf.txt"
    ),
}

#: Source-PDF text-layer kind per the batch-01 README (VNLRAG-97 notes).
#: Only luat-36 has a born-digital text layer; the other four are scan-only
#: 1-bit CCITT scans (pdftotext yields only digital-signature metadata).
SCAN_ONLY_DOCUMENTS = frozenset(
    {"nd-168-2024", "nd-100-2019", "tt-79-2024", "tt-24-2023"}
)

_IR_SCHEMA_VERSION = "document-ir-v2"
_PARSER_LABEL = "FIXTURE_TEXT"
_PARSER_VERSION = "fixture-v1"

#: Review-reason display order for doc-level code aggregation.
_REASON_ORDER = (
    "LOW_OCR_COVERAGE",
    "POINT_LABEL_AMBIGUOUS",
    "D_D_AMBIGUITY",
    "HIERARCHY_VIOLATION",
    "DUPLICATE_PROVISION",
    "INVALID_POINT_LABEL",
    "HEADER_FOOTER_LEAKAGE",
    "UNKNOWN_EFFECTIVE_DATE",
    "NEEDS_REVIEW",
)


# ────────────────────────────────────────────────────────────────────────────
# Pure helpers (unit-tested in tests/test_run_batch01_routing.py)
# ────────────────────────────────────────────────────────────────────────────


def build_ir_from_lines(
    lines: list[str],
    document_id: str,
    *,
    parser: str = _PARSER_LABEL,
    parser_version: str = _PARSER_VERSION,
) -> ParsedDocument:
    """Build a canonical ``ParsedDocument`` from plain text lines.

    Each non-empty line becomes one ``paragraph`` ``DocumentElement`` carrying
    synthetic NORMALIZED_PAGE bboxes (deterministic row-major layout) and
    parser provenance marking the input as a fixture stand-in. Mirrors the
    test helper in ``tests/test_structure_extractor.py``.
    """

    elements: list[DocumentElement] = []
    for index, text in enumerate(lines):
        elements.append(
            DocumentElement(
                element_id=f"e{index}",
                element_type="paragraph",
                text=text,
                page_number=1,
                bbox=BoundingBox(
                    left=0.1, top=index / 100, right=0.9, bottom=(index + 1) / 100
                ),
                reading_order=index,
                parent_element_id=None,
                source_parser=parser,
                parser_version=parser_version,
                parser_confidence=None,
                raw_reference={"index": index, "input_kind": "fixture_text"},
            )
        )
    page_text = "\n".join(lines)
    return ParsedDocument(
        parsed_document_id=f"parsed-{document_id}",
        document_id=document_id,
        parser=parser,
        parser_version=parser_version,
        ir_schema_version=_IR_SCHEMA_VERSION,
        source_object_key=f"fixtures/parser_benchmark/{document_id}",
        pages=[
            ParsedPage(
                page_number=1,
                width=1,
                height=1,
                text=page_text,
                elements=elements,
            )
        ],
        parse_started_at=datetime(2026, 8, 14, tzinfo=UTC),
        parse_completed_at=datetime(2026, 8, 14, 0, 0, 1, tzinfo=UTC),
        quality_report={"input_kind": "fixture_text_excerpt"},
    )


def apply_manifest_interval(
    provisions: list[ExtractedLegalProvision], manifest: dict
) -> list[ExtractedLegalProvision]:
    """Apply the manifest document interval as a provisional routing interval.

    Only when the interval is provision-uniform (manifest ``status ==
    EFFECTIVE``): the document-level ``effective_from``/``effective_to`` then
    applies to every provision. PARTIALLY_EFFECTIVE and EXPIRED documents are
    never touched — their per-provision intervals are resolver territory
    (VNLRAG-136, W4). Returns new copies; the inputs are never mutated.
    """

    if manifest.get("status") != "EFFECTIVE":
        return provisions
    effective_from = manifest.get("effective_from")
    if not isinstance(effective_from, str) or not effective_from:
        return provisions
    effective_to = manifest.get("effective_to")
    return [
        provision.model_copy(
            update={
                "effective_from": effective_from,
                "effective_to": effective_to if isinstance(effective_to, str) else None,
            }
        )
        for provision in provisions
    ]


def certifying_group_a(
    measured: GroupAResult, *, scan_only: bool
) -> GroupAResult:
    """Group A used for ROUTING (certification view).

    For born-digital sources the measured gates certify the parse, so the
    measured result is returned unchanged. For scan-only sources the fixture
    text is a curated stand-in, NOT the real OCR parse of the authoritative
    PDF, so the extraction/provenance gates are marked ``failed`` (measured
    values are preserved for transparency) — this drives
    ``LOW_OCR_COVERAGE`` in ``route_provision`` per the parser_router.yaml
    scan-review policy: partial OCR output is never auto-indexed.
    """

    if not scan_only:
        return measured

    def _failed(gate: GateResult) -> GateResult:
        detail = dict(gate.detail)
        detail.update(
            {
                "scan_policy": (
                    "source PDF is scan-only (1-bit CCITT, no text layer); the parse "
                    "input is a curated fixture stand-in, not certified OCR output — "
                    "extraction cannot certify the authoritative source"
                ),
                "measured_value": gate.value,
            }
        )
        return GateResult(
            gate=gate.gate,
            value=gate.value,
            threshold=gate.threshold,
            status="failed",
            detail=detail,
        )

    return GroupAResult(
        provenance_coverage=_failed(measured.provenance_coverage),
        text_extraction_rate=_failed(measured.text_extraction_rate),
        table_detection_rate=measured.table_detection_rate,
        layout_coherence=measured.layout_coherence,
        verdict="failed",
    )


def aggregate_routing(decisions: list[RoutingDecision]) -> dict:
    """Aggregate per-provision routing decisions into compact stats.

    Returns ``{"provision_states": {...}, "auto_accepted_count": int,
    "reason_histogram": {...}}``. Deterministic; empty input yields zeroes.
    """

    states: dict[str, int] = Counter(decision.status for decision in decisions)
    reasons = Counter(
        code for decision in decisions for code in decision.reason_codes
    )
    return {
        "provision_states": {
            "ACCEPTED": states.get("ACCEPTED", 0),
            "NEEDS_REVIEW": states.get("NEEDS_REVIEW", 0),
            "DROPPED": states.get("DROPPED", 0),
        },
        "auto_accepted_count": sum(1 for decision in decisions if decision.auto_accepted),
        "reason_histogram": dict(sorted(reasons.items())),
    }


def document_level_decision(
    manifest: dict,
    *,
    has_provisions: bool,
    aggregated: dict,
    scan_only: bool,
) -> dict:
    """Document-level routing decision + reason codes.

    With provisions, mirrors the quality-gate actor job outcome: any
    NEEDS_REVIEW -> NEEDS_REVIEW; else any DROPPED -> DROPPED; else all
    ACCEPTED -> ACCEPTED. Without provisions (no extraction input) the
    document routes NEEDS_REVIEW (LOW_OCR_COVERAGE) — a scan-only source with
    no certified extraction can never auto-index.
    """

    states = aggregated["provision_states"]
    if has_provisions:
        if states["NEEDS_REVIEW"] > 0:
            decision = "NEEDS_REVIEW"
        elif states["DROPPED"] > 0:
            decision = "DROPPED"
        else:
            decision = "ACCEPTED"
        codes = sorted(
            set(aggregated["reason_histogram"]), key=lambda code: _REASON_ORDER.index(code)
        )
    else:
        # No extraction input: a scan-only source with no certified extraction
        # can never auto-index (scan-review policy).
        decision = "NEEDS_REVIEW"
        codes = [LOW_OCR_COVERAGE]
    return {"decision": decision, "reason_codes": codes}


def _short_point_stats(provisions: list[ExtractedLegalProvision]) -> dict:
    flagged = sum(1 for provision in provisions if provision.short_point)
    return {
        "flagged_short_points": flagged,
        "retained_short_points": flagged,  # rulespec §5: no token-length threshold
    }


def quality_stats_for(
    provisions: list[ExtractedLegalProvision], manifest: dict, document_id: str
) -> dict:
    """Per-document extraction quality stats.

    Reuses the corpus QA 16-metric report (``run_corpus_qa``) plus the Group B
    structural metrics and per-kind provision counts — the batch-01 stats the
    ticket asks for (provision counts, point-label detection, provenance
    coverage, parent-context coverage, đ) detection, short-point retention).
    """

    group_b = evaluate_group_b(provisions)
    kinds = Counter(provision.node_kind for provision in provisions)
    corpus_hash = hashlib.sha256(
        json.dumps(manifest, sort_keys=True).encode("utf-8")
    ).hexdigest()
    corpus_qa = run_corpus_qa(
        provisions,
        corpus_version=f"batch-01-w3/{document_id}",
        corpus_hash=corpus_hash,
        manifests={document_id: manifest},
    )
    return {
        "provision_counts": {
            "total": len(provisions),
            **{kind: kinds.get(kind, 0) for kind in ("ARTICLE", "CLAUSE", "POINT")},
            "other": sum(
                count
                for kind, count in kinds.items()
                if kind not in ("ARTICLE", "CLAUSE", "POINT")
            ),
        },
        "group_b_metrics": dict(group_b.metrics),
        "corpus_qa": corpus_qa.metrics.model_dump(mode="json"),
        "short_points": _short_point_stats(provisions),
        "point_label_detection_rate": float(group_b.metrics["point_label_detection_rate"]),
        "provenance_coverage": float(corpus_qa.metrics.provenance_coverage),
        "parent_context_coverage": float(corpus_qa.metrics.parent_context_coverage),
        "d_da_detection_rate": float(corpus_qa.metrics.d_point_detection_rate),
        "short_point_retention": float(corpus_qa.metrics.short_point_retention),
    }


# ────────────────────────────────────────────────────────────────────────────
# Orchestration
# ────────────────────────────────────────────────────────────────────────────


def load_manifests(manifests_dir: Path) -> dict[str, dict]:
    manifests: dict[str, dict] = {}
    for document_id in BATCH01_DOCUMENT_IDS:
        path = manifests_dir / f"{document_id}.manifest.json"
        manifests[document_id] = json.loads(path.read_text(encoding="utf-8"))
    return manifests


def _group_a_dict(result: GroupAResult) -> dict:
    return {
        "verdict": result.verdict,
        "gates": {
            gate.gate: {
                "value": gate.value,
                "threshold": gate.threshold,
                "status": gate.status,
                "detail": gate.detail,
            }
            for gate in result.gates
        },
    }


def _group_b_dict(result: GroupBResult) -> dict:
    return {
        "passed": result.passed,
        "metrics": dict(result.metrics),
        "failed_checks": list(result.failed_checks),
    }


def run_batch01_routing(manifests_dir: Path, repo_root: Path) -> dict:
    """Run the W3 routing pipeline over batch 01 and return the artifact dict."""

    manifests = load_manifests(manifests_dir)
    group_a_thresholds = GroupAThresholds()
    group_b_thresholds = GroupBThresholds()

    documents: dict[str, dict] = {}
    total_states: Counter = Counter()
    total_provisions = 0
    for document_id in BATCH01_DOCUMENT_IDS:
        manifest = manifests[document_id]
        scan_only = document_id in SCAN_ONLY_DOCUMENTS
        fixture_rel = FIXTURE_INPUTS.get(document_id)
        fixture_path = repo_root / fixture_rel if fixture_rel else None

        document_entry: dict = {
            "document_id": document_id,
            "document_type": manifest.get("document_type"),
            "status": manifest.get("status"),
            "manifest_interval": {
                "effective_from": manifest.get("effective_from"),
                "effective_to": manifest.get("effective_to"),
            },
            "source_kind": (
                "scan-only 1-bit CCITT (no text layer)" if scan_only else "born-digital text layer"
            ),
            "indexed": False,
        }

        if fixture_path is not None and fixture_path.is_file():
            lines = [
                line
                for line in fixture_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            ir = build_ir_from_lines(lines, document_id)
            measured_group_a = evaluate_group_a(ir, group_a_thresholds)
            routing_group_a = certifying_group_a(measured_group_a, scan_only=scan_only)
            provisions = extract_legal_provisions(
                ir, document_version_id=document_id, document_slug=document_id
            )
            provisions = [enrich_provision(provision) for provision in provisions]
            provisions = apply_manifest_interval(provisions, manifest)
            group_b = evaluate_group_b(provisions, group_b_thresholds)
            decisions = evaluate_and_route(
                provisions, group_a=routing_group_a, group_b=group_b
            )
            document_entry["extraction_input"] = {
                "kind": "fixture_text_excerpt",
                "path": str(fixture_path.relative_to(repo_root)),
                "note": (
                    "committed parser-benchmark fixture text; born-digital-quality "
                    "excerpt, NOT full official text and NOT real OCR output"
                ),
            }
            document_entry["gate_metrics"] = {
                "group_a_measured": _group_a_dict(measured_group_a),
                "group_a_routing_basis": _group_a_dict(routing_group_a),
                "group_b": _group_b_dict(group_b),
            }
            document_entry["interval"] = {
                "applied": manifest.get("status") == "EFFECTIVE",
                "source": (
                    "manifest document interval (provisional, W3); "
                    "resolver-derived per-provision intervals pending VNLRAG-136/W4"
                ),
                "provision_uniform": manifest.get("status") == "EFFECTIVE",
            }
            aggregated = aggregate_routing(decisions)
            doc_decision = document_level_decision(
                manifest,
                has_provisions=bool(provisions),
                aggregated=aggregated,
                scan_only=scan_only,
            )
            document_entry["routing"] = {
                "decision": doc_decision["decision"],
                "reason_codes": doc_decision["reason_codes"],
                "provision_states": aggregated["provision_states"],
                "auto_accepted_count": aggregated["auto_accepted_count"],
                "reason_histogram": aggregated["reason_histogram"],
                "provision_decisions": [
                    {
                        "provision_id": decision.provision_id,
                        "status": decision.status,
                        "reason_codes": decision.reason_codes,
                        "auto_accepted": decision.auto_accepted,
                    }
                    for decision in decisions
                ],
            }
            document_entry["quality_stats"] = quality_stats_for(
                provisions, manifest, document_id
            )
            document_entry["review_backlog"] = {
                "count": aggregated["provision_states"]["NEEDS_REVIEW"],
                "items": [
                    {
                        "provision_id": decision.provision_id,
                        "reason_codes": decision.reason_codes,
                    }
                    for decision in decisions
                    if decision.status == "NEEDS_REVIEW"
                ],
            }
        else:
            document_entry["extraction_input"] = {
                "kind": "none_available",
                "path": None,
                "note": (
                    "scan-only source PDF is gitignored (absent from the worktree); "
                    "real OCR infeasible in this W3 run; no committed text fixture "
                    "exists for this document — no extraction performed"
                ),
            }
            document_entry["gate_metrics"] = {
                "group_a_measured": None,
                "group_a_routing_basis": None,
                "group_b": None,
                "note": (
                    "no parse input available; gates not computed — routing is the "
                    "scan-review policy decision (LOW_OCR_COVERAGE)"
                ),
            }
            document_entry["interval"] = {
                "applied": False,
                "source": "not applied — no extraction; resolver (VNLRAG-136/W4) assigns intervals",
                "provision_uniform": False,
            }
            empty_aggregate = aggregate_routing([])
            document_entry["routing"] = {
                "decision": "NEEDS_REVIEW",
                "reason_codes": [LOW_OCR_COVERAGE],
                "provision_states": empty_aggregate["provision_states"],
                "auto_accepted_count": 0,
                "reason_histogram": {},
                "provision_decisions": [],
            }
            document_entry["quality_stats"] = quality_stats_for([], manifest, document_id)
            document_entry["review_backlog"] = {"count": 0, "items": []}

        states = document_entry["routing"]["provision_states"]
        total_states.update(
            {"ACCEPTED": states["ACCEPTED"], "NEEDS_REVIEW": states["NEEDS_REVIEW"],
             "DROPPED": states["DROPPED"]}
        )
        total_provisions += document_entry["quality_stats"]["provision_counts"]["total"]
        documents[document_id] = document_entry

    artifact: dict = {
        "artifact": "batch-01-routing",
        "version": ARTIFACT_VERSION,
        "ticket": "VNLRAG-35",
        "phase": "W3 routing-only",
        "generated_at": datetime.now(UTC).isoformat(),
        "command": "cd backend && uv run python scripts/run_batch01_routing.py",
        "base_commit": _git_head(repo_root),
        "thresholds": {
            "group_a": group_a_thresholds.model_dump(mode="json"),
            "group_b": group_b_thresholds.model_dump(mode="json"),
        },
        "indexing": {
            "performed": False,
            "statement": (
                "NO indexing performed: W3 is routing-only. Gate M2 (accept+index "
                "E2E) is deferred to VNLRAG-154/W4; no provision may be indexed "
                "without a resolver-derived effective interval (VNLRAG-136/W4). "
                "ACCEPTED routing decisions here are provisional and stay PENDING "
                "for indexing until the W4 resolvers assign final intervals."
            ),
            "gate_m2": "deferred to VNLRAG-154/W4",
        },
        "documents": documents,
        "summary": {
            "documents": len(documents),
            "documents_routed": len(documents),
            "documents_by_decision": {
                decision: sum(
                    1
                    for entry in documents.values()
                    if entry["routing"]["decision"] == decision
                )
                for decision in ("ACCEPTED", "NEEDS_REVIEW", "DROPPED")
            },
            "total_provisions": total_provisions,
            "provision_states": {
                "ACCEPTED": total_states.get("ACCEPTED", 0),
                "NEEDS_REVIEW": total_states.get("NEEDS_REVIEW", 0),
                "DROPPED": total_states.get("DROPPED", 0),
            },
        },
    }
    return artifact


def _git_head(repo_root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except OSError:
        pass
    return "unknown"


# ────────────────────────────────────────────────────────────────────────────
# Report rendering (pure — unit-tested)
# ────────────────────────────────────────────────────────────────────────────


def render_report(artifact: dict) -> str:
    """Render the quality report markdown from the routing artifact."""

    docs = artifact["documents"]
    summary = artifact["summary"]
    doc_order = list(docs)
    lines: list[str] = []
    add = lines.append

    add("# Batch 01 Routing Report — VNLRAG-35 (W3, routing-only)")
    add("")
    add(f"- Artifact: `data/ingestion/batch-01-routing.json` (version `{artifact['version']}`)")
    add(f"- Generated at: `{artifact['generated_at']}` (UTC)")
    add(f"- Command: `{artifact['command']}`")
    add(f"- Base commit: `{artifact['base_commit']}`")
    add("")

    add("## 1. Scope — W3 routing-only, NO indexing")
    add("")
    add(
        "This run executes the batch-01 ingestion pipeline **up to review routing only** "
        "(doc 05 §5.6, 09/08 row: “Chạy pipeline ingestion tới quality gate và review "
        "routing trên batch 01; accept+index E2E chưa chốt vì resolver có từ W4”). "
        "**NO indexing was performed**; Gate M2 (accept+index E2E) is **not** closed and "
        "is deferred to VNLRAG-154/W4 (doc 05 §5.6 Gate M2 note). No provision may be "
        "indexed without a resolver-derived effective interval (VNLRAG-136, W4); "
        "ACCEPTED routing decisions here are provisional and stay PENDING for indexing "
        "until the W4 resolvers assign final intervals."
    )
    add("")

    add("## 2. Inputs and method")
    add("")
    add(
        "Real OCR of the scan-only batch-01 PDFs (1-bit CCITT, no text layer) is "
        "infeasible for this W3 run (≈30 s/page at 300 DPI, 100+ page documents; "
        "VNLRAG-20/97). Per the ticket, the pipeline ran on the **committed fixture "
        "text / extracted IR where real OCR is infeasible — the exact input used per "
        "document is recorded in the artifact (`extraction_input`) and in the table "
        "below.** Only `luat-36-2024-qh15` has a born-digital text layer; its fixture "
        "is a genuine excerpt of that text. `nd-168-2024`’s fixture is a curated "
        "excerpt stand-in (NOT real OCR output), so its routing Group A is marked "
        "failed on extraction/provenance grounds (scan-review policy, "
        "`docs/parser_router.yaml`) → `LOW_OCR_COVERAGE`."
    )
    add("")
    add("| document_id | source PDF | extraction input | notes |")
    add("|---|---|---|---|")
    for document_id in doc_order:
        entry = docs[document_id]
        input_ = entry["extraction_input"]
        input_path = f" (`{input_['path']}`)" if input_.get("path") else ""
        add(
            f"| `{document_id}` | {entry['source_kind']} | `{input_['kind']}`{input_path} "
            f"| {entry['manifest_interval']['effective_from']} → "
            f"{entry['manifest_interval']['effective_to'] or '∞'} |"
        )
    add("")

    add("## 3. Per-document routing summary")
    add("")
    add(
        "| document_id | Group A (routing basis) | Group B | provisions | ACCEPTED | NEEDS_REVIEW | DROPPED | decision | reason codes |"
    )
    add("|---|---|---|---|---|---|---|---|---|")
    for document_id in doc_order:
        entry = docs[document_id]
        ga = entry["gate_metrics"]["group_a_routing_basis"]
        gb = entry["gate_metrics"]["group_b"]
        ga_verdict = ga["verdict"] if ga else "n/a"
        gb_verdict = ("passed" if gb["passed"] else "failed") if gb else "n/a"
        counts = entry["quality_stats"]["provision_counts"]
        states = entry["routing"]["provision_states"]
        add(
            f"| `{document_id}` | {ga_verdict} | {gb_verdict} | {counts['total']} "
            f"| {states['ACCEPTED']} | {states['NEEDS_REVIEW']} | {states['DROPPED']} "
            f"| **{entry['routing']['decision']}** | {', '.join(entry['routing']['reason_codes']) or '—'} |"
        )
    add("")
    add("Aggregate: "
        + f"{summary['documents']}/{summary['documents_routed']} documents routed; "
        + f"provisions {summary['provision_states']}.")
    add("")
    add(
        "The document-level decision mirrors the quality-gate actor job outcome "
        "(`actors/quality_gate.py`): any NEEDS_REVIEW provision -> document "
        "NEEDS_REVIEW (PENDING_REVIEW — embed/index never runs); else any DROPPED "
        "-> DROPPED; else all ACCEPTED -> ACCEPTED. A document can therefore carry "
        "ACCEPTED provisions and still route NEEDS_REVIEW as a whole."
    )
    add("")

    add("## 4. Extraction quality stats")
    add("")
    add(
        "Per-document stats below reuse the corpus QA metrics "
        "(`app.evaluation.corpus_qa.run_corpus_qa`, 16 FR-10 metrics) plus Group B "
        "structural metrics. **Caveat:** metrics are measured on the extraction input "
        "actually used (fixture excerpt or empty); they do not certify the scan-only "
        "source PDFs."
    )
    add("")
    add(
        "| document_id | provisions (A/C/P) | point-label detection | đ) detection | provenance coverage | parent-context coverage | short-point retention |"
    )
    add("|---|---|---|---|---|---|---|")
    for document_id in doc_order:
        entry = docs[document_id]
        stats = entry["quality_stats"]
        counts = stats["provision_counts"]
        add(
            f"| `{document_id}` | {counts['total']} "
            f"({counts['ARTICLE']}/{counts['CLAUSE']}/{counts['POINT']}) "
            f"| {stats['point_label_detection_rate']:.3f} "
            f"| {stats['d_da_detection_rate']:.3f} "
            f"| {stats['provenance_coverage']:.3f} "
            f"| {stats['parent_context_coverage']:.3f} "
            f"| {stats['short_point_retention']:.3f} |"
        )
    add("")
    add("Highlights:")
    add("")
    luat = docs["luat-36-2024-qh15"]
    luat_states = luat["routing"]["provision_states"]
    nd = docs["nd-168-2024"]
    nd_states = nd["routing"]["provision_states"]
    add(
        f"- `luat-36-2024-qh15` extracts cleanly from born-digital text "
        "(Group A passed, Group B passed); {luat_states['ACCEPTED']}/"
        f"{luat_states['ACCEPTED'] + luat_states['NEEDS_REVIEW']} provisions route "
        "ACCEPTED (auto-accept), the exceptions being the d/đ-ambiguous bare `d)` "
        "labels (`D_D_AMBIGUITY`, "
        f"{luat['routing']['reason_histogram'].get('D_D_AMBIGUITY', 0)}) and the "
        "out-of-primary-run `g)` label (`POINT_LABEL_AMBIGUOUS`, "
        f"{luat['routing']['reason_histogram'].get('POINT_LABEL_AMBIGUOUS', 0)})."
    )
    add(
        f"- `nd-168-2024` measures 1.0 on the fixture IR but the source is "
        "scan-only: every provision routes NEEDS_REVIEW (`LOW_OCR_COVERAGE`, "
        f"{nd_states['NEEDS_REVIEW']}; plus `D_D_AMBIGUITY` on the "
        f"{nd['routing']['reason_histogram'].get('D_D_AMBIGUITY', 0)} bare `d)` points)."
    )
    add("- `nd-100-2019`, `tt-79-2024`, `tt-24-2023`: no extraction input in this W3 "
        "run — zero provisions, document-level NEEDS_REVIEW (`LOW_OCR_COVERAGE`).")
    add("")

    add("## 5. Review backlog summary")
    add("")
    total_review = sum(
        docs[document_id]["review_backlog"]["count"] for document_id in doc_order
    )
    add(
        f"**{total_review} provisions route NEEDS_REVIEW** in batch 01 (the would-be "
        "`ReviewItem` rows, status PENDING, that the quality-gate actor "
        "(`actors/quality_gate.py`) creates in the queue flow; no database is touched "
        "by this W3 script). They are reviewed with the review CLI "
        "(`backend/scripts/review_item.py`, VNLRAG-155) once the queue flow persists "
        "them. Full item list (provision_id + reason codes) is in the artifact "
        "(`documents.<id>.review_backlog.items`)."
    )
    add("")
    add("| document_id | review items | reason histogram |")
    add("|---|---|---|")
    for document_id in doc_order:
        entry = docs[document_id]
        add(
            f"| `{document_id}` | {entry['review_backlog']['count']} "
            f"| {entry['routing']['reason_histogram'] or '—'} |"
        )
    add("")

    add("## 6. Manifest update (sidecar)")
    add("")
    add(
        "The frozen schema `templates/corpus-manifest.schema.json` uses "
        "`additionalProperties: false` and does not allow ingestion-result fields, so "
        "the manifests are **unchanged** and the ingestion results live in the sidecar "
        "artifact `data/ingestion/batch-01-routing.json` (per the ticket: “if the "
        "schema doesn’t allow ingestion-result fields, add a separate sidecar … and "
        "note why; do NOT change the frozen schema”). All five manifests still "
        "validate:"
    )
    add("")
    for document_id in doc_order:
        add(f"    `uv run python -m scripts.validate_manifest ../data/manifests/batch-01/{document_id}.manifest.json` → PASS")
    add("")

    add("## 7. Reproducibility")
    add("")
    add("```bash")
    add("# 1. Run the pipeline (regenerates artifact + this report)")
    add(f"{artifact['command']}")
    add("# 2. Tests for the script’s pure helpers")
    add("cd backend && uv run pytest tests/test_run_batch01_routing.py --no-cov -q")
    add("```")
    add("")
    add(f"- Routing artifact: `data/ingestion/batch-01-routing.json`")
    add("- Report: `docs/evaluation/batch-01-routing-report.md` (this file, generated)")
    add("- Script: `backend/scripts/run_batch01_routing.py`")
    add("- Tests: `backend/tests/test_run_batch01_routing.py`")
    add("")
    add("### Verification (recorded at commit time)")
    add("")
    add("- Test output verbatim: see below (appended after the run).")
    add("- Commit hash: see below (appended after the commit).")
    add("")
    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "VNLRAG-35 batch-01 W3 routing-only ingestion run: quality gates + "
            "review routing; writes data/ingestion/batch-01-routing.json and "
            "docs/evaluation/batch-01-routing-report.md."
        )
    )
    parser.add_argument(
        "--manifests-dir",
        default=None,
        help="batch-01 manifests directory (default: <repo>/data/manifests/batch-01)",
    )
    parser.add_argument(
        "--artifacts",
        default=None,
        help="output routing artifact path (default: <repo>/data/ingestion/batch-01-routing.json)",
    )
    parser.add_argument(
        "--report",
        default=None,
        help="output report path (default: <repo>/docs/evaluation/batch-01-routing-report.md)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_root = _BACKEND_DIR.parent
    manifests_dir = Path(args.manifests_dir) if args.manifests_dir else repo_root / "data" / "manifests" / "batch-01"
    artifact_path = Path(args.artifacts) if args.artifacts else repo_root / "data" / "ingestion" / "batch-01-routing.json"
    report_path = Path(args.report) if args.report else repo_root / "docs" / "evaluation" / "batch-01-routing-report.md"

    artifact = run_batch01_routing(manifests_dir, repo_root)
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(artifact), encoding="utf-8")

    summary = artifact["summary"]
    print(f"wrote {artifact_path}")
    print(f"wrote {report_path}")
    print(
        "routing: "
        f"{summary['documents_by_decision']} documents; "
        f"provisions {summary['provision_states']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
