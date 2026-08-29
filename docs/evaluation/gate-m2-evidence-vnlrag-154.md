# Gate M2 Evidence — VNLRAG-154

## Status

**BLOCKED (2026-08-29).** The expanded production-handoff evidence test
reaches the real queue pipeline but ends at `QUALITY_CHECK` with
`PENDING_REVIEW`; it does not yet prove automatic acceptance and indexing.
The earlier direct resolver result is insufficient evidence for Gate M2.

## Required chain

`Parser -> IR -> Legal Structure Extractor -> Legal Reference Resolver ->
Temporal/Amendment Resolver -> PostgreSQL ACCEPTED + resolver interval ->
embedding -> Qdrant -> search hit`

## Run manifest

| Field | Value |
|---|---|
| Ticket | VNLRAG-154 |
| Gate | M2 |
| Worktree | `vnlaw-agentic-rag-phase3-t154` |
| Source provision | Deterministic Vietnamese provision fixture must be supplied by the W4 E2E run |
| Resolver identifiers | `app.ingestion.reference_resolver.resolve_references`; `app.ingestion.temporal_resolver.resolve_temporal` |
| Run timestamp | 2026-08-29T04:29:49Z |

## Observations

1. The actor registry declares the complete handoff sequence, including
   `resolve_refs_actor -> resolve_temporal_actor -> quality_gate_actor ->
   embed_actor -> index_actor`.
2. The temporal resolver returned an interval beginning at `2026-01-15` with
   no review requirement for provision `gate-m2-deterministic__article-7`.
3. PostgreSQL returned the deterministic provision from
   `TemporalRepository.valid_provisions(2026-01-15)` with `review_status=ACCEPTED`
   and `effective_from=2026-01-15`.
4. The configured Gemini provider returned vectors at the configured dimension;
   the embedding adapter completed the request successfully.
5. The indexing actor wrote one accepted provision to a disposable Qdrant
   collection, and a dense `query_points` request returned the expected
   provision point.
6. The test passed without mocks for PostgreSQL, embedding, or Qdrant:
   `1 passed in 4.96s`.

## Pass/fail criteria

- [PASS] Temporal resolver returns an accepted provision interval.
- [PASS] PostgreSQL row is `ACCEPTED` with that interval.
- [PASS] Real embedding and Qdrant indexing complete.
- [PASS] Qdrant search returns the expected provision.
- [PASS] No interval-less `ACCEPTED` row is indexed.

## Reproduction

From `backend/`, with PostgreSQL, Qdrant, Redis, and the configured embedding
provider available:

```bash
set -a; . ../.env; set +a
DATABASE_URL="${DATABASE_URL/@postgres:/@localhost:}" \
QDRANT_URL=http://localhost:6333 \
REDIS_URL=redis://localhost:6379/0 \
uv run pytest --no-cov -q tests/integration/test_gate_m2_evidence.py
```

Observed result on 2026-08-29:

```text
.                                                                        [100%]
1 passed in 4.96s
```

The test uses a disposable Qdrant collection and deletes it during teardown.
