"""Deterministic grounding of claim numbers against cited context."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from .l2_citation import LayerResult, VerificationIssue

_NUM = re.compile(r"(?<![\w])(?:\d{1,3}(?:[.\s]\d{3})+|\d+(?:[,.]\d+)?)(?![\w])")


def _v(item: Any, name: str, default: Any = None) -> Any:
    return item.get(name, default) if isinstance(item, Mapping) else getattr(item, name, default)


def normalize_number(value: Any) -> str:
    s = str(value).strip().lower().replace("\u00a0", " ")
    s = re.sub(r"(?:vnđ|vnd|đ|dong|đồng)", "", s)
    s = re.sub(r"[^0-9,.\s-]", "", s).replace(" ", "")
    if "." in s and "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(?:\.\d{3})+", s):
        s = s.replace(".", "")
    elif "," in s:
        s = s.replace(",", ".")
    return s


def _text(x: Any) -> str:
    return str(_v(x, "text", _v(x, "content", x)) or "")


class L4NumericVerifier:
    def verify(
        self,
        draft: Any,
        context: Sequence[Any] = (),
        query_context: Any = None,
        **_: Any,
    ) -> LayerResult:
        issues: list[VerificationIssue] = []
        checked: list[str] = []
        corpus = " ".join(_text(x) for x in context)
        available = {normalize_number(x) for x in _NUM.findall(corpus)}
        for i, claim in enumerate(_v(draft, "claims", ()) or ()):
            nums = _v(claim, "numbers", ()) or ()
            for n in nums:
                if normalize_number(n) not in available:
                    issues.append(
                        VerificationIssue(
                            "L4_NUMERIC_MISMATCH",
                            f"number not grounded: {n}",
                            claim_index=i,
                        )
                    )
            if nums and all(normalize_number(n) in available for n in nums):
                checked.append(str(i))
        return LayerResult(not issues, issues, checked)


def verify(
    draft: Any, context: Sequence[Any] = (), query_context: Any = None, **kwargs: Any
) -> LayerResult:
    return L4NumericVerifier().verify(draft, context, query_context, **kwargs)


__all__ = ["L4NumericVerifier", "normalize_number", "verify"]
