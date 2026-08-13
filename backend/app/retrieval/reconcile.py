"""PostgreSQL-Qdrant index reconciliation (VNLRAG-45).

Qdrant is a **derived index** over the authoritative PostgreSQL store (doc 00
§8.6, ADR-005, doc 03 §3.11): when the two diverge, PostgreSQL wins. This
module compares the two stores point-by-point, reports the divergence, and
optionally repairs the derived index:

- :func:`compare_indexes` — pure set/dict diff (missing / extra / stale),
  fully testable without any service;
- :func:`reconcile_index` — compare-and-repair orchestration: read ACCEPTED
  provisions from PostgreSQL, scroll the live Qdrant collection, re-index
  missing and stale points from PostgreSQL via ``app.retrieval.indexing``
  ``index_provision_units`` (VNLRAG-44), and drop points that no longer exist
  in PostgreSQL. PostgreSQL wins on every conflict: stale points are
  re-indexed from PG rows, never deleted; PG rows are never touched;
- :func:`rebuild_index` — full collection replacement (doc 03 §3.11.7): build
  a new versioned collection from ALL accepted provisions, then switch
  ``PROVISION_ALIAS`` via ``qdrant_store.rebuild_alias``. The previous
  collection is RETAINED for the rollback/grace period — deleting it is the
  caller's policy (per §3.11.7 step 6), never done here;
- :func:`write_run_manifest` — record a reconcile run as an immutable JSON
  run manifest under ``data/evaluation/reconcile/<run_id>/run.json`` following
  the evaluation run-manifest conventions (``run.json`` shape used by Suite A
  and the corpus-qa tooling).

Only ``review_status = 'ACCEPTED'`` provisions are ever indexed or compared;
``DROPPED`` / ``REJECTED`` / ``NEEDS_REVIEW`` / ``PENDING`` rows are outside
the index boundary (VNLRAG-44 contract). Like ``index_accepted_provisions``,
``reconcile_index``/``rebuild_index`` require ``effective_from`` by default:
provisions without an effective interval are not part of the PG side of the
comparison (doc 03 §3.11.5/§3.13; §8.6 temporal validity) unless
``effective_from_required=False``.
"""

from __future__ import annotations

import json
import logging
import re
import subprocess
import uuid
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field
from qdrant_client import QdrantClient, models
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.retrieval_units import RetrievalUnit
from app.persistence.models import (
    DocumentVersion,
    LegalDocument,
    LegalProvision,
)
from app.retrieval.qdrant_store import (
    PAYLOAD_INDEX_FIELDS,
    PROVISION_ALIAS,
    PROVISION_COLLECTION,
    build_collection_config,
    rebuild_alias,
)

logger = logging.getLogger(__name__)

__all__ = [
    "ACCEPTED_REVIEW_STATUS",
    "CONTENT_HASH_PAYLOAD_KEY",
    "ReconciliationReport",
    "RepairCounts",
    "accepted_provisions",
    "compare_indexes",
    "make_run_id",
    "provision_to_unit",
    "rebuild_index",
    "reconcile_index",
    "resolve_collection",
    "scroll_point_ids_and_content",
    "unit_payload_for_provision",
    "write_run_manifest",
]

#: The only review status that is indexable / comparable (doc 03 §3.13; the
#: VNLRAG-44 contract) — DROPPED/REJECTED/NEEDS_REVIEW/PENDING never are.
ACCEPTED_REVIEW_STATUS = "ACCEPTED"

#: Payload key holding the provision content hash used for stale detection
#: (doc 03 §3.11.3).
CONTENT_HASH_PAYLOAD_KEY = "content_hash"

#: Default run-manifest directory: ``data/evaluation/reconcile/`` (gitignored
#: run-artifact tree, same convention as the evaluation runs).
DEFAULT_OUT_DIR = Path(__file__).resolve().parents[3] / "data" / "evaluation" / "reconcile"

#: Scroll page size while reading Qdrant point ids + payloads.
_SCROLL_PAGE_SIZE = 1024

#: Versioned-collection name pattern (``legal_provisions_v{n}``, doc 03 §3.11.7).
_VERSIONED_COLLECTION_RE = re.compile(r"^(?P<prefix>.+)_v(?P<version>\d+)$")


class RepairCounts(BaseModel):
    """How many divergences a repair pass actually fixed."""

    model_config = ConfigDict(extra="forbid")

    missing_reindexed: int = 0
    stale_reindexed: int = 0
    extra_dropped: int = 0


class ReconciliationReport(BaseModel):
    """Point-level divergence between PostgreSQL and Qdrant.

    ``missing`` are PG point ids absent from Qdrant, ``extra`` are Qdrant
    point ids with no PG row, ``stale`` are point ids present in both whose
    payload ``content_hash`` differs from the PG row (PG wins: re-indexed,
    never deleted). Lists are sorted for deterministic output; ``repaired``
    counts what a repair pass changed (all zero for ``check``/``dry_run``).
    """

    model_config = ConfigDict(extra="forbid")

    missing: list[str] = Field(default_factory=list)
    stale: list[str] = Field(default_factory=list)
    extra: list[str] = Field(default_factory=list)
    total_pg: int = 0
    total_qdrant: int = 0
    repaired: RepairCounts = Field(default_factory=RepairCounts)

    @property
    def diverged(self) -> bool:
        """True when any point-level divergence exists (missing/stale/extra)."""
        return bool(self.missing or self.stale or self.extra)


# ---------------------------------------------------------------------------
# Pure diff logic (no services required)
# ---------------------------------------------------------------------------


def compare_indexes(
    client: QdrantClient,
    *,
    pg_point_ids: set[str],
    qdrant_point_ids: set[str] | None = None,
    fetch_qdrant_ids: Callable[[QdrantClient], set[str]] | None = None,
    pg_content: dict[str, str] | None = None,
    qdrant_content: dict[str, str] | None = None,
) -> ReconciliationReport:
    """Diff the PG and Qdrant point-id universes (pure, no I/O besides the
    optional ``fetch_qdrant_ids`` callable).

    - ``missing`` = ``pg_point_ids - qdrant_point_ids``;
    - ``extra`` = ``qdrant_point_ids - pg_point_ids``;
    - ``stale`` = point ids in BOTH sets whose ``pg_content`` hash differs
      from the ``qdrant_content`` hash.

    ``qdrant_point_ids`` may be omitted when ``fetch_qdrant_ids`` is given
    (then ``fetch_qdrant_ids(client)`` supplies it). Stale detection requires
    both ``pg_content`` (point id → PG ``content_hash``) and ``qdrant_content``
    (point id → payload ``content_hash``): when either is ``None`` no point can
    be compared and ``stale`` stays empty. An intersection id missing from
    ``qdrant_content`` (payload without ``content_hash``) compares as stale —
    the payload cannot be verified, and PostgreSQL wins. ``client`` is unused
    unless ``fetch_qdrant_ids`` is provided; it is kept in the signature so
    callers can wire a live client without touching the pure logic.
    """
    if qdrant_point_ids is None:
        if fetch_qdrant_ids is None:
            raise ValueError(
                "compare_indexes needs qdrant_point_ids or a fetch_qdrant_ids callable"
            )
        qdrant_point_ids = fetch_qdrant_ids(client)

    missing = sorted(pg_point_ids - qdrant_point_ids)
    extra = sorted(qdrant_point_ids - pg_point_ids)
    stale: list[str] = []
    if pg_content is not None and qdrant_content is not None:
        stale = sorted(
            point_id
            for point_id in pg_point_ids & qdrant_point_ids
            if pg_content.get(point_id) != qdrant_content.get(point_id)
        )

    return ReconciliationReport(
        missing=missing,
        stale=stale,
        extra=extra,
        total_pg=len(pg_point_ids),
        total_qdrant=len(qdrant_point_ids),
        repaired=RepairCounts(),
    )


# ---------------------------------------------------------------------------
# PostgreSQL side (authoritative)
# ---------------------------------------------------------------------------


def _accepted_provisions_stmt():
    """SELECT for ACCEPTED provisions in deterministic ``(created_at, id)`` order.

    The index boundary is enforced HERE at selection: non-ACCEPTED rows
    (DROPPED/REJECTED/NEEDS_REVIEW/PENDING) are never returned and therefore
    never compared or indexed (doc 03 §3.13; VNLRAG-44 contract).
    """
    return (
        select(LegalProvision)
        .where(LegalProvision.review_status == ACCEPTED_REVIEW_STATUS)
        .order_by(LegalProvision.created_at, LegalProvision.id)
    )


def accepted_provisions(session: Session) -> list[LegalProvision]:
    """All ``review_status = 'ACCEPTED'`` provision rows, deterministic order.

    Repeated runs produce identical point-id sets and identical repair batches.
    """
    return list(session.scalars(_accepted_provisions_stmt()))


def provision_to_unit(provision: LegalProvision) -> RetrievalUnit:
    """Build the :class:`RetrievalUnit` for one provision row.

    ``unit_id`` is ``f"{provision_id}__v{version}"``, ``retrieval_text`` /
    ``source_text`` / ``parent_context`` are copied verbatim from the row
    (never regenerated — the enricher output is already stored, VNLRAG-132),
    and ``short_point`` follows the extractor convention: a POINT whose
    source text is at most 3 whitespace tokens.
    """
    return RetrievalUnit(
        unit_id=f"{provision.provision_id}__v{provision.version}",
        provision_id=provision.provision_id,
        version=provision.version,
        node_kind=provision.node_kind,
        retrieval_text=provision.retrieval_text,
        source_text=provision.source_text,
        parent_context=provision.parent_context,
        page_number=provision.page_number,
        document_id=str(provision.document_version_id),
        short_point=provision.node_kind == "POINT" and len(provision.source_text.split()) <= 3,
    )


def _iso_date(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _document_metadata(
    session: Session, document_version_ids: set[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """Document-level payload fields per ``document_version_id`` (doc 03 §3.11.3).

    Loads the ``document_versions`` + ``legal_documents`` rows behind the given
    provision rows so repaired points carry the same document metadata as a
    fresh full index. Unknown ids are simply absent from the result.
    """
    if not document_version_ids:
        return {}
    stmt = (
        select(DocumentVersion, LegalDocument)
        .join(LegalDocument, LegalDocument.document_id == DocumentVersion.document_id)
        .where(DocumentVersion.id.in_(document_version_ids))
    )
    out: dict[uuid.UUID, dict[str, Any]] = {}
    for version, document in session.execute(stmt):
        out[version.id] = {
            "document_id": document.document_id,
            "document_number": document.document_number,
            "document_type": document.document_type,
            "document_title": document.document_title,
            "document_status": document.status,
            "document_version": version.version,
        }
    return out


def unit_payload_for_provision(
    provision: LegalProvision, document_metadata: Mapping[uuid.UUID, dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Per-unit payload fields for one provision row (doc 03 §3.11.3 key set).

    Returns the payload fields that differ per row — identity, hierarchy,
    interval, review status and content hash — merged with the document-level
    metadata from :func:`_document_metadata` when available. These are passed
    to ``index_provision_units`` as ``unit_payloads`` (VNLRAG-44 contract).
    """
    payload: dict[str, Any] = {
        "content_hash": provision.content_hash,
        "review_status": ACCEPTED_REVIEW_STATUS,
        "effective_from": _iso_date(provision.effective_from),
        "effective_to": _iso_date(provision.effective_to),
        "chapter": provision.chapter,
        "section": provision.section,
        "article": provision.article,
        "clause": provision.clause,
        "point": provision.point,
        "heading": provision.heading,
        "document_version_id": str(provision.document_version_id),
    }
    if document_metadata:
        payload.update(document_metadata.get(provision.document_version_id, {}))
    return payload


def _select_provisions(
    session: Session,
    *,
    effective_from_required: bool,
) -> list[LegalProvision]:
    """ACCEPTED provisions, dropping rows without ``effective_from`` when
    ``effective_from_required`` (those are not indexable, doc 03 §3.11.5)."""
    provisions = accepted_provisions(session)
    if effective_from_required:
        provisions = [p for p in provisions if p.effective_from is not None]
    return provisions


# ---------------------------------------------------------------------------
# Qdrant side (derived index)
# ---------------------------------------------------------------------------


def _alias_target(client: QdrantClient) -> str | None:
    for alias in client.get_aliases().aliases:
        if alias.alias_name == PROVISION_ALIAS:
            return alias.collection_name
    return None


def resolve_collection(client: QdrantClient, *, collection: str | None = None) -> str:
    """Resolve the collection to compare/repair against.

    Precedence: explicit ``collection`` override > ``PROVISION_ALIAS`` target
    > ``PROVISION_COLLECTION`` (bootstrap before the alias exists).
    """
    if collection is not None:
        return collection
    return _alias_target(client) or PROVISION_COLLECTION


def scroll_point_ids_and_content(
    client: QdrantClient, *, collection: str
) -> tuple[set[str], dict[str, str]]:
    """Scroll ``collection`` and return ``(point ids, {point id: content_hash})``.

    A collection that does not exist yet (derived index not bootstrapped)
    yields an empty Qdrant side — every PG provision then reports as missing,
    which is exactly the fresh-bootstrap state. Points whose payload lacks a
    non-empty ``content_hash`` contribute their id to the id set but not to
    the content map — they are later classified stale by
    :func:`compare_indexes` (unverifiable payload, PostgreSQL wins).
    """
    if not client.collection_exists(collection):
        logger.info("collection %s does not exist; Qdrant side treated as empty", collection)
        return set(), {}
    point_ids: set[str] = set()
    content: dict[str, str] = {}
    offset: Any = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection,
            with_vectors=False,
            with_payload=True,
            limit=_SCROLL_PAGE_SIZE,
            offset=offset,
        )
        for point in points:
            point_ids.add(str(point.id))
            payload = point.payload if isinstance(point.payload, dict) else {}
            content_hash = payload.get(CONTENT_HASH_PAYLOAD_KEY)
            if isinstance(content_hash, str) and content_hash:
                content[str(point.id)] = content_hash
        if next_offset is None:
            break
        offset = next_offset
    return point_ids, content


# ---------------------------------------------------------------------------
# VNLRAG-44 wiring (lazy, so this module stays importable pre-merge)
# ---------------------------------------------------------------------------


def _resolve_index_provision_units() -> Callable[..., Any]:
    """Lazily import ``index_provision_units`` from ``app.retrieval.indexing``.

    Kept lazy because the indexing module is developed in parallel (VNLRAG-44)
    and may not exist yet; callers (CLI, tests) may also inject their own
    implementation.
    """
    try:
        from app.retrieval.indexing import index_provision_units
    except ImportError as exc:
        raise RuntimeError(
            "app.retrieval.indexing.index_provision_units is not available (VNLRAG-44 "
            "not merged); pass an index_provision_units callable explicitly"
        ) from exc
    return index_provision_units


def _resolve_point_id_for() -> Callable[[uuid.UUID], str]:
    """Lazily import ``point_id_for``; identical deterministic fallback.

    The deterministic point id is the provision-version row UUID
    (``str(LegalProvision.id)``) — the VNLRAG-44 contract. The fallback
    reproduces it exactly so this module works standalone during parallel
    development; once VNLRAG-44 lands the real implementation is used.
    """
    try:
        from app.retrieval.indexing import point_id_for
    except ImportError:

        def _fallback_point_id(row_id: uuid.UUID) -> str:
            return str(row_id)

        return _fallback_point_id

    return point_id_for


def _prepare_units(
    provisions: list[LegalProvision],
    point_id_for: Callable[[uuid.UUID], str],
    document_metadata: Mapping[uuid.UUID, dict[str, Any]],
) -> tuple[list[RetrievalUnit], dict[str, str], dict[str, dict[str, Any]], dict[str, str]]:
    """Build ``(units, unit_point_ids, unit_payloads, point_id_to_unit_id)``.

    ``unit_point_ids`` maps unit_id → deterministic point id and
    ``unit_payloads`` maps unit_id → per-row payload fields — exactly the two
    mappings ``index_provision_units`` consumes (VNLRAG-44 contract).
    """
    units: list[RetrievalUnit] = []
    unit_point_ids: dict[str, str] = {}
    unit_payloads: dict[str, dict[str, Any]] = {}
    point_id_to_unit_id: dict[str, str] = {}
    for provision in provisions:
        unit = provision_to_unit(provision)
        point_id = point_id_for(provision.id)
        units.append(unit)
        unit_point_ids[unit.unit_id] = point_id
        unit_payloads[unit.unit_id] = unit_payload_for_provision(provision, document_metadata)
        point_id_to_unit_id[point_id] = unit.unit_id
    return units, unit_point_ids, unit_payloads, point_id_to_unit_id


def _reindex_units(
    index_provision_units: Callable[..., Any],
    client: QdrantClient,
    units: list[RetrievalUnit],
    *,
    unit_point_ids: Mapping[str, str],
    unit_payloads: Mapping[str, Mapping[str, Any]],
    collection: str | None,
    batch_size: int,
) -> int:
    """Call ``index_provision_units`` for one repair batch; return indexed count."""
    if not units:
        return 0
    result = index_provision_units(
        client,
        units,
        point_ids={unit.unit_id: unit_point_ids[unit.unit_id] for unit in units},
        unit_payloads={unit.unit_id: unit_payloads[unit.unit_id] for unit in units},
        collection=collection,
        batch_size=batch_size,
    )
    indexed = int(getattr(result, "indexed", len(units)))
    for error in getattr(result, "errors", []) or []:
        logger.warning("index_provision_units error during reconcile: %s", error)
    if indexed != len(units):
        logger.warning(
            "index_provision_units indexed %d of %d units in a reconcile batch",
            indexed,
            len(units),
        )
    return indexed


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def reconcile_index(
    client: QdrantClient,
    *,
    session: Session,
    index_provision_units: Callable[..., Any] | None = None,
    point_id_for: Callable[[uuid.UUID], str] | None = None,
    collection: str | None = None,
    effective_from_required: bool = True,
    batch_size: int = 32,
    dry_run: bool = False,
) -> ReconciliationReport:
    """Compare PostgreSQL (authoritative) with the live Qdrant collection and
    repair the divergence — PostgreSQL wins on every conflict.

    Steps:

    1. read ACCEPTED provisions from ``session`` (``review_status =
       'ACCEPTED'`` only; rows without ``effective_from`` excluded when
       ``effective_from_required``, matching the indexing boundary) and derive
       the PG point-id set via ``point_id_for`` (deterministic point id =
       provision row UUID);
    2. scroll ``collection`` (``resolve_collection``: override > alias target
       > ``PROVISION_COLLECTION``) for point ids + payload ``content_hash``;
    3. ``compare_indexes`` — missing / stale / extra;
    4. unless ``dry_run``: re-index missing and stale units from PG via
       ``index_provision_units`` (lazily imported from
       ``app.retrieval.indexing`` unless injected) and drop extra points with
       ``client.delete``. Stale points are RE-INDEXED from PG, never deleted;
       PG rows are never modified.

    Returns the :class:`ReconciliationReport`; ``repaired`` counts what was
    fixed (zeros for ``dry_run``). The indexer is resolved lazily only when a
    repair will actually run, so ``check``/``dry_run`` work even before the
    VNLRAG-44 indexing module lands.
    """
    point_id = _resolve_point_id_for() if point_id_for is None else point_id_for

    provisions = _select_provisions(session, effective_from_required=effective_from_required)
    document_metadata = _document_metadata(session, {p.document_version_id for p in provisions})
    units, unit_point_ids, unit_payloads, point_id_to_unit_id = _prepare_units(
        provisions, point_id, document_metadata
    )

    pg_point_ids = {point_id(p.id) for p in provisions}
    pg_content = {point_id(p.id): p.content_hash for p in provisions}
    qdrant_point_ids, qdrant_content = scroll_point_ids_and_content(
        client, collection=resolve_collection(client, collection=collection)
    )
    target_collection = resolve_collection(client, collection=collection)

    report = compare_indexes(
        client,
        pg_point_ids=pg_point_ids,
        qdrant_point_ids=qdrant_point_ids,
        pg_content=pg_content,
        qdrant_content=qdrant_content,
    )

    if dry_run or not report.diverged:
        return report

    indexer = (
        _resolve_index_provision_units() if index_provision_units is None else index_provision_units
    )

    unit_by_unit_id = {unit.unit_id: unit for unit in units}
    missing_units = [
        unit_by_unit_id[point_id_to_unit_id[pid]]
        for pid in report.missing
        if pid in point_id_to_unit_id
    ]
    stale_units = [
        unit_by_unit_id[point_id_to_unit_id[pid]]
        for pid in report.stale
        if pid in point_id_to_unit_id
    ]

    missing_reindexed = _reindex_units(
        indexer,
        client,
        missing_units,
        unit_point_ids=unit_point_ids,
        unit_payloads=unit_payloads,
        collection=target_collection,
        batch_size=batch_size,
    )
    stale_reindexed = _reindex_units(
        indexer,
        client,
        stale_units,
        unit_point_ids=unit_point_ids,
        unit_payloads=unit_payloads,
        collection=target_collection,
        batch_size=batch_size,
    )
    extra_dropped = 0
    if report.extra:
        # ``report.extra`` is ``list[str]`` (point ids as strings); Qdrant's
        # selector wants ``list[ExtendedPointId]`` — invariant, so cast.
        client.delete(
            collection_name=target_collection,
            points_selector=models.PointIdsList(
                points=cast(list[models.ExtendedPointId], report.extra)
            ),
        )
        extra_dropped = len(report.extra)

    report.repaired = RepairCounts(
        missing_reindexed=missing_reindexed,
        stale_reindexed=stale_reindexed,
        extra_dropped=extra_dropped,
    )
    return report


def next_collection_name(client: QdrantClient) -> str:
    """Next versioned collection name: ``legal_provisions_v{n+1}`` (doc 03 §3.11.7).

    Scans existing collections matching the versioned pattern and increments
    the highest version; with none present returns the initial
    ``PROVISION_COLLECTION`` name. Scratch/test collections (e.g.
    ``legal_provisions_v1_test_...``) never match the strict pattern.
    """
    prefix = PROVISION_COLLECTION.rsplit("_v", 1)[0]
    highest = 0
    for info in client.get_collections().collections:
        match = _VERSIONED_COLLECTION_RE.match(info.name)
        if match and match.group("prefix") == prefix:
            highest = max(highest, int(match.group("version")))
    return f"{prefix}_v{highest + 1}"


def _ensure_named_collection(client: QdrantClient, collection_name: str) -> None:
    """Create ``collection_name`` with the provision config + payload indexes
    when missing (mirrors ``qdrant_store`` lifecycle using its public builders).
    """
    if not client.collection_exists(collection_name):
        client.create_collection(collection_name=collection_name, **build_collection_config())
    existing = set(client.get_collection(collection_name).payload_schema or {})
    for field in PAYLOAD_INDEX_FIELDS:
        if field not in existing:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )


def rebuild_index(
    client: QdrantClient,
    *,
    session: Session,
    index_provision_units: Callable[..., Any] | None = None,
    point_id_for: Callable[[uuid.UUID], str] | None = None,
    collection_name: str | None = None,
    effective_from_required: bool = True,
    batch_size: int = 32,
    dry_run: bool = False,
) -> str | None:
    """Full collection replacement (doc 03 §3.11.7).

    1. create a new versioned collection (``collection_name`` override, else
       ``next_collection_name``) with the provision config + payload indexes;
    2. index ALL accepted provisions into it via ``index_provision_units``
       (injected or lazily imported from ``app.retrieval.indexing``);
    3. switch ``PROVISION_ALIAS`` via ``qdrant_store.rebuild_alias`` and
       return the OLD collection name.

    The old collection is RETAINED for the rollback/grace period (§3.11.7
    step 6): deleting it is the caller's policy (e.g. after retrieval
    regression), never done here. Returns ``None`` when the alias already
    pointed at the new collection (idempotent re-run) or on ``dry_run``.
    """
    point_id = _resolve_point_id_for() if point_id_for is None else point_id_for

    provisions = _select_provisions(session, effective_from_required=effective_from_required)
    document_metadata = _document_metadata(session, {p.document_version_id for p in provisions})
    units, unit_point_ids, unit_payloads, _ = _prepare_units(
        provisions, point_id, document_metadata
    )

    new_name = collection_name or next_collection_name(client)
    logger.info("rebuild: indexing %d accepted provisions into %s", len(units), new_name)
    if dry_run:
        return None

    indexer = (
        _resolve_index_provision_units() if index_provision_units is None else index_provision_units
    )
    _ensure_named_collection(client, new_name)
    indexed = _reindex_units(
        indexer,
        client,
        units,
        unit_point_ids=unit_point_ids,
        unit_payloads=unit_payloads,
        collection=new_name,
        batch_size=batch_size,
    )
    if indexed != len(units):
        logger.warning(
            "rebuild indexed %d of %d units into %s; verify before retiring the old collection",
            indexed,
            len(units),
            new_name,
        )
    return rebuild_alias(client, new_name)


# ---------------------------------------------------------------------------
# Run recording (data/evaluation/reconcile/<run_id>/run.json)
# ---------------------------------------------------------------------------


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    return result.stdout.strip() or "unknown"


def make_run_id() -> str:
    """``run-YYYYMMDD-HHMMSS-<6 hex>`` — same scheme as the evaluation runs."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"run-{stamp}-{uuid.uuid4().hex[:6]}"


def write_run_manifest(
    report: ReconciliationReport,
    *,
    run_id: str,
    started_at: datetime,
    finished_at: datetime,
    out_dir: Path | None = None,
    config: dict[str, Any] | None = None,
) -> Path:
    """Write the immutable run manifest ``<out_dir>/<run_id>/run.json``.

    Follows the evaluation run-manifest conventions (Suite A ``run.json``:
    ``run_id`` / ``git_commit`` / ``status`` / ``created_at`` /
    ``completed_at`` / ``config`` / ``report`` / ``error``, JSON with sorted
    keys). ``config`` optionally records command context (e.g. the subcommand
    and collection used). The run directory is created with ``exist_ok=False``
    — reusing an existing ``run_id`` raises ``FileExistsError`` (runs are
    immutable, never rewritten). Default ``out_dir`` is
    ``data/evaluation/reconcile/`` (gitignored, matching the evaluation
    run-artifact tree). Returns the ``run.json`` path.
    """
    resolved_dir = DEFAULT_OUT_DIR if out_dir is None else out_dir
    run_root = resolved_dir / run_id
    run_root.mkdir(parents=True, exist_ok=False)
    manifest = {
        "run_id": run_id,
        "git_commit": _git_commit(),
        "status": "COMPLETED",
        "created_at": started_at.isoformat(),
        "completed_at": finished_at.isoformat(),
        "suite": "reconcile",
        "tool": "reconcile_index",
        "config": {} if config is None else config,
        "report": report.model_dump(mode="json"),
        "error": None,
    }
    path = run_root / "run.json"
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path
