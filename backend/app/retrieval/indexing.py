"""Idempotent provision indexing (VNLRAG-44).

Turns ACCEPTED ``LegalProvision`` rows from PostgreSQL into Qdrant points in
``PROVISION_ALIAS`` (``legal_provisions_active``) following the doc 03 §3.11
contract implemented by ``app.retrieval.qdrant_store``:

- One point per provision version row; the Qdrant point id is the row UUID
  itself (:func:`point_id_for`) — deterministic, which is what makes indexing
  **idempotent**: re-running (or resuming after a killed worker) upserts the
  same point ids with replace semantics, so points are never duplicated.
- Only ``review_status == 'ACCEPTED'`` provisions are indexed (doc 00 §8.6,
  FR-09): DROPPED/REJECTED/NEEDS_REVIEW/PENDING never enter the index. The
  boundary is enforced at selection time in :func:`index_accepted_provisions`
  (a ``WHERE review_status = 'ACCEPTED'`` query); the lower-level
  :func:`index_provision_units` builds whatever units it is given and does
  not second-guess their status.
- Payload per doc 03 §3.11.3 (built by ``qdrant_store.payload_for_unit``),
  with the dense vector from an ``EmbeddingProvider`` and the sparse vector
  from a ``SparseEncoder``. Both providers are optional — a ``None`` provider
  simply omits that vector channel, so contract tests and dry runs need no
  live embedding API.

W3 contract scope
-----------------
This module delivers the *indexing* half of the W3 data platform: an
idempotent, queue-ready indexer that can be re-run safely. The E2E
accept+index closure (ACCEPTED provisions flowing from review routing into
this indexer with resolved intervals) is the M2 gate locked at W4
(VNLRAG-154) — it depends on the reference/temporal resolvers existing and is
deliberately NOT claimed here.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import date
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import QdrantClient, models
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.retrieval_units import RetrievalUnit
from app.persistence.models import LegalProvision
from app.retrieval.embedding import EmbeddingProvider
from app.retrieval.qdrant_store import (
    DENSE_VECTOR_NAME,
    PROVISION_ALIAS,
    SPARSE_VECTOR_NAME,
    payload_for_unit,
)
from app.retrieval.sparse import SparseEncoder, sparse_vector_dict, with_encoder_version

__all__ = [
    "ACCEPTED_REVIEW_STATUS",
    "IndexResult",
    "build_point",
    "index_accepted_provisions",
    "index_provision_units",
    "point_id_for",
    "provision_row_to_unit",
    "payload_metadata_from_row",
]

#: The only review status that may enter the index (doc 00 §8.6, FR-09).
ACCEPTED_REVIEW_STATUS = "ACCEPTED"


class IndexResult(BaseModel):
    """Outcome of one indexing run.

    Attributes:
        indexed: number of points upserted (one per provision version row).
        skipped_no_effective_from: ACCEPTED provisions skipped because they
            lack an ``effective_from`` while ``effective_from_required`` was
            set (defensive guard — the PG check constraint
            ``legal_provisions_effective_from_accepted_check`` already
            guarantees ACCEPTED rows carry an interval).
        errors: human-readable failures recorded during the run. A failed
            batch/unit does not abort the run; a re-run retries it (idempotent
            resume — the point ids are deterministic).
    """

    model_config = ConfigDict(extra="forbid")

    indexed: int = 0
    skipped_no_effective_from: int = 0
    errors: list[str] = Field(default_factory=list)


def point_id_for(provision_row_id: uuid.UUID) -> str:
    """Deterministic Qdrant point id for a ``LegalProvision`` row.

    The point id IS the provision row UUID rendered as a string — a
    Qdrant-valid id (Qdrant accepts UUID-string ids). Deterministic by
    construction: the same row always maps to the same point, which is what
    makes indexing idempotent (upsert replaces the point; re-running never
    duplicates).
    """
    return str(provision_row_id)


def build_point(
    unit: RetrievalUnit,
    *,
    point_id: str,
    embedder: EmbeddingProvider | None = None,
    sparse_encoder: SparseEncoder | None = None,
    dense_vector: list[float] | None = None,
    sparse_weights: dict[int, float] | None = None,
    **payload_kwargs: Any,
) -> models.PointStruct:
    """Build one Qdrant point (payload + named vectors) for a retrieval unit.

    The payload is ``qdrant_store.payload_for_unit`` output — the full
    doc 03 §3.11.3 key set. Input provenance:

    - From the ``RetrievalUnit``: ``provision_id``, ``version``
      (``provision_version``), ``node_kind``, ``retrieval_text`` (``text``),
      ``source_text``, ``parent_context``, ``page_number``, and
      ``document_version_id`` (defaulted from ``unit.document_id``, the
      document-version UUID).
    - From ``payload_kwargs`` (forwarded verbatim to ``payload_for_unit``):
      everything the unit does not carry — ``review_status``,
      ``effective_from``/``effective_to``, ``parser_version``,
      ``legal_parser_version``, ``sparse_encoder_version``,
      ``content_version``, ``relations``, ``vehicle_types``, hierarchy labels
      (``chapter``/``section``/``article``/``clause``/``point``/``heading``)
      and document metadata (``document_number``/``document_type``/
      ``document_title``/``document_version``/``document_status``/``parser``/
      ``content_hash``/``document_id``). ``document_id`` (the LOGICAL
      document id) is derived from the ``provision_id`` slug prefix when not
      given.

    Vectors:

    - Dense: ``embedder.embed([unit.retrieval_text])[0]`` when ``embedder``
      is given and ``dense_vector`` is not. ``index_provision_units`` passes
      precomputed batched vectors so embedding happens once per batch, not
      once per point.
    - Sparse: ``sparse_encoder.encode(unit.retrieval_text)`` when
      ``sparse_encoder`` is given and ``sparse_weights`` is not; the payload
      ``sparse_encoder_version`` key is then pinned to ``encoder.version``
      (``sparse.with_encoder_version``, doc 03 §3.11.2). Weights are stored
      in Qdrant's sparse wire format under the ``sparse`` named vector; empty
      weights (no in-vocabulary tokens) are omitted — Qdrant rejects empty
      sparse vectors.

    Returns a ``models.PointStruct`` (``id`` = ``point_id``, ``payload``,
    ``vector``); ``vector`` contains only the channels that could be produced
    (``{"dense": [...], "sparse": models.SparseVector(...)}``).
    """
    if dense_vector is None and embedder is not None:
        dense_vector = embedder.embed([unit.retrieval_text])[0]
    if sparse_weights is None and sparse_encoder is not None:
        sparse_weights = sparse_encoder.encode(unit.retrieval_text)

    payload = payload_for_unit(unit, **payload_kwargs)
    if sparse_encoder is not None:
        payload = with_encoder_version(payload, sparse_encoder)

    vector: dict[str, Any] = {}
    if dense_vector is not None:
        vector[DENSE_VECTOR_NAME] = dense_vector
    if sparse_weights:
        formatted = sparse_vector_dict(sparse_weights)
        vector[SPARSE_VECTOR_NAME] = models.SparseVector(
            indices=formatted["indices"], values=formatted["values"]
        )
    return models.PointStruct(id=point_id, payload=payload, vector=vector)


def provision_row_to_unit(row: LegalProvision) -> RetrievalUnit:
    """Map one persisted ``LegalProvision`` row to its ``RetrievalUnit``.

    The row already carries the final ``retrieval_text`` (context enrichment
    happened at extraction time, before persistence), so no enricher call is
    needed here — the unit is built from the row verbatim. This is the
    simplest faithful path for an indexer that consumes PostgreSQL rows rather
    than in-memory ``ExtractedLegalProvision`` objects. ``document_id`` is the
    row's ``document_version_id`` (the document-version UUID), matching what
    ``build_retrieval_units`` stores. ``short_point`` is not persisted, so it
    is recomputed with the extractor's rule (a POINT of <= 3 whitespace
    tokens; doc 03 §3.8.5).
    """
    return RetrievalUnit(
        unit_id=f"{row.provision_id}__v{row.version}",
        provision_id=row.provision_id,
        version=row.version,
        node_kind=row.node_kind,
        retrieval_text=row.retrieval_text,
        source_text=row.source_text,
        parent_context=row.parent_context,
        page_number=row.page_number,
        document_id=str(row.document_version_id),
        short_point=row.node_kind == "POINT" and len(row.source_text.split()) <= 3,
    )


def index_provision_units(
    client: QdrantClient,
    units: list[RetrievalUnit],
    *,
    point_ids: Mapping[str, str],
    embedder: EmbeddingProvider | None = None,
    sparse_encoder: SparseEncoder | None = None,
    collection: str | None = None,
    batch_size: int = 32,
    effective_from: str | None = None,
    effective_to: str | None = None,
    review_status: str = ACCEPTED_REVIEW_STATUS,
    unit_payloads: Mapping[str, Mapping[str, Any]] | None = None,
    **payload_kwargs: Any,
) -> IndexResult:
    """Upsert retrieval units into the provision collection (idempotent).

    Lower-level unit-based indexing used by :func:`index_accepted_provisions`
    and by the VNLRAG-45 reconciliation/repair path. ``RetrievalUnit`` does
    not carry the ``LegalProvision`` row id, so point ids come from
    ``point_ids`` — a ``unit_id -> point id`` mapping built with
    :func:`point_id_for` on the row UUIDs. The mapping is keyed by
    ``unit_id`` (``f"{provision_id}__v{version}"``), which is unique per
    provision version; a bare ``provision_id`` can span several versions in
    the authoritative version table and is therefore NOT a safe key. Units
    missing from ``point_ids`` are skipped and recorded in ``errors``.

    Idempotency: point ids are deterministic, so a re-run — or a resume after
    a killed worker — upserts the SAME points with replace semantics; Qdrant
    never accumulates duplicates. Units duplicated within one call collapse to
    a single point (the last build wins), matching upsert-replace semantics.

    Embedding is batched: each ``batch_size`` slice goes through
    ``embed_batch``/``encode_batch`` in one call. A failed batch is recorded
    in ``errors`` and skipped while the run continues; re-running retries it.
    With ``embedder=None``/``sparse_encoder=None`` the corresponding vector
    channel is omitted (payload-only points are still upserted).

    Payload metadata: ``review_status``/``effective_from``/``effective_to``
    flat keywords apply to every unit; ``payload_kwargs`` (the remaining
    ``payload_for_unit`` inputs) also apply to every unit and override the
    flat keywords; ``unit_payloads`` overrides per unit (keyed by
    ``unit_id``) and wins over both. ``collection`` defaults to
    ``PROVISION_ALIAS``; pass an explicit name for rebuild/test scenarios.
    """
    result = IndexResult()
    target = PROVISION_ALIAS if collection is None else collection
    # Collapse duplicate units: the point id is the unit's identity, so one
    # unit listed twice must produce ONE point (last build wins).
    unique_units = list({unit.unit_id: unit for unit in units}.values())

    for start in range(0, len(unique_units), batch_size):
        batch = unique_units[start : start + batch_size]
        texts = [unit.retrieval_text for unit in batch]
        try:
            dense_vectors = embedder.embed_batch(texts) if embedder is not None else None
            sparse_batch = (
                sparse_encoder.encode_batch(texts) if sparse_encoder is not None else None
            )
        except Exception as exc:
            result.errors.append(f"batch {start // batch_size}: embedding/encoding failed: {exc}")
            continue
        points: list[models.PointStruct] = []
        for index, unit in enumerate(batch):
            point_id = point_ids.get(unit.unit_id)
            if point_id is None:
                result.errors.append(f"no point id for unit {unit.unit_id}")
                continue
            merged = {
                "review_status": review_status,
                "effective_from": effective_from,
                "effective_to": effective_to,
            }
            merged.update(payload_kwargs)
            if unit_payloads is not None:
                merged.update(unit_payloads.get(unit.unit_id, {}))
            try:
                points.append(
                    build_point(
                        unit,
                        point_id=point_id,
                        embedder=embedder,
                        sparse_encoder=sparse_encoder,
                        dense_vector=dense_vectors[index] if dense_vectors is not None else None,
                        sparse_weights=sparse_batch[index] if sparse_batch is not None else None,
                        **merged,
                    )
                )
            except Exception as exc:
                result.errors.append(f"{unit.unit_id}: {exc}")
                continue
        if points:
            client.upsert(collection_name=target, points=points)
            result.indexed += len(points)
    return result


def _date_iso(value: date | None) -> str | None:
    """ISO-format a date column value for the payload (doc 03 §3.11.3/§3.11.5)."""
    return value.isoformat() if value is not None else None


def payload_metadata_from_row(row: LegalProvision) -> dict[str, Any]:
    """Map citation metadata from the authoritative document/version rows."""
    version_row = getattr(row, "document_version", None)
    document = getattr(version_row, "document", None)
    return {
        "document_id": getattr(document, "document_id", None),
        "document_number": getattr(document, "document_number", None),
        "document_type": getattr(document, "document_type", None),
        "document_title": getattr(document, "document_title", None),
        "document_status": getattr(document, "status", None),
        "document_version": getattr(version_row, "version", None),
    }


def index_accepted_provisions(
    client: QdrantClient,
    *,
    session: Session,
    embedder: EmbeddingProvider | None = None,
    sparse_encoder: SparseEncoder | None = None,
    effective_from_required: bool = True,
    batch_size: int = 32,
    collection: str | None = None,
    **payload_kwargs: Any,
) -> IndexResult:
    """Index every ACCEPTED provision from PostgreSQL into Qdrant.

    Selects ``LegalProvision`` rows with ``review_status == 'ACCEPTED'``
    (doc 00 §8.6, FR-09 — PENDING/NEEDS_REVIEW/REJECTED/DROPPED are never
    selected, so they never enter the index), maps each row to a retrieval
    unit via :func:`provision_row_to_unit` (the persisted row already carries
    the final enriched ``retrieval_text``), embeds + sparse-encodes it, and
    upserts one point per row into ``PROVISION_ALIAS`` (or ``collection``)
    with the deterministic point id :func:`point_id_for` ``(row.id)``.

    Payload inputs: per-row values (``effective_from``/``effective_to``,
    ``chapter``/``section``/``article``/``clause``/``point``/``heading``,
    ``content_hash``, ``review_status='ACCEPTED'``) come from the row;
    everything else (``parser_version``, ``legal_parser_version``,
    ``content_version``, ``relations``, ``vehicle_types``, document
    metadata, ...) is passed via ``payload_kwargs`` and applies to all rows —
    see :func:`build_point` for the full provenance map.

    ``effective_from_required=True`` (default): ACCEPTED rows without an
    ``effective_from`` are skipped and counted in
    ``skipped_no_effective_from``. This is a defensive guard — the PG check
    constraint ``legal_provisions_effective_from_accepted_check`` already
    guarantees ACCEPTED rows carry an interval — so out-of-band writes cannot
    leak interval-less points into the temporal index. Set ``False`` to index
    them anyway (documented escape hatch).

    Idempotent: re-running (or resuming after a killed worker) upserts the
    same deterministic point ids, replacing rather than duplicating points.
    """
    stmt = (
        select(LegalProvision)
        .where(LegalProvision.review_status == ACCEPTED_REVIEW_STATUS)
        .order_by(LegalProvision.id)
    )
    rows = list(session.scalars(stmt))

    units: list[RetrievalUnit] = []
    point_ids: dict[str, str] = {}
    unit_payloads: dict[str, dict[str, Any]] = {}
    skipped = 0
    for row in rows:
        if effective_from_required and row.effective_from is None:
            skipped += 1
            continue
        unit = provision_row_to_unit(row)
        units.append(unit)
        point_ids[unit.unit_id] = point_id_for(row.id)
        unit_payloads[unit.unit_id] = {
            **payload_metadata_from_row(row),
            "review_status": ACCEPTED_REVIEW_STATUS,
            "effective_from": _date_iso(row.effective_from),
            "effective_to": _date_iso(row.effective_to),
            "chapter": row.chapter,
            "section": row.section,
            "article": row.article,
            "clause": row.clause,
            "point": row.point,
            "heading": row.heading,
            "content_hash": row.content_hash,
        }

    result = index_provision_units(
        client,
        units,
        point_ids=point_ids,
        embedder=embedder,
        sparse_encoder=sparse_encoder,
        collection=collection,
        batch_size=batch_size,
        unit_payloads=unit_payloads,
        **payload_kwargs,
    )
    result.skipped_no_effective_from += skipped
    return result
