"""Review routing for ingested provisions (VNLRAG-33).

Runs AFTER the quality gates (Group A parser-level, Group B structural) and
classifies every extracted provision as ``ACCEPTED`` (auto-accept),
``NEEDS_REVIEW`` or ``DROPPED`` per the auto-accept policy of
``docs/03-thiet-ke-he-thong.md`` §3.7.5 and the scan-review routing policy of
``docs/parser_router.yaml``. Routing is deterministic — no confidence scores,
no models, no randomness.

Core principle (doc 03 §3.7.5): **a confidence score NEVER decides a
legal-effect fact** (effective dates, amendment/repeal relations). Legal
decisions rest only on authoritative sources (official manifest, exact
deterministic patterns, reviewer decisions).

Auto-accept policy (the 8 rows of doc 03 §3.7.5, implemented):

===============  =================  ===========================================
Result kind      Auto-accept?       Condition
===============  =================  ===========================================
1. Deterministic parser structure (Chương/Mục/Điều/Khoản/Điểm, đ label, short point)
                 Yes                Group A + B gates pass, no ambiguity flag;
                                    still must be ACCEPTED before indexing.
2. Official manifest metadata (document_number, issued_date, effective_from,
   effective_to from the official source)
                 Yes                Manifest matches the official source; if the
                                    manifest contradicts the source → review.
3. Exact REFERS_TO resolution (explicit pattern pointing at an existing target)
                 Yes, if            Target exists, pattern matches exactly, no
                   deterministic    ambiguity.
4. Inferred PENALTY_COMPANION (not explicit)
                 Review             Always routed to review, never auto.
5. Inferred partial amendment (not explicit in the manifest)
                 Review             Always reviewed.
6. Uncertain effective date (no reliable source)
                 Review             UNKNOWN/PENDING_REVIEW until a reviewer
                                    decides.
7. Legal-effect relations based purely on confidence
                 Never              Confidence never decides a legal fact;
                                    a source or a review is required.
8. Document/provision with missing provenance (page/bbox)
                 Review             Except elements that do not need provenance.
===============  =================  ===========================================

This module implements rows 1, 6 and 8 (and the "never" rule of row 7) for
provision routing; rows 2–5 belong to the manifest/normalization and
reference/temporal resolvers. Consequences (doc 03 §3.7.5): ``ACCEPTED`` is
only assigned by valid auto-accept (row 1) or by a later reviewer decision
(VNLRAG-155 Review CLI, which persists reviewer identity + timestamp), and
every auto-accept decision is recorded here as ``auto_accepted=True`` for the
``ingestion_runs.parser_routing`` audit trail.

Routing rules (deterministic, in priority order):

1. **DROPPED** on hard structural failures — never indexed:
   * ``DUPLICATE_PROVISION`` — the provision_id appears more than once in the
     document (provision_ids are globally unique by construction, docs/03
     §3.8.5); every row sharing the duplicated id is untrustworthy.
   * ``INVALID_POINT_LABEL`` — a POINT provision whose label is not a
     recognizable Vietnamese point label (no label at all, or text with no
     point-label form such as ``"xyz"``).
2. **NEEDS_REVIEW** on any ambiguity or policy flag (all codes accumulated):
   * ``D_D_AMBIGUITY`` — d/đ ambiguity: the extractor flagged an OCR d/đ
     normalization or duplicate ``d)`` label (rulespec §4.1), or the label is
     a bare ``d)`` without ordinal context (per
     :func:`app.ingestion.metadata_normalizer.canonical_point_label`, the
     caller must flag review).
   * ``POINT_LABEL_AMBIGUOUS`` — point label recognized but outside the PRIMARY
     run ``a→b→c→d→đ→e`` (e.g. ``g)``), or reconstructed from a
     marker-stripped list item.
   * ``HIERARCHY_VIOLATION`` — orphan point/clause, non-numeric article
     suffix, or clause number reconstructed from a marker-stripped list item.
   * ``HEADER_FOOTER_LEAKAGE`` — the provision text carries the republic
     header/footer boilerplate (:func:`app.ingestion.metadata_normalizer.
     is_header_footer_leakage`).
   * ``UNKNOWN_EFFECTIVE_DATE`` — ``effective_from`` is missing or
     ``UNKNOWN``/``PENDING_REVIEW`` (policy row 6; never guessed).
   * ``LOW_OCR_COVERAGE`` — Group A ``text_extraction_rate`` or
     ``provenance_coverage`` is below its threshold (scan-derived; never
     auto-index partial OCR output, parser_router.yaml scan-review policy).
   * ``NEEDS_REVIEW`` — generic fallback: any other extractor review flag, a
     Group A verdict of N/A, or a failed Group B verdict without a
     provision-specific reason (a failed document-level gate blocks
     auto-accept for every provision, policy row 1).
3. **ACCEPTED** (``auto_accepted=True``) only when every gate passes
   (Group A verdict ``passed``, Group B ``passed``) AND no review flag above
   applies — policy row 1 exactly.

Short points are retained by rule (rulespec §5: no token-length threshold) and
route exactly like any other point — being short is never a review reason by
itself; a short point whose label is ambiguous/invalid routes on the label.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

from app.ingestion.metadata_normalizer import canonical_point_label, is_header_footer_leakage
from app.ingestion.quality_gates import (
    GroupAResult,
    GroupBResult,
    GroupBThresholds,
    evaluate_group_b,
)
from app.ingestion.structure_extractor import ExtractedLegalProvision

RoutingStatus = Literal["ACCEPTED", "NEEDS_REVIEW", "DROPPED"]

#: Routing reason codes (aligned with parser_router.yaml scan-review policy
#: and doc 03 §3.7.5). ``INVALID_POINT_LABEL`` is the DROPPED counterpart of
#: the review-level ``POINT_LABEL_AMBIGUOUS``.
LOW_OCR_COVERAGE = "LOW_OCR_COVERAGE"
POINT_LABEL_AMBIGUOUS = "POINT_LABEL_AMBIGUOUS"
D_D_AMBIGUITY = "D_D_AMBIGUITY"
HIERARCHY_VIOLATION = "HIERARCHY_VIOLATION"
DUPLICATE_PROVISION = "DUPLICATE_PROVISION"
INVALID_POINT_LABEL = "INVALID_POINT_LABEL"
HEADER_FOOTER_LEAKAGE = "HEADER_FOOTER_LEAKAGE"
UNKNOWN_EFFECTIVE_DATE = "UNKNOWN_EFFECTIVE_DATE"
NEEDS_REVIEW = "NEEDS_REVIEW"

ReviewReason = Literal[
    "LOW_OCR_COVERAGE",
    "POINT_LABEL_AMBIGUOUS",
    "D_D_AMBIGUITY",
    "HIERARCHY_VIOLATION",
    "DUPLICATE_PROVISION",
    "INVALID_POINT_LABEL",
    "HEADER_FOOTER_LEAKAGE",
    "UNKNOWN_EFFECTIVE_DATE",
    "NEEDS_REVIEW",
]

#: Tree node kinds participating in the Điều hierarchy (docs/03 §3.8.1).
_TREE_KINDS = frozenset({"ARTICLE", "CLAUSE", "POINT"})

#: PRIMARY Vietnamese point-run alphabet (rulespec §4.1: ``a→b→c→d→đ→e``).
#: Mirrors ``hierarchy_validation._POINT_RUN_ALPHABET``.
_PRIMARY_POINT_RUN = "abcdđe"

#: Bare ``d)`` label needing ordinal context (rulespec §4.1) — the label form
#: :func:`canonical_point_label` cannot resolve without an ordinal.
_BARE_D_LABEL_RE = re.compile(r"^\s*(?:điểm\s+)?d[)）]", re.IGNORECASE)

#: Extractor review flags (``ExtractedLegalProvision.ambiguity`` values set by
#: the Legal Structure Extractor, structure_state_parser.py) → reason codes.
_AMBIGUITY_REASON: dict[str, str] = {
    "OCR d/đ ambiguity normalized from duplicate d)": D_D_AMBIGUITY,
    "duplicate d) point label": D_D_AMBIGUITY,
    "point label reconstructed from marker-stripped list item": POINT_LABEL_AMBIGUOUS,
    "clause number reconstructed from marker-stripped list item": HIERARCHY_VIOLATION,
    "non-numeric article suffix": HIERARCHY_VIOLATION,
    "orphan point without article/clause": HIERARCHY_VIOLATION,
    "orphan clause without article": HIERARCHY_VIOLATION,
    "table without article or appendix": HIERARCHY_VIOLATION,
}


class RoutingDecision(BaseModel):
    """One provision's routing verdict.

    ``status``: ``ACCEPTED`` (auto-accept per policy row 1), ``NEEDS_REVIEW``
    (human review required, VNLRAG-155) or ``DROPPED`` (never indexed).
    ``reason_codes`` lists the hard-failure codes for DROPPED and all review
    codes for NEEDS_REVIEW (empty for ACCEPTED). ``auto_accepted`` is True
    exactly when the decision was taken by the auto-accept policy
    (``status == "ACCEPTED"``) — recorded for the parser_routing audit trail.
    """

    provision_id: str
    status: RoutingStatus
    reason_codes: list[str]
    auto_accepted: bool


def _tree_kind(provision: ExtractedLegalProvision) -> str | None:
    """Effective tree kind: ``node_kind`` authoritative, else field inference.

    Mirrors ``hierarchy_validation._provision_kind``.
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


def _label_status(provision: ExtractedLegalProvision) -> str | None:
    """Point-label status for routing, or None when the provision is not a POINT.

    ``"valid"`` — canonical PRIMARY-run label; ``"d_ambiguity"`` — bare ``d)``
    without ordinal context; ``"ambiguous"`` — recognized Vietnamese label
    beyond the PRIMARY run (e.g. ``g)``); ``"invalid"`` — no recognizable
    point label at all.
    """

    if _tree_kind(provision) != "POINT":
        return None
    label = provision.point_label or provision.point
    if label is None:
        return "invalid"
    canonical = canonical_point_label(label)
    if canonical is not None:
        if canonical[0] in _PRIMARY_POINT_RUN:
            return "valid"
        return "ambiguous"
    if _BARE_D_LABEL_RE.match(label):
        return "d_ambiguity"
    return "invalid"


def _effective_date_unknown(provision: ExtractedLegalProvision) -> bool:
    """True when the provision carries no reliable effective date (policy row 6)."""

    value = provision.effective_from
    if value is None:
        return True
    cleaned = value.strip().casefold()
    return not cleaned or cleaned in {"unknown", "pending_review"}


def _duplicated_ids(provisions: list[ExtractedLegalProvision]) -> frozenset[str]:
    """Provision_ids appearing more than once (count > 1)."""

    counts: dict[str, int] = {}
    for provision in provisions:
        counts[provision.provision_id] = counts.get(provision.provision_id, 0) + 1
    return frozenset(pid for pid, count in counts.items() if count > 1)


def _append_unique(codes: list[str], code: str) -> None:
    if code not in codes:
        codes.append(code)


def route_provision(
    provision: ExtractedLegalProvision,
    *,
    group_a: GroupAResult,
    group_b: GroupBResult,
    duplicated_ids: frozenset[str] | None = None,
) -> RoutingDecision:
    """Route one provision: DROPPED / NEEDS_REVIEW / ACCEPTED (deterministic).

    ``duplicated_ids`` is the set of provision_ids appearing more than once in
    the document (computed by :func:`evaluate_and_route`; pass it when routing
    within a full document so duplicates can be DROPPED). Decision precedence:
    hard structural failures (duplicate, invalid point label) → DROPPED; any
    review flag → NEEDS_REVIEW; otherwise ACCEPTED. ``auto_accepted`` is True
    only for ACCEPTED decisions (policy row 1: gates pass AND no flags).
    """

    hard: list[str] = []
    review: list[str] = []

    # 1. Hard structural failures → DROPPED (never indexed).
    if duplicated_ids is not None and provision.provision_id in duplicated_ids:
        hard.append(DUPLICATE_PROVISION)
    if _label_status(provision) == "invalid":
        hard.append(INVALID_POINT_LABEL)
    if hard:
        return RoutingDecision(
            provision_id=provision.provision_id,
            status="DROPPED",
            reason_codes=hard,
            auto_accepted=False,
        )

    # 2. Review flags → NEEDS_REVIEW (all codes accumulated).
    label_status = _label_status(provision)
    if label_status == "d_ambiguity":
        _append_unique(review, D_D_AMBIGUITY)
    elif label_status == "ambiguous":
        _append_unique(review, POINT_LABEL_AMBIGUOUS)

    if provision.needs_review:
        if provision.ambiguity in _AMBIGUITY_REASON:
            _append_unique(review, _AMBIGUITY_REASON[provision.ambiguity])
        else:
            _append_unique(review, NEEDS_REVIEW)

    if is_header_footer_leakage(provision.source_text):
        _append_unique(review, HEADER_FOOTER_LEAKAGE)

    if _effective_date_unknown(provision):
        _append_unique(review, UNKNOWN_EFFECTIVE_DATE)

    if (
        group_a.text_extraction_rate.status == "failed"
        or group_a.provenance_coverage.status == "failed"
    ):
        # Scan-derived: low OCR extraction/provenance → never auto-index
        # partial OCR output (parser_router.yaml scan-review policy).
        _append_unique(review, LOW_OCR_COVERAGE)
    elif group_a.verdict != "passed":
        # Table/layout gate failure or an all-N/A verdict: not certifiable.
        _append_unique(review, NEEDS_REVIEW)

    if not group_b.passed:
        # Policy row 1: Group B must pass for auto-accept; a document-level
        # structural failure blocks it for every provision.
        _append_unique(review, NEEDS_REVIEW)

    if review:
        return RoutingDecision(
            provision_id=provision.provision_id,
            status="NEEDS_REVIEW",
            reason_codes=review,
            auto_accepted=False,
        )

    return RoutingDecision(
        provision_id=provision.provision_id,
        status="ACCEPTED",
        reason_codes=[],
        auto_accepted=True,
    )


def evaluate_and_route(
    provisions: list[ExtractedLegalProvision],
    *,
    group_a: GroupAResult,
    thresholds: GroupBThresholds | None = None,
    group_b: GroupBResult | None = None,
) -> list[RoutingDecision]:
    """Evaluate Group B (unless supplied) and route every provision.

    Convenience wrapper over :func:`evaluate_group_b` + :func:`route_provision`
    that computes the document-level duplicate set so duplicated ids are
    DROPPED. An empty ``provisions`` list yields an empty routing list.
    """

    result = group_b if group_b is not None else evaluate_group_b(provisions, thresholds)
    duplicated = _duplicated_ids(provisions)
    return [
        route_provision(provision, group_a=group_a, group_b=result, duplicated_ids=duplicated)
        for provision in provisions
    ]


__all__ = [
    "D_D_AMBIGUITY",
    "DUPLICATE_PROVISION",
    "HEADER_FOOTER_LEAKAGE",
    "HIERARCHY_VIOLATION",
    "INVALID_POINT_LABEL",
    "LOW_OCR_COVERAGE",
    "NEEDS_REVIEW",
    "POINT_LABEL_AMBIGUOUS",
    "ReviewReason",
    "RoutingDecision",
    "RoutingStatus",
    "UNKNOWN_EFFECTIVE_DATE",
    "evaluate_and_route",
    "route_provision",
]
