"""Dramatiq ingestion actors (VNLRAG-133).

Imports the queue wiring first (broker + middleware, doc 03 §3.13.1) and then
registers every actor of the documented pipeline (doc 03 §3.13.2):

    parse -> normalize -> extract -> resolve_refs -> resolve_temporal
    -> quality_gate -> embed -> index

``resolve_refs_actor`` / ``resolve_temporal_actor`` are STAGED until W4
(VNLRAG-31 / VNLRAG-136): they halt the job in the terminal ``STAGED`` state
and never advance or index (see their module docstrings).

Public API for the upload flow (VNLRAG-135): :func:`enqueue_parse` — a single
queue call; the parse actor bootstraps the ``ingestion_runs`` row itself.
"""

from app.ingestion.queue import (
    TRANSIENT_ERRORS,
    DeadLetterMiddleware,
    enqueue_parse,
    get_broker,
    make_retry_when,
)

from .embed import embed_actor
from .extract import extract_actor
from .index import index_actor
from .normalize import normalize_actor
from .parse import ParseRejectedError, parse_actor
from .quality_gate import quality_gate_actor
from .resolve_refs import resolve_refs_actor
from .resolve_temporal import resolve_temporal_actor

__all__ = [
    "DeadLetterMiddleware",
    "ParseRejectedError",
    "TRANSIENT_ERRORS",
    "embed_actor",
    "enqueue_parse",
    "extract_actor",
    "get_broker",
    "index_actor",
    "make_retry_when",
    "normalize_actor",
    "parse_actor",
    "quality_gate_actor",
    "resolve_refs_actor",
    "resolve_temporal_actor",
]
