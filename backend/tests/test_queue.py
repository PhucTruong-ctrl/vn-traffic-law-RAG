"""Unit tests for the Redis + Dramatiq ingestion queue (VNLRAG-133).

Covers broker/config construction, the ``enqueue_parse`` public contract, actor
registration + per-actor time limits, the DLQ middleware, the retry predicate
and actor idempotency (fake state transitions: a second run is a no-op).  No
Redis / PostgreSQL is touched — the global broker is swapped for a
:class:`StubBroker` and DB access is monkeypatched at the actor seams.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import Mock

import dramatiq
import pytest
from dramatiq import Message
from dramatiq.broker import MessageProxy
from dramatiq.brokers.redis import RedisBroker
from dramatiq.brokers.stub import StubBroker
from dramatiq.middleware.age_limit import AgeLimit
from dramatiq.middleware.retries import Retries
from dramatiq.middleware.time_limit import TimeLimit

from app.config import (
    DEFAULT_ACTOR_TIME_LIMITS_SECONDS,
    QueueSettings,
    RedisSettings,
    get_queue_settings,
)
from app.ingestion import actors
from app.ingestion.actors import normalize as normalize_module
from app.ingestion.actors import parse as parse_module
from app.ingestion.actors import resolve_refs, resolve_temporal
from app.ingestion.actors.embed import embed_actor
from app.ingestion.actors.extract import extract_actor
from app.ingestion.actors.index import index_actor
from app.ingestion.actors.normalize import normalize_actor
from app.ingestion.actors.parse import parse_actor
from app.ingestion.actors.quality_gate import quality_gate_actor
from app.ingestion.actors.resolve_refs import resolve_refs_actor
from app.ingestion.actors.resolve_temporal import resolve_temporal_actor
from app.ingestion.queue import (
    TRANSIENT_ERRORS,
    DeadLetterMiddleware,
    enqueue_parse,
    get_broker,
    make_retry_when,
)
from app.persistence.models import IngestionRun

#: Actor queue names (== stage names, doc 03 §3.13.2).
ACTOR_NAMES = [
    "parse",
    "normalize",
    "extract",
    "resolve_refs",
    "resolve_temporal",
    "quality_gate",
    "embed",
    "index",
]


@pytest.fixture(autouse=True)
def _stub_broker() -> StubBroker:
    """Swap the global dramatiq broker for an in-memory stub per test.

    Actors bind their broker at decoration time (the real RedisBroker), so
    ``.send()`` must be rebound to the stub — and restored afterwards so a
    later integration test (same pytest process) still sends to real Redis.
    """
    broker = StubBroker()
    for name in [*ACTOR_NAMES, "default.DLQ"]:
        broker.declare_queue(name)
    actors_under_test = (
        parse_actor,
        normalize_actor,
        extract_actor,
        resolve_refs_actor,
        resolve_temporal_actor,
        quality_gate_actor,
        embed_actor,
        index_actor,
    )
    original_brokers = {actor: actor.broker for actor in actors_under_test}
    original_global = dramatiq.get_broker()
    dramatiq.set_broker(broker)
    for actor in actors_under_test:
        actor.broker = broker
    yield broker
    for actor, bound in original_brokers.items():
        actor.broker = bound
    dramatiq.set_broker(original_global)


class _FakeSession:
    """Minimal session double: records commit/rollback/close, adds nothing."""

    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.closed = False
        self.added: list[Any] = []

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        pass

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True

    def scalar(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("unit tests monkeypatch load_run instead")

    def scalars(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError("unit tests monkeypatch load_* instead")


def _run(**overrides: Any) -> IngestionRun:
    """An in-memory IngestionRun (id set so FK-using code can run)."""
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "job_id": "job-1",
        "document_id": "nd-168-2024",
        "manifest_json": {"source_object_key": "documents/nd-168-2024/source/x.pdf"},
        "file_hash": uuid.uuid4().hex,
        "status": "QUEUED",
        "current_stage": "QUEUED",
        "started_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "retry_count": 0,
    }
    fields.update(overrides)
    return IngestionRun(**fields)


def _messages(broker: StubBroker, queue_name: str) -> list[Message]:
    """Drain a stub queue (StubBroker stores ``message.encode()`` bytes)."""
    queue = broker.queues[queue_name]
    messages: list[Message] = []
    while not queue.empty():
        messages.append(Message.decode(queue.get_nowait()))
    return messages


def _queue_empty(broker: StubBroker, queue_name: str) -> bool:
    return broker.queues[queue_name].empty()


# --- config ------------------------------------------------------------------


def test_redis_settings_default_url() -> None:
    assert RedisSettings().url == "redis://localhost:6379/0"


def test_queue_settings_defaults() -> None:
    settings = get_queue_settings()
    assert settings.max_retries == 3
    assert settings.min_backoff_ms == 15_000
    assert settings.max_backoff_ms == 3_600_000
    assert settings.dlq_queue == "default.DLQ"
    assert settings.actor_timeouts_seconds == DEFAULT_ACTOR_TIME_LIMITS_SECONDS
    # doc 03 §3.13.5: parse is the only long step.
    assert settings.actor_timeouts_seconds["parse"] == 1200
    assert settings.actor_timeouts_seconds["index"] == 300


def test_queue_settings_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("QUEUE_MAX_RETRIES", "5")
    monkeypatch.setenv("QUEUE_DLQ_QUEUE", "custom.DLQ")
    get_queue_settings.cache_clear()
    try:
        settings = get_queue_settings()
        assert settings.max_retries == 5
        assert settings.dlq_queue == "custom.DLQ"
    finally:
        get_queue_settings.cache_clear()


# --- broker ------------------------------------------------------------------


def test_broker_is_configured_redis_broker() -> None:
    broker = get_broker()
    assert isinstance(broker, RedisBroker)
    kwargs = broker.client.connection_pool.connection_kwargs
    assert kwargs["host"] == "localhost"
    assert kwargs["port"] == 6379
    assert kwargs["db"] == 0


def test_broker_middleware_stack_and_configuration() -> None:
    broker = get_broker()
    # dramatiq injects internal middleware (e.g. _WorkerMiddleware) onto the
    # broker when a Worker consumes — the assertion compares the full
    # NON-internal stack, which is ours and order-stable.
    middleware_types = [
        type(middleware).__name__
        for middleware in broker.middleware
        if not type(middleware).__name__.startswith("_")
    ]
    assert middleware_types == [
        "DeadLetterMiddleware",
        "Retries",
        "TimeLimit",
        "AgeLimit",
        "ShutdownNotifications",
        "Callbacks",
        "Pipelines",
    ]

    retries = next(m for m in broker.middleware if isinstance(m, Retries))
    assert retries.max_retries == 3
    assert retries.min_backoff == 15_000
    assert retries.max_backoff == 3_600_000

    dlq = next(m for m in broker.middleware if isinstance(m, DeadLetterMiddleware))
    assert dlq.queue_name == "default.DLQ"

    assert any(isinstance(m, TimeLimit) for m in broker.middleware)
    assert any(isinstance(m, AgeLimit) for m in broker.middleware)


def test_global_broker_is_our_broker() -> None:
    # queue.py installs the configured broker at import time; the autouse stub
    # fixture then overrides the global for tests.  The singleton still holds
    # our Redis broker.
    assert get_broker() is get_broker()
    assert isinstance(get_broker(), RedisBroker)


def test_broker_from_explicit_settings() -> None:
    broker = get_broker(QueueSettings(max_retries=5))
    retries = next(m for m in broker.middleware if isinstance(m, Retries))
    assert retries.max_retries == 5


# --- retry predicate ----------------------------------------------------------


def test_retry_when_only_transient_and_bounded() -> None:
    retry = make_retry_when(3)
    assert retry(0, ConnectionError("down")) is True
    assert retry(2, TimeoutError("slow")) is True
    assert retry(3, ConnectionError("down")) is False  # bound reached
    assert retry(0, ValueError("bad data")) is False  # validation never retried
    assert retry(0, KeyError("missing")) is False


def test_transient_errors_exclude_validation_errors() -> None:
    assert ConnectionError in TRANSIENT_ERRORS
    assert TimeoutError in TRANSIENT_ERRORS
    assert ValueError not in TRANSIENT_ERRORS


# --- actor registration -------------------------------------------------------


def test_all_pipeline_actors_registered() -> None:
    broker = get_broker()
    for name in ACTOR_NAMES:
        assert broker.get_actor(f"{name}_actor") is not None


def test_actors_reexported_from_package() -> None:
    for name in ACTOR_NAMES:
        assert getattr(actors, f"{name}_actor") is not None
    assert callable(actors.enqueue_parse)
    assert callable(actors.get_broker)


def test_per_actor_options_time_limit_max_retries_queue() -> None:
    broker = get_broker()
    for name in ACTOR_NAMES:
        actor = broker.get_actor(f"{name}_actor")
        assert actor.queue_name == name, name
        assert actor.options["time_limit"] == DEFAULT_ACTOR_TIME_LIMITS_SECONDS[name], name
        assert actor.options["max_retries"] == 3, name


# --- enqueue_parse contract ---------------------------------------------------


def test_enqueue_parse_payload_small_and_field_exact(_stub_broker: StubBroker) -> None:
    message_id = enqueue_parse(
        "job-1",
        "documents/nd-168-2024/source/abc123.pdf",
        document_id="nd-168-2024",
    )
    messages = _messages(_stub_broker, "parse")
    assert len(messages) == 1
    message = messages[0]
    assert message.message_id == message_id
    assert message.actor_name == "parse_actor"
    assert message.queue_name == "parse"
    assert message.args == ("job-1", "documents/nd-168-2024/source/abc123.pdf")
    assert message.kwargs == {"document_id": "nd-168-2024"}
    # No large payload through Redis: message must stay tiny.
    assert len(json.dumps(message.asdict()).encode("utf-8")) < 1024


def test_enqueue_parse_without_document_id(_stub_broker: StubBroker) -> None:
    message_id = enqueue_parse("job-2", "documents/nd-168-2024/source/abc.pdf")
    message = _messages(_stub_broker, "parse")[0]
    assert message.message_id == message_id
    assert message.kwargs == {}


def test_enqueue_parse_rejects_empty_arguments() -> None:
    with pytest.raises(ValueError):
        enqueue_parse("", "documents/x.pdf")
    with pytest.raises(ValueError):
        enqueue_parse("job-1", "   ")


# --- DLQ middleware -----------------------------------------------------------


def _proxy_failed_message(*, failed: bool = True, **options: Any) -> MessageProxy:
    message = Message(
        queue_name="parse",
        actor_name="parse_actor",
        args=("job-1", "object-key"),
        kwargs={},
        options=options,
    )
    proxy = MessageProxy(message)
    if failed:
        proxy.fail()
    return proxy


def test_dlq_middleware_forwards_failed_message(_stub_broker: StubBroker) -> None:
    middleware = DeadLetterMiddleware(queue_name="default.DLQ")
    proxy = _proxy_failed_message()
    middleware.after_process_message(_stub_broker, proxy, exception=RuntimeError("boom"))

    dead = _messages(_stub_broker, "default.DLQ")
    assert len(dead) == 1
    assert dead[0].actor_name == "parse_actor"
    assert dead[0].args == ("job-1", "object-key")
    assert dead[0].options["dlq_original_queue"] == "parse"
    assert dead[0].options["dlq_original_actor"] == "parse_actor"


def test_dlq_middleware_ignores_success_and_retryable_failures(
    _stub_broker: StubBroker,
) -> None:
    middleware = DeadLetterMiddleware(queue_name="default.DLQ")
    middleware.after_process_message(_stub_broker, _proxy_failed_message(), exception=None)
    middleware.after_process_message(
        _stub_broker, _proxy_failed_message(failed=False), exception=RuntimeError("retryable")
    )
    assert _queue_empty(_stub_broker, "default.DLQ")


# --- staged resolvers ---------------------------------------------------------


def test_resolve_refs_halts_job_in_staged_state(
    _stub_broker: StubBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(status="EXTRACTING", current_stage="EXTRACTING")
    session = _FakeSession()
    monkeypatch.setattr(resolve_refs, "load_run", lambda s, job_id: run)
    monkeypatch.setattr(resolve_refs, "new_session", lambda: session)

    resolve_refs_actor(job_id="job-1")

    assert run.status == "STAGED"
    assert run.current_stage == "RESOLVING_REFS"
    assert run.error is not None
    assert run.error["code"] == "STAGED_ACTOR"
    assert "W4" in run.error["message"]
    assert session.committed is True
    # The chain MUST NOT advance: no quality_gate / embed / index messages.
    assert _queue_empty(_stub_broker, "quality_gate")
    assert _queue_empty(_stub_broker, "embed")
    assert _queue_empty(_stub_broker, "index")


def test_resolve_refs_second_run_is_noop(_stub_broker: StubBroker, monkeypatch) -> None:
    run = _run(status="STAGED", current_stage="RESOLVING_REFS")
    monkeypatch.setattr(resolve_refs, "load_run", lambda s, job_id: run)
    monkeypatch.setattr(resolve_refs, "new_session", lambda: _FakeSession())

    resolve_refs_actor(job_id="job-1")

    assert run.status == "STAGED"  # untouched
    assert _queue_empty(_stub_broker, "quality_gate")


def test_resolve_temporal_halts_job_in_staged_state(
    _stub_broker: StubBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = _run(status="RESOLVING_REFS", current_stage="RESOLVING_REFS")
    session = _FakeSession()
    monkeypatch.setattr(resolve_temporal, "load_run", lambda s, job_id: run)
    monkeypatch.setattr(resolve_temporal, "new_session", lambda: session)

    resolve_temporal_actor(job_id="job-1")

    assert run.status == "STAGED"
    assert run.current_stage == "RESOLVING_TEMPORAL"
    assert run.error["code"] == "STAGED_ACTOR"
    assert session.committed is True
    assert _queue_empty(_stub_broker, "quality_gate")


# --- actor idempotency (fake state transitions) -------------------------------


def test_parse_actor_skips_when_stage_already_passed(monkeypatch: pytest.MonkeyPatch) -> None:
    run = _run(status="NORMALIZING", current_stage="NORMALIZING")
    session = _FakeSession()
    monkeypatch.setattr(parse_module, "load_run", lambda s, job_id: run)
    monkeypatch.setattr(parse_module, "new_session", lambda: session)
    # The heavy path must never run for an already-passed stage.
    monkeypatch.setattr(parse_module, "_get_storage", lambda: pytest.fail("storage fetched"))

    parse_actor(job_id="job-1", object_key="documents/x.pdf")

    assert session.committed is False
    assert session.rolled_back is False


def test_normalize_actor_skips_when_stage_already_passed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = _run(status="EXTRACTING", current_stage="EXTRACTING")
    session = _FakeSession()
    monkeypatch.setattr(normalize_module, "load_run", lambda s, job_id: run)
    monkeypatch.setattr(normalize_module, "new_session", lambda: session)
    monkeypatch.setattr(
        normalize_module,
        "load_parsed_document",
        lambda s, document_id: pytest.fail("parsed document loaded"),
    )

    normalize_actor(job_id="job-1")

    assert session.committed is False


def test_parse_actor_bootstraps_run_and_chains(
    _stub_broker: StubBroker, monkeypatch: pytest.MonkeyPatch
) -> None:
    bootstrapped = _run()
    calls = {"bootstrap": 0, "parse": 0, "loads": 0}

    def _load_run(session, job_id: str):
        calls["loads"] += 1
        return None if calls["loads"] == 1 else bootstrapped

    def _bootstrap(session, *, job_id, document_id, object_key) -> IngestionRun:
        calls["bootstrap"] += 1
        assert job_id == "job-1"
        assert document_id == "nd-168-2024"
        assert object_key == "documents/nd-168-2024/source/x.pdf"
        return bootstrapped

    class _Storage:
        def get(self, bucket: str, key: str) -> bytes:
            calls["parse"] += 1
            assert bucket == "source-pdfs"
            return b"%PDF-1.4 fake pdf bytes"

    monkeypatch.setattr(parse_module, "new_session", lambda: _FakeSession())
    monkeypatch.setattr(parse_module, "load_run", _load_run)
    monkeypatch.setattr(parse_module, "bootstrap_run", _bootstrap)
    monkeypatch.setattr(parse_module, "_get_storage", lambda: _Storage())
    monkeypatch.setattr(
        parse_module,
        "route_and_parse",
        lambda path, **kw: (
            Mock(),
            {"schema": "parser_routing-v1", "terminal_outcome": "accepted"},
        ),
    )
    monkeypatch.setattr(parse_module, "persist_parsed_document", lambda s, ir, run: None)

    parse_actor(
        job_id="job-1",
        object_key="documents/nd-168-2024/source/x.pdf",
        document_id="nd-168-2024",
    )

    assert calls["bootstrap"] == 1
    assert calls["parse"] == 1
    assert bootstrapped.status == "PARSING"
    assert bootstrapped.current_stage == "PARSING"
    # sha256 of the fake PDF bytes
    assert bootstrapped.file_hash == "2825bfc89e1fae627faeee6aa8007367636d00604e36f711fb12b8dee3255ad5"  # noqa: E501
    assert bootstrapped.parser_routing == {
        "schema": "parser_routing-v1",
        "terminal_outcome": "accepted",
    }
    # Chain advanced: a normalize message was enqueued.
    assert _messages(_stub_broker, "normalize")[0].args == ("job-1",)


def test_index_sparse_encoder_fitted_on_corpus_aligns_shared_tokens() -> None:
    """Shared tokens land on the SAME sparse dimension across provisions.

    The index actor must fit ONE BM25 vocabulary over the corpus before
    indexing — an unfitted encoder assigns text-local token ids, so the same
    dimension would mean different tokens in different points (invalid
    keyword scoring, doc 03 §3.11.2 sparse-space contract).
    """
    from app.ingestion.actors.index import _fit_sparse_encoder

    corpus = [
        "Điều 7. Xử phạt người điều khiển xe mô tô",
        "1. Phạt tiền từ 400.000 đồng đến 600.000 đồng",
    ]
    encoder = _fit_sparse_encoder(corpus)
    first = encoder.encode(corpus[0])
    second = encoder.encode(corpus[1])

    # "phạt" (lowercased by the tokenizer) occurs in both texts and must map
    # to one shared dimension in both sparse dicts.
    shared = encoder.vocabulary["phạt"]
    assert shared in first
    assert shared in second
    assert first[shared] > 0.0
    assert second[shared] > 0.0

    # Deterministic across runs for the same corpus: re-fitting yields the
    # identical vocabulary, so a re-run indexes with the same dimensions.
    refitted = _fit_sparse_encoder(corpus)
    assert refitted.vocabulary == encoder.vocabulary
    assert refitted.encode(corpus[0]) == first
