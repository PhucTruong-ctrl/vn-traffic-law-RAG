"""Embed actor — EMBEDDING stage (VNLRAG-133).

Embeds every ACCEPTED provision of the job's document through the configured
dense embedding adapter (doc 03 §3.13.2: ``embed_actor`` runs only after
review/gates accepted the provisions).  Embeddings are not persisted — Qdrant
is the embedding store — so this stage validates provider configuration and
warms the provider cache; the authoritative embed happens inside the index
actor's idempotent upsert (which re-embeds through the same adapter).

Only ``review_status == 'ACCEPTED'`` provisions are embedded; a job whose
provisions are all PENDING (temporal resolution staged until W4) embeds
nothing and still advances.  The stage marker commits BEFORE the provider
call, so a provider failure leaves the run at EMBEDDING and a re-run (or the
retry) re-embeds — never duplicating anything (no per-provision writes).

Test seam: ``_get_provider`` is monkeypatched by unit/integration tests.
"""

from __future__ import annotations

from typing import Any

import dramatiq

from app.config import get_embedding_settings, get_queue_settings
from app.retrieval.embedding import EmbeddingProvider, get_embedding_provider
from app.retrieval.indexing import provision_row_to_unit

from ._state import (
    JobNotFoundError,
    JobStateError,
    latest_document_version,
    list_provisions,
    load_run,
    new_session,
    set_stage,
    stage_done,
)

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "embed",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["embed"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}

ACCEPTED_REVIEW_STATUS = "ACCEPTED"


def _get_provider() -> EmbeddingProvider:
    """Configured dense embedding provider (test seam)."""
    return get_embedding_provider(get_embedding_settings())


@dramatiq.actor(**_ACTOR_OPTIONS)
def embed_actor(job_id: str) -> None:
    """Embed the job's ACCEPTED provisions (EMBEDDING)."""
    session = new_session()
    texts: list[str] = []
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "EMBEDDING"):
            return
        version = latest_document_version(session, run.document_id)
        if version is None:
            raise JobStateError(
                f"no document version for run {job_id!r}; extract must run first"
            )
        accepted = [
            row
            for row in list_provisions(session, version.id)
            if row.review_status == ACCEPTED_REVIEW_STATUS
        ]
        # Capture plain values while the rows are still bound (the session
        # expires them on commit; a detached row cannot be read afterwards).
        texts = [provision_row_to_unit(row).retrieval_text for row in accepted]
        set_stage(run, "EMBEDDING")
        session.commit()
    finally:
        session.close()

    if texts:
        provider = _get_provider()
        provider.embed_batch(texts)  # result intentionally discarded (cache warm)

    from .index import index_actor

    index_actor.send(job_id)


__all__ = ["ACCEPTED_REVIEW_STATUS", "embed_actor"]
