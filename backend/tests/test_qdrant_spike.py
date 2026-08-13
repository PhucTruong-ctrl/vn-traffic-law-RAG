"""Unit tests for the VNLRAG-42 Qdrant BM25/RRF spike's pure helpers.

Covers the pieces that need no live Qdrant: collection/config building,
Vietnamese tokenization + vocabulary + sparse-vector encoding, deterministic
point ids, the doc 03 §3.11.3 payload builder, the RRF QueryRequest builder,
and the parser-benchmark fixture-selection/extraction path (real provisions,
enricher applied). The end-to-end server run is the separate
``scripts.qdrant_bm25_rrf_spike`` spike, guarded by a reachability check.
"""

from __future__ import annotations

import uuid

from qdrant_client.http.models import Distance, Fusion, FusionQuery, Modifier, SparseVector

from scripts.qdrant_bm25_rrf_spike import (
    DEFAULT_QUERY,
    DENSE_DIM,
    SPARSE_ENCODER_VERSION,
    build_rrf_query,
    build_sparse_query,
    build_spike_payload,
    build_vectors_config,
    build_vocab,
    dummy_dense_vector,
    load_benchmark_provisions,
    point_id_for,
    sparse_vector_for,
    spike_collection_name,
    tokenize_vietnamese,
)


def test_spike_collection_name_is_prefixed_and_versioned() -> None:
    name = spike_collection_name("20260814T120000Z")
    assert name == "qdrant_bm25_rrf_spike_20260814T120000Z"
    # The spike must never collide with the production collection/alias.
    assert name != "legal_provisions_v1"
    assert "legal_provisions_active" not in name


def test_build_vectors_config_matches_vnlrag40_contract() -> None:
    config = build_vectors_config()
    dense = config["vectors_config"]["dense"]
    assert dense.size == 768
    assert dense.distance == Distance.COSINE
    sparse = config["sparse_vectors_config"]["sparse"]
    assert sparse.modifier == Modifier.IDF
    assert sparse.index.on_disk is False


def test_tokenize_vietnamese_lowercases_and_keeps_diacritics() -> None:
    assert tokenize_vietnamese("xe ô tô phạt tiền") == ["xe", "ô", "tô", "phạt", "tiền"]
    # Case-folded but diacritics and đ are kept (no folding).
    assert tokenize_vietnamese("XE Ô TÔ Phạt Tiền") == ["xe", "ô", "tô", "phạt", "tiền"]
    assert tokenize_vietnamese("nồng độ cồn") == ["nồng", "độ", "cồn"]
    # Punctuation splits; digits are dropped (legal amounts contribute no tokens).
    assert tokenize_vietnamese("Điều 5. Xử phạt...") == ["điều", "xử", "phạt"]
    assert tokenize_vietnamese("") == []


def test_build_vocab_is_deterministic_and_unique() -> None:
    vocab = build_vocab(["xe ô tô", "phạt tiền", "xe đạp"])
    assert vocab["xe"] == 1
    assert vocab["ô"] == 2
    assert vocab["tô"] == 3
    assert len(vocab) == len(set(vocab.values()))
    # Same input order -> same ids.
    assert build_vocab(["xe ô tô", "phạt tiền", "xe đạp"]) == vocab


def test_sparse_vector_for_uses_counts_and_skips_oov() -> None:
    vocab = build_vocab(["xe ô tô xe máy"])
    vector = sparse_vector_for("xe xe ô tô", vocab)
    expected = SparseVector(indices=[vocab["xe"], vocab["ô"], vocab["tô"]], values=[2.0, 1.0, 1.0])
    assert vector == expected
    # Unknown tokens are skipped entirely.
    assert sparse_vector_for("máy bay", vocab) == SparseVector(indices=[vocab["máy"]], values=[1.0])
    assert sparse_vector_for("không có gì", vocab) == SparseVector(indices=[], values=[])


def test_dummy_dense_vector_is_768_zeros() -> None:
    vector = dummy_dense_vector()
    assert len(vector) == DENSE_DIM == 768
    assert vector == [0.0] * DENSE_DIM


def test_point_id_for_is_deterministic_uuid5() -> None:
    first = point_id_for("nd-168-2024__dieu-5__v1")
    assert isinstance(first, uuid.UUID)
    assert first == point_id_for("nd-168-2024__dieu-5__v1")
    assert first != point_id_for("nd-168-2024__dieu-5__khoan-1__v1")


def test_build_spike_payload_matches_doc_03_313_payload() -> None:
    triples = load_benchmark_provisions(["nd"])
    provision, unit, document_id = triples[0]
    payload = build_spike_payload(provision, unit, document_id=document_id)

    # Contract fields (doc 03 §3.11.3 / VNLRAG-40): identity + text fields.
    assert payload["provision_id"] == provision.provision_id
    assert payload["document_id"] == document_id
    assert payload["node_kind"] == provision.node_kind
    assert payload["version"] == provision.version
    assert payload["document_version_id"] == provision.document_version_id
    # Hierarchy labels pass through untouched.
    for field in ("chapter", "section", "article", "clause", "point", "heading"):
        assert payload[field] == getattr(provision, field)
    # source_text verbatim; retrieval_text is the enricher output.
    assert payload["source_text"] == provision.source_text
    assert payload["retrieval_text"] == unit.retrieval_text
    # Bounded metadata: empty in the spike (no relation/vehicle-type extraction).
    assert payload["relations"] == []
    assert payload["vehicle_types"] == []
    assert payload["sparse_encoder_version"] == SPARSE_ENCODER_VERSION
    # Placeholders are explicit, not fabricated legal data.
    assert payload["status"] == "UNKNOWN"
    assert payload["review_status"] == "PENDING"


def test_build_sparse_query_uses_vocab() -> None:
    vocab = build_vocab(["xe ô tô phạt tiền"])
    query = build_sparse_query(DEFAULT_QUERY, vocab)
    expected = [vocab["xe"], vocab["ô"], vocab["tô"], vocab["phạt"], vocab["tiền"]]
    assert query.indices == expected


def test_build_rrf_query_prefetch_and_fusion() -> None:
    dense = dummy_dense_vector()
    vocab = build_vocab(["xe ô tô phạt tiền"])
    sparse = build_sparse_query(DEFAULT_QUERY, vocab)
    request = build_rrf_query(dense, sparse)

    assert len(request.prefetch) == 2
    assert request.prefetch[0].using == "dense"
    assert request.prefetch[0].query == dense
    assert request.prefetch[1].using == "sparse"
    assert request.prefetch[1].query == sparse
    assert request.query == FusionQuery(fusion=Fusion.RRF)
    assert request.using == ""
    assert request.limit == 20


def test_load_benchmark_provisions_nd_fixture() -> None:
    triples = load_benchmark_provisions(["nd"])
    assert len(triples) >= 50
    provisions = [provision for provision, _, _ in triples]
    units = [unit for _, unit, _ in triples]
    node_kinds = {provision.node_kind for provision in provisions}
    assert {"ARTICLE", "CLAUSE", "POINT"} <= node_kinds

    ids = {unit.unit_id for unit in units}
    assert "nd-168-2024__dieu-5__v1" in ids
    assert "nd-168-2024__dieu-5__khoan-1__v1" in ids
    assert "nd-168-2024__dieu-5__khoan-1__diem-đ__v1" in ids  # đ distinct from d (FR-03)

    # Enricher applied: a POINT's retrieval_text inherits the clause lead-in.
    point_unit = next(unit for unit in units if unit.node_kind == "POINT")
    assert "Khoản" in point_unit.retrieval_text
    # source_text stays verbatim (still the original point label, e.g. "a) ...").
    assert point_unit.source_text
    assert point_unit.source_text[:2].strip() in {"a)", "b)", "c)", "d)", "đ)", "e)", "g)"}


def test_expected_hits_for_default_query_are_nonempty() -> None:
    """Fixture-selection logic: the default query must have keyword-relevant units."""
    triples = load_benchmark_provisions(["nd", "luat", "tt"])
    query_tokens = tokenize_vietnamese(DEFAULT_QUERY)
    expected = {
        unit.unit_id
        for _, unit, _ in triples
        if all(token in tokenize_vietnamese(unit.retrieval_text) for token in query_tokens)
    }
    # Nghị định 168 Điều 5 regulates "xe ô tô" and its clauses open with
    # "Phạt tiền ..."; the ARTICLE heading alone contains no "phạt tiền",
    # so the enriched CLAUSE units carry all five query tokens.
    assert "nd-168-2024__dieu-5__khoan-1__v1" in expected
    assert "nd-168-2024__dieu-5__khoan-4__v1" in expected
    assert "nd-168-2024__dieu-5__v1" not in expected
