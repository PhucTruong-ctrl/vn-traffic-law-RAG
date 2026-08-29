# Gate M2 Evidence — VNLRAG-154

## Status

**PASS (2026-08-29).** The production-handoff evidence test passed against
host-mapped PostgreSQL, Qdrant, Redis, and the configured Gemini embedding
provider. The test uses a disposable Qdrant collection and a deterministic
dated provision hierarchy; it does not modify the production collection.

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
2. The temporal resolver returned accepted dated provision rows beginning at
   `2026-01-15`.
3. PostgreSQL persisted the deterministic provision hierarchy with
   `review_status=ACCEPTED` and `effective_from=2026-01-15`.
4. The configured Gemini provider returned vectors at the configured dimension.
5. The indexing actor wrote accepted provisions to a disposable Qdrant
   collection, and a dense `query_points` request returned the expected
   provision point.
6. The test passed without mocks for PostgreSQL, embedding, Redis, or Qdrant:
   `1 passed in 13.42s`.

## Pass/fail criteria

- [PASS] Temporal resolver returns accepted provision intervals.
- [PASS] PostgreSQL rows are `ACCEPTED` with those intervals.
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
1 passed in 13.42s
```

The test uses a disposable Qdrant collection and deletes it during teardown.
