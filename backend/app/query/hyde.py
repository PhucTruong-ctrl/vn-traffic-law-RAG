"""Conditional HyDE generation boundary for dense retrieval only."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from .query_understanding_types import EvidenceType


class HyDEProvider(Protocol):
    """Provider that returns hypothetical legal text for dense embedding."""

    def generate(self, query: str, evidence_type: EvidenceType) -> str | None: ...


class HyDEGenerator:
    """Small adapter keeping the generation provider outside retrieval policy."""

    dense_only = True

    def __init__(
        self,
        provider: HyDEProvider | Callable[[str, EvidenceType], str | None],
    ) -> None:
        self._provider = provider

    def generate(self, query: str, evidence_type: EvidenceType) -> str | None:
        generator = self._provider
        if callable(generator):
            return generator(query, evidence_type)
        return generator.generate(query, evidence_type)


__all__ = ["HyDEGenerator", "HyDEProvider"]
