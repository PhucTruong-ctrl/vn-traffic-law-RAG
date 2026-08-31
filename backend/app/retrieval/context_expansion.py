"""Bounded expansion of accepted legal context through resolved relations."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date
from types import SimpleNamespace
from typing import Any

from app.persistence.models import LegalProvision
from app.retrieval.contracts import RetrievalResult

_RELATION_TYPES = frozenset({"PARENT_OF", "SIBLING_OF", "REFERS_TO", "PENALTY_COMPANION"})
_DOCUMENT_AMENDMENT_RELATION_TYPES = frozenset(
    {"AMENDS", "REPEALS", "SUPERSEDES", "CORRECTS"}
)
_ADDED_BY = {
    "PARENT_OF": "PARENT_CONTEXT",
    "REFERS_TO": "CROSS_REFERENCE",
    "SIBLING_OF": "SIBLING",
    "PENALTY_COMPANION": "PENALTY_COMPANION",
}


class LegalContextExpander:
    """Add a small, date-valid relation neighborhood around retrieval seeds."""

    def __init__(
        self,
        relation_repository: Any,
        temporal_repository: Any,
        *,
        max_depth: int = 2,
        max_breadth: int = 5,
        max_added_provisions: int = 10,
    ) -> None:
        self._relations = relation_repository
        self._temporal = temporal_repository
        self._max_depth = max_depth
        self._max_breadth = max_breadth
        self._max_added = max_added_provisions

    def expand(
        self, seeds: Sequence[RetrievalResult], *, query_date: date
    ) -> list[RetrievalResult]:
        """Expand only top-three seeds, retaining deterministic breadth/depth bounds."""
        frontier = [seed for seed in seeds if seed.rank <= 3]
        if not frontier or self._max_depth < 1 or self._max_added < 1:
            return []

        # RelationRepository requires LegalProvision rows pinned to exact versions.
        seed_rows = self._valid_rows(query_date, [seed.provision_id for seed in frontier])
        rows_by_id = {row.provision_id: row for row in seed_rows}
        current = [
            rows_by_id[seed.provision_id]
            for seed in frontier
            if seed.provision_id in rows_by_id
        ]
        seen = {seed.provision_id for seed in seeds}
        added: list[RetrievalResult] = []

        for depth in range(1, self._max_depth + 1):
            if not current or len(added) >= self._max_added:
                break
            related = self._related(query_date, current)
            next_rows: list[Any] = []
            for relation in related:
                if len(added) >= self._max_added:
                    break
                provision = _related_provision(relation)
                provision_id = getattr(provision, "provision_id", None)
                if not provision_id or provision_id in seen:
                    continue
                valid = self._valid_rows(query_date, [provision_id])
                canonical = next((row for row in valid if row.provision_id == provision_id), None)
                if canonical is None:
                    continue
                result = _result(canonical, len(seeds) + len(added) + 1, relation, depth)
                seen.add(provision_id)
                added.append(result)
                next_rows.append(canonical)
            current = next_rows[: self._max_breadth]
        return added

    def _valid_rows(
        self,
        query_date: date,
        provision_ids: Iterable[str],
        *,
        document_id: str | None = None,
    ) -> list[LegalProvision]:
        ids = list(provision_ids)
        if not ids and document_id is None:
            return []
        method = getattr(self._temporal, "valid_provisions", None)
        if not callable(method):
            raise RuntimeError(
                "context expansion requires temporal_repository.valid_provisions()"
            )
        return list(
            method(
                query_date,
                provision_ids=ids or None,
                document_id=document_id,
            )
        )

    def _related(self, query_date: date, seeds: Sequence[Any]) -> list[Any]:
        method = getattr(self._relations, "related_provisions", None)
        if not callable(method):
            raise RuntimeError(
                "context expansion requires relation_repository.related_provisions()"
            )
        related: list[Any] = list(
            method(query_date, seeds, relation_types=_RELATION_TYPES)
        )

        # Document relations are an optional repository capability.  An
        # available method must still fail loudly rather than being swallowed.
        document_method = getattr(self._relations, "related_documents", None)
        if not callable(document_method):
            return related[: self._max_breadth]

        documents: dict[str, str] = {}
        for seed in seeds:
            document_version = getattr(seed, "document_version", None)
            document = getattr(document_version, "document", None)
            document_id = getattr(document, "document_id", None) or getattr(
                seed, "document_id", None
            )
            if document_id:
                documents.setdefault(
                    str(document_id), str(getattr(seed, "provision_id", document_id))
                )
        for document_id, source_id in documents.items():
            for document_relation in document_method(
                query_date,
                document_id,
                relation_types=_DOCUMENT_AMENDMENT_RELATION_TYPES,
            ):
                relation_type = getattr(document_relation, "relation_type", None)
                if relation_type not in _DOCUMENT_AMENDMENT_RELATION_TYPES:
                    continue
                target_id = getattr(document_relation, "target_document_id", None)
                if not target_id:
                    continue
                targets = self._valid_rows(query_date, [], document_id=str(target_id))
                for target in targets[: self._max_breadth]:
                    related.append(
                        SimpleNamespace(
                            provision=target,
                            relation_type=relation_type,
                            source_id=source_id,
                            added_by="AMENDMENT",
                        )
                    )
        return related[: self._max_breadth]


def _related_provision(relation: Any) -> Any:
    return getattr(relation, "provision", relation)


def _relation_value(relation: Any, name: str, default: Any) -> Any:
    value = getattr(relation, name, default)
    return value() if callable(value) else value


def _result(row: Any, rank: int, relation: Any, depth: int) -> RetrievalResult:
    document_version = getattr(row, "document_version", None)
    document = getattr(document_version, "document", None)
    document_number = getattr(document, "document_number", None) or getattr(
        row, "document_number", None
    )
    document_id = getattr(document, "document_id", None) or getattr(row, "document_id", None)
    effective_from = getattr(row, "effective_from", None)
    article = getattr(row, "article", None)
    if effective_from is None or article is None or document_number is None:
        raise ValueError("accepted related provision lacks citation metadata")
    relation_type = _relation_value(relation, "relation_type", "RELATION")
    return RetrievalResult(
        rank=rank,
        provision_id=row.provision_id,
        provision_version=row.version,
        document_id=document_id,
        document_version_id=str(row.document_version_id),
        text=row.retrieval_text,
        source_text=row.source_text,
        parent_context=row.parent_context,
        document_number=document_number,
        article=article,
        clause=row.clause,
        point=row.point,
        effective_from=effective_from,
        effective_to=row.effective_to,
        page_number=row.page_number,
        retrieval_sources=["context_expansion"],
        fused_score=None,
        added_by=_relation_value(relation, "added_by", _ADDED_BY.get(relation_type)),
        source_id=str(_relation_value(relation, "source_id", "")) or None,
        depth=depth,
    )


__all__ = ["LegalContextExpander"]
