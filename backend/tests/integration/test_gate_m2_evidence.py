"""Opt-in Gate M2 proof: PostgreSQL acceptance -> real embedding -> Qdrant search."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any

import pytest
from dramatiq.worker import Worker
from qdrant_client import QdrantClient, models
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.config import get_embedding_settings, get_qdrant_settings
from app.ingestion.actors.resolve_refs import resolve_refs_actor
from app.ingestion.actors.resolve_temporal import resolve_temporal_actor
from app.ingestion.queue import get_broker
from app.persistence.models import (
    DocumentElement,
    DocumentVersion,
    IngestionRun,
    LegalDocument,
    LegalProvision,
    ParsedDocument,
)
from app.persistence.repositories import content_hash
from app.retrieval import qdrant_store
from app.retrieval.embedding import ConfigError, get_embedding_provider
from app.retrieval.qdrant_store import DENSE_VECTOR_NAME, ensure_qdrant_collection

try:
    from conftest import _resolve_base_url
except ImportError:
    from tests.integration.conftest import _resolve_base_url
pytestmark = pytest.mark.integration

_ACCEPTED_AT = date(2026, 1, 15)
_PROVISION_ID = "gate-m2-deterministic__article-7"


@pytest.fixture()
def gate_m2_engine(request: pytest.FixtureRequest):
    """Load the existing migrated PostgreSQL fixture only after a reachability check."""
    try:
        base_url = _resolve_base_url()
        probe = create_engine(base_url, connect_args={"connect_timeout": 3})
        try:
            with probe.connect():
                pass
        finally:
            probe.dispose()
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: {type(exc).__name__}")
    return request.getfixturevalue("upgraded_engine")


@pytest.fixture()
def gate_m2_qdrant(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[QdrantClient, str]]:
    """Use a disposable collection and skip when Qdrant is unavailable."""
    settings = get_qdrant_settings()
    kwargs: dict[str, Any] = {"url": settings.url, "api_key": settings.api_key or None}
    client = QdrantClient(timeout=3, **kwargs)
    try:
        client.get_collections()
    except Exception:
        client.close()
        pytest.skip("Qdrant unavailable")

    suffix = uuid.uuid4().hex[:8]
    collection = f"legal_provisions_v1_gate_m2_{suffix}"
    alias = f"legal_provisions_active_gate_m2_{suffix}"
    monkeypatch.setattr(qdrant_store, "PROVISION_COLLECTION", collection)
    monkeypatch.setattr(qdrant_store, "PROVISION_ALIAS", alias)
    try:
        yield client, collection
    finally:
        if any(item.alias_name == alias for item in client.get_aliases().aliases):
            client.update_collection_aliases(
                [models.DeleteAliasOperation(delete_alias=models.DeleteAlias(alias_name=alias))]
            )
        if client.collection_exists(collection):
            client.delete_collection(collection)
        client.close()


def test_gate_m2_accepts_temporal_provision_and_finds_it(
    gate_m2_engine, gate_m2_qdrant: tuple[QdrantClient, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Prove persisted source -> resolver actors -> real embedding/index/search."""
    settings = get_embedding_settings()
    key = settings.gemini_api_key if settings.provider == "gemini" else settings.jina_api_key
    if not key:
        pytest.skip(f"{settings.provider} embedding API key unavailable")
    try:
        embedder = get_embedding_provider(settings)
    except ConfigError as exc:
        pytest.skip(f"embedding provider unavailable: {type(exc).__name__}")

    broker = get_broker()
    try:
        broker.client.ping()
    except Exception:
        pytest.skip("Redis unavailable")
    monkeypatch.setenv(
        "DATABASE_URL", gate_m2_engine.url.render_as_string(hide_password=False)
    )

    client, collection = gate_m2_qdrant
    ensure_qdrant_collection(client)
    retrieval_text = "Điều 7. Quy định xác định cho bằng chứng Gate M2."
    document_id = "gate-m2-deterministic-document"
    job_id = "gate-m2-deterministic-job"
    with Session(gate_m2_engine) as session:
        document = LegalDocument(
            document_id=document_id,
            document_number="M2/2026",
            document_title="Gate M2 deterministic fixture",
            document_type="DECREE",
            file_hash=content_hash("gate-m2-document"),
            status="EFFECTIVE",
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document_id,
            version=1,
            manifest_json={"fixture": "gate-m2"},
            content_hash=content_hash("gate-m2-version"),
            review_status="PENDING",
        )
        session.add(version)
        run = IngestionRun(
            job_id=job_id,
            document_id=document_id,
            manifest_json={
                "fixture": "gate-m2",
                "effective_from": _ACCEPTED_AT.isoformat(),
                "provisions": [{"provision_id": _PROVISION_ID, "version": 1}],
                "effect_events": [
                    {
                        "event_type": "EFFECTIVE",
                        "event_date": _ACCEPTED_AT.isoformat(),
                        "affected_provision_versions": [
                            {"provision_id": _PROVISION_ID, "version": 1}
                        ],
                        "review_status": "ACCEPTED",
                    }
                ],
            },
            file_hash=content_hash("gate-m2-run"),
            status="RESOLVING_REFS",
            current_stage="RESOLVING_REFS",
        )
        session.add(run)
        session.flush()
        parsed = ParsedDocument(
            document_id=document_id,
            parser="gate-m2",
            parser_version="gate-m2",
            ir_schema_version="document-ir-v2",
            source_object_key="gate-m2/source.pdf",
            parse_status="SUCCESS",
            quality_report={},
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            completed_at=datetime(2026, 1, 1, 0, 0, 1, tzinfo=UTC),
        )
        session.add(parsed)
        session.flush()
        session.add(
            DocumentElement(
                parsed_document_id=parsed.id,
                element_id="gate-m2",
                element_type="heading",
                text=retrieval_text,
                page_number=1,
                bbox={"left": 0.1, "top": 0.1, "right": 0.9, "bottom": 0.2},
                reading_order=0,
                source_parser="gate-m2",
                parser_version="gate-m2",
                raw_reference={},
            )
        )
        provision = LegalProvision(
            provision_id=_PROVISION_ID,
            document_version_id=version.id,
            node_kind="ARTICLE",
            article="7",
            source_text=retrieval_text,
            retrieval_text=retrieval_text,
            status="EFFECTIVE",
            page_number=1,
            source_element_ids=["gate-m2"],
            content_hash=content_hash("gate-m2-provision"),
            version=1,
            review_status="PENDING",
        )
        session.add(provision)
        session.commit()
        provision_id = provision.id
        run_id = run.id

    worker = Worker(
        broker, queues={"resolve_refs", "resolve_temporal", "quality_gate", "embed", "index"}
    )
    worker.start()
    try:
        resolve_refs_actor.send(job_id)
        for queue in ("resolve_refs", "resolve_temporal", "quality_gate", "embed", "index"):
            broker.join(queue, timeout=60_000)
        worker.join()
    finally:
        worker.stop()

    with Session(gate_m2_engine) as session:
        run = session.get(IngestionRun, run_id)
        provision = session.scalar(
            select(LegalProvision).where(LegalProvision.id == provision_id)
        )
        assert run is not None and run.current_stage == "INDEXING"
        assert run.status == "COMPLETED"
        assert provision is not None
        assert provision.review_status == "ACCEPTED"
        assert provision.effective_from == _ACCEPTED_AT
        assert [row.provision_id for row in session.scalars(
            select(LegalProvision).where(LegalProvision.review_status == "ACCEPTED")
        ) if row.provision_id == _PROVISION_ID] == [_PROVISION_ID]

    query_vector = embedder.embed([retrieval_text])[0]
    response = client.query_points(
        collection_name=collection,
        query=query_vector,
        using=DENSE_VECTOR_NAME,
        limit=3,
        with_payload=True,
    )
    point_ids = [str(point.id) for point in response.points]
    assert str(provision_id) in point_ids, (
        f"Qdrant search evidence: expected provision row {provision_id}, got {point_ids}; "
        f"provider={settings.provider}, model={settings.model}, dimensions={settings.dimensions}"
    )
