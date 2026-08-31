"""Current-law retrieval using an explicit request date."""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol

from app.persistence.repositories.temporal import TemporalRepository
from app.query.query_understanding import QueryPlan
from app.retrieval.contracts import CandidateSet
from app.retrieval.filters import build_temporal_filter


class _Retriever(Protocol):
    def search(
        self,
        query: str,
        *,
        query_filter: Any = None,
        limit: int | None = None,
    ) -> CandidateSet: ...


class CurrentRetriever:
    """Retrieve provisions valid under the caller-supplied current date.

    The wrapped vector retriever applies the index-side temporal filter.  The
    PostgreSQL repository then supplies the authoritative accepted provision
    IDs, preventing stale derived-index rows from being served.
    """

    def __init__(
        self,
        retriever: _Retriever,
        temporal_repository: TemporalRepository | None = None,
        *,
        top_k: int | None = None,
    ) -> None:
        self._retriever = retriever
        self._temporal_repository = temporal_repository
        self._top_k = top_k

    def retrieve(self, plan: QueryPlan, *, current_date: date) -> CandidateSet:
        """Return candidates active at ``current_date`` (half-open interval)."""
        candidates = self._retriever.search(
            plan.normalized_query,
            query_filter=build_temporal_filter(current_date, vehicle_type=plan.vehicle_type),
            limit=self._top_k,
        )
        allowed_ids: set[str] | None = None
        if self._temporal_repository is not None:
            rows = self._temporal_repository.valid_provisions(
                current_date,
                provision_ids={result.provision_id for result in candidates.results},
            )
            allowed_ids = {row.provision_id for row in rows}

        results = [
            result
            for result in candidates.results
            if result.effective_from <= current_date
            and (result.effective_to is None or current_date < result.effective_to)
            and (allowed_ids is None or result.provision_id in allowed_ids)
        ]
        return CandidateSet(
            query=candidates.query,
            results=[
                result.model_copy(update={"rank": rank}) for rank, result in enumerate(results, 1)
            ],
            applied_date=current_date,
        )


__all__ = ["CurrentRetriever"]
