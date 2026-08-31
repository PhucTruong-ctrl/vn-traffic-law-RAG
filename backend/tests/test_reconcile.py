"""Tests for PostgreSQL-Qdrant reconciliation (VNLRAG-45).

Unit tests cover the pure diff logic (:func:`compare_indexes`), the
compare-and-repair orchestration (:func:`reconcile_index` with an injected
contract-matching ``index_provision_units`` fake), the full rebuild flow
(:func:`rebuild_index`) and the run-manifest writer. The integration test at
the bottom runs against REAL PostgreSQL + Qdrant when both are reachable:
it introduces a divergence (extra point / deleted point / stale payload) and
verifies the repair restores PostgreSQL's view — PostgreSQL wins.

``index_provision_units`` is owned by VNLRAG-44 (``app.retrieval.indexing``)
and is developed in parallel, so every test injects a contract-matching fake
``(client, units, *, point_ids, unit_payloads, collection, batch_size) ->
IndexResult``; the orchestrator verifies the real integration post-merge.
"""

from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from qdrant_client import QdrantClient, models
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.ingestion.retrieval_units import RetrievalUnit
from app.persistence.models import DocumentVersion, LegalDocument, LegalProvision
from app.retrieval import reconcile

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _provision(**overrides: object) -> LegalProvision:
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
        "retrieval_text": "Khoản 4 Điều 7: a) Điều khiển xe lạng lách, đánh võng",
        "parent_context": "Khoản 4 Điều 7 Nghị định 168/2024/NĐ-CP",
        "effective_from": date(2025, 1, 1),
        "effective_to": None,
        "status": "EFFECTIVE",
        "page_number": 12,
        "content_hash": "sha256:abc",
        "version": 1,
        "review_status": "ACCEPTED",
    }
    values.update(overrides)
    return LegalProvision(**values)  # type: ignore[arg-type]


class FakeSession:
    """Minimal session stand-in: ``scalars`` returns the loaded provisions,
    ``execute`` returns pre-loaded (DocumentVersion, LegalDocument) rows."""

    def __init__(
        self,
        provisions: list[LegalProvision],
        document_rows: list[tuple[DocumentVersion, LegalDocument]] | None = None,
    ) -> None:
        self._provisions = provisions
        self._document_rows = list(document_rows or [])

    def scalars(self, stmt: object):
        return iter(self._provisions)

    def execute(self, stmt: object):
        return list(self._document_rows)


class FakeQdrant:
    """Qdrant stand-in: payload-only points keyed by id, scroll + delete
    recording, no real vectors (vector semantics belong to VNLRAG-44)."""

    def __init__(
        self,
        points: dict[str, dict] | None = None,
        aliases: list[tuple[str, str]] | None = None,
        collections: list[str] | None = None,
    ) -> None:
        self.points = dict(points or {})
        self.aliases = list(aliases or [])
        self.collections = list(collections or [])
        self.deleted: list[list[str]] = []
        self.created: list[str] = []
        self.payload_indexes: list[dict[str, object]] = []
        self.deleted_collections: list[str] = []

    def get_aliases(self):
        return SimpleNamespace(
            aliases=[
                SimpleNamespace(alias_name=name, collection_name=target)
                for name, target in self.aliases
            ]
        )

    def scroll(
        self,
        *,
        collection_name: str,
        with_vectors: bool,
        with_payload: bool,
        limit: int,
        offset=None,
    ):
        items = [
            SimpleNamespace(id=point_id, payload=payload)
            for point_id, payload in sorted(self.points.items())
        ]
        return items, None

    def delete(self, *, collection_name: str, points_selector) -> None:
        self.deleted.append(list(points_selector.points))

    def get_collections(self):
        return SimpleNamespace(
            collections=[SimpleNamespace(name=name) for name in self.collections]
        )

    def collection_exists(self, collection_name: str) -> bool:
        return collection_name in self.collections

    def create_collection(self, **kwargs: object) -> None:
        self.collections.append(kwargs["collection_name"])
        self.created.append(kwargs["collection_name"])

    def get_collection(self, collection_name: str):
        return SimpleNamespace(payload_schema={})

    def create_payload_index(self, **kwargs: object) -> None:
        self.payload_indexes.append(kwargs)

    def delete_collection(self, collection_name: str) -> None:
        self.deleted_collections.append(collection_name)


class FakeIndexer:
    """Contract-matching fake for ``index_provision_units`` (VNLRAG-44):

    ``(client, units, *, point_ids, unit_payloads, collection, batch_size,
    embedder, sparse_encoder)`` returns an ``IndexResult``-shaped object and
    records every call.
    """

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, client, units: list[RetrievalUnit], **kwargs: object):
        self.calls.append(
            {
                "units": list(units),
                "point_ids": dict(kwargs["point_ids"]),
                "unit_payloads": dict(kwargs["unit_payloads"] or {}),
                "collection": kwargs["collection"],
                "batch_size": kwargs["batch_size"],
                "embedder": kwargs.get("embedder"),
                "sparse_encoder": kwargs.get("sparse_encoder"),
            }
        )
        return SimpleNamespace(indexed=len(units), skipped_no_effective_from=0, errors=[])


class VectorIndexer(FakeIndexer):
    """Fake indexer that actually builds points with dense+sparse vectors from
    the passed encoders (mirrors ``indexing.build_point`` vector logic)."""

    def __init__(self) -> None:
        super().__init__()
        self.points_built: list[dict] = []

    def __call__(self, client, units: list[RetrievalUnit], **kwargs: object):
        super().__call__(client, units, **kwargs)
        embedder = kwargs.get("embedder")
        sparse_encoder = kwargs.get("sparse_encoder")
        for unit in units:
            vector: dict[str, object] = {}
            if embedder is not None:
                vector["dense"] = embedder.embed([unit.retrieval_text])[0]  # type: ignore[attr-defined]
            if sparse_encoder is not None:
                vector["sparse"] = sparse_encoder.encode(unit.retrieval_text)  # type: ignore[attr-defined]
            self.points_built.append({"unit_id": unit.unit_id, "vector": vector})
        return SimpleNamespace(indexed=len(units), skipped_no_effective_from=0, errors=[])


class PartialIndexer(FakeIndexer):
    """Fake indexer that fails one unit (e.g. an embedding batch error)."""

    def __init__(self, errors: list[str] | None = None) -> None:
        super().__init__()
        self._errors = errors if errors is not None else ["batch 0: embedding failed"]

    def __call__(self, client, units: list[RetrievalUnit], **kwargs: object):
        super().__call__(client, units, **kwargs)
        return SimpleNamespace(
            indexed=len(units) - 1, skipped_no_effective_from=0, errors=list(self._errors)
        )


class ErrorIndexer(FakeIndexer):
    """Fake indexer that reports every unit indexed BUT with recorded errors."""

    def __call__(self, client, units: list[RetrievalUnit], **kwargs: object):
        super().__call__(client, units, **kwargs)
        return SimpleNamespace(
            indexed=len(units), skipped_no_effective_from=0, errors=["p-x: payload build failed"]
        )


class FakeEmbedder:
    """Minimal dense-embedding fake (``embed``/``embed_batch`` only)."""

    name = "fake-embedder"
    dims = 4
    batch_size = 32

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.embed(texts)


class FakeSparseEncoder:
    """Minimal sparse-encoder fake (``encode``/``encode_batch`` only)."""

    name = "bm25"
    version = "bm25-v1"
    vocabulary: dict[str, int] = {"dieu": 1, "khoan": 2}

    def encode(self, text: str) -> dict[int, float]:
        return {1: 1.0, 2: 0.5}

    def encode_batch(self, texts: list[str]) -> list[dict[int, float]]:
        return [self.encode(text) for text in texts]


def _doc_metadata_rows(
    document_version_id: uuid.UUID,
) -> list[tuple[DocumentVersion, LegalDocument]]:
    document = LegalDocument(
        document_id="nd-168-2024",
        document_number="168/2024/NĐ-CP",
        document_title="Nghị định 168",
        document_type="DECREE",
        status="EFFECTIVE",
        file_hash="sha256:doc",
    )
    version = DocumentVersion(
        id=document_version_id,
        document_id="nd-168-2024",
        version=1,
        manifest_json={"manifest": "x", "vehicle_types": ["Ô tô", "Xe máy"]},
        content_hash="sha256:docver",
        review_status="ACCEPTED",
    )
    return [(version, document)]


# ---------------------------------------------------------------------------
# compare_indexes — pure diff
# ---------------------------------------------------------------------------


def test_compare_indexes_missing_extra_stale() -> None:
    pg = {"p-a", "p-b", "p-c"}
    qdrant = {"p-b", "p-c", "p-d"}
    report = reconcile.compare_indexes(
        SimpleNamespace(),
        pg_point_ids=pg,
        qdrant_point_ids=qdrant,
        pg_content={"p-a": "h1", "p-b": "h2", "p-c": "h3"},
        qdrant_content={"p-b": "h2", "p-c": "CHANGED", "p-d": "h4"},
    )
    assert report.missing == ["p-a"]
    assert report.extra == ["p-d"]
    assert report.stale == ["p-c"]
    assert report.total_pg == 3
    assert report.total_qdrant == 3
    assert report.repaired.model_dump() == {
        "missing_reindexed": 0,
        "stale_reindexed": 0,
        "extra_dropped": 0,
    }


def test_compare_indexes_uses_fetch_qdrant_ids() -> None:
    sentinel = object()

    def fetch(client: object) -> set[str]:
        assert client is sentinel
        return {"p-b", "p-d"}

    report = reconcile.compare_indexes(
        sentinel,  # type: ignore[arg-type]
        pg_point_ids={"p-a", "p-b"},
        fetch_qdrant_ids=fetch,  # type: ignore[arg-type]
    )
    assert report.missing == ["p-a"]
    assert report.extra == ["p-d"]
    assert report.total_qdrant == 2


def test_compare_indexes_requires_ids_or_fetch() -> None:
    with pytest.raises(ValueError):
        reconcile.compare_indexes(SimpleNamespace(), pg_point_ids={"p-a"})


def test_compare_indexes_no_content_dicts_means_no_stale() -> None:
    report = reconcile.compare_indexes(
        SimpleNamespace(),
        pg_point_ids={"p-a", "p-b"},
        qdrant_point_ids={"p-b", "p-c"},
    )
    assert report.stale == []


def test_compare_indexes_missing_qdrant_hash_is_stale() -> None:
    # p-b is in both sets but its Qdrant payload has no content_hash — the
    # payload cannot be verified, so PostgreSQL wins and it is stale.
    report = reconcile.compare_indexes(
        SimpleNamespace(),
        pg_point_ids={"p-a", "p-b"},
        qdrant_point_ids={"p-b", "p-c"},
        pg_content={"p-a": "h1", "p-b": "h2"},
        qdrant_content={"p-c": "h4"},
    )
    assert report.stale == ["p-b"]


def test_compare_indexes_output_sorted_deterministic() -> None:
    report = reconcile.compare_indexes(
        SimpleNamespace(),
        pg_point_ids={"z", "a", "m"},
        qdrant_point_ids={"m", "a"},
    )
    assert report.missing == ["z"]
    assert report.extra == []
    assert report.total_pg == 3
    assert report.total_qdrant == 2


def test_reconciliation_report_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        reconcile.ReconciliationReport(missing=[], unexpected="nope")  # type: ignore[call-arg]


def test_repair_counts_extra_forbidden() -> None:
    with pytest.raises(ValidationError):
        reconcile.RepairCounts(missing_reindexed=1, nope=2)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# PostgreSQL-side selection boundary
# ---------------------------------------------------------------------------


def test_accepted_provisions_stmt_filters_review_status() -> None:
    sql = str(
        reconcile._accepted_provisions_stmt().compile(  # type: ignore[attr-defined]
            compile_kwargs={"literal_binds": True}
        )
    )
    assert "review_status" in sql
    assert "'ACCEPTED'" in sql


def test_provision_to_unit_maps_row_fields() -> None:
    provision = _provision(source_text="a) Lạng lách")
    unit = reconcile.provision_to_unit(provision)
    assert unit.unit_id == f"{provision.provision_id}__v{provision.version}"
    assert unit.retrieval_text == provision.retrieval_text
    assert unit.source_text == provision.source_text
    assert unit.parent_context == provision.parent_context
    assert unit.page_number == provision.page_number
    assert unit.document_id == str(provision.document_version_id)
    assert unit.short_point is True  # POINT with <= 3 source tokens


def test_provision_to_unit_short_point_false_for_long_text() -> None:
    unit = reconcile.provision_to_unit(
        _provision(node_kind="ARTICLE", source_text="Điều 7. Nội dung rất dài với nhiều từ hơn ba.")
    )
    assert unit.short_point is False

def test_unit_payload_for_provision_carries_hash_interval_identity() -> None:
    provision = _provision()
    metadata = {provision.document_version_id: {"vehicle_types": ["Ô tô"]}}
    payload = reconcile.unit_payload_for_provision(provision, metadata)
    assert payload["content_hash"] == provision.content_hash
    assert payload["review_status"] == "ACCEPTED"
    assert payload["effective_from"] == "2025-01-01"
    assert payload["effective_to"] is None
    assert payload["article"] == "7"
    assert payload["document_version_id"] == str(provision.document_version_id)
    assert payload["vehicle_types"] == ["Ô tô"]


def test_point_id_for_is_deterministic_row_uuid() -> None:
    row_id = uuid.uuid4()
    point_id_for = reconcile._resolve_point_id_for()
    assert point_id_for(row_id) == str(row_id)
    assert point_id_for(row_id) == point_id_for(row_id)


# ---------------------------------------------------------------------------
# reconcile_index — orchestration + repair
# ---------------------------------------------------------------------------


def _run_reconcile(
    client: FakeQdrant,
    session: FakeSession,
    *,
    indexer: FakeIndexer | None = None,
    dry_run: bool = False,
    effective_from_required: bool = True,
    collection: str | None = None,
    embedder: object | None = None,
    sparse_encoder: object | None = None,
) -> tuple[reconcile.ReconciliationReport, FakeIndexer]:
    indexer = indexer or FakeIndexer()
    report = reconcile.reconcile_index(
        client,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        index_provision_units=indexer,
        point_id_for=str,
        embedder=embedder,  # type: ignore[arg-type]
        sparse_encoder=sparse_encoder,  # type: ignore[arg-type]
        collection=collection,
        effective_from_required=effective_from_required,
        dry_run=dry_run,
    )
    return report, indexer


def test_reconcile_index_full_repair_pg_wins() -> None:
    p1 = _provision(content_hash="sha256:pg-1")
    p2 = _provision(
        provision_id="nd-168-2024__dieu-8",
        node_kind="ARTICLE",
        source_text="Điều 8. Nội dung điều 8.",
        content_hash="sha256:pg-2",
    )
    pid1, pid2 = str(p1.id), str(p2.id)
    client = FakeQdrant(
        points={
            pid1: {"content_hash": "sha256:STALE"},  # stale: hash differs from PG
            "extra-1": {"content_hash": "sha256:ghost"},  # extra: no PG row
        },
        collections=["legal_provisions_v1"],
    )
    session = FakeSession([p1, p2], _doc_metadata_rows(p1.document_version_id))

    report, indexer = _run_reconcile(client, session)

    assert report.missing == [pid2]
    assert report.stale == [pid1]
    assert report.extra == ["extra-1"]
    assert report.total_pg == 2
    assert report.total_qdrant == 2

    # Two repair batches: missing (p2) then stale (p1).
    assert len(indexer.calls) == 2
    missing_call = indexer.calls[0]
    stale_call = indexer.calls[1]
    assert [u.provision_id for u in missing_call["units"]] == [p2.provision_id]
    assert [u.provision_id for u in stale_call["units"]] == [p1.provision_id]
    # Point ids are the deterministic row UUIDs.
    assert missing_call["point_ids"] == {f"{p2.provision_id}__v{p2.version}": pid2}
    assert stale_call["point_ids"] == {f"{p1.provision_id}__v{p1.version}": pid1}
    # Stale is re-indexed from the PG payload (PG wins): the unit text AND the
    # content_hash come from the provision row, never from the Qdrant payload.
    stale_unit = stale_call["units"][0]
    assert stale_unit.retrieval_text == p1.retrieval_text
    assert stale_call["unit_payloads"][stale_unit.unit_id]["content_hash"] == "sha256:pg-1"
    # Extra point dropped.
    assert client.deleted == [["extra-1"]]
    assert report.repaired.model_dump() == {
        "missing_reindexed": 1,
        "stale_reindexed": 1,
        "extra_dropped": 1,
    }


def test_reconcile_index_threads_encoders_and_produces_vectors() -> None:
    # Fix 1: repair must thread the configured dense+sparse providers into
    # index_provision_units so repaired points carry real vectors, never
    # payload-only points.
    p1 = _provision(content_hash="sha256:pg-1")
    pid1 = str(p1.id)
    client = FakeQdrant(collections=["legal_provisions_v1"])
    indexer = VectorIndexer()
    embedder = FakeEmbedder()
    sparse_encoder = FakeSparseEncoder()

    report, indexer = _run_reconcile(
        client,
        FakeSession([p1]),
        indexer=indexer,
        embedder=embedder,
        sparse_encoder=sparse_encoder,
    )

    assert report.missing == [pid1]
    assert report.repaired.missing_reindexed == 1
    assert len(indexer.calls) == 1
    assert indexer.calls[0]["embedder"] is embedder
    assert indexer.calls[0]["sparse_encoder"] is sparse_encoder
    # The points the indexer built carry BOTH vector channels.
    assert len(indexer.points_built) == 1
    built = indexer.points_built[0]
    assert built["vector"]["dense"] == [1.0, 0.0, 0.0, 0.0]
    assert built["vector"]["sparse"] == {1: 1.0, 2: 0.5}


def test_reconcile_index_dry_run_never_mutates() -> None:
    p1 = _provision(content_hash="sha256:pg-1")
    pid1 = str(p1.id)
    client = FakeQdrant(
        points={"extra-1": {"content_hash": "sha256:ghost"}},
        collections=["legal_provisions_v1"],
    )
    indexer = FakeIndexer()

    report, indexer = _run_reconcile(client, FakeSession([p1]), indexer=indexer, dry_run=True)

    assert report.missing == [pid1]
    assert report.extra == ["extra-1"]
    assert indexer.calls == []
    assert client.deleted == []
    assert report.repaired.model_dump() == {
        "missing_reindexed": 0,
        "stale_reindexed": 0,
        "extra_dropped": 0,
    }


def test_reconcile_index_determinism_same_divergence_same_actions() -> None:
    p1 = _provision(content_hash="sha256:pg-1")
    session = FakeSession([p1])

    def run() -> tuple[reconcile.ReconciliationReport, FakeIndexer]:
        client = FakeQdrant(
            points={"extra-1": {"content_hash": "h"}},
            collections=["legal_provisions_v1"],
        )
        return _run_reconcile(client, session)

    report_a, indexer_a = run()
    report_b, indexer_b = run()

    assert report_a.model_dump() == report_b.model_dump()
    assert indexer_a.calls == indexer_b.calls


def test_reconcile_index_effective_from_required_by_default() -> None:
    p1 = _provision(content_hash="sha256:pg-1")  # has effective_from
    p2 = _provision(
        provision_id="nd-168-2024__dieu-8",
        node_kind="ARTICLE",
        source_text="Điều 8. Nội dung điều 8.",
        effective_from=None,
        content_hash="sha256:pg-2",
    )
    pid1, pid2 = str(p1.id), str(p2.id)

    report_required, indexer_required = _run_reconcile(FakeQdrant(), FakeSession([p1, p2]))
    assert report_required.total_pg == 1
    assert report_required.missing == [pid1]
    assert len(indexer_required.calls[0]["units"]) == 1

    report_relaxed, indexer_relaxed = _run_reconcile(
        FakeQdrant(), FakeSession([p1, p2]), effective_from_required=False
    )
    assert report_relaxed.total_pg == 2
    assert set(report_relaxed.missing) == {pid1, pid2}
    assert len(indexer_relaxed.calls[0]["units"]) == 2


def test_reconcile_index_clean_index_no_repair() -> None:
    p1 = _provision(content_hash="sha256:pg-1")
    pid1 = str(p1.id)
    client = FakeQdrant(
        points={pid1: {"content_hash": "sha256:pg-1"}},
        collections=["legal_provisions_v1"],
    )
    indexer = FakeIndexer()

    report, indexer = _run_reconcile(client, FakeSession([p1]), indexer=indexer)

    assert not report.diverged
    assert report.missing == []
    assert report.stale == []
    assert report.extra == []
    assert indexer.calls == []
    assert client.deleted == []


def test_reconcile_index_repairs_into_explicit_collection() -> None:
    p1 = _provision(content_hash="sha256:pg-1")
    indexer = FakeIndexer()
    _run_reconcile(FakeQdrant(), FakeSession([p1]), indexer=indexer, collection="my_coll")
    assert indexer.calls[0]["collection"] == "my_coll"


def test_reconcile_index_missing_collection_is_empty_qdrant_side() -> None:
    # A not-yet-bootstrapped collection (no alias, no collection) is an empty
    # derived index: every PG provision reports missing, nothing is extra.
    p1 = _provision(content_hash="sha256:pg-1")
    pid1 = str(p1.id)
    report, indexer = _run_reconcile(FakeQdrant(), FakeSession([p1]))
    assert report.missing == [pid1]
    assert report.extra == []
    assert report.total_qdrant == 0
    assert indexer.calls[0]["collection"] == "legal_provisions_v1"


# ---------------------------------------------------------------------------
# rebuild_index — full collection replacement (doc 03 §3.11.7)
# ---------------------------------------------------------------------------


def test_rebuild_index_creates_next_collection_indexes_switches_retains_old(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    p1 = _provision(content_hash="sha256:pg-1")
    p2 = _provision(
        provision_id="nd-168-2024__dieu-8",
        node_kind="ARTICLE",
        source_text="Điều 8. Nội dung điều 8.",
        content_hash="sha256:pg-2",
    )
    client = FakeQdrant(collections=["legal_provisions_v1"])
    session = FakeSession([p1, p2], _doc_metadata_rows(p1.document_version_id))
    indexer = FakeIndexer()
    switched: list[str] = []
    monkeypatch.setattr(
        reconcile, "rebuild_alias", lambda c, name: switched.append(name) or "legal_provisions_v1"
    )

    old = reconcile.rebuild_index(
        client,  # type: ignore[arg-type]
        session=session,  # type: ignore[arg-type]
        index_provision_units=indexer,
        point_id_for=str,
    )

    assert old == "legal_provisions_v1"  # previous target, RETAINED
    assert switched == ["legal_provisions_v2"]  # next versioned name
    schemas = {entry["field_name"]: entry["field_schema"] for entry in client.payload_indexes}
    assert schemas["effective_from"] == models.PayloadSchemaType.DATETIME
    assert schemas["effective_to"] == models.PayloadSchemaType.DATETIME
    assert all(
        schema == models.PayloadSchemaType.KEYWORD
        for field, schema in schemas.items()
        if field not in {"effective_from", "effective_to"}
    )
    assert "legal_provisions_v2" in client.created
    assert len(indexer.calls) == 1
    assert indexer.calls[0]["collection"] == "legal_provisions_v2"
    assert {u.provision_id for u in indexer.calls[0]["units"]} == {
        p1.provision_id,
        p2.provision_id,
    }
    assert client.deleted_collections == []  # old collection never deleted here
    unit_payloads = indexer.calls[0]["unit_payloads"]
    assert unit_payloads[f"{p1.provision_id}__v{p1.version}"]["vehicle_types"] == [
        "Ô tô",
        "Xe máy",
    ]


def test_rebuild_index_respects_collection_override(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeQdrant(collections=["legal_provisions_v1"])
    indexer = FakeIndexer()
    switched: list[str] = []
    monkeypatch.setattr(
        reconcile, "rebuild_alias", lambda c, name: switched.append(name) or "legal_provisions_v1"
    )
    reconcile.rebuild_index(
        client,  # type: ignore[arg-type]
        session=FakeSession([_provision()]),  # type: ignore[arg-type]
        index_provision_units=indexer,
        point_id_for=str,
        collection_name="legal_provisions_v9",
    )
    assert switched == ["legal_provisions_v9"]
    assert indexer.calls[0]["collection"] == "legal_provisions_v9"


def test_rebuild_index_dry_run_mutates_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeQdrant(collections=["legal_provisions_v1"])
    indexer = FakeIndexer()
    switched: list[str] = []
    monkeypatch.setattr(reconcile, "rebuild_alias", lambda c, name: switched.append(name) or None)
    old = reconcile.rebuild_index(
        client,  # type: ignore[arg-type]
        session=FakeSession([_provision()]),  # type: ignore[arg-type]
        index_provision_units=indexer,
        point_id_for=str,
        dry_run=True,
    )
    assert old is None
    assert switched == []
    assert indexer.calls == []
    assert client.created == []


def test_rebuild_alias_noop_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    # rebuild_alias returns None when the alias already points at the new
    # collection (idempotent re-run) — rebuild_index passes it through. The
    # override names a FRESH collection (existing overrides are rejected).
    client = FakeQdrant(collections=["legal_provisions_v1"])
    monkeypatch.setattr(reconcile, "rebuild_alias", lambda c, name: None)
    old = reconcile.rebuild_index(
        client,  # type: ignore[arg-type]
        session=FakeSession([_provision()]),  # type: ignore[arg-type]
        index_provision_units=FakeIndexer(),
        point_id_for=str,
        collection_name="legal_provisions_v9",
    )
    assert old is None


def test_rebuild_index_rejects_existing_collection_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Rebuilding into an EXISTING collection would leave prior points live
    # (stale/extra surviving the rebuild) — refuse and touch nothing.
    client = FakeQdrant(collections=["legal_provisions_v1"])
    indexer = FakeIndexer()
    switched: list[str] = []
    monkeypatch.setattr(reconcile, "rebuild_alias", lambda c, name: switched.append(name) or None)
    with pytest.raises(reconcile.ReconcileError, match="already exists"):
        reconcile.rebuild_index(
            client,  # type: ignore[arg-type]
            session=FakeSession([_provision()]),  # type: ignore[arg-type]
            index_provision_units=indexer,
            point_id_for=str,
            collection_name="legal_provisions_v1",
        )
    assert switched == []  # alias untouched
    assert indexer.calls == []  # nothing indexed
    assert client.created == []  # nothing created


def test_rebuild_index_aborts_on_partial_index(monkeypatch: pytest.MonkeyPatch) -> None:
    # A partial indexing pass (e.g. a failed embedding batch) must NOT switch
    # PROVISION_ALIAS: live retrieval would lose provisions.
    p1 = _provision(content_hash="sha256:pg-1")
    p2 = _provision(
        provision_id="nd-168-2024__dieu-8",
        node_kind="ARTICLE",
        source_text="Điều 8. Nội dung điều 8.",
        content_hash="sha256:pg-2",
    )
    client = FakeQdrant(collections=["legal_provisions_v1"])
    indexer = PartialIndexer()
    switched: list[str] = []
    monkeypatch.setattr(reconcile, "rebuild_alias", lambda c, name: switched.append(name) or None)
    with pytest.raises(reconcile.ReconcileError, match="incomplete"):
        reconcile.rebuild_index(
            client,  # type: ignore[arg-type]
            session=FakeSession([p1, p2]),  # type: ignore[arg-type]
            index_provision_units=indexer,
            point_id_for=str,
        )
    assert switched == []  # alias NOT switched
    assert "legal_provisions_v2" in client.created  # partial collection left on disk


def test_rebuild_index_aborts_on_indexing_errors_even_when_all_indexed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # indexed == len(units) is NOT enough: any recorded error (e.g. a payload
    # build failure on one unit) still aborts the alias switch.
    client = FakeQdrant(collections=["legal_provisions_v1"])
    indexer = ErrorIndexer()
    switched: list[str] = []
    monkeypatch.setattr(reconcile, "rebuild_alias", lambda c, name: switched.append(name) or None)
    with pytest.raises(reconcile.ReconcileError, match="incomplete"):
        reconcile.rebuild_index(
            client,  # type: ignore[arg-type]
            session=FakeSession([_provision()]),  # type: ignore[arg-type]
            index_provision_units=indexer,
            point_id_for=str,
        )
    assert switched == []


def test_next_collection_name_increments_version() -> None:
    client = FakeQdrant(
        collections=[
            "legal_provisions_v1",
            "legal_provisions_v2",
            "legal_provisions_v1_test_abc",  # scratch names never match
        ]
    )
    assert reconcile.next_collection_name(client) == "legal_provisions_v3"


def test_next_collection_name_bootstrap_defaults_to_v1() -> None:
    assert reconcile.next_collection_name(FakeQdrant()) == "legal_provisions_v1"


# ---------------------------------------------------------------------------
# write_run_manifest — run recording
# ---------------------------------------------------------------------------


def test_write_run_manifest_writes_report_content(tmp_path: Path) -> None:
    report = reconcile.ReconciliationReport(
        missing=["p-a"],
        stale=["p-b"],
        extra=["p-c"],
        total_pg=3,
        total_qdrant=3,
        repaired=reconcile.RepairCounts(missing_reindexed=1, stale_reindexed=1, extra_dropped=1),
    )
    started = datetime(2026, 8, 14, 1, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 8, 14, 1, 0, 5, tzinfo=UTC)

    path = reconcile.write_run_manifest(
        report,
        run_id="run-test-000001",
        started_at=started,
        finished_at=finished,
        out_dir=tmp_path,
    )

    assert path == tmp_path / "run-test-000001" / "run.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["run_id"] == "run-test-000001"
    assert payload["status"] == "COMPLETED"
    assert payload["created_at"] == started.isoformat()
    assert payload["completed_at"] == finished.isoformat()
    assert payload["suite"] == "reconcile"
    assert payload["error"] is None
    assert payload["report"] == report.model_dump(mode="json")
    assert isinstance(payload["git_commit"], str) and payload["git_commit"]


def test_write_run_manifest_config_recorded(tmp_path: Path) -> None:
    path = reconcile.write_run_manifest(
        reconcile.ReconciliationReport(),
        run_id="run-test-000002",
        started_at=datetime(2026, 8, 14, tzinfo=UTC),
        finished_at=datetime(2026, 8, 14, tzinfo=UTC),
        out_dir=tmp_path,
        config={"command": "check", "dry_run": True},
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["config"] == {"command": "check", "dry_run": True}


def test_write_run_manifest_immutable_run_id(tmp_path: Path) -> None:
    kwargs = dict(
        run_id="run-test-000003",
        started_at=datetime(2026, 8, 14, tzinfo=UTC),
        finished_at=datetime(2026, 8, 14, tzinfo=UTC),
        out_dir=tmp_path,
    )
    reconcile.write_run_manifest(reconcile.ReconciliationReport(), **kwargs)  # type: ignore[arg-type]
    with pytest.raises(FileExistsError):
        reconcile.write_run_manifest(reconcile.ReconciliationReport(), **kwargs)  # type: ignore[arg-type]


def test_write_run_manifest_default_out_dir() -> None:
    assert reconcile.DEFAULT_OUT_DIR.name == "reconcile"
    assert reconcile.DEFAULT_OUT_DIR.parent.name == "evaluation"
    assert reconcile.DEFAULT_OUT_DIR.parent.parent.name == "data"


# ---------------------------------------------------------------------------
# CLI parser shape
# ---------------------------------------------------------------------------


def test_cli_parser_subcommands_and_defaults() -> None:
    from scripts.reconcile_index import build_parser

    parser = build_parser()
    for command in ("check", "repair", "rebuild"):
        args = parser.parse_args([command])
        assert args.command == command
        assert args.dry_run is False
        assert args.collection is None
        assert args.batch_size == 32
        assert args.out_dir is None
    args = parser.parse_args(["repair", "--dry-run", "--collection", "c1", "--batch-size", "8"])
    assert args.dry_run is True
    assert args.collection == "c1"
    assert args.batch_size == 8
    assert "check" in parser.format_help()


def _cli_resolution_harness(monkeypatch: pytest.MonkeyPatch, fitted: object) -> dict:
    """Monkeypatch the CLI's client/session/reconcile entry points so
    ``_run`` can execute without services; returns the captured call kwargs."""
    import scripts.reconcile_index as cli

    monkeypatch.setattr(cli, "_load_or_fit_sparse_encoder", lambda corpus_texts: fitted)
    captured: dict[str, object] = {}

    class FakeClient:
        def close(self) -> None:
            pass

    monkeypatch.setattr(cli, "_qdrant_client", lambda: FakeClient())

    @contextmanager
    def fake_session():
        # scalars() serves both the ACCEPTED corpus query and any other
        # statement — the corpus texts the CLI feeds to load_or_fit.
        yield SimpleNamespace(scalars=lambda stmt: iter(["điều 1 nội dung", "điều 2 nội dung"]))

    monkeypatch.setattr(cli, "_session", fake_session)
    return captured


def test_cli_repair_resolves_fitted_sparse_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    # Fix: CLI repair must use the SHARED fitted/persisted sparse encoder
    # (load_or_fit_sparse_encoder on the ACCEPTED corpus), never a fresh
    # unfitted one — unfitted encoders assign text-local token ids and would
    # produce inconsistent sparse dimensions across repaired points.
    import scripts.reconcile_index as cli

    fitted = FakeSparseEncoder()
    captured = _cli_resolution_harness(monkeypatch, fitted)
    seen_corpus: list[list[str]] = []
    monkeypatch.setattr(
        cli, "_load_or_fit_sparse_encoder", lambda texts: seen_corpus.append(list(texts)) or fitted
    )

    def fake_reconcile(
        client,
        *,
        session,
        embedder=None,
        sparse_encoder=None,
        collection=None,
        batch_size=32,
        dry_run=False,
        **kwargs: object,
    ) -> reconcile.ReconciliationReport:
        captured["embedder"] = embedder
        captured["sparse_encoder"] = sparse_encoder
        return reconcile.ReconciliationReport()

    monkeypatch.setattr(reconcile, "reconcile_index", fake_reconcile)

    args = cli.build_parser().parse_args(["repair", "--dry-run"])
    exit_code, report, old = cli._run(args)  # type: ignore[attr-defined]

    assert captured["sparse_encoder"] is fitted  # fitted encoder, not a fresh one
    assert captured["embedder"] is not None  # configured dense provider
    assert seen_corpus == [["điều 1 nội dung", "điều 2 nội dung"]]  # ACCEPTED corpus
    assert exit_code == 0
    assert not report.diverged


def test_cli_rebuild_resolves_fitted_sparse_encoder(monkeypatch: pytest.MonkeyPatch) -> None:
    import scripts.reconcile_index as cli

    fitted = FakeSparseEncoder()
    captured = _cli_resolution_harness(monkeypatch, fitted)

    def fake_rebuild(
        client,
        *,
        session,
        embedder=None,
        sparse_encoder=None,
        collection_name=None,
        batch_size=32,
        dry_run=False,
        **kwargs: object,
    ) -> str | None:
        captured["embedder"] = embedder
        captured["sparse_encoder"] = sparse_encoder
        return "legal_provisions_v1"

    monkeypatch.setattr(reconcile, "rebuild_index", fake_rebuild)

    args = cli.build_parser().parse_args(["rebuild", "--dry-run"])
    exit_code, report, old = cli._run(args)  # type: ignore[attr-defined]

    assert captured["sparse_encoder"] is fitted
    assert captured["embedder"] is not None
    assert old == "legal_provisions_v1"
    assert exit_code == 0


# ---------------------------------------------------------------------------
# Integration (guarded: PostgreSQL + Qdrant reachable)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_engine() -> object:
    """Migrated scratch PostgreSQL engine; skips when PG is not configured/reachable."""
    from tests.integration.conftest import (  # local import: no sys.path coupling at collection
        _alembic_config,
        _create_scratch_database,
        _drop_scratch_database,
        _resolve_base_url,
        _scratch_name,
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

    scratch = _scratch_name(base_url, f"t45{uuid.uuid4().hex[:6]}")
    _create_scratch_database(base_url, scratch)
    url = _with_database(base_url, scratch)
    cfg = _alembic_config(url)
    from alembic import command

    command.upgrade(cfg, "head")
    engine = create_engine(url)
    try:
        yield engine
    finally:
        engine.dispose()
        _drop_scratch_database(base_url, scratch)


def _with_database(url: str, database: str) -> str:
    from sqlalchemy.engine import make_url

    return make_url(url).set(database=database).render_as_string(hide_password=False)


@pytest.fixture(scope="module")
def qdrant_client() -> object:
    """Real Qdrant client; skips when the server is unreachable."""
    from app.config import get_qdrant_settings

    settings = get_qdrant_settings()
    kwargs: dict[str, object] = {"url": settings.url, "api_key": settings.api_key or None}
    probe = QdrantClient(timeout=3, **kwargs)
    try:
        probe.get_collections()
    except Exception:
        probe.close()
        pytest.skip(f"Qdrant not reachable at {settings.url}")
    probe.close()
    client = QdrantClient(timeout=30, **kwargs)
    yield client
    client.close()


def _integration_indexer(client: QdrantClient, units: list[RetrievalUnit], **kwargs: object):
    """Real upserting fake for ``index_provision_units``: writes payload-only
    points (vector semantics are VNLRAG-44's domain) with the PG-derived
    per-unit payloads."""
    point_ids = dict(kwargs["point_ids"])
    unit_payloads = dict(kwargs["unit_payloads"] or {})
    collection = kwargs["collection"] or "legal_provisions_active"
    points = []
    for unit in units:
        payload: dict[str, object] = dict(unit_payloads.get(unit.unit_id, {}))
        payload.update(
            {
                "provision_id": unit.provision_id,
                "provision_version": unit.version,
                "node_kind": unit.node_kind,
                "text": unit.retrieval_text,
                "source_text": unit.source_text,
            }
        )
        # vector={} is required by qdrant-client for payload-only collections
        # (vector semantics are VNLRAG-44's domain, not exercised here).
        points.append(models.PointStruct(id=point_ids[unit.unit_id], vector={}, payload=payload))
    client.upsert(collection_name=collection, points=points)
    return SimpleNamespace(indexed=len(units), skipped_no_effective_from=0, errors=[])


@pytest.mark.integration
def test_reconcile_integration_pg_wins_over_qdrant(
    pg_engine: object, qdrant_client: object
) -> None:
    """Real PG + Qdrant: baseline index, introduce divergence, repair, verify
    PostgreSQL wins; clean up the scratch collection."""
    engine = pg_engine  # type: ignore[assignment]
    collection = f"legal_provisions_v1_t45_{uuid.uuid4().hex[:8]}"
    assert not qdrant_client.collection_exists(collection)  # type: ignore[attr-defined]
    qdrant_client.create_collection(collection_name=collection)  # type: ignore[attr-defined]

    session = Session(engine)
    try:
        # --- PG rows: one document with 2 ACCEPTED provisions + 1 REJECTED ---
        from app.persistence.repositories.documents import DocumentRepository
        from app.persistence.repositories.provisions import ProvisionRepository

        documents = DocumentRepository(session)
        provisions_repo = ProvisionRepository(session)

        document = LegalDocument(
            document_id="nd-168-2024",
            document_number="168/2024/NĐ-CP",
            document_title="Nghị định 168/2024/NĐ-CP",
            document_type="DECREE",
            status="EFFECTIVE",
            file_hash="sha256:doc",
        )
        documents.create_document(document)
        version = DocumentVersion(
            document_id="nd-168-2024",
            version=1,
            manifest_json={"manifest": "x"},
            content_hash="sha256:docver",
            effective_from=date(2025, 1, 1),
            review_status="ACCEPTED",
        )
        documents.create_version(version)

        p1 = LegalProvision(
            provision_id="nd-168-2024__dieu-7__khoan-4__diem-b",
            document_version_id=version.id,
            node_kind="POINT",
            article="7",
            clause="4",
            point="b",
            source_text="a) Điều khiển xe lạng lách, đánh võng trên đường bộ",
            retrieval_text="Khoản 4 Điều 7: a) Điều khiển xe lạng lách, đánh võng",
            effective_from=date(2025, 1, 1),
            status="EFFECTIVE",
            page_number=12,
            content_hash="sha256:pg-1",
            version=1,
            review_status="ACCEPTED",
        )
        p2 = LegalProvision(
            provision_id="nd-168-2024__dieu-8",
            document_version_id=version.id,
            node_kind="ARTICLE",
            article="8",
            source_text="Điều 8. Tốc độ tối đa của xe cơ giới.",
            retrieval_text="Điều 8. Tốc độ tối đa của xe cơ giới.",
            effective_from=date(2025, 1, 1),
            status="EFFECTIVE",
            page_number=13,
            content_hash="sha256:pg-2",
            version=1,
            review_status="ACCEPTED",
        )
        rejected = LegalProvision(
            provision_id="nd-168-2024__dieu-9",
            document_version_id=version.id,
            node_kind="ARTICLE",
            article="9",
            source_text="Điều 9. Bị loại khỏi index.",
            retrieval_text="Điều 9. Bị loại khỏi index.",
            effective_from=date(2025, 1, 1),
            status="EFFECTIVE",
            page_number=14,
            content_hash="sha256:pg-rejected",
            version=1,
            review_status="REJECTED",
        )
        provisions_repo.create_provision(p1)
        provisions_repo.create_provision(p2)
        provisions_repo.create_provision(rejected)
        session.commit()
        # Re-read for server-generated ids (created_at defaults applied).
        session.refresh(p1)
        session.refresh(p2)
        pid1, pid2 = str(p1.id), str(p2.id)

        # --- Baseline: fresh Qdrant, everything missing ---
        baseline = reconcile.reconcile_index(
            qdrant_client,  # type: ignore[arg-type]
            session=session,
            index_provision_units=_integration_indexer,
            point_id_for=str,
            collection=collection,
        )
        assert sorted(baseline.missing) == sorted([pid1, pid2])
        assert baseline.extra == []
        assert baseline.total_pg == 2  # REJECTED provision never compared
        assert baseline.repaired.model_dump() == {
            "missing_reindexed": 2,
            "stale_reindexed": 0,
            "extra_dropped": 0,
        }

        def scroll_payloads() -> dict[str, dict]:
            points, _ = qdrant_client.scroll(  # type: ignore[attr-defined]
                collection_name=collection, with_vectors=False, with_payload=True, limit=100
            )
            return {str(p.id): dict(p.payload or {}) for p in points}

        assert set(scroll_payloads()) == {pid1, pid2}

        # --- Introduce divergence: delete p2, extra point, stale p1 payload ---
        extra_point_id = str(uuid.uuid4())
        qdrant_client.delete(  # type: ignore[attr-defined]
            collection_name=collection,
            points_selector=models.PointIdsList(points=[pid2]),
        )
        qdrant_client.upsert(  # type: ignore[attr-defined]
            collection_name=collection,
            points=[
                models.PointStruct(
                    id=extra_point_id, vector={}, payload={"content_hash": "sha256:ghost"}
                )
            ],
        )
        qdrant_client.set_payload(  # type: ignore[attr-defined]
            collection_name=collection,
            payload={"content_hash": "sha256:STALE"},
            points=[pid1],
        )

        # --- Repair: PostgreSQL wins ---
        repaired = reconcile.reconcile_index(
            qdrant_client,  # type: ignore[arg-type]
            session=session,
            index_provision_units=_integration_indexer,
            point_id_for=str,
            collection=collection,
        )
        assert repaired.missing == [pid2]
        assert repaired.stale == [pid1]
        assert repaired.extra == [extra_point_id]
        assert repaired.repaired.model_dump() == {
            "missing_reindexed": 1,
            "stale_reindexed": 1,
            "extra_dropped": 1,
        }

        final = scroll_payloads()
        assert set(final) == {pid1, pid2}
        assert final[pid1]["content_hash"] == "sha256:pg-1"  # PG wins, stale fixed
        assert final[pid2]["content_hash"] == "sha256:pg-2"  # missing restored
        assert final[pid1]["review_status"] == "ACCEPTED"
        assert final[pid1]["effective_from"] == "2025-01-01"
    finally:
        session.close()
        qdrant_client.delete_collection(collection_name=collection)  # type: ignore[attr-defined]
