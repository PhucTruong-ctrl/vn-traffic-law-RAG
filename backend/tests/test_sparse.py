"""Unit tests: versioned sparse encoder adapter (VNLRAG-43) — no live Qdrant needed.

Covers the doc 03 §3.11.2 contract implemented in ``app.retrieval.sparse``:
- the deterministic Vietnamese-aware tokenizer (lowercase + NFC, keeps ``đ``,
  splits on non-letter/digit, minimal opt-in stopwords);
- ``BM25SparseEncoder`` determinism: tf-only weights before ``fit``, tf x
  corpus idf after, sorted deterministic vocabulary, OOV skipping;
- the Qdrant glue: ``sparse_vector_dict`` wire format, ``with_encoder_version``
  payload contract, ``upsert_sparse_vectors`` alias default;
- ``SparseSettings`` env mapping (``SPARSE_ENCODER_VERSION`` /
  ``SPARSE_TOKENIZER``).

One Qdrant integration test (marked ``integration``) round-trips
``upsert_sparse_vectors`` through a THROWAWAY collection; it is skipped when
Qdrant is not reachable at ``QDRANT_URL`` (default ``http://localhost:6333``).
"""

from __future__ import annotations

import math
import unicodedata
import uuid
from collections.abc import Iterator

import pytest
from qdrant_client import QdrantClient, models

from app.config import SparseSettings, get_qdrant_settings
from app.retrieval import sparse
from app.retrieval.qdrant_store import (
    PROVISION_ALIAS,
    SPARSE_VECTOR_NAME,
    build_collection_config,
)
from app.retrieval.sparse import (
    SPARSE_ENCODER_VERSION,
    SPARSE_ENCODER_VERSION_PAYLOAD_KEY,
    SPARSE_TOKENIZER,
    VIETNAMESE_STOPWORDS,
    BM25SparseEncoder,
    sparse_vector_dict,
    tokenize_vietnamese,
    upsert_sparse_vectors,
    with_encoder_version,
)


class _RecordingClient:
    """Minimal QdrantClient stand-in recording upsert calls (no live Qdrant)."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, list[models.PointStruct]]] = []

    def upsert(self, *, collection_name: str, points: list[models.PointStruct]) -> None:
        self.calls.append((collection_name, points))


# ---------------------------------------------------------------------------
# Tokenizer — Vietnamese behavior
# ---------------------------------------------------------------------------


def test_tokenize_vietnamese_keeps_diacritics_and_d() -> None:
    assert tokenize_vietnamese("xe ô tô phạt tiền") == ["xe", "ô", "tô", "phạt", "tiền"]
    # đ (U+0111) and Đ are kept as letters; digits and punctuation are dropped/split.
    assert tokenize_vietnamese("Điều 5, Khoản 4, Điểm đ") == ["điều", "khoản", "điểm", "đ"]


def test_tokenize_vietnamese_lowercases_and_normalizes_nfc() -> None:
    assert tokenize_vietnamese("XE Ô TÔ") == tokenize_vietnamese("xe ô tô")
    decomposed = "xe o\u0302 tô"  # 'ô' as 'o' + combining circumflex (NFD form)
    assert not unicodedata.is_normalized("NFC", decomposed)
    assert tokenize_vietnamese(decomposed) == ["xe", "ô", "tô"]


def test_tokenize_vietnamese_splits_on_non_letters_and_drops_digits() -> None:
    assert tokenize_vietnamese("a) xe, ô-tô.") == ["a", "xe", "ô", "tô"]
    assert tokenize_vietnamese("800.000 đồng (mức phạt)") == ["đồng", "mức", "phạt"]
    assert tokenize_vietnamese("") == []


def test_tokenize_vietnamese_stopwords_are_opt_in_and_minimal() -> None:
    text = "xe và ô tô với người điều khiển"
    assert tokenize_vietnamese(text) == ["xe", "và", "ô", "tô", "với", "người", "điều", "khiển"]
    assert tokenize_vietnamese(text, drop_stopwords=True) == [
        "xe",
        "ô",
        "tô",
        "người",
        "điều",
        "khiển",
    ]
    # Deliberate exclusions: negation/possession/legal words are load-bearing.
    assert "và" in VIETNAMESE_STOPWORDS
    assert {"không", "được", "có", "của"} & VIETNAMESE_STOPWORDS == set()


# ---------------------------------------------------------------------------
# BM25SparseEncoder — determinism and idf
# ---------------------------------------------------------------------------


def test_encode_unfitted_is_term_frequency_only_and_deterministic() -> None:
    encoder = BM25SparseEncoder()
    assert encoder.encode("xe ô tô") == {1: 1.0, 2: 1.0, 3: 1.0}
    assert encoder.encode("") == {}
    assert encoder.encode("xe ô tô") == encoder.encode("xe ô tô")


def test_fit_idf_changes_weights_and_is_deterministic() -> None:
    encoder = BM25SparseEncoder()
    tf_only = encoder.encode("xe ô tô")
    encoder.fit(["xe ô tô", "ô tô"])
    # Corpus: N=2, df(xe)=1, df(ô)=df(tô)=2. Vocabulary sorted by codepoint:
    # 'tô' < 'xe' < 'ô' -> tô=1, xe=2, ô=3.
    idf_xe = math.log(1.0 + (2 - 1 + 0.5) / (1 + 0.5))
    idf_common = math.log(1.0 + (2 - 2 + 0.5) / (2 + 0.5))
    encoded = encoder.encode("xe ô tô")
    assert encoded == {1: idf_common, 2: idf_xe, 3: idf_common}
    assert encoded != tf_only  # fit changed the weights (idf now applied)
    assert encoder.encode("xe ô tô") == encoded  # deterministic
    encoder.fit(["xe ô tô", "ô tô"])
    assert encoder.encode("xe ô tô") == encoded  # re-fit same corpus -> identical
    # The rare term (in 1 of 2 docs) outweighs the corpus-common terms.
    assert encoded[2] > encoded[1]


def test_fit_vocabulary_is_sorted_and_deterministic() -> None:
    encoder = BM25SparseEncoder()
    corpus = ["xe ô tô", "phạt tiền", "xe đạp"]
    encoder.fit(corpus)
    # Sorted by Unicode codepoint: ascii letters first, then ô (U+00F4), đ (U+0111).
    assert encoder.vocabulary == {"phạt": 1, "tiền": 2, "tô": 3, "xe": 4, "ô": 5, "đạp": 6}
    encoder.fit(corpus)
    assert encoder.vocabulary == {"phạt": 1, "tiền": 2, "tô": 3, "xe": 4, "ô": 5, "đạp": 6}
    # The property returns a copy: mutating it must not corrupt the encoder.
    encoder.vocabulary["phạt"] = 999
    assert encoder.vocabulary["phạt"] == 1


def test_encode_skips_out_of_vocabulary_tokens() -> None:
    encoder = BM25SparseEncoder()
    encoder.fit(["xe ô tô"])
    idf_xe = math.log(1.0 + (1 - 1 + 0.5) / (1 + 0.5))
    encoded = encoder.encode("xe máy")
    assert encoded == {encoder.vocabulary["xe"]: idf_xe}  # 'máy' skipped
    assert encoder.encode("máy") == {}  # all OOV -> empty weights


def test_encode_batch_matches_individual_encode() -> None:
    encoder = BM25SparseEncoder()
    encoder.fit(["xe ô tô", "phạt tiền", "xe máy"])
    texts = ["xe ô tô phạt tiền", "xe máy", ""]
    assert encoder.encode_batch(texts) == [encoder.encode(text) for text in texts]


# ---------------------------------------------------------------------------
# Qdrant glue — wire format, payload contract, upsert
# ---------------------------------------------------------------------------


def test_sparse_vector_dict_sorts_indices_and_aligns_values() -> None:
    assert sparse_vector_dict({3: 0.5, 1: 0.25}) == {"indices": [1, 3], "values": [0.25, 0.5]}
    assert sparse_vector_dict({}) == {"indices": [], "values": []}


def test_with_encoder_version_adds_payload_key_without_mutating() -> None:
    encoder = BM25SparseEncoder(version="bm25-test-v9")
    payload = {"provision_id": "p-1", "source_text": "verbatim"}
    updated = with_encoder_version(payload, encoder)
    assert updated == {
        "provision_id": "p-1",
        "source_text": "verbatim",
        SPARSE_ENCODER_VERSION_PAYLOAD_KEY: "bm25-test-v9",
    }
    assert SPARSE_ENCODER_VERSION_PAYLOAD_KEY not in payload  # input untouched


def test_upsert_sparse_vectors_defaults_to_provision_alias() -> None:
    client = _RecordingClient()
    upsert_sparse_vectors(client, [("p1", {2: 0.5, 1: 0.25}), ("p2", {3: 1.0})])
    assert len(client.calls) == 1
    collection_name, points = client.calls[0]
    assert collection_name == PROVISION_ALIAS
    assert [point.id for point in points] == ["p1", "p2"]
    assert points[0].vector == {
        SPARSE_VECTOR_NAME: models.SparseVector(indices=[1, 2], values=[0.25, 0.5])
    }


def test_upsert_sparse_vectors_skips_empty_weights_and_empty_points() -> None:
    client = _RecordingClient()
    upsert_sparse_vectors(client, [], collection="scratch")
    assert client.calls == []
    upsert_sparse_vectors(client, [("empty", {}), ("ok", {1: 1.0})], collection="scratch")
    assert len(client.calls) == 1
    collection_name, points = client.calls[0]
    assert collection_name == "scratch"
    assert [point.id for point in points] == ["ok"]


# ---------------------------------------------------------------------------
# Config — SparseSettings (SPARSE_* env)
# ---------------------------------------------------------------------------


def test_sparse_settings_defaults_match_module_constants(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SPARSE_ENCODER_VERSION", raising=False)
    monkeypatch.delenv("SPARSE_TOKENIZER", raising=False)
    settings = SparseSettings()
    assert settings.encoder_version == SPARSE_ENCODER_VERSION
    assert settings.tokenizer == SPARSE_TOKENIZER


def test_sparse_settings_env_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SPARSE_ENCODER_VERSION", "bm25-test-v2")
    monkeypatch.setenv("SPARSE_TOKENIZER", "unicode-word")
    settings = SparseSettings()
    assert settings.encoder_version == "bm25-test-v2"
    assert settings.tokenizer == "unicode-word"


def test_encoder_version_defaults_and_constructor_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SPARSE_ENCODER_VERSION", raising=False)
    assert BM25SparseEncoder().version == SPARSE_ENCODER_VERSION
    assert BM25SparseEncoder(version="custom-v2").version == "custom-v2"


def test_encoder_rejects_unsupported_tokenizer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sparse, "get_sparse_settings", lambda: SparseSettings(tokenizer="pyvi"))
    with pytest.raises(ValueError, match="unsupported sparse tokenizer"):
        BM25SparseEncoder()


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
    name = f"legal_provisions_v1_sparse_test_{uuid.uuid4().hex[:8]}"
    qdrant_client.create_collection(collection_name=name, **build_collection_config())
    try:
        yield name
    finally:
        if qdrant_client.collection_exists(name):
            qdrant_client.delete_collection(name)


@pytest.mark.integration
def test_upsert_sparse_vectors_round_trips_through_qdrant(
    qdrant_client: QdrantClient, scratch_collection: str
) -> None:
    encoder = BM25SparseEncoder()
    encoder.fit(["xe ô tô", "phạt tiền", "xe máy", "xe ô tô kinh doanh vận tải"])
    # Qdrant point ids must be unsigned integers or UUIDs (no arbitrary strings).
    point_ids = [str(uuid.uuid5(uuid.NAMESPACE_URL, f"vnlaw:sparse-test:{i}")) for i in range(2)]
    points = [
        (point_ids[0], encoder.encode("xe ô tô phạt tiền")),
        (point_ids[1], encoder.encode("xe máy")),
    ]
    assert all(weights for _, weights in points)

    upsert_sparse_vectors(qdrant_client, points, collection=scratch_collection)

    records = qdrant_client.retrieve(
        collection_name=scratch_collection,
        ids=[point_id for point_id, _ in points],
        with_vectors=True,
    )
    assert {record.id for record in records} == {point_id for point_id, _ in points}
    by_id = {record.id: record for record in records}
    for point_id, weights in points:
        expected = sparse_vector_dict(weights)
        sparse_vector = by_id[point_id].vector[SPARSE_VECTOR_NAME]
        assert sparse_vector.indices == expected["indices"]
        assert sparse_vector.values == pytest.approx(expected["values"])
