# VNLRAG defense runbook

This runbook is the reproducible operator path for the active MVP contract. It records commands and evidence locations; it does not claim that a gate passed until the referenced artifact says so.

## 1. Start and health

```bash
cp .env.example .env
uv run --project backend alembic upgrade head
docker compose --env-file .env up -d
# Start API using the repository's configured command:
uv run --project backend uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Check service health before continuing:

```bash
curl --fail http://127.0.0.1:8000/health
# Confirm PostgreSQL, Qdrant and Redis/MinIO health in:
docker compose ps
```

Record the output and timestamp in the release evidence directory. If health is not ready, stop; do not run ingestion or evaluation.

## 2. Corpus snapshot and ingestion

The active corpus is exactly 14 deduplicated local PDFs from `datafiles.chinhphu.vn`. Ingestion is manual CLI only:

```bash
uv run --project backend python scripts/validate_manifest.py data/candidate-corpus-manifest.json
uv run --project backend python scripts/ingest_local_corpus.py --manifest data/candidate-corpus-manifest.json
```

Use the generated snapshot/gate report to fill `release-manifest.json`. Every document must be classified automatically as `ACCEPTED` or `REJECTED`; only accepted records may be indexed. Preserve rejected snapshots and reports. There is no reviewer/auth/approval step. A failed gate leaves the previously active alias unchanged.

## 3. Serving demo, search and citation

Use the running API/UI and capture the response JSON or screenshots for these representative paths:

1. A supported current traffic-law question: verified answer with applied date and provision citation.
2. A greeting such as `Hello gemini`: `GREETING`, not an evidence failure.
3. A traffic-law question outside the 14-PDF corpus: `CORPUS_NOT_COVERED`.
4. An out-of-domain question: `OUT_OF_SCOPE`.

Run serving-corpus search through the search endpoint/UI. Confirm every result is from the active alias and exposes document identity, Điều/Khoản/Điểm, page, source URL, snapshot/hash and passage text. Confirm the citation/passage view rejects unknown or non-serving provision IDs; query-time web lookup is not part of the demo.

## 4. Feedback

Submit one anonymous `LIKE` and one `DISLIKE` through the UI/API and record the trace/message IDs. Feedback is minimal telemetry only: it does not mutate corpus, index, model or gold data and is explicitly non-gating. A feedback storage failure must not change the legal response.

## 5. Embedding and 200-question release evaluation

Run the bounded local embedding benchmark before selecting a model. Record candidate model/version, dimensions, configuration, throughput, quality metrics and artifact hash; do not fill an unmeasured result into the manifest.

Run all 200 frozen gold records against the actual serving runtime, not fixture-only adapters. Persist per-question query, status, retrieved IDs, evidence coverage, citations, latency and error:

```bash
uv run --project backend python scripts/validate_gold_set.py
# Use the repository's release-evaluation command/configuration after the serving runtime is ready.
```

The release report must separate retrieval, evidence completeness, temporal validity, citation validity, numeric grounding, verified-answer rate and abstention taxonomy. Release is blocked unless all 200 execute, invalid citation rate is 0, and no rejected/non-serving provision supports output. Any failed hard gate gets a named remediation record. LIKE/DISLIKE metrics remain non-gating.

## 6. Rollback evidence

Before promotion, record the current active alias and collection in `release-manifest.json`. Promotion is atomic and occurs only after corpus reconciliation, embedding/index smoke checks and evaluation hard gates pass. To roll back, switch the alias to `serving.rollback_target`, verify `/health`, run one supported query and one citation/search check, and preserve the failed release's snapshot, gate report and evaluation outputs. Never delete the prior serving collection before rollback evidence is captured.

## 7. Evidence checklist

- [ ] 14-PDF snapshot ID/hash and accepted/rejected identity sets
- [ ] Automatic gate report and ingestion/reconciliation report
- [ ] Embedding benchmark and selected embedding manifest
- [ ] Gold hash/readiness and 40/40/120 split evidence
- [ ] Per-question outputs for all 200 records
- [ ] Separate evaluation metrics and hard-gate report
- [ ] Startup/health, demo, search/citation and feedback captures
- [ ] Active alias, code commit and rollback evidence

The release manifest remains `TEMPLATE_UNVERIFIED` until these artifacts are produced and their measured values are entered.
