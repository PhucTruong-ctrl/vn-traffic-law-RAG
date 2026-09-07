"""Durable outbox dispatcher for post-transaction ingestion events."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import dramatiq
from sqlalchemy import select

from app.config import get_queue_settings
from app.persistence.models import OutboxEvent

from ._state import new_session
from .embed import embed_actor

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "outbox",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["embed"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}


@dramatiq.actor(**_ACTOR_OPTIONS)
def outbox_dispatcher_actor() -> None:
    """Publish one pending event, leaving it pending if publish fails.

    The row lock is held until the broker publish succeeds and delivery is
    committed, so a failed publish rolls back both the attempt and claim.
    """
    session = new_session()
    try:
        event = session.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.status == "PENDING")
            .order_by(OutboxEvent.created_at, OutboxEvent.id)
            .with_for_update(skip_locked=True)
        )
        if event is None:
            session.rollback()
            return
        event.attempts += 1
        if event.event_type == "RESUME_EMBED":
            job_id = event.payload.get("job_id")
            if not isinstance(job_id, str) or not job_id:
                raise ValueError("RESUME_EMBED event has no valid job_id")
            embed_actor.send(job_id)
        else:
            raise ValueError(f"unsupported outbox event type: {event.event_type!r}")
        event.status = "DELIVERED"
        event.delivered_at = datetime.now(UTC)
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


__all__ = ["outbox_dispatcher_actor"]
