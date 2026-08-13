"""Temporal resolver actor — STAGED (VNLRAG-133, activated at W4 by VNLRAG-136).

The Temporal and Amendment Resolver (doc 03 §3.15, FR-06) does not exist yet:
it ships with the W4 ticket VNLRAG-136.  Until then this actor MUST NOT
compute effective intervals, MUST NOT advance the pipeline and MUST NOT index
anything — ACCEPTED provisions legally require an ``effective_from`` (DB check
``legal_provisions_effective_from_accepted_check``), so completing a job
without temporal resolution would be factually wrong.

Staging contract
----------------
Identical to :mod:`app.ingestion.actors.resolve_refs`: the job is moved to the
terminal ``STAGED`` state (``current_stage=RESOLVING_TEMPORAL``) and no
next-step message is sent.  This actor is unreachable in the current chain
(because ``resolve_refs_actor`` already halts the job), but it is declared
with the same contract so the full documented actor list (doc 03 §3.13.2)
exists and the W4 swap-in is a drop-in replacement.
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
    "queue_name": "resolve_temporal",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["resolve_temporal"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}


@dramatiq.actor(**_ACTOR_OPTIONS)
def resolve_temporal_actor(job_id: str) -> None:
    """STAGED: halt the job in STAGED state until W4 activates VNLRAG-136."""
    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "RESOLVING_TEMPORAL"):
            return
        finish_terminal(
            run,
            STATUS_STAGED,
            stage="RESOLVING_TEMPORAL",
            error={
                "code": "STAGED_ACTOR",
                "actor": "resolve_temporal_actor",
                "message": STAGED_RESOLVERS_MESSAGE,
            },
        )
        session.commit()
    finally:
        session.close()
    # Intentionally no next-stage enqueue: the pipeline stops here.


__all__ = ["resolve_temporal_actor"]
