"""Parser provenance aggregation for legal provisions (VNLRAG-29).

Aggregates the provenance the parser already attached to each
:class:`ExtractedLegalProvision` record (``source_element_ids``,
``page_number``, ``bbox``) into :class:`ProvenanceRecord` instances that
mirror the ``provision_provenances`` persistence contract (doc 03 §3.9.14):
one record per ``source_element_id``, carrying the role of the source
document version that contributed that content.

A provision version may legitimately originate from more than one source
document (base text plus amending/correcting documents); the multi-source
API records per-source roles explicitly — this module never assumes one
source PDF per provision version.  ``page_number``/``bbox`` on
``LegalProvision`` stay a convenience projection; the authoritative
per-content source lives in the provenance records (doc 03 §3.9.14).

This module is a pure mapping layer: it never touches a session or a
transaction — the repository layer (VNLRAG-39) owns persistence and must
supply the persisted ``legal_provisions.id`` as ``provision_version_row_id``
(available after the row is flushed).
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.ingestion.structure_extractor import ExtractedLegalProvision

#: Provenance roles — mirror the ``provision_provenances.role`` CHECK
#: constraint and ``ProvisionProvenanceRole`` in doc 03 §3.9.14.
ProvisionProvenanceRole = Literal[
    "BASE_TEXT", "AMENDMENT_TEXT", "CORRECTION_TEXT", "EFFECT_SOURCE"
]

#: A single-source provenance "source": (source_document_version_id, role,
#: element ids contributed by that source document version).
_SourceAttribution = tuple[UUID, ProvisionProvenanceRole, list[str]]


class ProvenanceRecord(BaseModel):
    """One content-source mapping for a persisted provision version row.

    Field-for-field mirror of the ``provision_provenances`` columns
    (doc 03 §3.9.14): ``provision_version_row_id`` is the persisted
    ``legal_provisions.id`` of the version row the content belongs to.
    """

    model_config = ConfigDict(extra="forbid")

    provision_version_row_id: UUID
    source_document_version_id: UUID
    source_element_id: str
    page_number: int
    bbox: dict[str, float] | None
    role: ProvisionProvenanceRole


def aggregate_provenance(
    provision: ExtractedLegalProvision,
    *,
    provision_version_row_id: UUID,
    source_document_version_id: UUID,
    role: ProvisionProvenanceRole = "BASE_TEXT",
) -> list[ProvenanceRecord]:
    """Aggregate single-source provenance for one extracted provision.

    Produces one :class:`ProvenanceRecord` per entry in
    ``provision.source_element_ids``; every record inherits
    ``provision.page_number`` and ``provision.bbox`` and carries
    ``role`` for ``source_document_version_id``.

    ``provision_version_row_id`` is the persisted ``legal_provisions.id`` of
    the row this content belongs to — available only after the row is
    flushed, so aggregation itself stays session-free.
    """

    return [
        ProvenanceRecord(
            provision_version_row_id=provision_version_row_id,
            source_document_version_id=source_document_version_id,
            source_element_id=element_id,
            page_number=provision.page_number,
            bbox=provision.bbox,
            role=role,
        )
        for element_id in provision.source_element_ids
    ]


def aggregate_multi_source_provenance(
    provision: ExtractedLegalProvision,
    *,
    provision_version_row_id: UUID,
    sources: list[_SourceAttribution],
) -> list[ProvenanceRecord]:
    """Aggregate provenance for a provision whose content comes from several
    source documents (e.g. an amended clause: base text + amendment text).

    Each ``sources`` entry is ``(source_document_version_id, role,
    element_ids)`` — the element ids contributed by that source document
    version.  Records inherit ``provision.page_number`` and
    ``provision.bbox``; each record carries the role of its own source, so
    amended provisions get ``BASE_TEXT`` records plus
    ``AMENDMENT_TEXT``/``CORRECTION_TEXT`` records without assuming one
    source PDF per provision version (ticket VNLRAG-29).

    Raises ``ValueError`` unless the attributed element ids match
    ``provision.source_element_ids`` exactly (every source element must be
    attributed to exactly one source).
    """

    attributed: list[str] = []
    for _source_document_version_id, _role, element_ids in sources:
        attributed.extend(element_ids)
    if sorted(attributed) != sorted(provision.source_element_ids):
        raise ValueError(
            f"attributed element ids {sorted(attributed)} do not match "
            f"provision.source_element_ids {sorted(provision.source_element_ids)} "
            f"for {provision.provision_id!r}"
        )

    records: list[ProvenanceRecord] = []
    for source_document_version_id, role, element_ids in sources:
        records.extend(
            ProvenanceRecord(
                provision_version_row_id=provision_version_row_id,
                source_document_version_id=source_document_version_id,
                source_element_id=element_id,
                page_number=provision.page_number,
                bbox=provision.bbox,
                role=role,
            )
            for element_id in element_ids
        )
    return records


def provenance_coverage(provisions: list[ExtractedLegalProvision]) -> float:
    """Fraction of provisions with ≥1 ``source_element_id`` and a non-null
    ``page_number``; ``0.0`` for an empty list.

    Cross-ticket contract (VNLRAG-127 corpus QA consumes this exact
    signature): both conditions must hold for a provision to count as
    covered.
    """

    if not provisions:
        return 0.0
    covered = sum(
        1
        for provision in provisions
        if provision.source_element_ids and provision.page_number is not None
    )
    return covered / len(provisions)


__all__ = [
    "ProvisionProvenanceRole",
    "ProvenanceRecord",
    "aggregate_provenance",
    "aggregate_multi_source_provenance",
    "provenance_coverage",
]
