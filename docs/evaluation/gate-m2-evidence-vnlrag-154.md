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

1. `backend/app/ingestion/actors/__init__.py` documents the intended actor
   sequence, but explicitly says both resolver actors are **STAGED**.
2. `resolve_refs_actor` transitions the run to terminal `STAGED` with
   `STAGED_ACTOR` and sends no next-stage message. Therefore the temporal
   actor, quality gate, embedding, indexing, and search cannot be reached by
   the real actor pipeline.
3. `resolve_temporal_actor` independently has the same staged behavior and
   explicitly does not compute an interval.
4. The quality gate correctly refuses premature acceptance: an `ACCEPTED`
   provision requires `effective_from`; interval-less rows remain `PENDING`.
5. Consequently there is no honest PostgreSQL `ACCEPTED` observation, Qdrant
   point, or search hit to record from this pipeline state.

## Pass/fail criteria

- [FAIL] Accepted provision has an interval returned by the temporal resolver:
  resolver actor is staged.
- [FAIL] PostgreSQL row is `ACCEPTED` with that interval: downstream gate is
  unreachable.
- [FAIL] Embedding and Qdrant indexing: index actor is unreachable.
- [FAIL] Search returns the provision: no point is produced.
- [PASS] No interval-less `ACCEPTED` row is indexed: staged resolver and quality
  gate prevent premature acceptance/indexing.

## Reproduction

From `backend/`, inspect and run the existing real-path integration test:

```bash
uv run pytest tests/integration/test_queue_actors.py -k staged -q
```
 
Observed command result in this environment: `1 skipped in 5.93s` (exit
status 1), because the integration fixture skips when the configured external
services are unavailable. This is an additional blocker, not a passing
observation.

The test demonstrates the resolver halt. A Gate M2 closure run must be added
only after VNLRAG-31 and VNLRAG-136 replace the staged actor bodies; it must
capture actual PostgreSQL, embedding, Qdrant, and search responses in this
report (including timestamps and configuration/collection identifiers).
