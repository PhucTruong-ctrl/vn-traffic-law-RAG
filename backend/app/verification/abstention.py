"""Standardized fail-closed abstention reasons."""

from __future__ import annotations

from enum import StrEnum


class AbstentionReason(StrEnum):
    MISSING_EVIDENCE = "MISSING_EVIDENCE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    MISSING_DATE = "MISSING_DATE"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    VERIFICATION_FAILURE = "VERIFICATION_FAILURE"


class AbstentionDecision:
    """Stable abstention contract consumed by workflow and API layers."""

    __slots__ = ("abstain", "reason")

    def __init__(self, reason: AbstentionReason) -> None:
        self.abstain = True
        self.reason = reason

    @property
    def reason_code(self) -> str:
        return self.reason.value


def abstain(reason: AbstentionReason) -> AbstentionDecision:
    return AbstentionDecision(reason)


__all__ = ["AbstentionDecision", "AbstentionReason", "abstain"]
