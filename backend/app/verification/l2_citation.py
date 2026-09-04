"""Deterministic L2 citation/provision ID verification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class VerificationIssue:
    code: str
    message: str
    claim_index: int | None = None
    provision_id: str | None = None


@dataclass(frozen=True)
class LayerResult:
    passed: bool
    issues: list[VerificationIssue] = field(default_factory=list)
    checked_provision_ids: list[str] = field(default_factory=list)


def _value(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, Mapping) else getattr(item, name, default)


def _provision_id(item: Any) -> str | None:
    return _value(item, "provision_id") or _value(item, "id")


def _metadata_matches(citation: Any, record: Any) -> bool:
    names = ("document_id", "document_number", "article", "clause", "point")
    return all(
        _value(citation, name) is None or _value(citation, name) == _value(record, name)
        for name in names
    )


class L2CitationVerifier:
    """Verify cited IDs against accepted records and retrieved/expanded context."""

    def __init__(self, provisions: Any = None) -> None:
        self.provisions = provisions

    def verify(
        self,
        draft: Any,
        context: Sequence[Any] = (),
        query_context: Any = None,
        *,
        provisions: Any = None,
        expanded: Sequence[Any] = (),
    ) -> LayerResult:
        records = provisions if provisions is not None else self.provisions
        records = records() if callable(records) else (records or ())
        known = {_provision_id(item): item for item in records if _provision_id(item)}
        whitelist = {_provision_id(item) for item in (*context, *expanded) if _provision_id(item)}
        issues: list[VerificationIssue] = []
        checked: list[str] = []
        for claim_index, claim in enumerate(_value(draft, "claims", ()) or ()):
            provision_ids = _value(claim, "provision_ids", None)
            if provision_ids is None:
                # Legacy drafts carried citation objects instead of Claim IDs.
                citations = _value(claim, "citations", ()) or ()
            else:
                citations = provision_ids
                if not citations:
                    issues.append(
                        VerificationIssue(
                            "L2_INVALID_CITATION",
                            "claim has no provision_ids",
                            claim_index=claim_index,
                        )
                    )
                    continue
            for citation in citations:
                pid = _provision_id(citation) or (citation if isinstance(citation, str) else None)
                if not pid:
                    issues.append(
                        VerificationIssue(
                            "L2_INVALID_CITATION",
                            "citation has no provision_id",
                            claim_index=claim_index,
                        )
                    )
                    continue
                record = known.get(pid)
                if record is None:
                    issues.append(
                        VerificationIssue(
                            "L2_UNKNOWN_PROVISION",
                            f"unknown provision_id: {pid}",
                            claim_index=claim_index,
                            provision_id=pid,
                        )
                    )
                    continue
                if pid not in whitelist and _value(record, "added_by") not in {
                    "expanded",
                    "context_expansion",
                    "legal_context",
                }:
                    issues.append(
                        VerificationIssue(
                            "L2_INVALID_CITATION",
                            f"provision_id not in context whitelist: {pid}",
                            claim_index=claim_index,
                            provision_id=pid,
                        )
                    )
                    continue
                if _value(record, "review_status", "ACCEPTED") != "ACCEPTED":
                    issues.append(
                        VerificationIssue(
                            "L2_INVALID_CITATION",
                            f"provision is not accepted: {pid}",
                            claim_index=claim_index,
                            provision_id=pid,
                        )
                    )
                    continue
                if not _metadata_matches(citation, record):
                    issues.append(
                        VerificationIssue(
                            "L2_INVALID_CITATION",
                            f"citation metadata mismatch: {pid}",
                            claim_index=claim_index,
                            provision_id=pid,
                        )
                    )
                    continue
                checked.append(pid)
        return LayerResult(not issues, issues, checked)


def verify(
    draft: Any, context: Sequence[Any] = (), query_context: Any = None, **kwargs: Any
) -> LayerResult:
    return L2CitationVerifier().verify(draft, context, query_context, **kwargs)


__all__ = ["L2CitationVerifier", "LayerResult", "VerificationIssue", "verify"]
