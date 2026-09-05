"""Repository layer over the v2 persistence models (VNLRAG-39).

Repositories wrap ``app.persistence.models`` with the CRUD and temporal /
relation queries used by ingestion, retrieval and verification (doc 03
§3.10.5/§3.15.2, doc 05 W3-W4). Write methods flush to the injected session;
the caller owns the transaction (commit/rollback).
"""

from .documents import DocumentRepository
from .hashing import content_hash, manifest_hash
from .provisions import ProvisionRepository
from .relations import RelatedProvision, RelationRepository
from .review_items import ReviewItemNotFoundError, ReviewItemRepository
from .temporal import TemporalRepository

__all__ = [
    "DocumentRepository",
    "ProvisionRepository",
    "RelatedProvision",
    "RelationRepository",
    "ReviewItemNotFoundError",
    "ReviewItemRepository",
    "TemporalRepository",
    "content_hash",
    "manifest_hash",
]
