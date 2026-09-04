"""Deterministic-first claim support verification with fail-closed judging."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from .l2_citation import LayerResult, VerificationIssue


def _v(x: Any, n: str, d: Any = None) -> Any:
    return x.get(n, d) if isinstance(x, Mapping) else getattr(x, n, d)


def _text(x: Any) -> str:
    return str(_v(x, "text", _v(x, "content", x)) or "")


def _tokens(s: str) -> set[str]:
    return {w.casefold() for w in s.split() if len(w) > 2}


class L5ClaimVerifier:
    def __init__(
        self, judge: Callable[..., Any] | None = None, judge_enabled: bool = True
    ) -> None:
        self.judge, self.judge_enabled = judge, judge_enabled

    def verify(
        self,
        draft: Any,
        context: Sequence[Any] = (),
        query_context: Any = None,
        **_: Any,
    ) -> LayerResult:
        issues: list[VerificationIssue] = []
        checked: list[str] = []
        by_id = {_v(x, "provision_id", _v(x, "id")): x for x in context}
        for i, claim in enumerate(_v(draft, "claims", ()) or ()):
            ids = _v(claim, "provision_ids", ()) or ()
            if not ids:
                issues.append(
                    VerificationIssue(
                        "L5_CLAIM_WITHOUT_CITATION", "claim has no citation", claim_index=i
                    )
                )
                continue
            passages = [_text(by_id[x]) for x in ids if x in by_id]
            if not passages:
                issues.append(
                    VerificationIssue("L5_CLAIM_NOT_SUPPORTED", "no cited passage", claim_index=i)
                )
                continue
            claim_text = (
                _text(claim)
                if _v(claim, "claim") is None
                else str(_v(claim, "claim"))
            )
            if _tokens(claim_text) & set().union(*(_tokens(p) for p in passages)):
                checked.append(str(i))
                continue
            if self.judge_enabled and self.judge is not None:
                try:
                    verdict = self.judge(claim_text, passages)
                    if verdict is True or _v(verdict, "supported", False) is True:
                        checked.append(str(i))
                        continue
                except Exception:
                    issues.append(
                        VerificationIssue(
                            "L5_JUDGE_UNAVAILABLE",
                            "semantic judge unavailable",
                            claim_index=i,
                        )
                    )
                    continue
            issues.append(
                VerificationIssue("L5_CLAIM_NOT_SUPPORTED", "claim is not supported", claim_index=i)
            )
        return LayerResult(not issues, issues, checked)


def verify(
    draft: Any, context: Sequence[Any] = (), query_context: Any = None, **kwargs: Any
) -> LayerResult:
    return L5ClaimVerifier().verify(draft, context, query_context, **kwargs)


__all__ = ["L5ClaimVerifier", "verify"]
