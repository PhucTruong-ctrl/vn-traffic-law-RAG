"""Small structured multi-intent decomposition with deterministic fallback."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Intent:
    text: str
    kind: str = "legal"


@dataclass(frozen=True, slots=True)
class Analysis:
    intents: tuple[Intent, ...]


def analyze_question(question: str, model: object | None = None) -> Analysis:
    """Use an optional structured model; otherwise split common Vietnamese conjunctions."""
    if model is not None and hasattr(model, "invoke"):
        try:
            value = model.invoke(question)
            parsed = _from_model(value)
            if parsed:
                return Analysis(tuple(parsed[:4]))
        except Exception:
            pass
    pieces = [
        piece.strip(" .?!")
        for piece in re.split(r"\s+(?:và|đồng thời|ngoài ra)\s+", question, flags=re.I)
    ]
    intents = tuple(Intent(piece, classify_intent(piece)) for piece in pieces if piece)
    return Analysis(intents or (Intent(question.strip(), classify_intent(question)),))


def classify_intent(text: str) -> str:
    lowered = text.casefold()
    if re.search(r"\b(hello|hi|xin chào|cảm ơn|tạm biệt)\b", lowered):
        return "chitchat"
    if re.search(r"\b(google|web|internet|trên mạng|tin tức)\b", lowered):
        return "web"
    if re.search(r"\b(luật|điều|khoản|nghị định|thông tư|phạt|giao thông)\b", lowered):
        return "legal"
    return "out_of_scope"


def _from_model(value: object) -> list[Intent]:
    raw = getattr(value, "intents", value)
    if not isinstance(raw, (list, tuple)):
        return []
    result: list[Intent] = []
    for item in raw:
        if isinstance(item, Intent):
            result.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            result.append(
                Intent(item["text"], str(item.get("kind") or classify_intent(item["text"])))
            )
    return result


__all__ = ["Analysis", "Intent", "analyze_question", "classify_intent"]
