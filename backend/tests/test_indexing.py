"""Unit + integration tests: idempotent provision indexing (VNLRAG-44).

Covers the contract implemented in ``app.retrieval.indexing``:

- ``point_id_for`` determinism (the point id IS the provision row UUID);
- ``build_point`` payload completeness (full doc 03 §3.11.3 key set via
  ``qdrant_store.payload_for_unit``) plus dense/sparse vector inclusion when
  the providers are given and absence when they are ``None``;
- ``index_provision_units`` idempotency against a recording fake client
  (re-running upserts the same point ids — replace, never duplicate; a unit
  listed twice collapses to one point);
- ``index_accepted_provisions`` selection boundary (only ACCEPTED rows are
  indexed; PENDING/NEEDS_REVIEW/REJECTED/DROPPED never) and the
  ``effective_from`` skip/count behaviour;
- one Qdrant integration test (guarded by reachability, THROWAWAY collection):
  index, re-index (point count stable), read back payload + vectors, clean up.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient, models
from sqlalchemy.sql import operators
from sqlalchemy.sql.elements import BinaryExpression, BindParameter, BooleanClauseList

from app.config import get_qdrant_settings
from app.ingestion.retrieval_units import RetrievalUnit
from app.persistence.models import LegalProvision
from app.retrieval.contracts import result_from_payload
from app.retrieval.indexing import (
    ACCEPTED_REVIEW_STATUS,
    IndexResult,
    build_point,
    index_accepted_provisions,
    index_provision_units,
    point_id_for,
    provision_row_to_unit,
)
from app.retrieval.qdrant_store import (
    DENSE_VECTOR_NAME,
    DENSE_VECTOR_SIZE,
    PROVISION_ALIAS,
    SPARSE_VECTOR_NAME,
    build_collection_config,
)
from app.retrieval.sparse import BM25SparseEncoder

#: The full key set ``qdrant_store.payload_for_unit`` emits: the doc 03
#: §3.11.3 keys plus the ingest-only extras (node_kind/heading, content
#: version, verbatim source text, document-version UUID) — mirror of the
#: contract constant asserted in test_qdrant_store.py.
PAYLOAD_KEYS = frozenset(
    {
        "provision_id",
        "provision_version",
        "document_id",
        "document_version",
        "document_number",
        "document_type",
        "document_title",
        "article",
        "clause",
        "point",
        "chapter",
        "section",
        "vehicle_types",
        "effective_from",
        "effective_to",
        "document_status",
        "review_status",
        "page_number",
        "content_hash",
        "parser",
        "parser_version",
        "legal_parser_version",
        "sparse_encoder_version",
        "text",
        "parent_context",
        "relations",
        "node_kind",
        "heading",
        "content_version",
        "source_text",
        "document_version_id",
    }
)

#: The exact doc 03 §3.11.3 key set the contract mandates (doc names).
DOC_03_311_KEYS = frozenset(
    {
        "provision_id",
        "provision_version",
        "document_id",
        "document_version",
        "document_number",
        "document_type",
        "document_title",
        "article",
        "clause",
        "point",
        "chapter",
        "section",
        "vehicle_types",
        "effective_from",
        "effective_to",
        "document_status",
        "review_status",
        "page_number",
        "content_hash",
        "parser",
        "parser_version",
        "legal_parser_version",
        "sparse_encoder_version",
        "text",
        "parent_context",
        "relations",
    }
)


# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


def _unit(**overrides: object) -> RetrievalUnit:
    """Build a ``RetrievalUnit`` with minimal required fields."""
    values: dict[str, object] = {
        "unit_id": "nd-168-2024__dieu-7__khoan-4__diem-b__v1",
        "provision_id": "nd-168-2024__dieu-7__khoan-4__diem-b",
        "version": 1,
        "node_kind": "POINT",
        "retrieval_text": "Khoản 4 Điều 7: a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        "source_text": "a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        "parent_context": "Khoản 4 Điều 7 Nghị định 168/2024/NĐ-CP",
        "page_number": 12,
        "document_id": "8f3c1a2b-4d5e-4f6a-9b8c-7d6e5f4a3b2c",
        "short_point": True,
    }
    values.update(overrides)
    return RetrievalUnit(**values)  # type: ignore[arg-type]


def _row(**overrides: object) -> LegalProvision:
    """Build an in-memory ``LegalProvision`` row (no DB session needed)."""
    values: dict[str, object] = {
        "id": uuid.uuid4(),
        "provision_id": "nd-168-2024__dieu-7__khoan-4__diem-b",
        "document_version_id": uuid.uuid4(),
        "node_kind": "POINT",
        "chapter": None,
        "section": None,
        "article": "7",
        "clause": "4",
        "point": "b",
        "heading": None,
        "source_text": "a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        "retrieval_text": "Khoản 4 Điều 7: a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
        "parent_context": "Khoản 4 Điều 7 Nghị định 168/2024/NĐ-CP",
        "effective_from": date(2025, 1, 1),
        "effective_to": None,
        "status": "EFFECTIVE",
        "page_number": 12,
        "content_hash": "a" * 64,
        "version": 1,
        "review_status": ACCEPTED_REVIEW_STATUS,
    }
    values.update(overrides)
    return LegalProvision(**values)  # type: ignore[arg-type]


class _FakeEmbedder:
    """Deterministic dense embedder (no API); records ``embed_batch`` calls.

    ``fail=True`` makes every call raise, simulating a provider outage.
    """

    name = "fake-embedder"
    dims: int
    batch_size = 32

    def __init__(self, *, dims: int = DENSE_VECTOR_SIZE, fail: bool = False) -> None:
        self.dims = dims
        self.fail = fail
        self.batch_calls: list[list[str]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("embedding provider down")
        self.batch_calls.append(list(texts))
        return [self._vector(text) for text in texts]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)

    def _vector(self, text: str) -> list[float]:
        seed = sum(ord(char) for char in text)
        return [float((seed + index) % 7) / 10 for index in range(self.dims)]


class _FakeSparseEncoder:
    """Minimal ``SparseEncoder``-shaped fake with deterministic weights."""

    name = "fake-bm25"
    version = "fake-bm25-v1"
    vocabulary: dict[str, int] = {}

    def __init__(self, *, empty: bool = False, version: str = "fake-bm25-v1") -> None:
        self.empty = empty
        self.version = version

    def encode(self, text: str) -> dict[int, float]:
        return {} if self.empty else {1: 1.0, 2: 0.5}

    def encode_batch(self, texts: list[str]) -> list[dict[int, float]]:
        return [self.encode(text) for text in texts]

    def fit(self, documents: list[str]) -> None:  # pragma: no cover — fake
        pass


class _RecordingClient:
    """Minimal QdrantClient stand-in recording upsert calls (no live Qdrant)."""

    def __init__(self) -> None:
        self.upserts: list[tuple[str, list[models.PointStruct]]] = []

    def upsert(self, *, collection_name: str, points: list[models.PointStruct]) -> None:
        self.upserts.append((collection_name, points))


def _row_matches(row: LegalProvision, clause: object) -> bool:
    """Evaluate a simple ``column == literal`` whereclause against a row.

    Supports the shape ``index_accepted_provisions`` issues (a single
    ``review_status == 'ACCEPTED'`` equality, possibly combined with
    ``and_``/``or_``). Any unsupported clause shape is treated as matching —
    the fake models the DB faithfully for the equality filters it is given.
    """
    if clause is None:
        return True
    if isinstance(clause, BooleanClauseList):
        return all(_row_matches(row, child) for child in clause.get_children())
    if isinstance(clause, BinaryExpression) and clause.operator is operators.eq:
        left, right = clause.left, clause.right
        if isinstance(right, BindParameter):
            right = right.value
        column_name = getattr(left, "name", None)
        if column_name is not None and hasattr(row, column_name):
            return getattr(row, column_name) == right
    return True


class _ScalarResult:
    """Iterable stand-in for ``Session.scalars`` output."""

    def __init__(self, rows: list[LegalProvision]) -> None:
        self._rows = rows

    def __iter__(self):
        return iter(self._rows)


class _FakeSession:
    """Session stand-in that applies the statement's WHERE clause to its rows.

    ``last_stmt`` records the statement the caller issued, so tests can also
    assert the query itself (e.g. that selection filters on
    ``review_status == 'ACCEPTED'``).
    """

    def __init__(self, rows: list[LegalProvision]) -> None:
        self._rows = rows
        self.last_stmt = None

    def scalars(self, stmt):
        self.last_stmt = stmt
        matching = [row for row in self._rows if _row_matches(row, stmt.whereclause)]
        return _ScalarResult(matching)


# ---------------------------------------------------------------------------
# point_id_for — determinism
# ---------------------------------------------------------------------------


def test_point_id_for_is_the_row_uuid_string() -> None:
    row_id = uuid.uuid4()
    assert point_id_for(row_id) == str(row_id)
    assert uuid.UUID(point_id_for(row_id)) == row_id


def test_point_id_for_is_deterministic() -> None:
    row_id = uuid.uuid4()
    assert point_id_for(row_id) == point_id_for(row_id)


# ---------------------------------------------------------------------------
# build_point — payload completeness + vector inclusion/absence
# ---------------------------------------------------------------------------


def test_build_point_payload_contains_exactly_the_contract_keys() -> None:
    point = build_point(_unit(), point_id="p-1")
    assert point.id == "p-1"
    assert set(point.payload) == PAYLOAD_KEYS
    assert set(point.payload) >= DOC_03_311_KEYS
    assert point.vector == {}


def test_build_point_maps_unit_fields_and_metadata() -> None:
    unit = _unit()
    point = build_point(
        unit,
        point_id="p-1",
        review_status="ACCEPTED",
        effective_from="2025-01-01",
        effective_to="2026-01-01",
        parser_version="docling-2.1.0",
        legal_parser_version="vnlrag-legal-parser-v1",
        sparse_encoder_version="bm25-v1",
        content_version=3,
        relations=[{"relation_type": "PENALTY_COMPANION", "target_provision_id": "p-9"}],
        vehicle_types=["MOTORCYCLE", "CAR"],
        document_version_id="11111111-2222-3333-4444-555555555555",
        document_status="EFFECTIVE",
        chapter="Chương I",
        section="Mục 1",
        article="7",
        clause="4",
        point="b",
        heading=None,
        document_number="168/2024/NĐ-CP",
        document_type="DECREE",
        document_title="Nghị định quy định xử phạt vi phạm hành chính",
        document_version=2,
        document_id="nd-168-2024",
        parser="DOCLING",
        content_hash="b" * 64,
    )
    payload = point.payload
    assert payload["provision_id"] == unit.provision_id
    assert payload["provision_version"] == unit.version
    assert payload["node_kind"] == unit.node_kind
    assert payload["text"] == unit.retrieval_text
    assert payload["source_text"] == unit.source_text
    assert payload["parent_context"] == unit.parent_context
    assert payload["page_number"] == unit.page_number
    assert payload["document_version_id"] == "11111111-2222-3333-4444-555555555555"
    assert payload["document_id"] == "nd-168-2024"
    assert payload["review_status"] == "ACCEPTED"
    assert payload["effective_from"] == "2025-01-01"
    assert payload["effective_to"] == "2026-01-01"
    assert payload["parser_version"] == "docling-2.1.0"
    assert payload["legal_parser_version"] == "vnlrag-legal-parser-v1"
    assert payload["sparse_encoder_version"] == "bm25-v1"
    assert payload["content_version"] == 3
    assert payload["relations"] == [
        {"relation_type": "PENALTY_COMPANION", "target_provision_id": "p-9"}
    ]
    assert payload["vehicle_types"] == ["MOTORCYCLE", "CAR"]
    assert payload["chapter"] == "Chương I"
    assert payload["section"] == "Mục 1"
    assert payload["article"] == "7"
    assert payload["clause"] == "4"
    assert payload["point"] == "b"
    assert payload["heading"] is None
    assert payload["document_number"] == "168/2024/NĐ-CP"
    assert payload["document_type"] == "DECREE"
    assert payload["document_title"] == "Nghị định quy định xử phạt vi phạm hành chính"
    assert payload["document_version"] == 2
    assert payload["document_status"] == "EFFECTIVE"
    assert payload["parser"] == "DOCLING"
    assert payload["content_hash"] == "b" * 64


def test_build_point_dense_included_when_embedder_given() -> None:
    unit = _unit()
    embedder = _FakeEmbedder()
    point = build_point(unit, point_id="p-1", embedder=embedder)
    assert point.vector["dense"] == embedder.embed([unit.retrieval_text])[0]
    assert "sparse" not in point.vector
    assert point.payload["sparse_encoder_version"] is None


def test_build_point_sparse_included_when_encoder_given() -> None:
    unit = _unit()
    encoder = _FakeSparseEncoder()
    point = build_point(unit, point_id="p-1", sparse_encoder=encoder)
    assert "dense" not in point.vector
    assert point.vector["sparse"] == models.SparseVector(indices=[1, 2], values=[1.0, 0.5])
    assert point.payload["sparse_encoder_version"] == encoder.version


def test_build_point_both_vectors_when_both_providers_given() -> None:
    unit = _unit()
    embedder = _FakeEmbedder()
    encoder = _FakeSparseEncoder()
    point = build_point(unit, point_id="p-1", embedder=embedder, sparse_encoder=encoder)
    assert point.vector["dense"] == embedder.embed([unit.retrieval_text])[0]
    assert point.vector["sparse"] == models.SparseVector(indices=[1, 2], values=[1.0, 0.5])
    assert point.payload["sparse_encoder_version"] == encoder.version


def test_build_point_vectors_absent_when_providers_none() -> None:
    point = build_point(_unit(), point_id="p-1")
    assert point.vector == {}


def test_build_point_precomputed_vectors_win_and_provider_not_called() -> None:
    embedder = _FakeEmbedder(fail=True)  # raises if actually called
    point = build_point(
        _unit(),
        point_id="p-1",
        embedder=embedder,
        sparse_encoder=_FakeSparseEncoder(),
        dense_vector=[0.5, 0.25],
        sparse_weights={1: 2.0},
    )
    assert embedder.batch_calls == []
    assert point.vector["dense"] == [0.5, 0.25]
    assert point.vector["sparse"] == models.SparseVector(indices=[1], values=[2.0])


def test_build_point_empty_sparse_weights_are_omitted() -> None:
    point = build_point(_unit(), point_id="p-1", sparse_weights={})
    assert "sparse" not in point.vector


# ---------------------------------------------------------------------------
# index_provision_units — idempotency, batching, error isolation
# ---------------------------------------------------------------------------


def test_index_units_upserts_into_alias_with_review_status() -> None:
    unit = _unit()
    client = _RecordingClient()
    result = index_provision_units(
        client, [unit], point_ids={unit.unit_id: "p-1"}, review_status="ACCEPTED"
    )
    assert result.indexed == 1
    assert result.skipped_no_effective_from == 0
    assert result.errors == []
    assert len(client.upserts) == 1
    collection_name, points = client.upserts[0]
    assert collection_name == PROVISION_ALIAS
    assert [point.id for point in points] == ["p-1"]
    assert points[0].payload["review_status"] == "ACCEPTED"


def test_index_units_collection_override() -> None:
    unit = _unit()
    client = _RecordingClient()
    index_provision_units(
        client, [unit], point_ids={unit.unit_id: "p-1"}, collection="scratch-collection"
    )
    (collection_name, _points) = client.upserts[0]
    assert collection_name == "scratch-collection"


def test_index_units_rerun_reuses_same_point_ids() -> None:
    """Idempotency: re-running upserts the SAME point id — replace, no duplicates."""
    unit = _unit()
    point_ids = {unit.unit_id: "p-1"}
    client = _RecordingClient()
    first = index_provision_units(client, [unit], point_ids=point_ids)
    second = index_provision_units(client, [unit], point_ids=point_ids)
    assert first.indexed == 1
    assert second.indexed == 1
    assert len(client.upserts) == 2
    for _collection, points in client.upserts:
        assert [point.id for point in points] == ["p-1"]


def test_index_units_duplicate_unit_in_call_collapses_to_one_point() -> None:
    unit = _unit()
    client = _RecordingClient()
    result = index_provision_units(client, [unit, unit], point_ids={unit.unit_id: "p-1"})
    assert result.indexed == 1
    assert len(client.upserts) == 1
    assert len(client.upserts[0][1]) == 1


def test_index_units_missing_point_id_is_error_not_indexed() -> None:
    unit = _unit()
    client = _RecordingClient()
    result = index_provision_units(client, [unit], point_ids={})
    assert result.indexed == 0
    assert result.errors == [f"no point id for unit {unit.unit_id}"]
    assert client.upserts == []


def test_index_units_payload_only_points_when_no_providers() -> None:
    unit = _unit()
    client = _RecordingClient()
    result = index_provision_units(
        client, [unit], point_ids={unit.unit_id: "p-1"}, review_status="ACCEPTED"
    )
    assert result.indexed == 1
    (_, points) = client.upserts[0]
    assert points[0].vector == {}
    assert points[0].payload["provision_id"] == unit.provision_id


def test_index_units_batches_embedding_by_batch_size() -> None:
    units = [_unit(unit_id=f"u{index}", provision_id=f"p-{index}") for index in range(5)]
    point_ids = {unit.unit_id: f"point-{index}" for index, unit in enumerate(units)}
    embedder = _FakeEmbedder()
    client = _RecordingClient()
    result = index_provision_units(
        client, units, point_ids=point_ids, embedder=embedder, batch_size=2
    )
    assert result.indexed == 5
    assert [len(call) for call in embedder.batch_calls] == [2, 2, 1]
    assert len(client.upserts) == 3


def test_index_units_embedding_failure_recorded_and_skipped() -> None:
    unit = _unit()
    client = _RecordingClient()
    result = index_provision_units(
        client,
        [unit],
        point_ids={unit.unit_id: "p-1"},
        embedder=_FakeEmbedder(fail=True),
    )
    assert result.indexed == 0
    assert len(result.errors) == 1
    assert "failed" in result.errors[0]
    assert client.upserts == []


def test_index_units_per_unit_payload_overrides_flat_kwargs() -> None:
    units = [
        _unit(unit_id="u1", provision_id="p-1"),
        _unit(unit_id="u2", provision_id="p-2"),
    ]
    client = _RecordingClient()
    result = index_provision_units(
        client,
        units,
        point_ids={"u1": "1", "u2": "2"},
        effective_from="2025-01-01",
        unit_payloads={"u2": {"effective_from": "2026-06-01"}},
    )
    assert result.indexed == 2
    by_id = {point.id: point.payload for _c, points in client.upserts for point in points}
    assert by_id["1"]["effective_from"] == "2025-01-01"
    assert by_id["2"]["effective_from"] == "2026-06-01"


# ---------------------------------------------------------------------------
# index_accepted_provisions — selection boundary + effective_from handling
# ---------------------------------------------------------------------------


def test_only_accepted_rows_are_indexed() -> None:
    accepted_1 = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-1")
    accepted_2 = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-2")
    pending = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-3", review_status="PENDING")
    needs_review = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-4", review_status="NEEDS_REVIEW")
    rejected = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-5", review_status="REJECTED")
    dropped = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-6", review_status="DROPPED")
    client = _RecordingClient()
    session = _FakeSession([accepted_1, accepted_2, pending, needs_review, rejected, dropped])

    result = index_accepted_provisions(client, session=session)

    assert result.indexed == 2
    assert result.skipped_no_effective_from == 0
    assert result.errors == []
    # Enforcement happens at selection: the issued query filters on ACCEPTED.
    assert session.last_stmt is not None
    assert session.last_stmt.whereclause is not None
    assert session.last_stmt.whereclause.compare(
        LegalProvision.review_status == ACCEPTED_REVIEW_STATUS
    )
    point_ids = [point.id for _c, points in client.upserts for point in points]
    assert sorted(point_ids) == sorted(point_id_for(row.id) for row in (accepted_1, accepted_2))
    for _c, points in client.upserts:
        for point in points:
            assert point.payload["review_status"] == ACCEPTED_REVIEW_STATUS


def test_effective_from_none_skipped_and_counted() -> None:
    with_interval = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-1")
    without_interval = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-2", effective_from=None)
    client = _RecordingClient()

    result = index_accepted_provisions(
        client, session=_FakeSession([with_interval, without_interval])
    )

    assert result.indexed == 1
    assert result.skipped_no_effective_from == 1
    point_ids = [point.id for _c, points in client.upserts for point in points]
    assert point_ids == [point_id_for(with_interval.id)]


def test_effective_from_not_required_indexes_missing_interval() -> None:
    without_interval = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-2", effective_from=None)
    client = _RecordingClient()

    result = index_accepted_provisions(
        client, session=_FakeSession([without_interval]), effective_from_required=False
    )

    assert result.indexed == 1
    assert result.skipped_no_effective_from == 0
    (_, points) = client.upserts[0]
    assert points[0].payload["effective_from"] is None


def test_row_metadata_mapped_into_payload_and_point_id() -> None:
    row_id = uuid.uuid4()
    document_version_id = uuid.uuid4()
    row = _row(
        id=row_id,
        document_version_id=document_version_id,
        chapter="Chương I",
        section="Mục 1",
        article="7",
        clause="4",
        point="b",
        effective_from=date(2025, 1, 1),
        effective_to=date(2026, 1, 1),
        content_hash="c" * 64,
    )
    client = _RecordingClient()

    result = index_accepted_provisions(client, session=_FakeSession([row]))

    assert result.indexed == 1
    (_, points) = client.upserts[0]
    payload = points[0].payload
    assert points[0].id == point_id_for(row_id)
    assert payload["provision_id"] == row.provision_id
    assert payload["document_version_id"] == str(document_version_id)
    # document_id is the LOGICAL document id derived from the provision_id
    # slug prefix, never the document-version UUID.
    assert payload["document_id"] == "nd-168-2024"
    assert payload["effective_from"] == "2025-01-01"
    assert payload["effective_to"] == "2026-01-01"
    assert payload["chapter"] == "Chương I"
    assert payload["section"] == "Mục 1"
    assert payload["article"] == "7"
    assert payload["clause"] == "4"
    assert payload["point"] == "b"
    assert payload["content_hash"] == "c" * 64
    assert payload["text"] == row.retrieval_text
    assert payload["source_text"] == row.source_text

def test_accepted_payload_maps_authoritative_document_citation_metadata() -> None:
    row = _row(id=uuid.uuid4())
    document = SimpleNamespace(
        document_id="nd-168-2024",
        document_number="168/2024/NĐ-CP",
        document_type="DECREE",
        document_title="Nghị định 168",
        status="ACTIVE",
    )
    row_with_document = SimpleNamespace(
        **{name: getattr(row, name) for name in (
            "id", "provision_id", "document_version_id", "node_kind", "chapter",
            "section", "article", "clause", "point", "heading", "source_text",
            "retrieval_text", "parent_context", "effective_from", "effective_to",
            "status", "page_number", "content_hash", "version", "review_status",
        )},
        document_version=SimpleNamespace(
            version=3,
            manifest_json={"vehicle_types": ["xe máy"]},
            document=document,
        ),
    )
    client = _RecordingClient()

    result = index_accepted_provisions(client, session=_FakeSession([row_with_document]))

    assert result.indexed == 1
    payload = client.upserts[0][1][0].payload
    assert payload["document_id"] == "nd-168-2024"
    assert payload["document_number"] == "168/2024/NĐ-CP"
    assert payload["document_type"] == "DECREE"
    assert payload["document_title"] == "Nghị định 168"
    assert payload["document_status"] == "ACTIVE"
    assert payload["vehicle_types"] == ["xe máy"]
    assert payload["document_version"] == 3

    assert result_from_payload(payload, rank=1, score=0.9, source="dense").document_number == (
        "168/2024/NĐ-CP"
    )
    assert payload["review_status"] == ACCEPTED_REVIEW_STATUS


def test_accepted_index_collection_override_and_common_metadata() -> None:
    row = _row(id=uuid.uuid4(), provision_id="nd-1__dieu-1")
    client = _RecordingClient()

    result = index_accepted_provisions(
        client,
        session=_FakeSession([row]),
        collection="scratch-collection",
        parser_version="docling-2.1.0",
        vehicle_types=["MOTORCYCLE"],
    )

    assert result.indexed == 1
    (collection_name, points) = client.upserts[0]
    assert collection_name == "scratch-collection"
    assert points[0].payload["parser_version"] == "docling-2.1.0"
    assert points[0].payload["vehicle_types"] == ["MOTORCYCLE"]


def test_accepted_index_with_embedder_and_sparse_encoder() -> None:
    row = _row(id=uuid.uuid4())
    embedder = _FakeEmbedder()
    encoder = _FakeSparseEncoder()
    client = _RecordingClient()

    result = index_accepted_provisions(
        client, session=_FakeSession([row]), embedder=embedder, sparse_encoder=encoder
    )

    assert result.indexed == 1
    (_, points) = client.upserts[0]
    assert points[0].vector["dense"] == embedder.embed([row.retrieval_text])[0]
    assert points[0].vector["sparse"] == models.SparseVector(indices=[1, 2], values=[1.0, 0.5])
    assert points[0].payload["sparse_encoder_version"] == encoder.version


# ---------------------------------------------------------------------------
# provision_row_to_unit — row -> unit mapper
# ---------------------------------------------------------------------------


def test_provision_row_to_unit_maps_row_fields() -> None:
    document_version_id = uuid.uuid4()
    row = _row(
        id=uuid.uuid4(),
        document_version_id=document_version_id,
        version=3,
        source_text="a) Điều khiển",  # 3 whitespace tokens -> short point
    )
    unit = provision_row_to_unit(row)
    assert unit.unit_id == f"{row.provision_id}__v3"
    assert unit.provision_id == row.provision_id
    assert unit.version == 3
    assert unit.node_kind == row.node_kind
    assert unit.retrieval_text == row.retrieval_text
    assert unit.source_text == row.source_text
    assert unit.parent_context == row.parent_context
    assert unit.page_number == row.page_number
    assert unit.document_id == str(document_version_id)
    # POINT of <= 3 whitespace tokens -> short_point (extractor rule, recomputed).
    assert unit.short_point is True


def test_provision_row_to_unit_short_point_rule() -> None:
    long_point = _row(
        id=uuid.uuid4(),
        node_kind="POINT",
        source_text="a) Một điểm có nội dung dài hơn ba từ",
    )
    article = _row(id=uuid.uuid4(), node_kind="ARTICLE", source_text="Điều 7. Xử phạt vi phạm")
    assert provision_row_to_unit(long_point).short_point is False
    assert provision_row_to_unit(article).short_point is False  # POINT rule only


# ---------------------------------------------------------------------------
# IndexResult contract
# ---------------------------------------------------------------------------


def test_index_result_forbids_extra_fields() -> None:
    with pytest.raises(ValidationError):
        IndexResult(indexed=1, extra_field=1)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Integration — Qdrant round-trip (guarded by reachability, throwaway collection)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qdrant_client() -> Iterator[QdrantClient]:
    """Qdrant client for the module; skipped when the server is unreachable."""
    settings = get_qdrant_settings()
    kwargs: dict[str, object] = {"url": settings.url, "api_key": settings.api_key or None}
    probe = QdrantClient(timeout=3, **kwargs)
    try:
        probe.get_collections()
    except Exception:
        probe.close()
        pytest.skip(
            f"Qdrant not reachable at {settings.url} — skipping integration test "
            "(start the vnlaw-qdrant docker-compose service to run it)"
        )
    probe.close()
    client = QdrantClient(timeout=30, **kwargs)
    try:
        yield client
    finally:
        client.close()


@pytest.fixture()
def scratch_collection(qdrant_client: QdrantClient) -> Iterator[str]:
    """THROWAWAY collection with the production config; deleted afterwards."""
    name = f"legal_provisions_v1_index_test_{uuid.uuid4().hex[:8]}"
    qdrant_client.create_collection(collection_name=name, **build_collection_config())
    try:
        yield name
    finally:
        if qdrant_client.collection_exists(name):
            qdrant_client.delete_collection(name)


@pytest.mark.integration
def test_index_provision_units_round_trips_through_qdrant(
    qdrant_client: QdrantClient, scratch_collection: str
) -> None:
    units = [
        _unit(
            unit_id="nd-168-2024__dieu-7__khoan-4__diem-b__v1",
            provision_id="nd-168-2024__dieu-7__khoan-4__diem-b",
            retrieval_text="Khoản 4 Điều 7: a) Điều khiển xe lạng lách, đánh võng",
        ),
        _unit(
            unit_id="nd-168-2024__dieu-8__khoan-1__diem-a__v1",
            provision_id="nd-168-2024__dieu-8__khoan-1__diem-a",
            retrieval_text="Khoản 1 Điều 8: a) Điều khiển xe chạy quá tốc độ",
            short_point=False,
        ),
    ]
    point_ids = {unit.unit_id: str(uuid.uuid4()) for unit in units}
    embedder = _FakeEmbedder(dims=DENSE_VECTOR_SIZE)
    encoder = BM25SparseEncoder()
    encoder.fit([unit.retrieval_text for unit in units])

    first = index_provision_units(
        qdrant_client,
        units,
        point_ids=point_ids,
        embedder=embedder,
        sparse_encoder=encoder,
        collection=scratch_collection,
        review_status="ACCEPTED",
        effective_from="2025-01-01",
        content_version=1,
    )
    assert first.indexed == 2
    assert first.errors == []
    assert qdrant_client.count(collection_name=scratch_collection, exact=True).count == 2

    # Re-index: same deterministic point ids -> replace, point count stays 2.
    second = index_provision_units(
        qdrant_client,
        units,
        point_ids=point_ids,
        embedder=embedder,
        sparse_encoder=encoder,
        collection=scratch_collection,
        review_status="ACCEPTED",
        effective_from="2025-01-01",
        content_version=1,
    )
    assert second.indexed == 2
    assert second.errors == []
    assert qdrant_client.count(collection_name=scratch_collection, exact=True).count == 2

    records = qdrant_client.retrieve(
        collection_name=scratch_collection,
        ids=list(point_ids.values()),
        with_vectors=True,
    )
    by_id = {record.id: record for record in records}
    assert set(by_id) == set(point_ids.values())
    for unit in units:
        record = by_id[point_ids[unit.unit_id]]
        assert record.payload["provision_id"] == unit.provision_id
        assert record.payload["text"] == unit.retrieval_text
        assert record.payload["source_text"] == unit.source_text
        assert record.payload["review_status"] == "ACCEPTED"
        assert record.payload["effective_from"] == "2025-01-01"
        assert set(record.payload) >= DOC_03_311_KEYS
        assert len(record.vector[DENSE_VECTOR_NAME]) == DENSE_VECTOR_SIZE
        sparse_vector = record.vector[SPARSE_VECTOR_NAME]
        assert sparse_vector.indices
        assert sparse_vector.values
