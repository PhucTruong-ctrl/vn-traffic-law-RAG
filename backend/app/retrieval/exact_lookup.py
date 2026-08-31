"""Authoritative exact legal-reference retrieval."""

from __future__ import annotations

from collections.abc import Collection
from datetime import date
from typing import Any

from app.persistence.models import LegalProvision
from app.persistence.repositories.provisions import ProvisionRepository
from app.retrieval.contracts import CandidateSet, RetrievalResult


class ExactLookup:
    """Resolve document and hierarchy references against PostgreSQL."""

    def __init__(self, repository: ProvisionRepository) -> None:
        self._repository = repository

    def lookup(
        self,
        *,
        document_number: str,
        article: str | None,
        clause: str | None,
        point: str | None,
        query_date: date,
        vehicle_type: str | None = None,
        derived_provision_ids: Collection[str] = (),
    ) -> CandidateSet:
        """Return only accepted provisions valid at ``query_date``.

        ``derived_provision_ids`` is an optional Qdrant hint.  It can improve
        intersection when the index is current, but never suppresses the
        canonical PostgreSQL result when it is stale.
        """
        rows = self._repository.lookup_exact(
            document_number=document_number,
            article=article,
            clause=clause,
            point=point,
            query_date=query_date,
        )
        if vehicle_type is not None:
            rows = [row for row in rows if _supports_vehicle(row, vehicle_type)]

        derived = set(derived_provision_ids)
        if derived:
            matched = [row for row in rows if row.provision_id in derived or str(row.id) in derived]
            if matched:
                rows = matched

        results = [_result(row, rank) for rank, row in enumerate(rows, 1)]
        query = _reference_query(document_number, article, clause, point)
        return CandidateSet(query=query, results=results, applied_date=query_date)



def _supports_vehicle(row: LegalProvision, vehicle_type: str) -> bool:
    """Apply optional vehicle metadata without making it part of the schema."""
    metadata: Any = row.document_version.manifest_json
    vehicle_types = metadata.get("vehicle_types") if isinstance(metadata, dict) else None
    return not vehicle_types or vehicle_type in vehicle_types

def _result(row: LegalProvision, rank: int) -> RetrievalResult:
    document = row.document_version.document
    if row.effective_from is None or row.article is None:
        raise ValueError("accepted exact lookup row lacks citation metadata")
    return RetrievalResult(
        rank=rank,
        provision_id=row.provision_id,
        provision_version=row.version,
        document_id=document.document_id,
        document_version_id=str(row.document_version_id),
        text=row.retrieval_text,
        source_text=row.source_text,
        parent_context=row.parent_context,
        document_number=document.document_number,
        article=row.article,
        clause=row.clause,
        point=row.point,
        effective_from=row.effective_from,
        effective_to=row.effective_to,
        page_number=row.page_number,
        retrieval_sources=["exact"],
        fused_score=None,
        added_by=None,
        source_id=str(document.source_id) if document.source_id is not None else None,
        depth=0,
    )


def _reference_query(
    document_number: str, article: str | None, clause: str | None, point: str | None
) -> str:
    parts = [document_number]
    if article is not None:
        parts.append(f"Điều {article}")
    if clause is not None:
        parts.append(f"Khoản {clause}")
    if point is not None:
        parts.append(f"Điểm {point}")
    return ", ".join(parts)


__all__ = ["ExactLookup"]
