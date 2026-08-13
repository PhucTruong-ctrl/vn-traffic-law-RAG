"""S3-compatible object storage layer (VNLRAG-134, doc 03 §3.12, FR-08).

Exposes the storage port (:class:`ObjectStoragePort`), the MinIO-backed
implementation (:class:`S3ObjectStorage`), the canonical bucket set
(:data:`BUCKETS`), the doc 03 §3.12.2 object-key convention helper
(:func:`object_key`) and the process-wide factory (:func:`get_object_storage`).
"""

from app.storage.object_storage import (
    BUCKETS,
    ObjectStoragePort,
    S3ObjectStorage,
    get_object_storage,
    object_key,
)

__all__ = [
    "BUCKETS",
    "ObjectStoragePort",
    "S3ObjectStorage",
    "get_object_storage",
    "object_key",
]
