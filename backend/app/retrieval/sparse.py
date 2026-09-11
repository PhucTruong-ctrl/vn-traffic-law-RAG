"""Versioned sparse encoder adapter (VNLRAG-43).

Doc 03 §3.11.2 versions the sparse channel: every indexed point records the
encoder id in its ``sparse_encoder_version`` payload key, and changing the
encoder means a **collection rebuild + alias switch**, never mixing two sparse
spaces in one collection. This module owns the client-side encoder that
produces the ``sparse`` named-vector weights and the Qdrant glue to upsert
them:

- ``SparseEncoder`` — the encoder interface consumed by indexing (VNLRAG-44)
  and query (VNLRAG-45);
- ``BM25SparseEncoder`` — deterministic, Vietnamese-aware BM25-style encoder:
  Unicode-word tokenizer (lowercase + NFC, keeps ``đ`` and diacritics), term
  frequency x corpus idf (log idf with smoothing, computed by ``fit``);
- ``sparse_vector_dict`` / ``upsert_sparse_vectors`` — Qdrant sparse-vector
  wire format and upsert into ``PROVISION_ALIAS`` (``qdrant_store``);
- ``with_encoder_version`` — payload contract: adds
  ``{"sparse_encoder_version": encoder.version}`` to a payload dict.

Determinism contract
--------------------
``fit`` builds the vocabulary from the corpus in sorted order and derives idf
from a fixed corpus snapshot, so given the same fit corpus ``encode`` /
``encode_batch`` return identical weight dicts on every call (same input ->
same output). There is no pickle index and no ``rank-bm25`` dependency
(ADR-005 rejects the v1 pickle approach).

``idf`` requires ``fit()`` before ``encode``
--------------------------------------------
Calling ``encode`` before ``fit`` raises ``RuntimeError``. Always fit the
corpus first so every document shares one vocabulary (and corpus idf);
out-of-vocabulary tokens are skipped, matching the VNLRAG-42 spike baseline
(``docs/evaluation/qdrant-bm25-rrf-validation.md`` §5).

Collection modifier note
------------------------
``qdrant_store`` configures the collection's ``sparse`` vector with
``modifier=Modifier.IDF``, which re-weights stored sparse vectors at query
time (server-side IDF over client-supplied values — spike finding §2).
``BM25SparseEncoder`` already embeds corpus idf in its weights after ``fit``;
callers that use both must keep the idf application consistent (the encoder
version records which scheme produced the index, per doc 03 §3.11.2).
"""

from __future__ import annotations

import math
import re
import unicodedata
from collections import Counter
from typing import Protocol, TypedDict, runtime_checkable

from qdrant_client import QdrantClient, models

from app.config import get_sparse_settings
from app.retrieval.qdrant_store import PROVISION_ALIAS, SPARSE_VECTOR_NAME

__all__ = [
    "BM25SparseEncoder",
    "SPARSE_ENCODER_VERSION",
    "SPARSE_ENCODER_VERSION_PAYLOAD_KEY",
    "SPARSE_TOKENIZER",
    "SparseEncoder",
    "VIETNAMESE_STOPWORDS",
    "sparse_vector_dict",
    "tokenize_vietnamese",
    "upsert_sparse_vectors",
    "with_encoder_version",
]

#: Payload key recording the sparse-encoder id (doc 03 §3.11.3); written by
#: ``with_encoder_version`` at indexing time (VNLRAG-44).
SPARSE_ENCODER_VERSION_PAYLOAD_KEY = "sparse_encoder_version"

#: Hash of the immutable corpus snapshot used to fit the sparse vocabulary.
SPARSE_VOCABULARY_HASH_PAYLOAD_KEY = "sparse_vocabulary_hash"

#: Default encoder version (must match ``SparseSettings.encoder_version`` /
#: ``SPARSE_ENCODER_VERSION`` env). The effective value is config-driven via
#: ``get_sparse_settings()``; this constant is the documented default.
SPARSE_ENCODER_VERSION = "bm25-v2"

#: Tokenizer id implemented by :class:`BM25SparseEncoder` (config
#: ``SPARSE_TOKENIZER``); Suite C tokenizer verification may add variants.
SPARSE_TOKENIZER = "unicode-word"

#: Unicode word tokens, including numeric legal clause markers; underscores
#: remain excluded. NFC/lowercase normalization happens before matching.
_TOKEN_RE = re.compile(r"[^\W_]+")


#: Minimal connective/function-word list, opt-in via ``drop_stopwords``.
#: Deliberately EXCLUDES semantically load-bearing words: Vietnamese legal
#: text is negation/possession-sensitive (``không``, ``được``, ``có``,
#: ``của``) and legal terms must survive unchanged — see spike doc §5.
VIETNAMESE_STOPWORDS: frozenset[str] = frozenset(
    {
        "và",
        "với",
        "để",
        "là",
        "các",
        "những",
        "một",
        "khi",
        "nếu",
        "thì",
        "cũng",
        "đều",
        "về",
        "từ",
        "ở",
        "bởi",
        "như",
        "hay",
    }
)


def tokenize_vietnamese(text: str, *, drop_stopwords: bool = False) -> list[str]:
    """Deterministic Vietnamese-aware tokenizer.

    Normalizes to NFC (composes decomposed diacritics), lowercases, then
    splits on any non-letter/digit character. Vietnamese letters are kept
    intact — ``đ`` and diacritics are preserved (FR-03 requires distinct
    ``d``/``đ``, so no diacritic folding is ever applied). Numeric tokens are
    retained, including clause markers such as ``96`` and numeric-only text
    such as ``96.`` (which tokenizes to ``["96"]``). Optionally removes the
    minimal :data:`VIETNAMESE_STOPWORDS`.
    """
    normalized = unicodedata.normalize("NFC", text.lower())
    tokens = _TOKEN_RE.findall(normalized)
    if drop_stopwords:
        tokens = [token for token in tokens if token not in VIETNAMESE_STOPWORDS]
    return tokens


@runtime_checkable
class SparseEncoder(Protocol):
    """Interface for versioned sparse encoders.

    ``version`` is recorded in every indexed point's
    ``sparse_encoder_version`` payload key; changing the encoder requires a
    collection rebuild + alias switch (doc 03 §3.11.2). ``encode`` is
    deterministic: the same input always yields the same weight dict.
    """

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> str: ...

    @property
    def vocabulary(self) -> dict[str, int]: ...

    def encode(self, text: str) -> dict[int, float]: ...

    def encode_batch(self, texts: list[str]) -> list[dict[int, float]]: ...

    def fit(self, documents: list[str]) -> None: ...


class BM25SparseEncoder:
    """Deterministic Vietnamese-aware BM25-style sparse encoder.

    - Tokenizer: :func:`tokenize_vietnamese` (lowercase + NFC, keeps ``đ`` and
      diacritics, splits on non-letter/digit); ``drop_stopwords`` opts into
      the minimal :data:`VIETNAMESE_STOPWORDS` list.
    - Weights: term frequency x corpus idf, ``idf(t) = ln(1 + (N - df(t) +
      0.5) / (df(t) + 0.5))`` (log idf with +0.5 smoothing, never negative;
      same formula family as Qdrant's BM25 IDF modifier). ``fit`` is required
      before encoding so indexed and query vectors share one vocabulary.
    - Vocabulary: built by ``fit`` from the corpus tokens in sorted order with
      ids starting at 1, so it is deterministic across runs/processes.
    - Out-of-vocabulary tokens are skipped at encode time (spike baseline).
    ``version`` defaults to ``SparseSettings.encoder_version`` (env
    ``SPARSE_ENCODER_VERSION``) and ``tokenizer`` to
    ``SparseSettings.tokenizer`` (env ``SPARSE_TOKENIZER``); only
    :data:`SPARSE_TOKENIZER` is implemented.
    """

    def __init__(
        self,
        *,
        drop_stopwords: bool = False,
        version: str | None = None,
    ) -> None:
        settings = get_sparse_settings()
        if settings.tokenizer != SPARSE_TOKENIZER:
            raise ValueError(
                f"unsupported sparse tokenizer {settings.tokenizer!r} "
                f"(implemented: {SPARSE_TOKENIZER!r})"
            )
        self.name = "bm25"
        self.version = version or settings.encoder_version or SPARSE_ENCODER_VERSION
        self.tokenizer = settings.tokenizer
        self.drop_stopwords = drop_stopwords
        self._vocabulary: dict[str, int] = {}
        self._idf: dict[str, float] = {}

    def _tokenize(self, text: str) -> list[str]:
        return tokenize_vietnamese(text, drop_stopwords=self.drop_stopwords)

    @property
    def vocabulary(self) -> dict[str, int]:
        """Copy of the fitted token -> id vocabulary (deterministic, sorted)."""
        return dict(self._vocabulary)

    def fit(self, documents: list[str]) -> None:
        """Compute corpus idf and the vocabulary from ``documents``.

        Deterministic given the same corpus: the vocabulary is the sorted
        union of corpus tokens (ids from 1) and idf is derived from document
        frequencies. Re-fitting replaces the previous corpus state. An empty
        corpus yields an empty vocabulary; ``encode`` then returns ``{}`` for
        any input (all tokens out-of-vocabulary).
        """
        document_count = len(documents)
        df: Counter[str] = Counter()
        for document in documents:
            df.update(set(self._tokenize(document)))
        self._vocabulary = {token: token_id for token_id, token in enumerate(sorted(df), start=1)}
        self._idf = {
            token: math.log(1.0 + (document_count - doc_freq + 0.5) / (doc_freq + 0.5))
            for token, doc_freq in df.items()
        }

    def encode(self, text: str) -> dict[int, float]:
        """Encode ``text`` using the fitted corpus vocabulary."""
        if not self._vocabulary:
            raise RuntimeError("BM25SparseEncoder must be fitted before encode")
        tokens = self._tokenize(text)
        tf = Counter(tokens)
        weights: dict[int, float] = {}
        for token, count in tf.items():
            token_id = self._vocabulary.get(token)
            if token_id is None:
                continue
            weights[token_id] = count * self._idf[token]
        return weights

    def encode_batch(self, texts: list[str]) -> list[dict[int, float]]:
        """Encode each text; identical to ``[encode(t) for t in texts]``."""
        return [self.encode(text) for text in texts]


class SparseVectorDict(TypedDict):
    """Qdrant sparse-vector wire format (``indices``/``values``)."""

    indices: list[int]
    values: list[float]


def sparse_vector_dict(weights: dict[int, float]) -> SparseVectorDict:
    """Convert ``{token_index: weight}`` to the Qdrant sparse-vector format.

    Returns ``{"indices": [...], "values": [...]}`` with indices sorted
    ascending and values aligned (Qdrant requires strictly increasing unique
    indices). ``encode`` output always has positive weights, so no zero
    filtering is needed here — this is a pure format conversion.
    """
    indices = sorted(weights)
    return {"indices": indices, "values": [weights[index] for index in indices]}


def with_encoder_version(
    payload: dict,
    encoder: SparseEncoder,
    *,
    vocabulary_hash: str | None = None,
) -> dict:
    """Return ``payload`` plus immutable sparse-space identity metadata."""
    updated = dict(payload)
    updated[SPARSE_ENCODER_VERSION_PAYLOAD_KEY] = encoder.version
    if vocabulary_hash is not None:
        updated[SPARSE_VOCABULARY_HASH_PAYLOAD_KEY] = vocabulary_hash
    return updated


def upsert_sparse_vectors(
    client: QdrantClient,
    points: list[tuple[str, dict[int, float]]],
    *,
    collection: str | None = None,
) -> None:
    """Upsert ``point_id -> sparse weights`` into ``PROVISION_ALIAS``.

    ``collection`` defaults to ``PROVISION_ALIAS`` (imported from
    ``app.retrieval.qdrant_store``); pass an explicit collection name for
    rebuild/test scenarios. Weights are converted with
    :func:`sparse_vector_dict` and stored under the ``SPARSE_VECTOR_NAME``
    named vector. ``point_id`` must be a Qdrant-valid id — an unsigned integer
    or a UUID string (Qdrant rejects arbitrary strings; the VNLRAG-40 contract
    uses deterministic uuid5 ids). Points whose weights are empty (no
    in-vocabulary tokens) are skipped — Qdrant rejects empty sparse vectors.
    A no-op for an empty ``points`` list.
    """
    if not points:
        return
    target = PROVISION_ALIAS if collection is None else collection
    structured_points: list[models.PointStruct] = []
    for point_id, weights in points:
        if not weights:
            continue  # Qdrant rejects empty sparse vectors
        formatted = sparse_vector_dict(weights)
        structured_points.append(
            models.PointStruct(
                id=point_id,
                vector={
                    SPARSE_VECTOR_NAME: models.SparseVector(
                        indices=formatted["indices"], values=formatted["values"]
                    )
                },
            )
        )
    if structured_points:
        client.upsert(collection_name=target, points=structured_points)
