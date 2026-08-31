"""Independent before/after retrieval for comparison questions."""

from __future__ import annotations

from datetime import date
from typing import Protocol

from pydantic import BaseModel, ConfigDict

from app.query.query_understanding import QueryPlan
from app.retrieval.contracts import CandidateSet


class _HistoricalRetriever(Protocol):
    def retrieve(self, plan: QueryPlan, *, query_date: date) -> CandidateSet: ...


class _CurrentRetriever(Protocol):
    def retrieve(self, plan: QueryPlan, *, current_date: date) -> CandidateSet: ...


class ComparisonResult(BaseModel):
    """Two independently retrieved contexts, retaining their temporal sides."""

    model_config = ConfigDict(extra="forbid", strict=True)

    before: CandidateSet
    after: CandidateSet

    @property
    def before_applied_date(self) -> date | None:
        return self.before.applied_date

    @property
    def after_applied_date(self) -> date | None:
        return self.after.applied_date


class ComparisonRetriever:
    """Retrieve before and after contexts without combining citation lists."""

    def __init__(
        self,
        historical: _HistoricalRetriever,
        current: _CurrentRetriever,
    ) -> None:
        self._historical = historical
        self._current = current

    def compare(
        self,
        plan: QueryPlan,
        *,
        date_from: date,
        date_to: date,
    ) -> ComparisonResult:
        """Run each side independently, including when both dates are equal."""
        before = self._historical.retrieve(plan, query_date=date_from)
        after = self._current.retrieve(plan, current_date=date_to)
        return ComparisonResult(before=before, after=after)


__all__ = ["ComparisonResult", "ComparisonRetriever"]
