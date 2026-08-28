"""Reference resolver actor — STAGED (VNLRAG-133, activated at W4 by VNLRAG-31).

The Legal Reference Resolver (doc 03 §3.14, FR-05) does not exist yet: it
ships with the W4 ticket VNLRAG-31.  Until then this actor MUST NOT resolve
references, MUST NOT advance the pipeline and MUST NOT index anything — doing
so would falsely complete a job whose cross-references are unresolved.

import dramatiq
from sqlalchemy import select

from app.config import get_queue_settings
from app.ingestion.reference_resolver import (
    extract_document_relations,
    resolve_references,
    review_item_for,
)
from app.persistence.models import ProvisionReference
from app.persistence.repositories.review_items import ReviewItemRepository
At W4 the VNLRAG-31 implementation replaces the short-circuit body with the
real resolution + ``finish_terminal(run, ...)`` / ``resolve_temporal_actor.send``
chain; the state-machine helpers in ``_state`` already support it.
"""

from __future__ import annotations

from typing import Any

import dramatiq

from app.config import get_queue_settings

from ._state import (
    STAGED_RESOLVERS_MESSAGE,
    STATUS_STAGED,
    JobNotFoundError,
    finish_terminal,
    load_run,
    new_session,
    stage_done,
)

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "resolve_refs",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["resolve_refs"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}


@dramatiq.actor(**_ACTOR_OPTIONS)
def resolve_refs_actor(job_id: str) -> None:
    """STAGED: halt the job in STAGED state until W4 activates VNLRAG-31."""
    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "RESOLVING_REFS"):
            return
        finish_terminal(
            run,
            STATUS_STAGED,
            stage="RESOLVING_REFS",
            error={
                "code": "STAGED_ACTOR",
                "actor": "resolve_refs_actor",
                "message": STAGED_RESOLVERS_MESSAGE,
            },
        )
        session.commit()
    finally:
        session.close()
    # Intentionally no next-stage enqueue: the pipeline stops here.


__all__ = ["resolve_refs_actor"]
