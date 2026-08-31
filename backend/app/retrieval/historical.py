"""Historical retrieval with temporal and PostgreSQL authority checks."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from app.query.query_understanding import QueryPlan
from app.retrieval.contracts import CandidateSet
from app.retrieval.filters import build_temporal_filter


class TemporalAuthority(Protocol):
    """The PostgreSQL-backed validity query needed by serving retrieval."""

    def valid_provisions(self, d: date, *, provision_ids: list[str]) -> list[object]: ...


class CandidateRetriever(Protocol):
    """A vector retriever accepting the shared Qdrant temporal filter."""

    def search(
        self,
        query: str,
        *,
        query_filter: object | None = None,
        limit: int | None = None,
    ) -> CandidateSet: ...


def _row_is_valid_at(row: object, query_date: date) -> bool:
    """Defensively mirror the database predicate for repository test doubles."""
    if getattr(row, "review_status", "ACCEPTED") != "ACCEPTED":
        return False
    effective_from = getattr(row, "effective_from", None)
    if effective_from is not None and effective_from > query_date:
        return False
    effective_to = getattr(row, "effective_to", None)
    return effective_to is None or query_date < effective_to


class HistoricalRetriever:
    """Retrieve provisions valid at an explicitly resolved historical date."""

    def __init__(
        self,
        retriever: CandidateRetriever,
        temporal_repository: TemporalAuthority,
        *,
        top_k: int | None = None,
    ) -> None:
        self._retriever = retriever
        self._temporal_repository = temporal_repository
        self._top_k = top_k

    def retrieve(self, plan: QueryPlan, *, query_date: date | None) -> CandidateSet:
        """Return only candidates accepted and valid at ``query_date``.

        A missing date is unsafe for historical serving: current law must never
        be used as a fallback. Qdrant filtering is followed by the
        PostgreSQL-authoritative validity check because the index is derived.
        """
        if query_date is None or "query_date" in plan.missing_query_information:
            raise ValueError("historical retrieval requires an unambiguous query date")

        query = plan.normalized_query
        candidates = self._retriever.search(
            query,
            query_filter=build_temporal_filter(query_date, vehicle_type=plan.vehicle_type),
            limit=self._top_k,
        )
        candidate_ids = [result.provision_id for result in candidates.results]
        valid_rows = self._temporal_repository.valid_provisions(
            query_date, provision_ids=candidate_ids
        )
        valid_ids = {
            provision_id
            for row in valid_rows
            if _row_is_valid_at(row, query_date)
            and (provision_id := getattr(row, "provision_id", None)) is not None
        }
        results = [
            result.model_copy(update={"rank": rank})
            for rank, result in enumerate(
                (result for result in candidates.results if result.provision_id in valid_ids),
                start=1,
            )
        ]
        return CandidateSet(query=candidates.query, results=results, applied_date=query_date)


__all__ = ["HistoricalRetriever"]
