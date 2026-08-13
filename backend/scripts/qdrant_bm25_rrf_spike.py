"""VNLRAG-42 spike: validate Qdrant server-side BM25 + RRF Query API.

Usage (from backend/):

    uv run python -m scripts.qdrant_bm25_rrf_spike [--url http://localhost:6333]

Creates a THROWAWAY collection ``qdrant_bm25_rrf_spike_<timestamp>`` carrying
the SAME contract as VNLRAG-40 (doc 03 §3.11.1-2): a named dense vector
``dense`` (768-d, Cosine) plus a sparse vector field ``sparse`` with the IDF
modifier. Real Vietnamese legal provisions extracted from the parser-benchmark
fixtures (backend/tests/fixtures/parser_benchmark/documents) are indexed, then
the spike validates:

(a) sparse BM25 keyword relevance — a keyword query (default
    ``xe ô tô phạt tiền``) must rank the provisions whose text contains the
    query terms in the top-k;
(b) the Query API prefetch [dense, sparse] with ``Fusion.RRF`` — executes and
    returns a valid fused rank list (dense uses dummy zero vectors);
(c) Vietnamese tokenization notes — how the query text is split, diacritic and
    case behavior, and multi-word term caveats.

The throwaway collection is always deleted on exit (also on failure). If
``app.retrieval.qdrant_store`` is importable, its collection constants are
reported as the contract source; otherwise the spike falls back to an identical
raw qdrant-client config and documents that path.

Exit codes: 0 = all checks passed; 1 = a validation check failed;
2 = Qdrant unreachable.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import uuid
from collections import Counter
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    Fusion,
    FusionQuery,
    Modifier,
    PointStruct,
    Prefetch,
    QueryRequest,
    SparseIndexParams,
    SparseVector,
    SparseVectorParams,
    VectorParams,
)

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ingestion.document_ir import (  # noqa: E402
    BoundingBox,
    DocumentElement,
    ParsedDocument,
    ParsedPage,
)
from app.ingestion.retrieval_units import RetrievalUnit, build_retrieval_units  # noqa: E402
from app.ingestion.structure_extractor import (  # noqa: E402
    ExtractedLegalProvision,
    LegalStructureExtractor,
)

#: Dense embedding dimension per doc 03 §3.11.1 (Gemini Embedding 2 / Jina v5 text-nano).
DENSE_DIM = 768
#: Sparse encoder id stored in the payload per doc 03 §3.11.2 (rebuild + alias switch on change).
SPARSE_ENCODER_VERSION = "qdrant-bm25-v1"
#: Throwaway collection name prefix (spike must never touch legal_provisions_v1 / the alias).
COLLECTION_PREFIX = "qdrant_bm25_rrf_spike"
#: Default keyword query — hits Nghị định 168/2024/NĐ-CP Điều 5 ("xe ô tô" + "phạt tiền").
DEFAULT_QUERY = "xe ô tô phạt tiền"
#: RRF prefetch limits mirror doc 03 §3.11.6 (dense_prefetch/sparse_prefetch 30, fusion_limit 20).
RRF_DENSE_LIMIT = 30
RRF_SPARSE_LIMIT = 30
RRF_LIMIT = 20
#: How many sparse results are inspected for the keyword-relevance check.
TOP_K = 5

FIXTURES_DIR = BACKEND_DIR / "tests" / "fixtures" / "parser_benchmark" / "documents"
#: (relative txt path, document_id) per parser-benchmark fixture.
FIXTURE_SOURCES: dict[str, tuple[str, str]] = {
    "nd": ("nd/nd-168-2024-fixture.pdf.txt", "nd-168-2024"),
    "luat": ("luat/luat-traffic-2024-fixture.pdf.txt", "luat-36-2024-qh15"),
    "tt": ("tt/tt-traffic-2024-fixture.pdf.txt", "tt-24-2024-tt-bgtvt"),
}

#: Unicode word tokens only (no digits/underscore) — lowercase, diacritics kept.
_TOKEN_RE = re.compile(r"[^\W\d_]+")


def spike_collection_name(timestamp: str) -> str:
    """Return the throwaway collection name for the given UTC timestamp."""
    return f"{COLLECTION_PREFIX}_{timestamp}"


def build_vectors_config() -> dict[str, object]:
    """Return the VNLRAG-40 collection contract (doc 03 §3.11.1-2) as create_collection kwargs.

    ``vectors_config`` carries the named dense vector ``dense`` (768-d Cosine);
    ``sparse_vectors_config`` carries the sparse field ``sparse`` with the BM25
    IDF modifier and the in-memory index from the doc. The spike encodes sparse
    vectors client-side (whitespace/Unicode-word tokenizer, see
    ``tokenize_vietnamese``) because Qdrant 1.19 accepts only pre-built sparse
    vectors for both upsert and query (verified in spike section (c)).
    """
    return {
        "vectors_config": {"dense": VectorParams(size=DENSE_DIM, distance=Distance.COSINE)},
        "sparse_vectors_config": {
            "sparse": SparseVectorParams(
                index=SparseIndexParams(on_disk=False), modifier=Modifier.IDF
            )
        },
    }


def tokenize_vietnamese(text: str) -> list[str]:
    """Baseline Vietnamese tokenizer: lowercase + Unicode-word split.

    Matches Qdrant's whitespace-tokenizer semantics that doc 03 §3.11.2 assumes
    for BM25 ("tiếng Việt chủ yếu tách theo khoảng trắng"): tokens are
    whitespace/punctuation-separated words, lowercased, with diacritics and
    ``đ`` kept intact (no diacritic folding). Digits are dropped (legal amounts
    like ``800.000`` produce no tokens).
    """
    return _TOKEN_RE.findall(text.lower())


def build_vocab(texts: Iterable[str]) -> dict[str, int]:
    """Build a deterministic token->id vocabulary from the indexed texts (ids start at 1)."""
    vocab: dict[str, int] = {}
    for text in texts:
        for token in tokenize_vietnamese(text):
            if token not in vocab:
                vocab[token] = len(vocab) + 1
    return vocab


def sparse_vector_for(text: str, vocab: dict[str, int]) -> SparseVector:
    """Encode ``text`` as a SparseVector (term-frequency values, server applies IDF).

    Out-of-vocabulary tokens are skipped: a query term absent from the indexed
    corpus contributes nothing (no fabricated ids).
    """
    counts = Counter(tokenize_vietnamese(text))
    indices: list[int] = []
    values: list[float] = []
    for token, count in counts.items():
        token_id = vocab.get(token)
        if token_id is not None:
            indices.append(token_id)
            values.append(float(count))
    return SparseVector(indices=indices, values=values)


def dummy_dense_vector(dim: int = DENSE_DIM) -> list[float]:
    """Dummy dense vector (zeros) — dense similarity is uninformative on purpose."""
    return [0.0] * dim


def point_id_for(unit_id: str) -> uuid.UUID:
    """Deterministic point id (uuid5) per retrieval unit."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"vnlaw:qdrant-bm25-rrf-spike:{unit_id}")


def build_spike_payload(
    provision: ExtractedLegalProvision,
    unit: RetrievalUnit,
    *,
    document_id: str,
    parser_version: str = "spike-fixture/test-1",
    content_version: int = 1,
) -> dict[str, object]:
    """Map one provision+unit to the doc 03 §3.11.3 payload contract.

    ``retrieval_text`` is the enricher output (parent context inherited),
    ``source_text`` the verbatim legal text (never mutated). ``relations`` is
    empty and ``vehicle_types`` empty because the spike fixtures carry no
    relation/vehicle-type metadata — production fills them from PostgreSQL and
    the metadata extractor. ``parser_version``/``content_version`` are spike
    placeholders (fixture extraction, no production parser).
    """
    return {
        "provision_id": provision.provision_id,
        "version": provision.version,
        "document_version_id": provision.document_version_id,
        "document_id": document_id,
        "node_kind": provision.node_kind,
        "chapter": provision.chapter,
        "section": provision.section,
        "article": provision.article,
        "clause": provision.clause,
        "point": provision.point,
        "heading": provision.heading,
        "effective_from": provision.effective_from,
        "effective_to": provision.effective_to,
        "review_status": provision.review_status,
        "status": provision.status,
        "parser_version": parser_version,
        "content_version": content_version,
        "content_hash": provision.content_hash,
        "sparse_encoder_version": SPARSE_ENCODER_VERSION,
        "relations": [],
        "vehicle_types": [],
        "page_number": provision.page_number,
        "source_text": provision.source_text,
        "retrieval_text": unit.retrieval_text,
    }


def _document_from_lines(document_id: str, lines: Sequence[tuple[str, str]]) -> ParsedDocument:
    """Build a ParsedDocument from (text, element_type) lines (test/benchmark pattern)."""
    elements = [
        DocumentElement(
            element_id=f"e{index}",
            element_type=element_type,
            text=text,
            page_number=1,
            bbox=BoundingBox(left=0.1, top=index / 100, right=0.9, bottom=(index + 1) / 100),
            reading_order=index,
            parent_element_id=None,
            source_parser="TEST",
            parser_version="test-1",
            parser_confidence=None,
            raw_reference={"index": index},
        )
        for index, (text, element_type) in enumerate(lines)
    ]
    return ParsedDocument(
        parsed_document_id="parsed-1",
        document_id=document_id,
        parser="TEST",
        parser_version="test-1",
        ir_schema_version="document-ir-v2",
        source_object_key="fixture",
        pages=[ParsedPage(page_number=1, width=1, height=1, text=None, elements=elements)],
        parse_started_at=datetime(2024, 1, 1, tzinfo=UTC),
        parse_completed_at=datetime(2024, 1, 1, 0, 0, 1, tzinfo=UTC),
        quality_report={},
    )


def load_benchmark_provisions(
    fixture_keys: Sequence[str],
) -> list[tuple[ExtractedLegalProvision, RetrievalUnit, str]]:
    """Load real provisions from the parser-benchmark fixtures.

    Light reliable path (no PDF parsing, no network): the fixture ``.txt``
    files are split into (line, ``paragraph``) elements, run through the Legal
    Structure Extractor (VNLRAG-22), then through Retrieval Units (VNLRAG-48),
    which applies the Legal Context Enricher (VNLRAG-132) to ``retrieval_text``.

    Returns ``(provision, unit, document_id)`` triples — exactly the input the
    spike indexes, so the payload builder and the expected-hit logic stay
    grounded in the same data.
    """
    triples: list[tuple[ExtractedLegalProvision, RetrievalUnit, str]] = []
    for key in fixture_keys:
        try:
            fixture_rel, document_id = FIXTURE_SOURCES[key]
        except KeyError as exc:
            choices = ", ".join(sorted(FIXTURE_SOURCES))
            raise ValueError(f"unknown fixture key {key!r}; choose from {choices}") from exc
        fixture_path = FIXTURES_DIR / fixture_rel
        lines = [
            (line, "paragraph")
            for line in fixture_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        document = _document_from_lines(document_id, lines)
        provisions = LegalStructureExtractor().extract(
            document, document_version_id=f"{document_id}__v1"
        )
        units = build_retrieval_units(provisions)
        for provision, unit in zip(provisions, units, strict=True):
            triples.append((provision, unit, document_id))
    return triples


def build_sparse_query(query_text: str, vocab: dict[str, int]) -> SparseVector:
    """Sparse query vector for the keyword query (OOV terms skipped)."""
    return sparse_vector_for(query_text, vocab)


def build_rrf_query(
    dense_vector: list[float],
    sparse_vector: SparseVector,
    *,
    dense_limit: int = RRF_DENSE_LIMIT,
    sparse_limit: int = RRF_SPARSE_LIMIT,
    limit: int = RRF_LIMIT,
) -> QueryRequest:
    """Query API request: prefetch [dense, sparse] fused with Fusion.RRF."""
    return QueryRequest(
        prefetch=[
            Prefetch(query=dense_vector, using="dense", limit=dense_limit),
            Prefetch(query=sparse_vector, using="sparse", limit=sparse_limit),
        ],
        query=FusionQuery(fusion=Fusion.RRF),
        using="",
        limit=limit,
    )


def qdrant_reachable(client: QdrantClient) -> bool:
    """True when the Qdrant server answers a trivial call."""
    try:
        client.get_collections()
        return True
    except Exception:
        return False


def _hit_summary(points: Sequence[object]) -> list[dict[str, object]]:
    """Compact (id, score, provision_id) rows for printing."""
    rows = []
    for point in points:
        payload = getattr(point, "payload", None) or {}
        rows.append(
            {
                "id": str(getattr(point, "id", "")),
                "score": round(float(getattr(point, "score", 0.0)), 4),
                "provision_id": payload.get("provision_id"),
            }
        )
    return rows


def _query_tokens_in(text: str, tokens: Sequence[str]) -> bool:
    tokenized = set(tokenize_vietnamese(text))
    return all(token in tokenized for token in tokens)


def run_spike(
    client: QdrantClient,
    triples: Sequence[tuple[ExtractedLegalProvision, RetrievalUnit, str]],
    *,
    query_text: str = DEFAULT_QUERY,
) -> dict[str, object]:
    """Create the throwaway collection, run the three validations, clean up.

    The collection is always deleted (also on exception) — the spike never
    leaves state behind and never touches the production collection/alias.
    """
    results: dict[str, object] = {}
    collection = spike_collection_name(datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"))
    results["collection"] = collection
    config = build_vectors_config()
    vocab = build_vocab(unit.retrieval_text for _, unit, _ in triples)
    results["indexed_points"] = len(triples)
    results["vocab_size"] = len(vocab)

    client.create_collection(collection, **config)
    try:
        points = [
            PointStruct(
                id=point_id_for(unit.unit_id),
                payload=build_spike_payload(provision, unit, document_id=document_id),
                vector={
                    "dense": dummy_dense_vector(),
                    "sparse": sparse_vector_for(unit.retrieval_text, vocab),
                },
            )
            for provision, unit, document_id in triples
        ]
        client.upsert(collection, points=points, wait=True)

        query_tokens = tokenize_vietnamese(query_text)
        expected_ids = {
            unit.unit_id
            for _, unit, _ in triples
            if _query_tokens_in(unit.retrieval_text, query_tokens)
        }
        results["query"] = query_text
        results["query_tokens"] = query_tokens
        results["expected_unit_ids"] = sorted(expected_ids)

        # (a) sparse BM25 keyword relevance -----------------------------------
        sparse_query = build_sparse_query(query_text, vocab)
        sparse_hits = client.query_points(
            collection, query=sparse_query, using="sparse", limit=TOP_K, with_payload=True
        ).points
        results["sparse_top"] = _hit_summary(sparse_hits)
        top_ids = {hit["id"] for hit in results["sparse_top"]}
        expected_point_ids = {str(point_id_for(unit_id)) for unit_id in expected_ids}
        results["sparse_relevance_ok"] = bool(top_ids & expected_point_ids)

        # (b) Query API prefetch [dense, sparse] + Fusion.RRF -----------------
        dense_vector = dummy_dense_vector()
        dense_hits = client.query_points(
            collection, query=dense_vector, using="dense", limit=10, with_payload=True
        ).points
        results["dense_prefetch_top"] = _hit_summary(dense_hits)
        results["sparse_prefetch_top"] = _hit_summary(sparse_hits)
        rrf_request = build_rrf_query(dense_vector, sparse_query)
        fused_hits = client.query_points(
            collection,
            query=rrf_request.query,
            prefetch=rrf_request.prefetch,
            using=rrf_request.using,
            limit=rrf_request.limit,
            with_payload=True,
        ).points
        results["rrf_fused_top"] = _hit_summary(fused_hits)
        fused_ids = [hit["id"] for hit in results["rrf_fused_top"]]
        results["rrf_ok"] = bool(fused_ids) and len(fused_ids) == len(set(fused_ids))

        # (c) Vietnamese tokenization notes ------------------------------------
        notes: dict[str, object] = {}
        try:
            client.query_points(collection, query=query_text, using="sparse", limit=1)
            notes["raw_string_query"] = "accepted"
        except Exception as exc:  # noqa: BLE001 - spike probes server behavior
            notes["raw_string_query"] = f"rejected: {type(exc).__name__} ({str(exc)[:120]})"

        notes["tokenize_query"] = tokenize_vietnamese(query_text)
        notes["tokenize_multiword_example"] = {
            "giao thông": tokenize_vietnamese("giao thông"),
            "giấy phép lái xe": tokenize_vietnamese("giấy phép lái xe"),
        }

        # Diacritics: 'ô tô' vs 'oto' are different token spaces (no folding).
        without_diacritics = tokenize_vietnamese("xe oto")
        notes["diacritics"] = {
            "query": "xe oto",
            "tokens": without_diacritics,
            "vocab_tokens": [t for t in without_diacritics if t in vocab],
            "vocab_missing": [t for t in without_diacritics if t not in vocab],
            "note": "no diacritic folding: 'ô tô' and 'oto' index/query different token ids",
        }
        # Case: client tokenizer lowercases, so uppercase queries match identically.
        upper_query = build_sparse_query(query_text.upper(), vocab)
        upper_hits = client.query_points(
            collection, query=upper_query, using="sparse", limit=5, with_payload=True
        ).points
        notes["case"] = {
            "upper_tokens": tokenize_vietnamese(query_text.upper()),
            "same_vector_as_lower": upper_query == sparse_query,
            "same_scores": [round(float(p.score), 4) for p in upper_hits]
            == [round(float(p.score), 4) for p in sparse_hits],
        }
        # Document frequencies of the query terms (IDF intuition, client-side df).
        doc_freq: dict[str, int] = {}
        for token in query_tokens:
            doc_freq[token] = sum(
                1 for _, unit, _ in triples if token in tokenize_vietnamese(unit.retrieval_text)
            )
        notes["query_term_doc_frequency"] = doc_freq
        notes["multiword_caveat"] = (
            "BM25 is bag-of-words: 'xe ô tô' is 3 independent tokens with no phrase or "
            "positional matching — any provision containing all terms (anywhere) can rank."
        )
        results["tokenization_notes"] = notes
        return results
    finally:
        client.delete_collection(collection)


def format_report(results: dict[str, object]) -> str:
    """Render the spike results as the human-readable run report."""
    lines: list[str] = []
    lines.append(f"collection: {results['collection']}")
    lines.append(
        f"indexed_points: {results['indexed_points']}  vocab_size: {results['vocab_size']}"
    )
    lines.append(f"query: {results['query']!r} -> tokens {results['query_tokens']}")
    lines.append(
        "expected (contain all query tokens): " + ", ".join(map(str, results["expected_unit_ids"]))
    )
    lines.append("")
    lines.append("[a] sparse BM25 top-5:")
    for hit in results["sparse_top"]:
        lines.append(f"    {hit['id']}  score={hit['score']}  provision={hit['provision_id']}")
    lines.append(f"    sparse_relevance_ok={results['sparse_relevance_ok']}")
    lines.append("")
    lines.append("[b] Query API prefetch [dense, sparse] + Fusion.RRF:")
    lines.append("    dense prefetch top-3 (dummy zero vectors, degenerate scores):")
    for hit in results["dense_prefetch_top"][:3]:
        lines.append(f"        {hit['id']}  score={hit['score']}  provision={hit['provision_id']}")
    lines.append("    sparse prefetch top-3:")
    for hit in results["sparse_prefetch_top"][:3]:
        lines.append(f"        {hit['id']}  score={hit['score']}  provision={hit['provision_id']}")
    lines.append(f"    fused RRF top-{len(results['rrf_fused_top'])}:")
    for hit in results["rrf_fused_top"]:
        lines.append(f"        {hit['id']}  score={hit['score']}  provision={hit['provision_id']}")
    lines.append(f"    rrf_ok={results['rrf_ok']}")
    lines.append("")
    notes: dict[str, object] = results["tokenization_notes"]
    lines.append("[c] Vietnamese tokenization notes:")
    lines.append(f"    raw string query: {notes['raw_string_query']}")
    lines.append(f"    tokenize query: {notes['tokenize_query']}")
    lines.append(f"    multi-word examples: {notes['tokenize_multiword_example']}")
    lines.append(f"    diacritics: {notes['diacritics']}")
    lines.append(f"    case: {notes['case']}")
    lines.append(
        f"    query term doc frequency (of {results['indexed_points']} docs): "
        f"{notes['query_term_doc_frequency']}"
    )
    lines.append(f"    multi-word caveat: {notes['multiword_caveat']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "VNLRAG-42 spike: validate Qdrant server-side BM25 + RRF Query API "
            "on real Vietnamese legal provisions (throwaway collection)."
        )
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("QDRANT_URL", "http://localhost:6333"),
        help="Qdrant URL (default: $QDRANT_URL or http://localhost:6333)",
    )
    parser.add_argument(
        "--fixtures",
        default="nd,luat,tt",
        help="comma-separated parser-benchmark fixtures to index (nd,luat,tt; default all)",
    )
    parser.add_argument(
        "--query", default=DEFAULT_QUERY, help="keyword query for the BM25 relevance check"
    )
    args = parser.parse_args(argv)

    client = QdrantClient(url=args.url, timeout=2)
    if not qdrant_reachable(client):
        print(
            f"[skip] Qdrant not reachable at {args.url} — spike requires a live server.",
            file=sys.stderr,
        )
        return 2

    try:
        from app.retrieval import qdrant_store  # type: ignore[import-not-found]  # noqa: F401

        contract_source = (
            f"app.retrieval.qdrant_store "
            f"({qdrant_store.PROVISION_COLLECTION} / {qdrant_store.PROVISION_ALIAS})"
        )
    except ImportError:
        contract_source = (
            "raw qdrant-client (app.retrieval.qdrant_store not importable on this branch; "
            "config mirrors doc 03 §3.11.1-2 / the VNLRAG-40 contract)"
        )

    fixture_keys = [key.strip() for key in args.fixtures.split(",") if key.strip()]
    triples = load_benchmark_provisions(fixture_keys)
    print(f"qdrant: {args.url}")
    print(f"contract source: {contract_source}")
    print(f"fixtures: {fixture_keys} -> {len(triples)} provisions indexed (throwaway collection)")
    print()

    results = run_spike(client, triples, query_text=args.query)
    print(format_report(results))

    passed = bool(results["sparse_relevance_ok"] and results["rrf_ok"])
    print()
    print(
        f"RESULT: {'PASS' if passed else 'FAIL'} "
        f"(sparse_relevance_ok={results['sparse_relevance_ok']}, rrf_ok={results['rrf_ok']})"
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
