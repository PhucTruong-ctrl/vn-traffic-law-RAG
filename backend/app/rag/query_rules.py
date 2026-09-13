"""Declarative query normalization rules."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[3]
_RULES = _ROOT / "data" / "rag" / "query_rules.json"


def _normalized(text: str) -> str:
    return " ".join(text.casefold().split())


@lru_cache(maxsize=1)
def load_query_rules() -> dict[str, Any]:
    payload = json.loads(_RULES.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("query rules must be an object")
    return payload


def expand_query(question: str) -> str:
    lowered = question.casefold()
    additions = [
        legal
        for alias, legal in load_query_rules().get("action_aliases", {}).items()
        if alias.casefold() in lowered and legal.casefold() not in lowered
    ]
    return "; ".join((question, *additions))


def requested_context(question: str) -> str:
    lowered = _normalized(question)
    rules = load_query_rules()
    matches = [
        (len(_normalized(str(alias))), str(context))
        for context, aliases in rules.get("context_aliases", {}).items()
        for alias in aliases
        if _normalized(str(alias)) in lowered
    ]
    if matches:
        return max(matches)[1]
    return str(rules.get("default_context", ""))


__all__ = ["expand_query", "load_query_rules", "requested_context"]
