# Gate M2 Evidence — VNLRAG-154

## Status

**FAIL / BLOCKED (2026-08-26).** This report is reproducible evidence that the
current checked-out pipeline does not yet satisfy Gate M2; it does not assert
closure or fabricate external-service observations.

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
| Database/Qdrant config | Repository settings (`DATABASE_URL`, `QDRANT_URL`, collection alias `legal_provisions_active`) |
| Run timestamp | 2026-08-26 (report generation) |

## Observations

1. The actor registry declares the complete handoff sequence, including
   `resolve_refs_actor -> resolve_temporal_actor -> quality_gate_actor ->
   embed_actor -> index_actor`. VNLRAG-31 and VNLRAG-136 are activated in the
   merged `dev/sprint-3` state.
2. With services available, the activated-path integration assertion captures
   the persisted resolver handoff at `status=RESOLVING_REFS` and
   `current_stage=RESOLVING_REFS`, with no `STAGED_ACTOR` error. This is not
   evidence of downstream indexing.
3. With services unavailable, no honest PostgreSQL `ACCEPTED` observation,
   Qdrant point, or search hit is recorded here.
4. The quality gate contract correctly refuses premature acceptance: an
   `ACCEPTED` provision requires `effective_from`; interval-less rows remain
   `PENDING`.
5. The activated resolver handoff must be rerun with reachable PostgreSQL,
   embedding, and Qdrant before Gate M2 can close.

## Pass/fail criteria

- [FAIL] Accepted provision has an interval returned by the temporal resolver:
  execution was blocked by unavailable external services.
- [FAIL] PostgreSQL row is `ACCEPTED` with that interval: no reachable DB
  observation.
- [FAIL] Embedding and Qdrant indexing: no reachable external services.
- [FAIL] Search returns the provision: no point was observed.
- [PASS] No interval-less `ACCEPTED` row is indexed: the quality gate requires
  `effective_from` before acceptance.

## Reproduction

From `backend/`, inspect and run the existing real-path integration test:

```bash
uv run pytest tests/integration/test_queue_actors.py \
  -k activated_resolvers -q
```

Observed prior run result: `1 skipped in 5.93s` (exit status 1), because the
integration fixture could not reach configured external services. No gate pass
is inferred from this skip.
The test demonstrates the activated resolver handoff prerequisite. After the
external services are reachable, append actual resolver interval, PostgreSQL,
embedding, Qdrant, and search observations (timestamps and
configuration/collection identifiers) to this report.
