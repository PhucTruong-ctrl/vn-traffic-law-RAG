"""Integration tests for the ingestion queue actors (VNLRAG-133).

Drives the REAL Redis broker and REAL PostgreSQL through the actor state
machine (doc 03 §3.13): parse -> normalize -> extract -> resolve_refs
-> resolve_temporal, plus the quality_gate -> embed -> index tail with an
idempotent index re-run, missing-successor review handoff, and the dead-letter
queue.

Guards (module-scoped fixture, following the ``tests/integration/conftest.py``
reachability pattern): the whole module is SKIPPED when PostgreSQL
(``DATABASE_URL``) or Redis (``REDIS_URL``) is not configured/reachable.
No MinIO, Qdrant, embedding API or real PDF parsing is required: the parse
actor's storage + parser runners and the index actor's Qdrant client /
embedder are monkeypatched — everything else (queue, PG state transitions,
provision/provenance persistence, review items) is the real implementation.
"""

from __future__ import annotations

import hashlib
import os
import uuid
from datetime import UTC, date, datetime
from typing import Any
from unittest.mock import Mock

import dramatiq
import pytest
from dramatiq import Worker
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from alembic import command
from app.config import get_redis_settings
from app.ingestion.actors import embed as embed_module
from app.ingestion.actors import enqueue_parse
from app.ingestion.actors import index as index_module
from app.ingestion.actors import parse as parse_module
from app.ingestion.actors.index import index_actor
from app.ingestion.actors.quality_gate import quality_gate_actor
from app.ingestion.actors import quality_gate as quality_gate_module
from app.ingestion.actors.resolve_temporal import resolve_temporal_actor
from app.ingestion.document_ir import BoundingBox, DocumentElement, ParsedDocument, ParsedPage
from app.ingestion.queue import get_broker
from app.persistence.models import (
    DocumentElement as DocumentElementRow,
)
from app.persistence.models import (
    DocumentVersion,
    IngestionRun,
    LegalDocument,
    LegalProvision,
    ProvisionProvenance,
    ReviewItem,
)
from app.persistence.models import (
    ParsedDocument as ParsedDocumentRow,
)

_QUEUES = (
    "parse",
    "normalize",
    "extract",
    "resolve_refs",
    "resolve_temporal",
    "quality_gate",
    "embed",
    "index",
)


# --- module-scoped environment: PG scratch DB + Redis reachability ------------


@pytest.fixture(scope="module")
def queue_env() -> Any:
    """Scratch PostgreSQL (migrated) + reachable Redis; sets DATABASE_URL.

    Skipped entirely when either service is unreachable.
    """
    from tests.integration.conftest import (  # local import (test_reconcile pattern)
        _alembic_config,
        _create_scratch_database,
        _drop_scratch_database,
        _resolve_base_url,
        _scratch_name,
        _with_database,
    )

    try:
        base_url = _resolve_base_url()
    except RuntimeError:
        pytest.skip("PostgreSQL not configured: set DATABASE_URL or a repo-root .env")
    probe = create_engine(base_url, connect_args={"connect_timeout": 3})
    try:
        with probe.connect():
            pass
    except Exception:
        probe.dispose()
        pytest.skip(f"PostgreSQL not reachable at {base_url}")
    probe.dispose()

    from redis import Redis

    try:
        Redis.from_url(get_redis_settings().url).ping()
    except Exception:
        pytest.skip(f"Redis not reachable at {get_redis_settings().url}")

    scratch = _scratch_name(base_url, f"t133{uuid.uuid4().hex[:6]}")
    _create_scratch_database(base_url, scratch)
    url = _with_database(base_url, scratch)
    config = _alembic_config(url)
    command.upgrade(config, "head")
    engine = create_engine(url)

    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = url  # actor sessions (new_session) use this
    try:
        yield engine
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        engine.dispose()
        _drop_scratch_database(base_url, scratch)


@pytest.fixture()
def clean_queues() -> None:
    """Flush every queue the tests use (before + after each test)."""
    broker = get_broker()
    for queue in (*_QUEUES, "default.DLQ"):
        broker.flush(queue)
    yield
    for queue in (*_QUEUES, "default.DLQ"):
        broker.flush(queue)


def _document_id() -> str:
    """A unique document_id whose slug satisfies the frozen provision_id grammar."""
    return f"nd-{uuid.uuid4().int % 10**7}-2026"


def _unique(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


# --- fixtures / doubles --------------------------------------------------------


def _nd_ir(document_id: str) -> ParsedDocument:
    """A realistic Vietnamese legal IR (mirrors tests/test_projection._nd_ir)."""
    rows = [
        ("CHÍNH PHỦ", "page_header"),
        ("NGHỊ ĐỊNH 168/2024/NĐ-CP VỀ XỬ PHẠT VI PHẠM HÀNH CHÍNH", "title"),
        ("Điều 7. Xử phạt người điều khiển xe mô tô", "heading"),
        ("1. Phạt tiền từ 400.000 đồng đến 600.000 đồng", "paragraph"),
        ("a) Không chấp hành hiệu lệnh của đèn tín hiệu", "paragraph"),
        ("d) Dừng xe, đỗ xe tại nơi có biển cấm dừng", "paragraph"),
        ("đ) Lùi xe không quan sát phía sau", "paragraph"),
    ]
    elements = [
        DocumentElement(
            element_id=f"e{index}",
            element_type=element_type,
            text=text,
            page_number=1,
            bbox=BoundingBox(left=0.1, top=index / 100, right=0.9, bottom=(index + 1) / 100),
            reading_order=index,
            parent_element_id=None,
            source_parser="DOCLING",
            parser_version="docling-2.1.0",
            parser_confidence=None,
            raw_reference={"index": index},
        )
        for index, (text, element_type) in enumerate(rows)
    ]
    return ParsedDocument(
        parsed_document_id=str(uuid.uuid4()),
        document_id=document_id,
        parser="DOCLING",
        parser_version="docling-2.1.0",
        ir_schema_version="document-ir-v2",
        source_object_key="fixture",
        pages=[ParsedPage(page_number=1, width=1, height=1, text=None, elements=elements)],
        parse_started_at=datetime(2025, 1, 1, tzinfo=UTC),
        parse_completed_at=datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC),
        quality_report={},
    )


class _FakeStorage:
    """ObjectStoragePort double returning one canned PDF."""

    def get(self, bucket: str, key: str) -> bytes:
        assert bucket == "source-pdfs"
        return b"%PDF-1.4 vnlaw integration fixture"


class _FakeEmbedder:
    """EmbeddingProvider double with fixed 768-dim vectors."""

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [[0.1 + 0.01 * (index % 10)] * 768 for index in range(len(texts))]

    def embed(self, text: str) -> list[float]:
        return [0.1] * 768


class _RecordingClient:
    """Qdrant double recording every upsert call."""

    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[Any]]] = []

    def upsert(self, *, collection_name: str, points: list[Any]) -> None:
        self.upserts.append((collection_name, list(points)))


# --- end-to-end chain test ------------------------------------------------------


def test_parse_chain_end_to_end_reaches_activated_resolvers(
    queue_env: Any, clean_queues: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """parse -> normalize -> extract -> activated reference resolver handoff.

    The resolver marks the run ``RESOLVING_REFS`` while temporal resolution
    continues downstream; parser/storage are doubled.
    """
    engine = queue_env
    document_id = _document_id()
    job_id = _unique("job")
    object_key = f"documents/{document_id}/source/{uuid.uuid4().hex}.pdf"

    with Session(engine) as session:
        session.add(
            LegalDocument(
                document_id=document_id,
                document_number="168/2024/NĐ-CP",
                document_title="Nghị định xử phạt vi phạm hành chính",
                document_type="DECREE",
                file_hash=uuid.uuid4().hex,
                status="EFFECTIVE",
            )
        )
        session.commit()

    fake_ir = _nd_ir(document_id)
    monkeypatch.setattr(parse_module, "_get_storage", lambda: _FakeStorage())
    monkeypatch.setattr(
        parse_module,
        "route_and_parse",
        lambda path, **kw: (
            fake_ir,
            {"schema": "parser_routing-v1", "terminal_outcome": "accepted"},
        ),
    )

    broker = get_broker()
    worker = Worker(broker, queues=set(_QUEUES[:4]), worker_timeout=30_000)
    worker.start()
    try:
        message_id = enqueue_parse(job_id, object_key, document_id=document_id)
        assert isinstance(message_id, str) and message_id
        for queue in ("parse", "normalize", "extract", "resolve_refs"):
            broker.join(queue, timeout=60_000)
        worker.join()

        with Session(engine) as session:
            run = session.scalar(select(IngestionRun).where(IngestionRun.job_id == job_id))
            assert run.status == "RESOLVING_REFS"
            assert run.current_stage == "RESOLVING_REFS"
            assert run.error is None
            expected_hash = hashlib.sha256(b"%PDF-1.4 vnlaw integration fixture").hexdigest()
            assert run.file_hash == expected_hash
            assert run.parser_routing["terminal_outcome"] == "accepted"

            parsed_rows = list(
                session.scalars(
                    select(ParsedDocumentRow).where(ParsedDocumentRow.document_id == document_id)
                )
            )
            assert len(parsed_rows) == 1
            elements = list(
                session.scalars(
                    select(DocumentElementRow).where(
                        DocumentElementRow.parsed_document_id == parsed_rows[0].id
                    )
                )
            )
            assert len(elements) == len(fake_ir.pages[0].elements)

            version = session.scalar(
                select(DocumentVersion).where(DocumentVersion.document_id == document_id)
            )
            assert version is not None
            provisions = list(
                session.scalars(
                    select(LegalProvision).where(
                        LegalProvision.document_version_id == version.id
                    )
                )
            )
            assert len(provisions) >= 3
            provenance_count = len(
                list(
                    session.scalars(
                        select(ProvisionProvenance).where(
                            ProvisionProvenance.provision_version_row_id.in_(
                                [row.id for row in provisions]
                            )
                        )
                    )
                )
            )
            assert provenance_count >= 1

        # --- re-run: a duplicate parse message must be a no-op (idempotent) ---
        enqueue_parse(job_id, object_key, document_id=document_id)
        broker.join("parse", timeout=60_000)
        worker.join()
        with Session(engine) as session:
            parsed_rows = list(
                session.scalars(
                    select(ParsedDocumentRow).where(ParsedDocumentRow.document_id == document_id)
                )
            )
            assert len(parsed_rows) == 1  # still one, not two
            run = session.scalar(select(IngestionRun).where(IngestionRun.job_id == job_id))
            assert run.status == "RESOLVING_REFS"  # idempotent handoff
    finally:
        worker.stop()


def test_temporal_missing_successor_hands_off_to_review(
    queue_env: Any, clean_queues: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing amendment successor content halts before the quality gate."""
    engine = queue_env
    document_id = _document_id()
    job_id = _unique("job")
    run_id, provision_ids = _seed_gate_pipeline(engine, document_id, job_id)

    with Session(engine) as session:
        run = session.get(IngestionRun, run_id)
        assert run is not None
        run.manifest_json = {
            "effective_from": "2025-01-01",
            "review_status": "ACCEPTED",
            "effect_events": [
                {
                    "event_type": "AMENDED",
                    "event_date": "2025-02-01",
                    "review_status": "ACCEPTED",
                    "affected_provision_versions": [
                        {"provision_id": provision_ids[0]}
                    ],
                }
            ],
        }
        session.commit()

    quality_gate_send = Mock()
    monkeypatch.setattr(quality_gate_module.quality_gate_actor, "send", quality_gate_send)
    broker = get_broker()
    worker = Worker(
        broker,
        queues={"resolve_temporal", "quality_gate"},
        worker_timeout=30_000,
    )
    worker.start()
    try:
        resolve_temporal_actor.send(job_id)
        broker.join("resolve_temporal", timeout=60_000)
        broker.join("quality_gate", timeout=60_000)
        worker.join()
    finally:
        worker.stop()

    with Session(engine) as session:
        run = session.get(IngestionRun, run_id)
        assert run is not None
        assert run.status == "PENDING_REVIEW"
        assert run.current_stage == "RESOLVING_TEMPORAL"
        assert run.error is not None
        assert run.error["code"] == "TEMPORAL_REVIEW"
        items = list(
            session.scalars(
                select(ReviewItem).where(ReviewItem.ingestion_run_id == run_id)
            )
        )
        assert len(items) == 1
        assert items[0].reason_code == "MISSING_SUCCESSOR_CONTENT"
        assert items[0].status == "PENDING"

    assert quality_gate_send.call_count == 0


# --- quality_gate -> embed -> index tail ----------------------------------------


def _seed_gate_pipeline(engine: Any, document_id: str, job_id: str) -> tuple[uuid.UUID, list[str]]:
    """Seed a job at EXTRACTING with 3 provisions (ARTICLE/CLAUSE/POINT)."""
    provision_ids = [
        f"{document_id}__dieu-7",
        f"{document_id}__dieu-7__khoan-1",
        f"{document_id}__dieu-7__khoan-1__diem-a",
    ]
    with Session(engine) as session:
        document = LegalDocument(
            document_id=document_id,
            document_number="168/2024/NĐ-CP",
            document_title="Nghị định xử phạt vi phạm hành chính",
            document_type="DECREE",
            file_hash=uuid.uuid4().hex,
            status="EFFECTIVE",
        )
        session.add(document)
        session.flush()  # legal_documents row must exist before run/provision inserts
        version = DocumentVersion(
            document_id=document_id,
            version=1,
            manifest_json={},
            content_hash=uuid.uuid4().hex,
            review_status="PENDING",
        )
        session.add(version)
        run = IngestionRun(
            id=uuid.uuid4(),
            job_id=job_id,
            document_id=document_id,
            manifest_json={},
            file_hash=uuid.uuid4().hex,
            status="EXTRACTING",
            current_stage="EXTRACTING",
        )
        session.add(run)
        parsed = ParsedDocumentRow(
            document_id=document_id,
            parser="DOCLING",
            parser_version="docling-2.1.0",
            ir_schema_version="document-ir-v2",
            source_object_key=f"documents/{document_id}/source/x.pdf",
            parse_status="SUCCESS",
            quality_report={},
            started_at=datetime(2025, 1, 1, tzinfo=UTC),
            completed_at=datetime(2025, 1, 1, 0, 0, 1, tzinfo=UTC),
        )
        session.add(parsed)
        session.flush()  # parsed.id must exist before element rows reference it
        for index, text in enumerate(
            ("NGHỊ ĐỊNH 168/2024/NĐ-CP VỀ XỬ PHẠT", "Điều 7. Xử phạt người điều khiển xe mô tô")
        ):
            session.add(
                DocumentElementRow(
                    parsed_document_id=parsed.id,
                    element_id=f"e{index}",
                    element_type="title" if index == 0 else "heading",
                    text=text,
                    page_number=1,
                    bbox={
                        "left": 0.1,
                        "top": 0.1 * index,
                        "right": 0.9,
                        "bottom": 0.1 * index + 0.1,
                        "coordinate_space": "NORMALIZED_PAGE",
                    },
                    reading_order=index,
                    parent_element_id=None,
                    source_parser="DOCLING",
                    parser_version="docling-2.1.0",
                    parser_confidence=None,
                    raw_reference={"index": index},
                )
            )
        sources = {
            provision_ids[0]: ("Điều 7. Xử phạt người điều khiển xe mô tô", "ARTICLE", "7", None, None),  # noqa: E501
            provision_ids[1]: ("1. Phạt tiền từ 400.000 đồng đến 600.000 đồng", "CLAUSE", "7", "1", None),  # noqa: E501
            provision_ids[2]: ("a) Không chấp hành hiệu lệnh của đèn tín hiệu", "POINT", "7", "1", "a)"),  # noqa: E501
        }
        session.flush()
        for pid, (text, kind, article, clause, point) in sources.items():
            session.add(
                LegalProvision(
                    provision_id=pid,
                    document_version_id=version.id,
                    node_kind=kind,
                    article=article,
                    clause=clause,
                    point=point,
                    source_text=text,
                    retrieval_text=text,
                    parent_context=None,
                    effective_from=date(2025, 1, 1),
                    effective_to=None,
                    status="EFFECTIVE",
                    page_number=1,
                    bbox=None,
                    source_element_ids=["e0"],
                    content_hash=hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    version=1,
                    review_status="PENDING",
                )
            )
        session.commit()
        return run.id, provision_ids


def test_quality_gate_embed_index_completes_without_duplicates(
    queue_env: Any, clean_queues: None, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """ACCEPTED provisions flow gate -> embed -> index -> COMPLETED.

    A re-sent index message must NOT upsert again (idempotent re-run, no
    duplicate points).  A SECOND job must reuse the PERSISTED sparse
    vocabulary (same token->dimension mapping — no refit drift) even when the
    corpus has grown.  Qdrant + the embedding API are doubled.
    """
    engine = queue_env
    document_id = _document_id()
    job_id = _unique("job")
    run_id, provision_ids = _seed_gate_pipeline(engine, document_id, job_id)

    vocab_dir = tmp_path / "sparse-vocab"
    monkeypatch.setattr(index_module, "_VOCAB_DIR", vocab_dir)

    client = _RecordingClient()
    monkeypatch.setattr(embed_module, "_get_provider", lambda: _FakeEmbedder())
    monkeypatch.setattr(index_module, "_get_qdrant_client", lambda: client)
    monkeypatch.setattr(index_module, "_get_embedder", lambda: _FakeEmbedder())
    # Sparse channel: NOT monkeypatched — the actor persists and reuses ONE
    # corpus vocabulary (data/sparse-vocab/{version}.json); the assertions
    # below verify shared tokens land on the SAME sparse dimension across
    # points AND across jobs (no refit drift, doc 03 §3.11.2).

    broker = get_broker()
    worker = Worker(broker, queues={"quality_gate", "embed", "index"}, worker_timeout=30_000)
    worker.start()
    try:
        quality_gate_actor.send(job_id)
        for queue in ("quality_gate", "embed", "index"):
            broker.join(queue, timeout=60_000)
        worker.join()

        with Session(engine) as session:
            run = session.get(IngestionRun, run_id)
            assert run.status == "COMPLETED"
            assert run.current_stage == "INDEXING"
            assert run.completed_at is not None

            rows = list(
                session.scalars(
                    select(LegalProvision).where(
                        LegalProvision.provision_id.in_(provision_ids)
                    )
                )
            )
            assert len(rows) == 3
            assert all(row.review_status == "ACCEPTED" for row in rows)

            review_items = list(
                session.scalars(
                    select(ReviewItem).where(ReviewItem.ingestion_run_id == run_id)
                )
            )
            assert review_items == []  # all ACCEPTED: no review items created

        # One upsert with exactly 3 points (deterministic point ids = row UUIDs).
        assert len(client.upserts) == 1
        collection, points = client.upserts[0]
        assert collection == "legal_provisions_active"
        assert len(points) == 3
        with Session(engine) as session:
            row_ids = {
                str(row.id)
                for row in session.scalars(
                    select(LegalProvision).where(
                        LegalProvision.provision_id.in_(provision_ids)
                    )
                )
            }
        assert {point.id for point in points} == row_ids

        # The vocabulary was persisted once, keyed by SPARSE_ENCODER_VERSION.
        from app.retrieval.sparse import SPARSE_ENCODER_VERSION

        vocab_path = vocab_dir / f"{SPARSE_ENCODER_VERSION}.json"
        assert vocab_path.is_file()
        vocab_bytes_after_job1 = vocab_path.read_bytes()
        vocab = index_module.load_vocabulary(version=SPARSE_ENCODER_VERSION)
        assert vocab is not None
        shared_dimension = vocab["phạt"]  # token shared by Điều 7 + Khoản 1
        for point in points:
            sparse = point.vector.get("sparse")
            assert sparse is not None
            assert sparse.indices  # non-empty: tokens are in-vocabulary
        article_and_clause = [
            point
            for point in points
            if "diem" not in point.payload["provision_id"]  # Điều 7 + Khoản 1
        ]
        assert len(article_and_clause) == 2
        for point in article_and_clause:
            assert shared_dimension in point.vector["sparse"].indices

        # --- re-run: duplicate index message must not upsert again ---
        index_actor.send(job_id)
        broker.join("index", timeout=60_000)
        worker.join()
        assert len(client.upserts) == 1  # no duplicate points

        # --- second job: corpus grows, vocabulary must NOT drift ---
        document_id_2 = _document_id()
        job_id_2 = _unique("job")
        _seed_gate_pipeline(engine, document_id_2, job_id_2)
        with Session(engine) as session:
            article_2 = session.scalar(
                select(LegalProvision).where(
                    LegalProvision.provision_id == f"{document_id_2}__dieu-7"
                )
            )
            # New content brings a brand-new token into the corpus.
            article_2.retrieval_text = article_2.source_text = (
                "Điều 7. Xử phạt người điều khiển xe mô tô nghiệp vụ mới"
            )
            session.commit()

        quality_gate_actor.send(job_id_2)
        for queue in ("quality_gate", "embed", "index"):
            broker.join(queue, timeout=60_000)
        worker.join()

        assert len(client.upserts) == 2  # second job upserted its own points
        _, points_2 = client.upserts[1]
        assert len(points_2) == 3
        # Same token -> same dimension as job 1: the persisted vocabulary was
        # REUSED, not refitted.
        assert vocab_path.read_bytes() == vocab_bytes_after_job1
        for point in points_2:
            sparse = point.vector.get("sparse")
            assert sparse is not None and sparse.indices
        for point in points_2:
            if "diem" not in point.payload["provision_id"]:
                assert shared_dimension in point.vector["sparse"].indices
        # The new token stayed out-of-vocabulary: no silent sparse-space drift.
        assert "nghiệp" not in index_module.load_vocabulary(version=SPARSE_ENCODER_VERSION)
    finally:
        worker.stop()


def test_needs_review_creates_review_items_and_halts(
    queue_env: Any, clean_queues: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A provision routed NEEDS_REVIEW yields a ReviewItem and PENDING_REVIEW.

    Re-running the gate must not duplicate review items.
    """
    engine = queue_env
    document_id = _document_id()
    job_id = _unique("job")
    run_id, provision_ids = _seed_gate_pipeline(engine, document_id, job_id)

    # Drop the effective_from on the POINT -> routing marks it NEEDS_REVIEW
    # (policy row 6: uncertain effective date is never auto-accepted).
    with Session(engine) as session:
        point = session.scalar(
            select(LegalProvision).where(
                LegalProvision.provision_id == provision_ids[2]
            )
        )
        point.effective_from = None
        session.commit()

    monkeypatch.setattr(index_module, "_get_qdrant_client", lambda: _RecordingClient())
    broker = get_broker()
    worker = Worker(broker, queues={"quality_gate"}, worker_timeout=30_000)
    worker.start()
    try:
        quality_gate_actor.send(job_id)
        broker.join("quality_gate", timeout=60_000)
        worker.join()

        with Session(engine) as session:
            run = session.get(IngestionRun, run_id)
            assert run.status == "PENDING_REVIEW"
            assert run.current_stage == "QUALITY_CHECK"
            items = list(
                session.scalars(
                    select(ReviewItem).where(ReviewItem.ingestion_run_id == run_id)
                )
            )
            assert len(items) == 1
            assert items[0].target_id == provision_ids[2]
            assert items[0].status == "PENDING"  # the review queue
            assert "UNKNOWN_EFFECTIVE_DATE" in items[0].reason_code

        # Re-run: gating again must not create a second review item.
        quality_gate_actor.send(job_id)
        broker.join("quality_gate", timeout=60_000)
        worker.join()
        with Session(engine) as session:
            items = list(
                session.scalars(
                    select(ReviewItem).where(ReviewItem.ingestion_run_id == run_id)
                )
            )
            assert len(items) == 1
    finally:
        worker.stop()


# --- dead letter queue -----------------------------------------------------------


def test_failed_message_lands_in_dead_letter_queue(queue_env: Any, clean_queues: None) -> None:
    """A permanently-failed message lands in ``default.DLQ`` (doc 03 §3.13.6)."""
    broker = get_broker()
    queue = f"fail-{uuid.uuid4().hex[:8]}"
    actor_name = f"failing_{uuid.uuid4().hex[:8]}"

    @dramatiq.actor(  # noqa: E501 - decorator options
        broker=broker, queue_name=queue, actor_name=actor_name, max_retries=0, time_limit=60
    )
    def failing_actor(payload: str) -> None:  # pragma: no cover - always raises
        raise RuntimeError(f"boom {payload}")

    worker = Worker(broker, queues={queue}, worker_timeout=5_000)
    worker.start()
    try:
        failing_actor.send("x")
        broker.join(queue, timeout=30_000)
        worker.join()
    finally:
        worker.stop()

    consumer = broker.consume("default.DLQ", timeout=1_000)
    proxy = next(consumer, None)  # Redis consumers are iterators
    assert proxy is not None, "failed message did not reach the DLQ"
    assert proxy.actor_name == actor_name
    assert proxy.options["dlq_original_queue"] == queue
    consumer.ack(proxy)
