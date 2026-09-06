"""Application-owned boundary for the optional RAGFlow benchmark adapter.

RAGFlow is deliberately not part of the VNLRAG correctness path.  The
application exchanges retrieval units and candidates through these protocols;
provider-specific SDKs and HTTP payloads stay outside the domain modules.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from app.ingestion.retrieval_units import RetrievalUnit
from app.retrieval.contracts import CandidateSet


@runtime_checkable
class RAGFlowIngestionPort(Protocol):
    """Boundary for loading VNLRAG legal-boundary units into RAGFlow."""

    def ingest(self, units: Sequence[RetrievalUnit]) -> int: ...


@runtime_checkable
class RAGFlowRetrievalPort(Protocol):
    """Boundary for benchmark retrieval; no RAGFlow type leaks into callers."""

    def search(self, query: str, *, limit: int = 10) -> CandidateSet: ...


__all__ = ["RAGFlowIngestionPort", "RAGFlowRetrievalPort"]
