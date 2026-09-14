# Release Candidate Evidence — 2026-09-14

## Decision

**Release-ready for covered corpus and current MVP runtime.**

This result does not claim complete Vietnamese traffic-law coverage or full
human semantic certification.

## Runtime

- Endpoint: authenticated `POST /api/v1/chat`
- Startup: `./dev.sh`
- `top_k`: 5
- Evaluation fixture: `data/evaluation/thesis-gold-40.json`
- Rows: 40
- Covered rows: 34
- `CORPUS_NOT_COVERED`: `00`, `15`, `16`, `17`, `18`, `19`
- Covered-case request errors: 0

## Metrics

| Metric | Covered result |
|---|---:|
| Citation validity | 1.0 |
| Invalid citation rate | 0% |
| Abstention accuracy | 0.9118 |
| Retrieval hit@5 | 0.3333 |
| Document accuracy | 0.5833 |
| Article accuracy | 0.5833 |
| Clause accuracy | 0.5385 |
| Point accuracy | 0.25 |
| Mean latency | 13.13 s |
| P95 latency | 24.11 s |
| Manual semantic correctness | N/A |

`CORPUS_NOT_COVERED` rows are retained in the 40-row output but excluded from
quality denominators. They represent expected provisions absent from the
serving corpus, not fabricated retrieval failures.

## Automated gates

- Backend Ruff check: pass.
- Backend Ruff format check: pass.
- Backend mypy: pass.
- Backend tests: **161 passed**.
- Frontend lint: 0 errors; two existing React Hook warnings.
- Frontend typecheck: pass.
- Frontend production build: pass.
- Frontend Prettier format check: pass.
- Authenticated exact-reference API smoke: HTTP 200 with citations.

## Limitations

- `answer_correctness_manual` remains N/A because full human semantic review
  was not supplied.
- Corpus coverage is limited to checked-in serving data.
- Public production hardening (TLS, firewall, rate limiting, secret rotation,
  backups, monitoring and load testing) remains deployment work outside this
  local MVP release claim.

## Reproduction

```bash
set -a && . ./.env && set +a
./dev.sh

PYTHONPATH=backend uv run --project backend python \
  backend/scripts/run_thesis_evaluation.py \
  data/evaluation/thesis-gold-40.json \
  --endpoint http://127.0.0.1:8000/api/v1/chat \
  --output-dir data/evaluation/thesis-run
```

The evaluator records raw JSONL, aggregate metrics, corpus coverage status,
request errors, and latency in the selected output directory.
