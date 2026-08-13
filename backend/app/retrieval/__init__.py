"""Retrieval index layer: Qdrant legal-provision store (VNLRAG-40).

Qdrant is a derived index over the authoritative PostgreSQL store (doc 03
§3.11, ADR-005); this package owns the collection contract, payload mapping
and alias-based rebuild flow used by the embedding/indexing pipeline and the
query pipeline.
"""

from app.retrieval.qdrant_store import (
    build_collection_config,
    build_sparse_vectors_config,
    build_vectors_config,
    ensure_qdrant_collection,
    get_collection_info,
    payload_for_unit,
    rebuild_alias,
)

__all__ = [
    "build_collection_config",
    "build_sparse_vectors_config",
    "build_vectors_config",
    "ensure_qdrant_collection",
    "get_collection_info",
    "payload_for_unit",
    "rebuild_alias",
]
