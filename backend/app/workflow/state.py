"""State passed between controlled query-graph nodes."""

from __future__ import annotations

from datetime import date
from typing import Any, TypedDict


class QueryState(TypedDict, total=False):
    question: str
    query_date: date
    vehicle_type: str | None
    # Transport aliases are accepted by the safe adapters in graph.py.
    input_question: str
    input_date: date
    query_understanding: Any
    temporal_context: Any
    expansion_set: Any
    recall_candidates: Any
    fused: Any
    reranked: Any
    expanded_context: Any
    evidence_status: Any
    evidence_gaps: list[Any]
    context_package: Any
    draft_answer: Any
    verification_result: Any
    repair_attempts: int
    max_repair_attempts: int
    final_response: Any
    error: str | None


__all__ = ["QueryState"]
