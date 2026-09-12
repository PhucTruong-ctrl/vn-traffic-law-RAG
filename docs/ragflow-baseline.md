# RAGFlow baseline (historical benchmark)

> **Historical record.** RAGFlow was evaluated as a possible local benchmark target during the earlier deployment design. It is not part of the active VNLRAG MVP and is not required for release, retrieval, ingestion, or answer generation. The active runtime is the two-application stack, with a Next.js frontend, FastAPI backend, Supabase REST/Auth persistence, and a local or service-hosted Qdrant collection.

The rest of this document preserves the old benchmark procedure for provenance. Do not use it as the current release runbook.

## Historical contract

RAGFlow is an optional, local-only benchmark target. It is not part of the VNLRAG release compose, answer path, source of truth, or ingestion workers. The baseline uses the pinned image `infiniflow/ragflow:v0.26.4` (the version specified by deployment design) and binds both endpoints to loopback.

Copy `deploy/env/ragflow.env.example` to an untracked local env file and fill in only the credentials required by the local RAGFlow installation. Never commit secrets. The supported non-secret settings are:

- `RAGFLOW_IMAGE`: pinned image reference; do not use `latest`.
- `RAGFLOW_WEB_PORT`: loopback web port (default `8088`).
- `RAGFLOW_API_PORT`: loopback API port (default `9380`).
- `RAGFLOW_API_HOST`: container bind address (default `0.0.0.0`).

The compose healthcheck is deterministic. It requires HTTP `200` from `http://127.0.0.1:80/healthz` twelve times at ten-second intervals after a 30-second startup grace period. A healthy container does not prove that a corpus has been ingested.

## Start and stop

Run from the repository root:

```bash
docker compose --project-directory . \
  -f deploy/compose/compose.ragflow.yml \
  --profile ragflow up -d

docker compose --project-directory . \
  -f deploy/compose/compose.ragflow.yml \
  --profile ragflow down
```

## Active release checks

The following checks replace the historical compose topology above. The active release has only `frontend`, `backend`, and `qdrant` services. Supabase is an external persistence/auth dependency. The release compose has no worker, PostgreSQL, Redis, MinIO, or RAGFlow service.

```bash
docker compose --project-directory . -f deploy/compose/compose.release.yml config
docker compose --project-directory . -f deploy/compose/compose.release.yml up -d
curl --fail http://127.0.0.1:8000/api/v1/health/live
curl --fail http://127.0.0.1:8000/api/v1/health/ready
curl --fail http://127.0.0.1:3000
docker compose --project-directory . -f deploy/compose/compose.release.yml down
```

The backend retrieves from Qdrant's `traffic_law` collection, combining dense OpenRouter embeddings with FastEmbed BM25. It then applies deterministic evidence checks before one OpenRouter generation. Legal answers expose citations, and the backend fails closed with HTTP 503 when retrieval or generation dependencies are unavailable.

## Adapter boundary

`app.ingestion.adapters.ragflow_adapter` defines the application-owned `RAGFlowIngestionPort` and `RAGFlowRetrievalPort`. Implementations may translate `RetrievalUnit` values to RAGFlow documents and translate results back to the existing `CandidateSet`; provider SDK objects must not cross that boundary. The existing parser, legal-boundary chunking, citation, and verification paths remain independent of RAGFlow.