"""Typed boundary between the query workflow and legal verification gates.

This module owns no legal policy. It composes the existing fail-closed gates
and exposes a stable result that orchestration can route without inspecting
provider-specific objects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from .abstention import AbstentionReason
from .l2_citation import L2CitationVerifier, VerificationIssue
from .l4_numeric import L4NumericVerifier
from .l5_claim import L5ClaimVerifier, OpenRouterClaimJudge
from .l6_evidence import L6EvidenceVerifier


@dataclass(frozen=True, slots=True)
class VerificationBoundaryResult:
    passed: bool
    reason_code: str | None = None
    issues: tuple[VerificationIssue, ...] = ()
    missing: tuple[str, ...] = ()
    checked_provision_ids: tuple[str, ...] = ()

    @classmethod
    def rejected(
        cls,
        reason_code: str,
        *,
        issues: tuple[VerificationIssue, ...] = (),
        missing: tuple[str, ...] = (),
    ) -> VerificationBoundaryResult:
        return cls(False, reason_code, issues, missing)


@dataclass(slots=True)
class LegalVerificationBoundary:
    citation: L2CitationVerifier = field(default_factory=L2CitationVerifier)
    numeric: L4NumericVerifier = field(default_factory=L4NumericVerifier)
    claim: L5ClaimVerifier = field(
        default_factory=lambda: L5ClaimVerifier(judge=OpenRouterClaimJudge(), judge_enabled=True)
    )
    evidence: L6EvidenceVerifier = field(default_factory=L6EvidenceVerifier)

    def verify(
        self,
        draft: Any,
        context: list[Any] | tuple[Any, ...],
        *,
        query_date: date | None,
        in_scope: bool = True,
    ) -> VerificationBoundaryResult:
        if not in_scope:
            return VerificationBoundaryResult.rejected(AbstentionReason.OUT_OF_SCOPE.value)
        records = tuple(
            item for item in context if getattr(item, "review_status", "ACCEPTED") == "ACCEPTED"
        )
        if not records:
            return VerificationBoundaryResult.rejected(AbstentionReason.MISSING_EVIDENCE.value)
        citation = self.citation.verify(draft, records, provisions=records, expanded=records)
        if not citation.passed:
            return VerificationBoundaryResult.rejected(
                citation.issues[0].code
                if citation.issues
                else AbstentionReason.VERIFICATION_FAILURE.value,
                issues=tuple(citation.issues),
            )
        numeric = self.numeric.verify(draft, records)
        if not numeric.passed:
            return VerificationBoundaryResult.rejected(
                numeric.issues[0].code
                if numeric.issues
                else AbstentionReason.VERIFICATION_FAILURE.value,
                issues=tuple(numeric.issues),
            )
        claim = self.claim.verify(draft, records)
        if not claim.passed:
            return VerificationBoundaryResult.rejected(
                claim.issues[0].code
                if claim.issues
                else AbstentionReason.VERIFICATION_FAILURE.value,
                issues=tuple(claim.issues),
            )
        evidence = self.evidence.verify(
            getattr(draft, "claims", None), records, query_date=query_date, verification_ok=True
        )
        if not evidence.passed:
            return VerificationBoundaryResult.rejected(
                evidence.reason.value
                if evidence.reason
                else AbstentionReason.VERIFICATION_FAILURE.value,
                missing=tuple(evidence.missing),
            )
        return VerificationBoundaryResult(
            True, checked_provision_ids=tuple(dict.fromkeys(citation.checked_provision_ids))
        )


__all__ = ["LegalVerificationBoundary", "VerificationBoundaryResult"]
