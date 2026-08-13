"""Retrieval Units: index LegalProvision records as atomic retrieval units.

VNLRAG-48 — each legal provision (``provision_id`` + ``version``) becomes
exactly one retrieval unit whose boundary is the legal boundary: units never
split or merge provision text (doc 00 §4.1/§8.3, doc 03 §3.8.6).

- ``source_text`` is preserved verbatim for citation display and is never
  mutated by enrichment (gold ``parent_context_annotation.json`` rule
  ``source_text_immutable``).
- ``retrieval_text`` may inherit parent context (clause lead-in / article
  heading) added by the Legal Context Enricher (VNLRAG-132, FR-04).
- Short points are retained: there is no token-length threshold (doc 03
  §3.8.5; gold ``short_point_annotation.json`` policy).
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict

from app.ingestion.structure_extractor import ExtractedLegalProvision

__all__ = ["RetrievalUnit", "build_retrieval_units", "retrieval_unit_stats"]


class RetrievalUnit(BaseModel):
    """One indexable retrieval unit — exactly one legal provision.

    The unit boundary is the legal boundary: a unit never splits or merges
    provision text. ``retrieval_text`` is the retrieval-side text (possibly
    enriched with parent context); ``source_text`` is the verbatim original
    used for citation display.
    """

    model_config = ConfigDict(extra="forbid")

    unit_id: str
    provision_id: str
    version: int
    node_kind: str
    retrieval_text: str
    source_text: str
    parent_context: str | None
    page_number: int | None
    document_id: str | None
    short_point: bool


def _unit_id(provision: ExtractedLegalProvision) -> str:
    return f"{provision.provision_id}__v{provision.version}"


def _enrich_retrieval_text(provision: ExtractedLegalProvision) -> str:
    """Apply the VNLRAG-132 Legal Context Enricher to one provision.

    The deferred import keeps this module importable while
    ``app.ingestion.context_enricher`` is developed in the parallel ticket;
    after the branches merge the real enricher is resolved and called here
    (orchestrator verifies the integration).
    """
    from app.ingestion.context_enricher import enrich_retrieval_text

    return enrich_retrieval_text(provision)


def build_retrieval_units(provisions: list[ExtractedLegalProvision]) -> list[RetrievalUnit]:
    """Build one retrieval unit per provision (legal-boundary chunking).

    Every provision yields exactly one unit — short points included; there is
    no token-length filtering and no text splitting/merging. ``retrieval_text``
    is the enricher output for the whole provision, ``source_text`` is copied
    verbatim, and ``unit_id`` is ``f"{provision_id}__v{version}"``.
    """
    return [
        RetrievalUnit(
            unit_id=_unit_id(provision),
            provision_id=provision.provision_id,
            version=provision.version,
            node_kind=provision.node_kind,
            retrieval_text=_enrich_retrieval_text(provision),
            source_text=provision.source_text,
            parent_context=provision.parent_context,
            page_number=provision.page_number,
            document_id=provision.document_version_id,
            short_point=provision.short_point,
        )
        for provision in provisions
    ]


def retrieval_unit_stats(units: list[RetrievalUnit]) -> dict[str, int | dict[str, int]]:
    """Count retrieval units per ``node_kind`` plus the total.

    Useful for tests/QA: e.g. asserting the corpus yielded the expected number
    of POINT units (short points included) after legal-boundary chunking.
    """
    by_node_kind = dict(sorted(Counter(unit.node_kind for unit in units).items()))
    return {"total": len(units), "by_node_kind": by_node_kind}
