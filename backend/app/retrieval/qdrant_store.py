"""Qdrant legal-provision store: collection, payload, alias management (VNLRAG-40).

Implements the Qdrant schema of doc 03 §3.11:

- Versioned collection ``legal_provisions_v1`` with a named dense vector
  ``dense`` (768-dim, Cosine) and a named sparse vector ``sparse``
  (Qdrant BM25 tokenizer with the IDF modifier) — §3.11.1/§3.11.2.
- Payload per §3.11.3 (provision identity, hierarchy, temporal interval,
  review/legal status, relations, vehicle types, source/retrieval text) and
  payload indexes per §3.11.4.
- Alias ``legal_provisions_active`` -> the active versioned collection, with
  an atomic alias-switch rebuild flow (§3.11.7).

Qdrant is a **derived index**: PostgreSQL is authoritative and Qdrant is fully
rebuildable from it (ADR-005). Any schema change (embedding model, vector
dimension, sparse encoding, payload schema, chunking) is done by rebuild +
alias switch, never in place:

1. Create a new collection ``legal_provisions_v{n+1}`` with the same config.
2. Read all accepted provisions from PostgreSQL:
   ``SELECT ... FROM legal_provisions WHERE review_status = 'ACCEPTED'``
   (each row is one provision version; never read back from Qdrant).
3. Embed + upsert into the new collection.
4. Run retrieval regression on the dev set.
5. Switch ``legal_provisions_active`` to the new collection (``rebuild_alias``).
6. Keep the old collection for a grace period, then delete per policy.
"""

from __future__ import annotations

from typing import TypedDict

from qdrant_client import QdrantClient, models

from app.config import get_qdrant_settings
from app.ingestion.retrieval_units import RetrievalUnit

__all__ = [
    "DENSE_VECTOR_DISTANCE",
    "DENSE_VECTOR_NAME",
    "DENSE_VECTOR_SIZE",
    "PAYLOAD_INDEX_FIELDS",
    "PROVISION_ALIAS",
    "PROVISION_COLLECTION",
    "SPARSE_VECTOR_NAME",
    "build_collection_config",
    "build_sparse_vectors_config",
    "build_vectors_config",
    "ensure_qdrant_collection",
    "get_collection_info",
    "payload_for_unit",
    "rebuild_alias",
]

# --- Collection identity (doc 03 §3.11.1) -----------------------------------

#: Versioned collection carrying the provision points (rebuild = new version).
PROVISION_COLLECTION = "legal_provisions_v1"

#: Stable query-facing alias; rebuilds switch this alias, never touch it.
PROVISION_ALIAS = "legal_provisions_active"

#: Named dense vector (embedding; default Gemini Embedding 2 / Jina text-nano).
DENSE_VECTOR_NAME = "dense"
DENSE_VECTOR_SIZE = 768
DENSE_VECTOR_DISTANCE = models.Distance.COSINE

#: Named sparse vector (Qdrant BM25 tokenizer, IDF modifier).
SPARSE_VECTOR_NAME = "sparse"

#: Payload fields indexed as Qdrant keywords (doc 03 §3.11.4). Temporal
#: range semantics on ``effective_from``/``effective_to`` follow doc 03
#: §3.11.5: keyword match or backend post-filtering — values are ISO dates.
PAYLOAD_INDEX_FIELDS: tuple[str, ...] = (
    "provision_id",
    "document_id",
    "node_kind",
    "chapter",
    "section",
    "article",
    "clause",
    "point",
    "heading",
    "effective_from",
    "effective_to",
    "review_status",
    "vehicle_types",
)

#: Allowed keys of a bounded relation entry (doc 03 §3.11.3).
_RELATION_KEYS = ("relation_type", "target_provision_id")


# --- Collection config builders (unit-testable without a live Qdrant) --------


def build_vectors_config() -> dict[str, models.VectorParams]:
    """Return the named dense ``vectors_config`` mapping (doc 03 §3.11.1/2)."""
    return {
        DENSE_VECTOR_NAME: models.VectorParams(
            size=DENSE_VECTOR_SIZE, distance=DENSE_VECTOR_DISTANCE
        )
    }


def build_sparse_vectors_config() -> dict[str, models.SparseVectorParams]:
    """Return the named ``sparse_vectors_config`` mapping (doc 03 §3.11.2).

    BM25 with the IDF modifier (supported by qdrant-client >= 1.13 / Qdrant
    >= 1.12); the in-memory index keeps the default tokenizer-based sparse
    encoding used by the query pipeline (doc 03 §3.18.2).
    """
    return {
        SPARSE_VECTOR_NAME: models.SparseVectorParams(
            modifier=models.Modifier.IDF, index=models.SparseIndexParams(on_disk=False)
        )
    }


class CollectionConfig(TypedDict):
    """Kwargs for ``QdrantClient.create_collection`` of a provision collection."""

    vectors_config: dict[str, models.VectorParams]
    sparse_vectors_config: dict[str, models.SparseVectorParams]


def build_collection_config() -> CollectionConfig:
    """Return ``client.create_collection`` kwargs for a provision collection.

    Combined named dense + sparse vector config; versioned collections are
    created with this exact config so vectors are never mixed across
    embedding/sparse spaces (doc 03 §3.11.7).
    """
    return {
        "vectors_config": build_vectors_config(),
        "sparse_vectors_config": build_sparse_vectors_config(),
    }


# --- Payload mapping (doc 03 §3.11.3) ----------------------------------------


def payload_for_unit(
    unit: RetrievalUnit,
    *,
    review_status: str = "PENDING",
    effective_from: str | None = None,
    effective_to: str | None = None,
    parser_version: str | None = None,
    content_version: int = 1,
    relations: list[dict] | None = None,
    vehicle_types: list[str] | None = None,
    document_version_id: str | None = None,
    document_status: str | None = None,
    chapter: str | None = None,
    section: str | None = None,
    article: str | None = None,
    clause: str | None = None,
    point: str | None = None,
    heading: str | None = None,
    document_number: str | None = None,
    document_type: str | None = None,
    document_title: str | None = None,
    document_version: int | None = None,
    parser: str | None = None,
    legal_parser_version: str | None = None,
    sparse_encoder_version: str | None = None,
    content_hash: str | None = None,
) -> dict:
    """Map a ``RetrievalUnit`` plus ingestion/review metadata to the Qdrant payload.

    The payload emits the full doc 03 §3.11.3 key set with the doc's field
    names (``provision_version``, ``document_version``, ``document_status``,
    ``text``, ...) plus the ingest-only extras ``node_kind``/``heading``
    (hierarchy filters), ``content_version``, ``source_text`` (verbatim,
    citation display) and ``document_version_id`` (the document-version UUID).
    ``text`` is the searchable retrieval text; ``source_text`` is preserved
    verbatim for citation display (doc 03 §3.11.3 names the searchable field
    ``text``).

    ``RetrievalUnit`` does not carry hierarchy labels, DB-row metadata or
    document-level metadata, so those are accepted as keyword-only arguments
    (default ``None`` / unit values). ``page_number`` and ``parent_context``
    are mapped from the unit when present. ``document_version_id`` defaults to
    ``unit.document_id``, which ``build_retrieval_units`` populates from the
    provision's ``document_version_id`` (the document-version UUID);
    ``document_version`` is the document's version number (doc §3.11.3).

    ``relations`` is bounded metadata (doc 03 §3.11.3): each entry must be
    exactly ``{"relation_type", "target_provision_id"}`` with non-empty string
    values; anything else raises ``ValueError``. Only RESOLVED, ACCEPTED
    ``REFERS_TO``/``PENALTY_COMPANION`` relations should be passed by callers.
    """
    if relations is not None:
        for relation in relations:
            if not isinstance(relation, dict):
                raise ValueError(f"relation entries must be dicts, got {relation!r}")
            if set(relation) != set(_RELATION_KEYS):
                raise ValueError(
                    "relation entries must contain exactly "
                    f"{sorted(_RELATION_KEYS)}, got {sorted(relation)}"
                )
            if not relation["relation_type"] or not isinstance(relation["relation_type"], str):
                raise ValueError("relation_type must be a non-empty string")
            if not relation["target_provision_id"] or not isinstance(
                relation["target_provision_id"], str
            ):
                raise ValueError("target_provision_id must be a non-empty string")
    if vehicle_types is not None and (
        not isinstance(vehicle_types, list)
        or any(not isinstance(v, str) or not v for v in vehicle_types)
    ):
        raise ValueError("vehicle_types must be a list of non-empty strings")

    return {
        "provision_id": unit.provision_id,
        "provision_version": unit.version,
        "document_version_id": (
            unit.document_id if document_version_id is None else document_version_id
        ),
        "document_version": document_version,
        "document_number": document_number,
        "document_type": document_type,
        "document_title": document_title,
        "document_id": unit.document_id,
        "node_kind": unit.node_kind,
        "chapter": chapter,
        "section": section,
        "article": article,
        "clause": clause,
        "point": point,
        "heading": heading,
        "effective_from": effective_from,
        "effective_to": effective_to,
        "document_status": document_status,
        "review_status": review_status,
        "page_number": unit.page_number,
        "content_hash": content_hash,
        "parser": parser,
        "parser_version": parser_version,
        "legal_parser_version": legal_parser_version,
        "sparse_encoder_version": sparse_encoder_version,
        "text": unit.retrieval_text,
        "source_text": unit.source_text,
        "parent_context": unit.parent_context,
        "relations": [] if relations is None else relations,
        "vehicle_types": [] if vehicle_types is None else vehicle_types,
        "content_version": content_version,
    }


# --- Collection lifecycle ----------------------------------------------------


def _default_client() -> QdrantClient:
    settings = get_qdrant_settings()
    return QdrantClient(
        url=settings.url,
        api_key=settings.api_key or None,
        timeout=30,
    )


def _create_collection_if_missing(client: QdrantClient, collection_name: str) -> None:
    if not client.collection_exists(collection_name):
        client.create_collection(collection_name=collection_name, **build_collection_config())


def _ensure_payload_indexes(client: QdrantClient, collection_name: str) -> None:
    """Idempotently create the keyword payload indexes missing on the collection."""
    existing = set(client.get_collection(collection_name).payload_schema or {})
    for field in PAYLOAD_INDEX_FIELDS:
        if field not in existing:
            client.create_payload_index(
                collection_name=collection_name,
                field_name=field,
                field_schema=models.PayloadSchemaType.KEYWORD,
            )


def _alias_target(client: QdrantClient) -> str | None:
    """Return the collection name ``PROVISION_ALIAS`` points at, or ``None``."""
    for alias in client.get_aliases().aliases:
        if alias.alias_name == PROVISION_ALIAS:
            return alias.collection_name
    return None


def _ensure_alias(client: QdrantClient) -> None:
    """Create ``PROVISION_ALIAS`` -> ``PROVISION_COLLECTION`` when the alias is missing.

    If the alias already exists (e.g. pointing at a newer versioned collection
    after a rebuild), it is left untouched — the alias is the live query path.
    """
    if _alias_target(client) is None:
        client.update_collection_aliases(
            [
                models.CreateAliasOperation(
                    create_alias=models.CreateAlias(
                        collection_name=PROVISION_COLLECTION, alias_name=PROVISION_ALIAS
                    )
                )
            ]
        )


def ensure_qdrant_collection(client: QdrantClient | None = None) -> QdrantClient:
    """Idempotently ensure the provision collection, indexes and alias exist.

    Creates ``PROVISION_COLLECTION`` (named dense ``dense`` 768-dim Cosine +
    sparse ``sparse`` BM25/IDF) when missing, adds the ``PAYLOAD_INDEX_FIELDS``
    keyword indexes that are missing, and creates ``PROVISION_ALIAS`` ->
    collection when the alias is missing. Safe to re-run at any time.

    Returns the client used (the passed-in one, or a default built from
    ``QdrantSettings``: ``QDRANT_URL`` env, default ``http://localhost:6333``).
    """
    client = client if client is not None else _default_client()
    _create_collection_if_missing(client, PROVISION_COLLECTION)
    _ensure_payload_indexes(client, PROVISION_COLLECTION)
    _ensure_alias(client)
    return client


def rebuild_alias(client: QdrantClient, new_collection_name: str) -> str | None:
    """Point ``PROVISION_ALIAS`` at ``new_collection_name`` and return the old target.

    Returns the name of the collection ``PROVISION_ALIAS`` previously pointed
    at (the previous versioned collection, retained for the rollback/grace
    period), or ``None`` when there was no previous target (first bootstrap)
    or the alias already pointed at ``new_collection_name`` (no-op).

    Implements doc 03 §3.11.7 steps 5-6: the alias switch (delete alias from
    the old target + create alias on the new collection) is issued as a single
    atomic ``update_collection_aliases`` batch, so queries through the alias
    never observe a missing/partial state; the previous versioned collection
    is **not** deleted here — it is kept for a grace period so queries can
    roll back to it (step 6). The caller decides when to delete: keep the old
    collection until the new one is verified (e.g. retrieval regression), then
    ``client.delete_collection(old)`` per the grace-period cleanup policy.
    ``new_collection_name`` is created with the same config + payload indexes
    when it does not exist yet, so the full flow is: PostgreSQL is
    authoritative -> rebuild the new collection -> call this helper to
    activate it (returns the previous collection to retire later).

    No-op when the alias already points at ``new_collection_name``.
    """
    _create_collection_if_missing(client, new_collection_name)
    _ensure_payload_indexes(client, new_collection_name)

    current = _alias_target(client)
    if current == new_collection_name:
        return None
    operations: list[models.AliasOperations] = [
        models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=PROVISION_ALIAS)),
        models.CreateAliasOperation(
            create_alias=models.CreateAlias(
                collection_name=new_collection_name, alias_name=PROVISION_ALIAS
            )
        ),
    ]
    if current is None:  # no alias yet: only create it
        operations = operations[1:]
    client.update_collection_aliases(operations)
    return current


def get_collection_info(client: QdrantClient) -> dict:
    """Return serializable info for the active provision collection.

    Resolves ``PROVISION_ALIAS`` to the live versioned collection when the
    alias exists, otherwise reports ``PROVISION_COLLECTION`` (e.g. during the
    initial bootstrap). Includes config (vectors, sparse vectors), status and
    the created payload indexes.
    """
    name = _alias_target(client) or PROVISION_COLLECTION
    return client.get_collection(name).model_dump()
