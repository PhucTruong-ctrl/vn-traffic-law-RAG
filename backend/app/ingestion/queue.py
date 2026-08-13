"""Redis + Dramatiq ingestion queue (VNLRAG-133).

Implements FR-07 / ADR-011 / doc 03 §3.13: background ingestion over a Redis
broker with a bounded retry policy, per-actor time limits and a named
dead-letter queue.  The public entry point is :func:`enqueue_parse` — the
upload API (VNLRAG-135) calls exactly this function and nothing else.

Broker wiring
-------------
``get_broker()`` builds a :class:`dramatiq.brokers.redis.RedisBroker` with an
explicit middleware stack (dramatiq 2.2.0 does not include a
``DeadLetterMiddleware``, so this module implements one):

* :class:`DeadLetterMiddleware` — forwards every permanently-failed message
  (retries exhausted) to the configured DLQ queue (``default.DLQ``, doc 03
  §3.13.6).  Registered BEFORE ``Retries`` so that, in dramatiq's reversed
  after-process chain, it observes the final failure decision.
* :class:`dramatiq.middleware.Retries` — bounded ``max_retries`` (default 3)
  with backoff 15s -> 1h and a ``retry_when`` predicate that retries ONLY
  transient errors (connection/timeout) and never validation errors
  (doc 03 §3.13.4).
* :class:`dramatiq.middleware.TimeLimit` / ``AgeLimit`` — enforce the
  per-actor ``time_limit`` options (doc 03 §3.13.5) and the message age cap.
* The remaining stock middleware (``ShutdownNotifications``, ``Callbacks``,
  ``Pipelines``) keeps stock dramatiq semantics; the default 20-retry
  ``Retries`` is intentionally NOT included (replaced by the bounded one).

Message contract
----------------
Messages carry ONLY small fields (``job_id`` + ``object_key`` +
``document_id``) — never file bytes or parse output (doc 03 §3.13.1: "actor
không trả payload lớn").  Every actor reads its job state back from
PostgreSQL (``ingestion_runs``) and enqueues the next step itself (explicit
chaining, doc 03 §3.13.3), which is what makes a killed worker resumable
without losing work.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import (
    Callbacks,
    Middleware,
    Pipelines,
    ShutdownNotifications,
)
from dramatiq.middleware.age_limit import AgeLimit
from dramatiq.middleware.retries import Retries
from dramatiq.middleware.time_limit import TimeLimit, TimeLimitExceeded

from app.config import QueueSettings, get_queue_settings

logger = logging.getLogger(__name__)

__all__ = [
    "DeadLetterMiddleware",
    "TRANSIENT_ERRORS",
    "enqueue_parse",
    "get_broker",
    "make_retry_when",
]

#: Queue names — the actor queue is its stage name (doc 03 §3.13.2), the DLQ
#: name is configurable via ``QUEUE_DLQ_QUEUE`` (default per doc 03 §3.13.6).
DLQ_QUEUE = "default.DLQ"

#: Exception types treated as transient (retryable). Connection and timeout
#: failures of object storage / providers / PostgreSQL are transient; data and
#: validation errors are not (doc 03 §3.13.4: "Chỉ retry transient error").
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
    TimeLimitExceeded,
)


def make_retry_when(max_retries: int) -> Callable[[int, BaseException], bool]:
    """Build the ``retry_when`` predicate for :class:`Retries`.

    Retries ONLY transient errors (:data:`TRANSIENT_ERRORS`) and stops after
    ``max_retries`` attempts.  The bound is encoded here because dramatiq's
    ``Retries`` middleware ignores ``max_retries`` entirely when
    ``retry_when`` is set — without the bound, transient errors would retry
    forever.
    """

    def _retry_when(retries: int, exception: BaseException) -> bool:
        if retries >= max_retries:
            return False
        return isinstance(exception, TRANSIENT_ERRORS)

    return _retry_when


class DeadLetterMiddleware(Middleware):
    """Forward permanently-failed messages to a named DLQ queue (doc 03 §3.13.6).

    dramatiq 2.2.0 ships no dead-letter middleware: a message that exhausts
    its retries is only marked failed by ``Retries`` (its Redis ``.XQ``
    bookkeeping is internal).  This middleware publishes an exact copy of the
    failed message (same args/kwargs, retry count recorded in ``options``) to
    the configured queue so operators can inspect, replay or purge rejected
    work via the same broker API used for live queues.

    Ordering: register BEFORE ``Retries`` so ``after_process_message`` (which
    dramatiq runs in reverse registration order) executes ``Retries`` first —
    the DLQ then only sees messages whose retries are truly exhausted
    (``message.failed`` set).
    """

    def __init__(self, *, queue_name: str = DLQ_QUEUE) -> None:
        super().__init__()
        self.queue_name = queue_name

    def after_process_message(
        self,
        broker: Any,
        message: Any,
        *,
        result: Any = None,
        exception: BaseException | None = None,
    ) -> None:
        if exception is None or not message.failed:
            return
        dead = message.copy(
            queue_name=self.queue_name,
            options={
                **message.options,
                "dlq_original_queue": message.queue_name,
                "dlq_original_actor": message.actor_name,
                "dlq_original_message_id": message.message_id,
            },
        )
        broker.enqueue(dead)
        logger.warning(
            "Message %s (%s) failed permanently; forwarded to DLQ %r.",
            message.message_id,
            message.actor_name,
            self.queue_name,
        )


def _build_middleware(settings: QueueSettings) -> list[Middleware]:
    """The broker middleware stack (see module docstring for the ordering)."""
    return [
        DeadLetterMiddleware(queue_name=settings.dlq_queue),
        Retries(
            max_retries=settings.max_retries,
            min_backoff=settings.min_backoff_ms,
            max_backoff=settings.max_backoff_ms,
            retry_when=make_retry_when(settings.max_retries),
        ),
        TimeLimit(),
        AgeLimit(),
        ShutdownNotifications(),
        Callbacks(),
        Pipelines(),
    ]


_broker_singleton: RedisBroker | None = None


def get_broker(settings: QueueSettings | None = None) -> RedisBroker:
    """Return the process-wide Redis broker (lazy, configured from settings).

    The middleware list is explicit (stock defaults minus the unbounded
    ``Retries``); per-actor ``time_limit`` / ``max_retries`` options are read
    from ``QueueSettings`` by the actor decorators at import time.  The
    no-argument form is cached (one broker per process); an explicit
    ``settings`` argument builds a fresh broker for tests/tools.
    """
    global _broker_singleton
    if settings is None:
        if _broker_singleton is None:
            _broker_singleton = _build_broker(get_queue_settings())
        return _broker_singleton
    return _build_broker(settings)


def _build_broker(settings: QueueSettings) -> RedisBroker:
    from app.config import get_redis_settings

    return RedisBroker(url=get_redis_settings().url, middleware=_build_middleware(settings))


#: Install the configured broker as dramatiq's global broker at import time so
#: actors declared afterwards register against it (doc 03 §3.13.1).
dramatiq.set_broker(get_broker())


def enqueue_parse(job_id: str, object_key: str, *, document_id: str | None = None) -> str:
    """Enqueue the parse actor for one ingestion job; return the message id.

    Public contract for VNLRAG-135: the upload API calls exactly this after
    storing the source PDF in object storage.  The message payload is small —
    ``job_id`` + ``object_key`` + ``document_id`` only (no file bytes, no
    parse output, doc 03 §3.13.1).  No database work happens here: the parse
    actor bootstraps the ``ingestion_runs`` row (status ``QUEUED``) when it
    picks the message up, so this function can never fail on a missing
    document/version row.

    Raises:
        ValueError: for empty ``job_id`` / ``object_key``.
    """
    if not job_id or not job_id.strip():
        raise ValueError("job_id must be a non-empty string")
    if not object_key or not object_key.strip():
        raise ValueError("object_key must be a non-empty string")

    # Imported lazily to avoid a circular import (parse.py imports this
    # module for the broker); by call time the actors package is imported.
    from app.ingestion.actors.parse import parse_actor

    if document_id is None:
        message = parse_actor.send(job_id, object_key)
    else:
        message = parse_actor.send(job_id, object_key, document_id=document_id)
    return message.message_id
