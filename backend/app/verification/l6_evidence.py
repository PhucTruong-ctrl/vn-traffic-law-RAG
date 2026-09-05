"""L6 evidence completeness verification.

The verifier is deliberately fail closed: malformed inputs or unavailable
checks produce a verification failure rather than an affirmative result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from .abstention import AbstentionReason


@dataclass(frozen=True)
class L6Result:
    passed: bool
    reason: AbstentionReason | None = None
    missing: list[str] = field(default_factory=list)


def _get(value: Any, key: str, default: Any = None) -> Any:
    return (
        value.get(key, default) if isinstance(value, Mapping) else getattr(value, key, default)
    )


class L6EvidenceVerifier:
    """Require every claim to have complete, in-scope, dated evidence."""

    def verify(
        self,
        claims: Sequence[Any] | None,
        evidence: Sequence[Any] | None,
        *,
        query_date: Any = None,
        in_scope: bool = True,
        verification_ok: bool = True,
    ) -> L6Result:
        if not in_scope:
            return L6Result(False, AbstentionReason.OUT_OF_SCOPE)
        if not verification_ok:
            return L6Result(False, AbstentionReason.VERIFICATION_FAILURE)
        if claims is None or evidence is None:
            return L6Result(False, AbstentionReason.VERIFICATION_FAILURE)
        if query_date is None:
            return L6Result(False, AbstentionReason.MISSING_DATE)
        try:
            records = list(evidence)
            if not records:
                return L6Result(False, AbstentionReason.MISSING_EVIDENCE)
            missing: list[str] = []
            for claim in claims:
                ids = _get(claim, "provision_ids", ())
                if not ids or not any(
                    _get(record, "provision_id", _get(record, "id")) in ids
                    and _get(record, "text", _get(record, "content", "")).strip()
                    and _get(record, "effective_from", query_date) <= query_date
                    and (_get(record, "effective_to") is None or query_date < _get(record, "effective_to"))
                    for record in records
                ):
                    missing.append(str(_get(claim, "claim", "claim")))
            if missing:
                return L6Result(False, AbstentionReason.INSUFFICIENT_EVIDENCE, missing)
            return L6Result(True)
        except Exception:
            return L6Result(False, AbstentionReason.VERIFICATION_FAILURE)


def verify(claims: Sequence[Any] | None, evidence: Sequence[Any] | None, **kwargs: Any) -> L6Result:
    return L6EvidenceVerifier().verify(claims, evidence, **kwargs)


__all__ = ["L6EvidenceVerifier", "L6Result", "verify"]
