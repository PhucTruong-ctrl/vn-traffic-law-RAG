"""Opt-in Gate M2 proof: PostgreSQL acceptance -> real embedding -> Qdrant search."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from typing import Any

import pytest
from qdrant_client import QdrantClient, models
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.config import get_embedding_settings, get_qdrant_settings
from app.ingestion.temporal_resolver import resolve_temporal
from app.persistence.models import DocumentVersion, LegalDocument, LegalProvision
from app.persistence.repositories import TemporalRepository, content_hash
from app.retrieval import qdrant_store
from app.retrieval.embedding import ConfigError, get_embedding_provider
from app.retrieval.indexing import index_accepted_provisions, point_id_for
from app.retrieval.qdrant_store import DENSE_VECTOR_NAME, ensure_qdrant_collection

try:
    from conftest import _resolve_base_url, clean_transaction
except ImportError:
    from tests.integration.conftest import _resolve_base_url, clean_transaction

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
    gate_m2_engine, gate_m2_qdrant: tuple[QdrantClient, str]
) -> None:
    """Prove all M2 links with real services; no mocks or production seams."""
    settings = get_embedding_settings()
    key = settings.gemini_api_key if settings.provider == "gemini" else settings.jina_api_key
    if not key:
        pytest.skip(f"{settings.provider} embedding API key unavailable")
    try:
        embedder = get_embedding_provider(settings)
    except ConfigError as exc:
        pytest.skip(f"embedding provider unavailable: {type(exc).__name__}")

    client, collection = gate_m2_qdrant
    ensure_qdrant_collection(client)
    retrieval_text = "Điều 7. Quy định xác định cho bằng chứng Gate M2."
    temporal = resolve_temporal(
        {
            "effective_from": _ACCEPTED_AT.isoformat(),
            "review_status": "ACCEPTED",
            "provisions": [{"provision_id": _PROVISION_ID}],
        },
        [
            {
                "event_type": "EFFECTIVE",
                "event_date": _ACCEPTED_AT.isoformat(),
                "affected_provision_versions": [{"provision_id": _PROVISION_ID}],
                "review_status": "ACCEPTED",
            }
        ],
    )
    assert temporal.review_required is False
    assert temporal.versions[0].effective_from == _ACCEPTED_AT
    with clean_transaction(gate_m2_engine) as conn, Session(bind=conn) as session:
        document = LegalDocument(
            document_id="gate-m2-deterministic-document",
            document_number="M2/2026",
            document_title="Gate M2 deterministic fixture",
            document_type="DECREE",
            file_hash=content_hash("gate-m2-document"),
            status="EFFECTIVE",
        )
        session.add(document)
        session.flush()
        version = DocumentVersion(
            document_id=document.document_id,
            version=1,
            manifest_json={"fixture": "gate-m2"},
            content_hash=content_hash("gate-m2-version"),
            effective_from=_ACCEPTED_AT,
            review_status="ACCEPTED",
        )
        session.add(version)
        session.flush()
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
            review_status="ACCEPTED",
            effective_from=_ACCEPTED_AT,
        )
        session.add(provision)
        session.flush()

        accepted = TemporalRepository(session).valid_provisions(_ACCEPTED_AT)
        assert [row.provision_id for row in accepted] == [_PROVISION_ID], (
            "PostgreSQL temporal acceptance must return the deterministic ACCEPTED provision"
        )
        result = index_accepted_provisions(
            client,
            session=session,
            embedder=embedder,
            collection=collection,
            document_number=document.document_number,
            document_type=document.document_type,
            document_title=document.document_title,
            document_version="1",
            document_status=document.status,
            parser="gate-m2",
            parser_version="gate-m2",
            legal_parser_version="gate-m2",
            content_version="gate-m2",
            relations=[],
            vehicle_types=[],
        )
        assert result.indexed == 1, f"Qdrant indexing evidence: {result.model_dump()}"
        query_vector = embedder.embed([retrieval_text])[0]
        response = client.query_points(
            collection_name=collection,
            query=query_vector,
            using=DENSE_VECTOR_NAME,
            limit=3,
            with_payload=True,
        )
        point_ids = [str(point.id) for point in response.points]
        assert point_id_for(provision.id) in point_ids, (
            f"Qdrant search evidence: expected provision row {provision.id}, got {point_ids}; "
            f"provider={settings.provider}, model={settings.model}, "
            f"dimensions={settings.dimensions}"
        )
