"""Index actor — INDEXING stage (VNLRAG-133).

Upserts the job's ACCEPTED provisions into Qdrant via
``retrieval.indexing.index_provision_units`` — the same machinery
``index_accepted_provisions`` (VNLRAG-44) uses, scoped to THIS job's document
(the global/corpus variant is used by reconciliation, not per-job ingestion).
Only ``review_status == 'ACCEPTED'`` rows with an ``effective_from`` are
selected (the DB check constraint already guarantees ACCEPTED rows carry an
interval; the defensive guard mirrors ``index_accepted_provisions``), so
PENDING / NEEDS_REVIEW / DROPPED / REJECTED provisions NEVER enter the index
(doc 00 §8.6, FR-09).

Sparse-encoder vocabulary (doc 03 §3.11.2, ADR sparse space)
-----------------------------------------------------------
Sparse dimensions MUST mean the same token across every point in the
collection — an unfitted :class:`BM25SparseEncoder` assigns per-text local
token ids, which would silently map different tokens onto the same dimension
(invalid keyword scoring).  The actor therefore uses ONE corpus vocabulary
PERSISTED per ``SPARSE_ENCODER_VERSION`` (``data/sparse-vocab/{version}.json`,
gitignored): :func:`load_or_fit_sparse_encoder` fits the FULL corpus and
persists the vocabulary the first time a version is seen; every later job
loads the persisted vocabulary verbatim (ids = 1-based stored order) and only
recomputes corpus idf for weights.  Incremental jobs therefore index with the
identical token->dimension map — never mixing sparse spaces.

Vocabulary lifecycle: growing or changing the vocabulary is a NEW sparse
space — it requires a collection rebuild + alias switch AND a
``SPARSE_ENCODER_VERSION`` bump (doc 03 §3.11.2), never a silent in-place
extension.  This actor indexes ONLY into the collection that matches the
persisted version: tokens that entered the corpus after the vocabulary was
persisted are out-of-vocabulary and skipped until the version is bumped and
the collection rebuilt.

Idempotency (doc 03 §3.4.1): the Qdrant upsert happens AFTER the PostgreSQL
commit and uses deterministic point ids (the row UUID), so a re-run — resume
after a killed worker, a duplicate message or a reconcile-triggered re-run —
REPLACES the same points instead of duplicating them.  On a Qdrant failure
the job stays at INDEXING and the retry/reconcile re-runs the upsert.

Test seams (monkeypatched by unit/integration tests): ``_get_qdrant_client``,
``_get_embedder``, ``_get_sparse_encoder``, ``_VOCAB_DIR``.
"""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Any, cast

import dramatiq
from qdrant_client import QdrantClient
from sqlalchemy import select

from app.config import get_embedding_settings, get_queue_settings
from app.persistence.models import LegalProvision
from app.retrieval.embedding import EmbeddingProvider, get_embedding_provider
from app.retrieval.indexing import (
    ACCEPTED_REVIEW_STATUS,
    index_provision_units,
    point_id_for,
    provision_row_to_unit,
)
from app.retrieval.qdrant_store import ensure_qdrant_collection
from app.retrieval.sparse import (
    SPARSE_ENCODER_VERSION,
    BM25SparseEncoder,
    SparseEncoder,
    tokenize_vietnamese,
)

from ._state import (
    STATUS_COMPLETED,
    JobNotFoundError,
    JobStateError,
    finish_terminal,
    latest_document_version,
    list_provisions,
    load_run,
    new_session,
    set_stage,
    stage_done,
)

_QUEUE_SETTINGS = get_queue_settings()
_ACTOR_OPTIONS: dict[str, Any] = {
    "queue_name": "index",
    "time_limit": _QUEUE_SETTINGS.actor_timeouts_seconds["index"],
    "max_retries": _QUEUE_SETTINGS.max_retries,
}


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value is not None else None


def _get_qdrant_client() -> QdrantClient:
    """The provision collection client (idempotent ensure; test seam)."""
    return ensure_qdrant_collection()


def _get_embedder() -> EmbeddingProvider | None:
    """Configured dense embedding provider (test seam)."""
    return get_embedding_provider(get_embedding_settings())


def _corpus_retrieval_texts(session) -> list[str]:
    """Every provision's ``retrieval_text`` — the sparse-encoder corpus.

    ALL rows participate (review status is irrelevant to the vocabulary);
    the vocabulary must cover the whole corpus so every point's tokens are
    in-vocabulary and dimension-stable across jobs (doc 03 §3.11.2).
    """
    return list(session.scalars(select(LegalProvision.retrieval_text)))


#: Directory holding one persisted vocabulary file per sparse-encoder version
#: (``{SPARSE_ENCODER_VERSION}.json``, gitignored runtime data).  Tests
#: monkeypatch this to a temp dir.
_VOCAB_DIR = Path(__file__).resolve().parents[4] / "data" / "sparse-vocab"


def _vocab_path(version: str) -> Path:
    return _VOCAB_DIR / f"{version}.json"


def load_vocabulary(*, version: str) -> dict[str, int] | None:
    """Load the persisted corpus vocabulary for ``version``, or None.

    The file stores the sorted token list plus the version string
    (:func:`persist_vocabulary`); ids are the 1-based positions in the stored
    order — exactly how ``BM25SparseEncoder.fit`` assigns them — so a loaded
    vocabulary reproduces the original dimension mapping bit-for-bit.
    """
    path = _vocab_path(version)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if data.get("version") != version or not isinstance(data.get("tokens"), list):
        return None
    return {token: token_id for token_id, token in enumerate(data["tokens"], start=1)}


def persist_vocabulary(encoder: BM25SparseEncoder, *, version: str) -> Path:
    """Persist ``encoder``'s vocabulary as ``{version}.json``; return the path.

    Idempotent and deterministic: the stored token list is the vocabulary
    sorted by id (the encoder's own sorted order), so persisting the same
    vocabulary twice yields byte-identical files.
    """
    tokens = sorted(encoder.vocabulary, key=lambda token: encoder.vocabulary[token])
    path = _vocab_path(version)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {"version": version, "tokens": tokens}, ensure_ascii=False, indent=2
    )
    path.write_text(payload + "\n", encoding="utf-8")
    return path


def _fit_sparse_encoder(
    corpus_texts: list[str], *, version: str | None = None
) -> BM25SparseEncoder:
    """A fresh BM25 encoder fitted on the FULL corpus (new vocabulary).

    Deterministic given the same corpus: sorted token vocabulary with ids
    from 1.  An empty corpus yields an empty vocabulary (``encode`` then
    returns ``{}`` for any input) — callers with no provisions omit the
    sparse channel entirely.
    """
    encoder = BM25SparseEncoder(version=version)
    if corpus_texts:
        encoder.fit(corpus_texts)
    return encoder


def _encoder_from_persisted_vocabulary(
    corpus_texts: list[str], *, version: str
) -> BM25SparseEncoder:
    """An encoder whose vocabulary is EXACTLY the persisted one for ``version``.

    Corpus document frequencies are still computed for idf (weights), but the
    vocabulary — and therefore every token's dimension — is frozen to the
    persisted set: tokens that entered the corpus after the vocabulary was
    persisted are out-of-vocabulary and skipped at encode time.  Growing the
    vocabulary is a NEW sparse space and requires a collection rebuild +
    alias switch + ``SPARSE_ENCODER_VERSION`` bump (doc 03 §3.11.2), never a
    silent in-place extension.
    """
    persisted = load_vocabulary(version=version)
    assert persisted is not None, "caller must check load_vocabulary first"
    encoder = BM25SparseEncoder(version=version)
    document_count = len(corpus_texts)
    df: Counter[str] = Counter()
    for text in corpus_texts:
        df.update(set(tokenize_vietnamese(text)))
    encoder._vocabulary = dict(persisted)
    # idf per persisted token (1.0 fallback keeps encode in the fitted branch
    # even for an empty corpus; an empty persisted vocabulary stays empty).
    encoder._idf = {
        token: (
            math.log(1.0 + (document_count - df[token] + 0.5) / (df[token] + 0.5))
            if df[token]
            else 1.0
        )
        for token in persisted
    }
    return encoder


def load_or_fit_sparse_encoder(
    corpus_texts: list[str], *, version: str | None = None
) -> BM25SparseEncoder:
    """Load the persisted corpus vocabulary for ``version``, or fit + persist.

    The persisted vocabulary is the single source of truth for sparse
    dimensions: every job indexes with the IDENTICAL token->dimension map, so
    incremental indexing never mixes sparse spaces (doc 03 §3.11.2).  When no
    vocabulary is persisted for the version yet, the FULL corpus is fitted and
    the vocabulary persisted; when one exists, it is loaded verbatim (ids from
    the stored order) and only the corpus idf is recomputed for weights.
    ``version`` defaults to :data:`app.retrieval.sparse.SPARSE_ENCODER_VERSION`.
    """
    if version is None:
        version = SPARSE_ENCODER_VERSION
    if load_vocabulary(version=version) is None:
        encoder = _fit_sparse_encoder(corpus_texts, version=version)
        persist_vocabulary(encoder, version=version)
        return encoder
    return _encoder_from_persisted_vocabulary(corpus_texts, version=version)


def _get_sparse_encoder(corpus_texts: list[str]) -> SparseEncoder:
    """Corpus BM25 encoder with a PERSISTED vocabulary (test seam).

    See :func:`load_or_fit_sparse_encoder` for the lifecycle; an unfitted
    encoder would assign text-local token ids — different tokens on the same
    dimension across points — which is why fitting/persisting is mandatory
    before indexing.
    """
    return cast(SparseEncoder, load_or_fit_sparse_encoder(corpus_texts))


def _accepted_rows(session, document_id: str) -> tuple[list[Any], Any | None]:
    """ACCEPTED provision rows of the job's latest document version.

    Returns ``(rows, version)``; rows carry an ``effective_from`` (defensive
    guard mirroring ``index_accepted_provisions``).
    """
    version = latest_document_version(session, document_id)
    if version is None:
        return [], version
    rows = [
        row
        for row in list_provisions(session, version.id)
        if row.review_status == ACCEPTED_REVIEW_STATUS and row.effective_from is not None
    ]
    return rows, version


@dramatiq.actor(**_ACTOR_OPTIONS)
def index_actor(job_id: str) -> None:
    """Index the job's ACCEPTED provisions into Qdrant (INDEXING)."""
    session = new_session()
    units: list[Any] = []
    point_ids: dict[str, str] = {}
    unit_payloads: dict[str, dict[str, Any]] = {}
    sparse_encoder: SparseEncoder | None = None
    try:
        run = load_run(session, job_id)
        if run is None:
            raise JobNotFoundError(f"ingestion run {job_id!r} not found")
        if stage_done(run, "INDEXING"):
            return
        accepted, version = _accepted_rows(session, run.document_id)
        if version is None:
            raise JobStateError(
                f"no document version for run {job_id!r}; extract must run first"
            )
        # Build every upsert input while the rows are still bound to the
        # session (commit expires them; detached rows cannot be read).
        for row in accepted:
            unit = provision_row_to_unit(row)
            units.append(unit)
            point_ids[unit.unit_id] = point_id_for(row.id)
            unit_payloads[unit.unit_id] = {
                "review_status": ACCEPTED_REVIEW_STATUS,
                "effective_from": _iso(row.effective_from),
                "effective_to": _iso(row.effective_to),
                "chapter": row.chapter,
                "section": row.section,
                "article": row.article,
                "clause": row.clause,
                "point": row.point,
                "heading": row.heading,
                "content_hash": row.content_hash,
            }
        if accepted:
            # ONE corpus vocabulary for the whole collection: a shared token
            # must land on the same sparse dimension in every point.
            sparse_encoder = _get_sparse_encoder(_corpus_retrieval_texts(session))
        set_stage(run, "INDEXING")
        session.commit()  # PG commit BEFORE the Qdrant upsert (doc 03 §3.4.1)
    finally:
        session.close()

    if units:
        result = index_provision_units(
            _get_qdrant_client(),
            units,
            point_ids=point_ids,
            embedder=_get_embedder(),
            sparse_encoder=sparse_encoder,
            unit_payloads=unit_payloads,
        )
        if result.errors:
            # Job stays at INDEXING; the retry (or reconcile) re-runs the
            # idempotent upsert — PG data is never rolled back (doc 03 §3.4.1).
            raise RuntimeError(f"indexing failed for run {job_id!r}: {result.errors}")

    session = new_session()
    try:
        run = load_run(session, job_id)
        if run is None or stage_done(run, "INDEXING"):
            return  # already completed by a duplicate delivery
        finish_terminal(run, STATUS_COMPLETED, stage="INDEXING")
        session.commit()
    finally:
        session.close()


__all__ = [
    "index_actor",
    "load_or_fit_sparse_encoder",
    "load_vocabulary",
    "persist_vocabulary",
]
