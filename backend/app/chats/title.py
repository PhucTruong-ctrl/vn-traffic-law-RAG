"""Small, deterministic chat-title generation helper."""

from __future__ import annotations

import re

_SPACE_RE = re.compile(r"\s+")


def generate_title(question: str, *, max_length: int = 60) -> str:
    """Return concise title derived solely from question text."""
    if max_length < 1:
        raise ValueError("max_length must be positive")
    text = _SPACE_RE.sub(" ", question).strip()
    if not text:
        raise ValueError("question must not be blank")
    text = text.rstrip("?.!;: ")
    if len(text) <= max_length:
        return text
    cut = text[: max_length - 1].rsplit(" ", 1)[0].rstrip()
    return (cut or text[: max_length - 1].rstrip()) + "…"


__all__ = ["generate_title"]
