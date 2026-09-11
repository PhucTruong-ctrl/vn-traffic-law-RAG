"""Deterministic helpers for turning chat history into follow-up queries."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def build_followup_query(
    question: str,
    messages: Iterable[Mapping[str, Any]] = (),
    *,
    limit: int = 6,
) -> str:
    """Combine recent conversational context with current question.

    Message mappings may use ``content`` and optionally ``role``. Empty content
    is ignored; at most the last six messages are retained by default.
    """
    current = " ".join(question.rstrip("?.!;: ").split())
    if not current:
        raise ValueError("question must not be blank")
    if limit < 1:
        raise ValueError("limit must be positive")

    context: list[str] = []
    for message in list(messages)[-limit:]:
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            role = message.get("role")
            prefix = f"{role}: " if isinstance(role, str) and role.strip() else ""
            context.append(f"{prefix}{' '.join(content.split())}")
    return f"{' '.join(context)}\nCurrent question: {current}" if context else current


__all__ = ["build_followup_query"]
