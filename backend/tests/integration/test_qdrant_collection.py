"""Integration tests: Qdrant legal-provision collection (VNLRAG-40).

Guarded by Qdrant reachability (``QDRANT_URL`` env, default
``http://localhost:6333`` — the ``vnlaw-qdrant`` service in docker-compose);
the whole module is skipped when Qdrant is not reachable.

Every test runs against a UNIQUE scratch collection + alias
(``legal_provisions_v1_test_<uuid>`` / ``legal_provisions_active_test_<uuid>``,
monkeypatched over the module constants), so the real ``legal_provisions_v1``
and ``legal_provisions_active`` are never created, modified or deleted.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from qdrant_client import QdrantClient, models

from app.config import get_qdrant_settings
from app.retrieval import qdrant_store
from app.retrieval.qdrant_store import (
    DENSE_VECTOR_DISTANCE,
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
    PAYLOAD_INDEX_FIELDS,
    SPARSE_VECTOR_NAME,
    ensure_qdrant_collection,
    get_collection_info,
    rebuild_alias,
)

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def qdrant_client() -> Iterator[QdrantClient]:
    """Qdrant client for the module; skipped when the server is unreachable."""
    settings = get_qdrant_settings()
    kwargs: dict[str, object] = {"url": settings.url, "api_key": settings.api_key or None}
    probe = QdrantClient(timeout=3, **kwargs)
    try:
        probe.get_collections()
    except Exception:
        probe.close()
        pytest.skip(
            f"Qdrant not reachable at {settings.url} — skipping (start the "
            "vnlaw-qdrant docker-compose service to run these tests)"
        )
    probe.close()
    client = QdrantClient(timeout=30, **kwargs)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture()
def scratch(
    qdrant_client: QdrantClient, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[str, str]]:
    """Patch the module constants to unique scratch names; clean up afterwards."""
    suffix = uuid.uuid4().hex[:8]
    collection = f"legal_provisions_v1_test_{suffix}"
    alias = f"legal_provisions_active_test_{suffix}"
    monkeypatch.setattr(qdrant_store, "PROVISION_COLLECTION", collection)
    monkeypatch.setattr(qdrant_store, "PROVISION_ALIAS", alias)
    try:
        yield collection, alias
    finally:
        if any(a.alias_name == alias for a in qdrant_client.get_aliases().aliases):
            qdrant_client.update_collection_aliases(
                [models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))]
            )
        for info in qdrant_client.get_collections().collections:
            if info.name == collection or info.name.startswith(f"{collection}_"):
                qdrant_client.delete_collection(info.name)


def _alias_target(client: QdrantClient, alias: str) -> str | None:
    for description in client.get_aliases().aliases:
        if description.alias_name == alias:
            return description.collection_name
    return None


# ---------------------------------------------------------------------------
# ensure_qdrant_collection
# ---------------------------------------------------------------------------


def test_ensure_creates_collection_alias_and_indexes(
    qdrant_client: QdrantClient, scratch: tuple[str, str]
) -> None:
    collection, alias = scratch
    returned = ensure_qdrant_collection(qdrant_client)
    assert returned is qdrant_client
    assert qdrant_client.collection_exists(collection)

    info = qdrant_client.get_collection(collection)
    dense = info.config.params.vectors[DENSE_VECTOR_NAME]
    assert dense.size == DENSE_VECTOR_SIZE
    assert dense.distance == DENSE_VECTOR_DISTANCE
    sparse = info.config.params.sparse_vectors[SPARSE_VECTOR_NAME]
    assert sparse.modifier == models.Modifier.IDF
    assert set(info.payload_schema) >= set(PAYLOAD_INDEX_FIELDS)

    # Alias exists, points at the collection and resolves.
    assert _alias_target(qdrant_client, alias) == collection
    assert qdrant_client.get_collection(alias).status == info.status


def test_ensure_is_idempotent(qdrant_client: QdrantClient, scratch: tuple[str, str]) -> None:
    collection, alias = scratch
    ensure_qdrant_collection(qdrant_client)
    collections_before = {c.name for c in qdrant_client.get_collections().collections}

    ensure_qdrant_collection(qdrant_client)

    collections_after = {c.name for c in qdrant_client.get_collections().collections}
    assert collections_after == collections_before
    info = qdrant_client.get_collection(collection)
    assert set(info.payload_schema) >= set(PAYLOAD_INDEX_FIELDS)
    assert _alias_target(qdrant_client, alias) == collection


def test_get_collection_info_reports_active_collection(
    qdrant_client: QdrantClient, scratch: tuple[str, str]
) -> None:
    collection, _alias = scratch
    ensure_qdrant_collection(qdrant_client)
    info = get_collection_info(qdrant_client)
    dense = info["config"]["params"]["vectors"][DENSE_VECTOR_NAME]
    assert dense["size"] == DENSE_VECTOR_SIZE
    assert dense["distance"] == "Cosine"
    assert set(info["payload_schema"]) >= set(PAYLOAD_INDEX_FIELDS)


# ---------------------------------------------------------------------------
# rebuild_alias
# ---------------------------------------------------------------------------


def test_rebuild_alias_switches_and_retains_old_for_grace_period(
    qdrant_client: QdrantClient, scratch: tuple[str, str]
) -> None:
    collection, alias = scratch
    ensure_qdrant_collection(qdrant_client)
    new_collection = f"{collection}_v2"

    # §3.11.7 step 5-6: alias switches atomically; the old versioned
    # collection is NOT deleted — it is returned for the grace-period/rollback
    # cleanup policy, and the caller decides when to delete it.
    old_collection = rebuild_alias(qdrant_client, new_collection)

    assert old_collection == collection
    assert _alias_target(qdrant_client, alias) == new_collection
    assert qdrant_client.collection_exists(new_collection)
    # Old collection retained (rollback path) until the caller deletes it.
    assert qdrant_client.collection_exists(collection)
    # New collection carries the same config + payload indexes.
    new_info = qdrant_client.get_collection(new_collection)
    assert new_info.config.params.vectors[DENSE_VECTOR_NAME].size == DENSE_VECTOR_SIZE
    assert set(new_info.payload_schema) >= set(PAYLOAD_INDEX_FIELDS)
    # get_collection_info now reports the new active collection.
    active = get_collection_info(qdrant_client)
    assert active["status"] == new_info.status

    # Test cleanup: retire the old collection per the grace-period policy.
    qdrant_client.delete_collection(old_collection)
    assert not qdrant_client.collection_exists(collection)
    assert _alias_target(qdrant_client, alias) == new_collection


def test_rebuild_alias_creates_alias_when_missing(
    qdrant_client: QdrantClient, scratch: tuple[str, str]
) -> None:
    collection, alias = scratch
    # No collection / alias exists yet; rebuild straight into the new one.
    old_collection = rebuild_alias(qdrant_client, collection)
    assert old_collection is None
    assert _alias_target(qdrant_client, alias) == collection
    assert qdrant_client.collection_exists(collection)


def test_rebuild_alias_noop_when_already_active(
    qdrant_client: QdrantClient, scratch: tuple[str, str]
) -> None:
    collection, alias = scratch
    ensure_qdrant_collection(qdrant_client)

    old_collection = rebuild_alias(qdrant_client, collection)

    assert old_collection is None
    assert _alias_target(qdrant_client, alias) == collection
    assert qdrant_client.collection_exists(collection)
