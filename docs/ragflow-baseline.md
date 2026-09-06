# RAGFlow baseline (benchmark only)

RAGFlow is an optional, local-only benchmark target. It is not part of the
VNLRAG release compose, answer path, source of truth, or ingestion workers.
The baseline uses the pinned image `infiniflow/ragflow:v0.26.4` (the version
specified by deployment design) and binds both endpoints to loopback.

## Contract

Copy `deploy/env/ragflow.env.example` to an untracked local env file and fill
only credentials required by the local RAGFlow installation. Never commit
secrets. The supported non-secret settings are:

- `RAGFLOW_IMAGE`: pinned image reference; do not use `latest`.
- `RAGFLOW_WEB_PORT`: loopback web port (default `8088`).
- `RAGFLOW_API_PORT`: loopback API port (default `9380`).
- `RAGFLOW_API_HOST`: container bind address (default `0.0.0.0`).

The compose healthcheck is deterministic: it requires HTTP `200` from
`http://127.0.0.1:80/healthz` twelve times at ten-second intervals after a
30-second startup grace period. A healthy container does not prove that a
corpus has been ingested.

## Start and stop

From the repository root:

```bash
docker compose --project-directory . \
  -f deploy/compose/compose.ragflow.yml \
  --profile ragflow up -d

docker compose --project-directory . \
  -f deploy/compose/compose.ragflow.yml \
  --profile ragflow ps

docker compose --project-directory . \
  -f deploy/compose/compose.ragflow.yml \
  --profile ragflow down
```

This profile is intentionally separate and must not be started alongside a
heavy ingestion/evaluation run. No external RAGFlow deployment or benchmark
run is claimed by this baseline.

## Gate M6 demo stabilization checks

These are runnable checks for the operator; this document does not claim that
they have been run.

```bash
# 1. Validate the release graph and required healthchecks without starting it.
docker compose --project-directory . -f deploy/compose/compose.release.yml config >/tmp/vnlaw-release.yml
python - <<'PY'
import yaml
with open('/tmp/vnlaw-release.yml') as f:
    services = yaml.safe_load(f)["services"]
assert set(services) == {"frontend", "backend", "worker", "postgres", "qdrant", "redis", "minio", "migrate"}
assert all("healthcheck" in spec for name, spec in services.items() if name != "migrate")
PY

# 2. Start the release stack and wait for app health.
docker compose --project-directory . -f deploy/compose/compose.release.yml up -d
curl --fail http://127.0.0.1:8000/api/v1/health/live
curl --fail http://127.0.0.1:3000

# 3. Exercise deterministic browser smoke checks against a mockable API boundary.
(cd frontend && npm ci && npx playwright install chromium && npm run test:e2e)

# 4. Stop the stack after the rehearsal.
docker compose --project-directory . -f deploy/compose/compose.release.yml down
```

## Adapter boundary

`app.ingestion.adapters.ragflow_adapter` defines the application-owned
`RAGFlowIngestionPort` and `RAGFlowRetrievalPort`. Implementations may translate
`RetrievalUnit` values to RAGFlow documents and translate results back to the
existing `CandidateSet`; provider SDK objects must not cross that boundary.
The existing parser, legal-boundary chunking, citation, and verification paths
remain independent of RAGFlow.
