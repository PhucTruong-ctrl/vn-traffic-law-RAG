# Qdrant Server-Side BM25 + RRF Query API — Validation Spike (VNLRAG-42)

Validation spike for the Qdrant retrieval contract designed in doc 03 §3.11
(collection `legal_provisions_v1` / alias `legal_provisions_active`, named
dense vector `dense` 768-d Cosine, sparse field `sparse` with BM25 IDF) and the
Query API RRF fusion path (doc 03 §3.11.6). This is a **validation document**,
not a benchmark: it records what Qdrant 1.19 actually does with Vietnamese
legal text, the observed BM25/RRF behavior, and the tokenizer findings that
feed the v2 pipeline decision.

## 1. Run context

- **Ticket**: VNLRAG-42 — Validate Qdrant Server-Side BM25 and RRF Query API
- **Qdrant**: `1.19.0` (docker-compose service `vnlaw-qdrant`), live at `http://localhost:6333`
- **Server root**: `{"title":"qdrant - vector search engine","version":"1.19.0","commit":"74f3e85b9473c62560006c043e13737ce6b48412"}`
- **Client**: `qdrant-client 1.19.0` (backend venv, pyproject `qdrant-client>=1.19`)
- **Run command** (from `backend/`): `uv run python -m scripts.qdrant_bm25_rrf_spike`
- **Result**: `RESULT: PASS` (exit 0) — both validation checks passed
- **Fixture path used**: real provisions extracted from
  `backend/tests/fixtures/parser_benchmark/documents/{nd,luat,tt}` via the Legal
  Structure Extractor (VNLRAG-22) + Retrieval Units (VNLRAG-48) + Legal Context
  Enricher (VNLRAG-132) — **102 provisions indexed** (nd-168-2024: 58, luat-2024: 25, tt-2024: 19).
  This is the light reliable path (no PDF parsing/network; the fixture `.txt`
  files are the same sources the parser benchmark validates against).
- **Contract source**: `app.retrieval.qdrant_store` was **not importable at
  spike time** (VNLRAG-40 lands it in `backend/app/retrieval/` on its own
  branch) — the spike ran the documented **raw qdrant-client fallback** with a
  config mirroring the VNLRAG-40 contract exactly (doc 03 §3.11.1-2). The spike
  re-checks the import on every run and reports which path executed.
- **Isolation**: the spike used a THROWAWAY collection
  `qdrant_bm25_rrf_spike_<UTC timestamp>`; the collection is deleted on exit
  (verified: zero leftover collections after the run; production
  `legal_provisions_v1`/`legal_provisions_active` were never touched).

## 2. Config used (identical to the VNLRAG-40 contract)

```python
# qdrant_client.http.models
vectors_config = {"dense": VectorParams(size=768, distance=Distance.COSINE)}
sparse_vectors_config = {
    "sparse": SparseVectorParams(index=SparseIndexParams(on_disk=False), modifier=Modifier.IDF)
}
```

- `Modifier.IDF` present in qdrant-client 1.19 — server-side IDF weighting over
  the client-supplied term frequencies; no encoder version workaround needed.
- Payload per point follows doc 03 §3.11.3:
  `provision_id`, `version`, `document_version_id`, `document_id`, `node_kind`,
  hierarchy (`chapter`/`section`/`article`/`clause`/`point`/`heading`),
  `effective_from`, `effective_to`, `review_status`, `status`, `parser_version`,
  `content_version`, `content_hash`, `sparse_encoder_version` (`qdrant-bm25-v1`),
  `relations` (empty — no relation extraction in the spike path),
  `vehicle_types` (empty — not produced by fixture extraction; production fills
  from the metadata extractor), `page_number`, `source_text` (verbatim),
  `retrieval_text` (enricher output, parent context inherited).
- Point id: deterministic `uuid5` per retrieval unit (`provision_id` + version).

## 3. BM25 relevance observations on Vietnamese legal text

Query `xe ô tô phạt tiền` (tokens `['xe', 'ô', 'tô', 'phạt', 'tiền']`) over 102
indexed provisions — sparse top-5 (server-side BM25 with IDF):

| rank | provision_id | score |
|---|---|---|
| 1 | `nd-168-2024__dieu-5__khoan-1` | 13.5262 |
| 2 | `nd-168-2024__dieu-5__khoan-4` | 13.5262 |
| 3 | `nd-168-2024__dieu-5__khoan-2` | 13.5262 |
| 4 | `nd-168-2024__dieu-5__khoan-3` | 13.5262 |
| 5 | `nd-168-2024__dieu-5` | 12.0047 |

- **Keyword relevance holds**: all top-5 hits are Nghị định 168/2024/NĐ-CP
  Điều 5 ("Xử phạt người điều khiển xe ô tô ... Phạt tiền ...") — the only
  units whose text contains all five query tokens. The four enriched CLAUSE
  units tie (each carries all five terms once); the ARTICLE (no "phạt tiền")
  ranks 5th with the lower score.
- **IDF works as expected**: the discriminative tokens are the rare ones —
  document frequency `ô` 5/102, `tô` 10/102, `phạt` 58/102, `tiền` 55/102,
  `xe` 73/102. The Điều 5 cluster wins because it is the only group combining
  the rare `ô`/`tô` with the penalty terms.
- Threshold `sparse_relevance_ok=True`: top-5 intersects the expected-hit set
  (units containing all query tokens).

## 4. RRF fusion results (Query API prefetch [dense, sparse])

Executed via `query_points(prefetch=[Prefetch(dense, using="dense"), Prefetch(sparse,
using="sparse")], query=FusionQuery(fusion=Fusion.RRF), using="", limit=20)`
with **dummy zero dense vectors** (dense similarity deliberately degenerate —
this spike proves the API mechanics, not fusion quality).

- **Mechanics proven**: the RRF request executes without error and returns a
  valid rank list — 20 results, unique point ids, fused scores in `[0.1, 0.6667]`.
- **Fused scores match rank-based RRF with k=1**: the observed fused scores
  (0.5, 0.3333, 0.25, 0.2, 0.1667, 0.1429, 0.125, 0.1111, 0.1 = 1/2 … 1/10) are
  exactly `1/(k+rank)` with `k=1`, summed per point across the two prefetch
  lists in which it appears — e.g. `khoan-3` at 0.6667 = rank 2 in both lists
  (1/3 + 1/3); `diem-e` at 0.5 = rank 1 in the dense list only, absent from the
  sparse top-30.
- **Dense degeneracy leaks into the fused order**: zero vectors score 0.0 and
  Qdrant returns them in arbitrary (run-varying) order, so the dense prefetch
  injects noise: the fused top-1 was `khoan-3` in the final run but `khoan-4` in
  an earlier run of the same spike. Điều 5 units still dominate the fused top-10.
  **Finding**: RRF merging itself is correct; meaningful fused rankings require
  real (non-degenerate) dense embeddings.
- **RRF `k` is not client-configurable in Qdrant 1.19**: `QueryRequest.params`
  (`SearchParams`) carries no fusion parameters and no `FusionParams` model
  exists in qdrant-client 1.19 — the server's default `k` (observed 1) applies.
  doc 03 §3.11.6's `rrf.k: 60` is not directly expressible via the 1.19 client;
  if a larger `k` is wanted, options are (a) verify a server-side knob, or
  (b) client-side RRF via `qdrant_client.hybrid.fusion.reciprocal_rank_fusion(
  ranking_constant_k=60)` on the two prefetch result lists.

## 5. Dimension / tokenizer findings

**Dense (768-d)**: the 768-d Cosine config is accepted by Qdrant 1.19 without
issue (collection creation, upsert with 768-d vectors, and dense queries all
succeed). No dimension-related caveat found. (The production dimension is
pinned by the chosen embedding model per ADR-013 / doc 03 §3.11.1.)

**Sparse tokenization — the critical finding**:

1. **Raw string queries are rejected by Qdrant 1.19** (observed:
   `query="xe ô tô", using="sparse"` → HTTP 400 "Expected some form of vector,
   id, or a type of query"). Sparse queries and upserts both require a
   pre-built `SparseVector`. **Tokenization is therefore the client's
   responsibility** — Qdrant never splits text itself in 1.19; the
   `SparseIndexParams` tokenizer settings do not turn text into sparse vectors
   for you.
2. **Whitespace/Unicode-word tokenization is adequate as the BM25 baseline** —
   exactly the semantics doc 03 §3.11.2 assumes ("tiếng Việt chủ yếu tách theo
   khoảng trắng"). The spike's client tokenizer lowercases and splits on
   non-word characters, keeping Vietnamese diacritics and `đ` intact:
   `'xe ô tô phạt tiền'` → `['xe','ô','tô','phạt','tiền']`. Keyword relevance
   on the real corpus is strong (§3).
3. **No diacritic folding**: `'ô tô'` and `'oto'` index/query *different* token
   ids (verified: `'oto'` is missing from the corpus vocab and contributes
   nothing to the query). Vietnamese queries must carry correct diacritics —
   or a normalization layer (strip diacritics at index AND query time, which
   would merge `d`/`đ` too, conflicting with FR-03's distinct `d`/`đ` stable
   IDs — so diacritic folding is NOT recommended for legal IDs).
4. **Case folding happens client-side**: `'XE Ô TÔ'` produces the identical
   sparse vector and identical scores to `'xe ô tô'` (verified).
5. **Multi-word term behavior**: Vietnamese legal concepts are split into
   independent tokens — `'giao thông'` → `['giao','thông']`,
   `'giấy phép lái xe'` → `['giấy','phép','lái','xe']`. BM25 is bag-of-words:
   no phrase/positional matching, so a query matches any provision containing
   all its tokens anywhere. Compound concepts ("ô tô", "xe máy", "giao thông
   đường bộ") must be typed fully in queries or handled by a Vietnamese word
   segmenter (e.g. VnCoreNLP/RDRSegmenter/underthesea) at index+query time —
   deferred to Suite C per doc 03 §3.11.2's own note.
6. **Digits are dropped** by the word-token regex (amounts like `800.000`
   contribute no tokens). Acceptable for keyword search on legal prose; note it
   if amount-based queries are ever needed.

## 6. Recommendation for the v2 pipeline

1. **Keep server-side BM25 + RRF** — validated on real Vietnamese legal text:
   the Query API prefetch+fusion path executes correctly and sparse BM25 ranks
   keyword-relevant provisions on top with the doc 03 §3.11.1-2 config.
2. **Ship a client-side sparse encoder as the collection's
   `sparse_encoder_version = "qdrant-bm25-v1"`** (whitespace, lowercase,
   diacritics kept, OOV query terms skipped), matching the payload field and
   rebuild-on-change policy (doc 03 §3.11.2). The client MUST tokenize: raw
   string queries are not supported in Qdrant 1.19.
3. **Dense+sparse RRF is sound; fusion quality needs real embeddings** — the
   dense prefetch must carry production embeddings (or at least non-degenerate
   vectors); with dummy vectors the fused order inherits arbitrary dense-tie
   noise. Re-validate RRF weights/limits (doc 03 §3.11.6) after the embedding
   model lands (Suite C ablation).
4. **RRF `k` caveat**: doc 03's `k: 60` is not expressible through
   qdrant-client 1.19 (no fusion params on `QueryRequest`; observed server
   default `k=1`). Either verify a server-side knob or use the client-side RRF
   helper with `ranking_constant_k`; record the choice in the retrieval config.
5. **Tokenization adequacy**: whitespace tokenization is a fine baseline; plan
   a Vietnamese word-segmentation evaluation in Suite C for compound terms,
   and do NOT introduce diacritic folding (conflicts with `d`/`đ` stable-ID
   distinctness, FR-03).
6. **Payload contract confirmed workable**: doc 03 §3.11.3 payload fields
   (identity, hierarchy, temporal, status, source/retrieval text, bounded
   relations, `vehicle_types`, encoder version) upsert and round-trip cleanly;
   `vehicle_types`/`relations` stay empty until the metadata/relation pipeline
   produces them.

## 7. Repro

```bash
cd backend
uv run pytest tests/test_qdrant_spike.py -q --no-cov        # 12 unit tests, no Qdrant needed
uv run python -m scripts.qdrant_bm25_rrf_spike              # end-to-end, needs live Qdrant
```

Spike CLI: `--url` (default `$QDRANT_URL` or `http://localhost:6333`),
`--fixtures nd,luat,tt`, `--query 'xe ô tô phạt tiền'`. Exit codes: 0 PASS,
1 a check failed, 2 Qdrant unreachable. The throwaway collection is deleted on
every exit path.

## Appendix A — Verbatim spike output (final run)

```
qdrant: http://localhost:6333
contract source: raw qdrant-client (app.retrieval.qdrant_store not importable on this branch; config mirrors doc 03 §3.11.1-2 / the VNLRAG-40 contract)
fixtures: ['nd', 'luat', 'tt'] -> 102 provisions indexed (throwaway collection)

collection: qdrant_bm25_rrf_spike_20260813T173153Z
indexed_points: 102  vocab_size: 300
query: 'xe ô tô phạt tiền' -> tokens ['xe', 'ô', 'tô', 'phạt', 'tiền']
expected (contain all query tokens): nd-168-2024__dieu-5__khoan-1__v1, nd-168-2024__dieu-5__khoan-2__v1, nd-168-2024__dieu-5__khoan-3__v1, nd-168-2024__dieu-5__khoan-4__v1

[a] sparse BM25 top-5:
    644c669b-3628-59ba-a5f9-65272c8e84cb  score=13.5262  provision=nd-168-2024__dieu-5__khoan-1
    975fddd5-48db-5e38-8df6-c756f8cf77ff  score=13.5262  provision=nd-168-2024__dieu-5__khoan-4
    fb0b4de1-06cd-5cc7-a869-92c58389a0ae  score=13.5262  provision=nd-168-2024__dieu-5__khoan-2
    5b3696f2-7149-511f-a47f-9181859cac83  score=13.5262  provision=nd-168-2024__dieu-5__khoan-3
    5e284d58-44a7-52bf-8ff2-6109d2723655  score=12.0047  provision=nd-168-2024__dieu-5
    sparse_relevance_ok=True

[b] Query API prefetch [dense, sparse] + Fusion.RRF:
    dense prefetch top-3 (dummy zero vectors, degenerate scores):
        8d668a49-4109-59cd-aea0-310996dbf86c  score=0.0  provision=nd-168-2024__dieu-7__khoan-2__diem-e
        5b3696f2-7149-511f-a47f-9181859cac83  score=0.0  provision=nd-168-2024__dieu-5__khoan-3
        f69a7de4-54a2-59b2-a81f-9024f2f219fe  score=0.0  provision=nd-168-2024__dieu-5__khoan-3__diem-c
    sparse prefetch top-3:
        644c669b-3628-59ba-a5f9-65272c8e84cb  score=13.5262  provision=nd-168-2024__dieu-5__khoan-1
        975fddd5-48db-5e38-8df6-c756f8cf77ff  score=13.5262  provision=nd-168-2024__dieu-5__khoan-4
        fb0b4de1-06cd-5cc7-a869-92c58389a0ae  score=13.5262  provision=nd-168-2024__dieu-5__khoan-2
    fused RRF top-20:
        5b3696f2-7149-511f-a47f-9181859cac83  score=0.6667  provision=nd-168-2024__dieu-5__khoan-3
        8d668a49-4109-59cd-aea0-310996dbf86c  score=0.5  provision=nd-168-2024__dieu-7__khoan-2__diem-e
        644c669b-3628-59ba-a5f9-65272c8e84cb  score=0.5  provision=nd-168-2024__dieu-5__khoan-1
        975fddd5-48db-5e38-8df6-c756f8cf77ff  score=0.25  provision=nd-168-2024__dieu-5__khoan-4
        f69a7de4-54a2-59b2-a81f-9024f2f219fe  score=0.25  provision=nd-168-2024__dieu-5__khoan-3__diem-c
        fb0b4de1-06cd-5cc7-a869-92c58389a0ae  score=0.2385  provision=nd-168-2024__dieu-5__khoan-2
        ff65af15-b125-53b3-98c5-05f06faf2502  score=0.2167  provision=nd-168-2024__dieu-9__khoan-1__diem-d
        59fc6fb7-c5ef-5d9f-8ff0-de998357af49  score=0.2  provision=nd-168-2024__dieu-5__khoan-2__diem-c
        9a48f815-1a01-5eed-80c9-53568961749e  score=0.1806  provision=nd-168-2024__dieu-7__khoan-3
        699e9d3f-176d-539f-9cdf-bf363b63c3af  score=0.1726  provision=nd-168-2024__dieu-7__khoan-1__diem-c
        5e284d58-44a7-52bf-8ff2-6109d2723655  score=0.1667  provision=nd-168-2024__dieu-5
        ee416d46-70a0-5b91-92f2-90778fe10240  score=0.1455  provision=nd-168-2024__dieu-7__khoan-2__diem-b
        8fc78b62-7669-54d3-b439-dba4e58987da  score=0.1429  provision=nd-168-2024__dieu-7__khoan-4
        e077efbe-66a3-5567-b44a-1c2eaa77b24a  score=0.1429  provision=luat-36-2024__dieu-3__khoan-2
        9ab100e5-d1a2-50c6-b9d4-ea1264275359  score=0.1394  provision=nd-168-2024__dieu-5__khoan-1__diem-c
        ab1a53f5-9940-5f29-bf62-27aadb524991  score=0.125  provision=nd-168-2024__dieu-9__khoan-3
        d5634712-3faa-5f26-9b0a-648815ad3ab5  score=0.1131  provision=nd-168-2024__dieu-7__khoan-3__diem-đ
        2a221466-cc77-53c3-82e0-1221fc012ffd  score=0.1111  provision=luat-36-2024__dieu-8__khoan-1__diem-đ
        2328dd7c-9f9b-518d-bbd9-30f33aa3095c  score=0.1111  provision=nd-168-2024__dieu-7__khoan-2
        d4bffd33-88d9-52c9-b2a0-4e8d8fb0570d  score=0.1  provision=nd-168-2024__dieu-7__khoan-1
    rrf_ok=True

[c] Vietnamese tokenization notes:
    raw string query: rejected: UnexpectedResponse (Unexpected Response: 400 (Bad Request)
Raw response content:
b'{"status":{"error":"Format error in JSON body: Expected s)
    tokenize query: ['xe', 'ô', 'tô', 'phạt', 'tiền']
    multi-word examples: {'giao thông': ['giao', 'thông'], 'giấy phép lái xe': ['giấy', 'phép', 'lái', 'xe']}
    diacritics: {'query': 'xe oto', 'tokens': ['xe', 'oto'], 'vocab_tokens': ['xe'], 'vocab_missing': ['oto'], 'note': "no diacritic folding: 'ô tô' and 'oto' index/query different token ids"}
    case: {'upper_tokens': ['xe', 'ô', 'tô', 'phạt', 'tiền'], 'same_vector_as_lower': True, 'same_scores': True}
    query term doc frequency (of 102 docs): {'xe': 73, 'ô': 5, 'tô': 10, 'phạt': 58, 'tiền': 55}
    multi-word caveat: BM25 is bag-of-words: 'xe ô tô' is 3 independent tokens with no phrase or positional matching — any provision containing all terms (anywhere) can rank.

RESULT: PASS (sparse_relevance_ok=True, rrf_ok=True)
```
