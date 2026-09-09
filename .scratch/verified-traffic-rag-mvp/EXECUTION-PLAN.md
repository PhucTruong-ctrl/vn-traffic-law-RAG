# VNLRAG MVP — Complete Execution Plan

Status: ready-for-agent

## 0. Definition of done

Release is complete only when all conditions pass:

1. Exactly 14 deduplicated local PDFs are represented by one immutable corpus snapshot.
2. Every target PDF has recorded source URL, exact allowlist validation, SHA-256, parser/OCR outcome, gate outcome and artifact paths.
3. PostgreSQL accepted provisions, temporal intervals and relations reconcile with the snapshot.
4. Qdrant active alias contains exactly the accepted serving corpus; rejected/non-serving records are absent.
5. Dense embedding model/revision/dimensions and sparse vocabulary are versioned and reproducible.
6. Greeting, out-of-scope, corpus-not-covered, insufficient-evidence, operational error and verified statuses are distinct end to end.
7. The three demo legal questions produce either verified cited answers or precise evidence/coverage abstentions; none is mislabeled by fallback default.
8. Search returns only serving provisions and opens source passage metadata.
9. Feedback accepts only anonymous LIKE/DISLIKE and never mutates legal data or release state.
10. Gold set is frozen at 200 records: 40 development, 40 validation, 120 final; all 200 run before release.
11. Release report includes retrieval, evidence, temporal, citation, numeric, verified-answer and abstention metrics.
12. Hard gates pass: invalid citation rate = 0, no rejected provision in results, no current answer from superseded version, no unsupported numeric claim, no unclassified workflow failure.

## 1. Non-negotiable decisions

- Single-user on localhost/private network; no application authentication, admin role, reviewer role, approval UI or approval API.
- Manual CLI is the only product ingestion trigger. A worker may execute CLI-submitted work, but worker availability is not a product contract.
- Exact HTTPS `datafiles.chinhphu.vn` allowlist. No arbitrary upload and no query-time web fetch.
- Snapshot/hash is immutable. Failed candidate snapshot never replaces the active snapshot/index.
- Automatic outcomes are `ACCEPTED` or `REJECTED`; rejected artifacts remain diagnosable but non-serving.
- Query-time search is exact + sparse + dense + fusion/context expansion over serving corpus only.
- Local embedding candidates already installed/cached are benchmarked in a bounded experiment; selected model/version requires collection rebuild.
- Feedback is anonymous LIKE/DISLIKE only, non-gating, non-training and non-mutating.
- Year-only query uses 01/07 when no in-year effect transition exists; otherwise `MISSING_QUERY_DATE`.
- Unspecified vehicle queries list separately evidenced vehicle/actor cases; never silently default to xe máy.

## 2. Execution sequence

### Phase A — Contract and migration foundation

**A1. Status taxonomy cutover**

Implement one canonical response classification across query plan, workflow state, API payload, conversation reconstruction and frontend types:

```text
VERIFIED
GREETING
OUT_OF_SCOPE
CORPUS_NOT_COVERED
INSUFFICIENT_EVIDENCE
WORKFLOW_UNAVAILABLE
PROVIDER_ERROR
MISSING_QUERY_DATE
UNSUPPORTED_VEHICLE
```

Remove fallback behavior that maps every non-valid result to `INSUFFICIENT_EVIDENCE`.

**A2. Serving-state migration**

Migrate every runtime boundary from review-oriented state to automatic serving state:

```text
ACCEPTED | REJECTED
```

Remove active `PENDING`, `NEEDS_REVIEW`, `PENDING_REVIEW`, `DROPPED`, reviewer fields, approval APIs and upload ingestion path. Update persistence checks, actors, reconciliation, Qdrant payload filters, verification and tests together.

### Phase B — Query correctness

**B1. Classification**

Add deterministic greeting detection before legal retrieval. Add domain/corpus classification without web lookup. Preserve legal query analysis for current, historical, comparison, source reference, vehicle and date policy.

**B2. Canonical legal concepts**

Create one terminology/concept seam shared by query expansion and evidence gate. Cover red-light, phone-use, helmet, lane, speed, alcohol and penalty variants. Keep source text immutable.

**B3. Evidence completeness**

Replace literal marker scoping with concept-aware candidate scoping. Parse monetary ranges and sanction companions. Ensure targeted repair cannot discard statutory-language candidates.

### Phase C — Corpus and serving index

**C1. Immutable 14-PDF snapshot**

Build target manifest from exactly 14 local PDFs, deduplicate `nd-168-2024`, verify exact source host and hashes, and persist snapshot ID/hash.

**C2. Full ingestion**

Run all 14 through parser route, OCR fallback where required, IR, legal structure extraction, reference resolution, temporal resolution and automatic gates. Do not silently skip failures.

**C3. Reconciliation**

Produce one report with counts and identity sets at each stage:

```text
snapshot PDFs
→ parsed documents/pages/elements
→ extracted provisions
→ accepted provisions
→ PostgreSQL accepted rows
→ embedded rows
→ Qdrant points
→ active alias
```

Every mismatch blocks promotion and records a reason.

**C4. Local embedding benchmark**

Benchmark only installed/cached candidates using a bounded retrieval dataset. Record model revision, dimensions, prefix/config, throughput, quality metrics, artifact hash and selected manifest.

**C5. Versioned rebuild**

Build new Qdrant collection with dense+sparse vectors, persisted sparse vocabulary and complete payload. Run smoke/regression retrieval. Atomically promote alias only after reconciliation and gates pass. Keep old collection for rollback.

### Phase D — Answer surface

**D1. Citation/passage contract**

Expose source text, parent context, document identity, Điều/Khoản/Điểm, page, source URL and snapshot/hash. Reject citation to non-serving records.

**D2. Serving-corpus search**

Search only active accepted corpus. Return stable metadata and open passage panel; never fetch web at query time.

**D3. Feedback contract**

Replace correctness/comment feedback with `LIKE | DISLIKE`. Store minimal anonymous event linked to trace/message and non-sensitive version metadata. Feedback failure is non-blocking.

### Phase E — Evaluation and release

**E1. Gold-set freeze**

Complete and review 200 records across 17 categories, freeze 40/40/120 splits, hash dataset and ensure expected evidence/provisions/temporal metadata are valid.

**E2. Full execution**

Run all 200 against the actual serving runtime, not fixture-only adapters. Persist per-question outputs, retrieved IDs, evidence coverage, citations, status, latency and error.

**E3. Release report**

Generate metrics and hard-gate report. Any hard-gate failure blocks release and produces a named remediation ticket.

### Phase F — Documentation and defense package

Synchronize README, CONTEXT, docs/00–08, ADR references, tracker and release manifest. Remove stale model/scope/reviewer claims. Prepare one reproducible defense script with startup, corpus health, demo questions, search/citation, feedback, evaluation report and rollback evidence.

## 3. Ticket order and dependencies

Use one tracker directory only: `.scratch/verified-traffic-rag-mvp/`.

```text
01 Status taxonomy
02 Serving-state migration                 [01]
03 Corpus snapshot/reconciliation          none
04 Full 14-PDF ingestion                   [02,03]
05 Local embedding benchmark               [03]
06 Versioned Qdrant rebuild/promotion      [02,03,04,05]
07 Evidence concept matching               [01]
08 Citation/passage contract               [02,06]
09 Serving-corpus search                   [06,08]
10 Minimal LIKE/DISLIKE feedback            [01]
11 Gold-set freeze 200                      [03,07]
12 Full 200 evaluation/release gate         [06,07,08,09,11]
13 Documentation/defense package            [01-12]
```

The old nine tickets are superseded by this dependency-complete list. Do not implement against both ticket sets.

## 4. Acceptance evidence per phase

### Foundation

- API contract tests show every status distinct.
- No active production path reads review state or accepts arbitrary uploads.
- Persistence/index filters use accepted serving state.

### Query

- Three reported demo questions pass concept/evidence regression.
- `Hello gemini` is greeting.
- Non-traffic input is out-of-scope.
- Traffic topic absent from 14-PDF snapshot is corpus-not-covered.

### Corpus/index

- Immutable snapshot manifest and hash.
- 14-document stage reconciliation with zero unexplained mismatch.
- Active alias collection identity matches release manifest.
- Rebuild failure rollback smoke test passes.

### Answer surface

- Citation contract tests reject missing/unknown/non-serving provision IDs.
- Search never returns rejected/non-serving records.
- Feedback API rejects comments, categories, raw answer fields and unknown extra fields.

### Evaluation

- Gold readiness is `FROZEN`, not `PARTIAL` or `BLOCKED`.
- All 200 records executed.
- Invalid citation rate is zero.
- Any remaining quality weakness is explicitly reported, never hidden by narrowing the set.

## 5. Known current blockers

- Runtime query taxonomy lacks `GREETING` and `CORPUS_NOT_COVERED`.
- API/conversation/frontend collapse non-verified statuses.
- Evidence gate remains literal-marker based.
- Ingestion exposes arbitrary `POST /documents` and review-oriented states.
- Local PDFs are not proven fully ingested; credible corpus review says serving evidence is partial/contradictory.
- Candidate corpus manifest is `PARTIAL` with 27 metadata entries.
- Qdrant serving proof is contradictory/stale and must be regenerated.
- Gold artifacts are 20/40/60 partial inputs, not frozen 40/40/120.
- No full 200 runner/release report is proven.
- README/docs/01/docs/04/CONTEXT contain stale claims.
- Tracker is split between two slugs and has no map.

## 6. Defense runbook output

The final release must contain:

1. `release-manifest.json` with corpus snapshot, accepted document IDs, active collection alias, embedding manifest, code commit and gold hash.
2. Corpus reconciliation report.
3. Full evaluation report for all 200 records.
4. Hard-gate report and known-limitations report.
5. Demo script for greeting, out-of-scope, three legal questions, date/year query, vehicle-unspecified query, search and citation.
6. Rollback evidence showing failed candidate promotion leaves old alias serving.
7. Minimal feedback persistence evidence showing only LIKE/DISLIKE metadata.
