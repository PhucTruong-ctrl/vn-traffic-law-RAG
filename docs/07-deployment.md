# 07. Deployment and runbook

> **Status:** RELEASE-READY FOR COVERED CORPUS / MVP RUNTIME (14 September 2026).
> Public deployment still requires TLS, firewall, rate limiting, secret rotation,
> backup/restore, and monitoring outside this local MVP compose boundary.
>
> The runtime boundary is localhost or a deliberately private network. The active application is FastAPI + Next.js + Qdrant. Supabase and OpenRouter are external services. The target architecture described in the scope document is not presented here as deployed functionality.

Related decisions and evidence:

- [Scope and decisions](00-scope-and-decisions.md)
- [System design](03-thiet-ke-he-thong.md)
- [Tech stack research](04-tech-stack-llm-research.md)
- [Evaluation evidence](evaluation/release-candidate-20260914.md)

## 1. Active topology

The release compose file is [`deploy/compose/compose.release.yml`](../deploy/compose/compose.release.yml). It defines exactly three services:

| Service | Runtime role | Exposure in release compose |
|---|---|---|
| `qdrant` | Qdrant `v1.19.0`, persistent named volume `qdrant_data` | Internal Docker network only |
| `backend` | FastAPI/Uvicorn on port 8000; uses `QDRANT_URL=http://qdrant:6333` | `${BACKEND_PORT:-8000}:8000` |
| `frontend` | Next.js production server on port 3000 | Internal Docker network only unless separately published |

`backend` waits for the Qdrant healthcheck; `frontend` waits for the backend healthcheck. The release compose does not publish the frontend port. To make the UI reachable outside the Docker network, an operator must add an intentional reverse proxy or port publication; that is not supplied by this repository.

The root [`docker-compose.yml`](../docker-compose.yml) is a separate local-development/simple smoke topology. It defines only `backend` and `frontend`, publishes both on `127.0.0.1`, and uses the backend's embedded/local Qdrant path (`/app/data/processed/qdrant`). It is not the release topology and must not be described as containing Qdrant, PostgreSQL, Redis, MinIO, workers, migrations, or parser services.

Neither compose file provisions Supabase or OpenRouter. Supabase supplies authentication and user-owned persistence through its REST/Auth APIs. OpenRouter supplies OpenAI-compatible generation and embedding calls. Their URLs, keys, availability, quotas, and policies remain external deployment prerequisites.

## 2. Release deployment

Run release commands from the repository root. The compose file's build contexts are already written for this location.

For local development, `dev.sh` uses same-origin browser transport by default: it leaves `NEXT_PUBLIC_API_URL` empty, so the browser requests `/api/v1/*` on the Next.js origin and `frontend/next.config.ts` rewrites those requests to `BACKEND_INTERNAL_URL`. This avoids CORS preflights on the chat path. To use a backend on another origin, set `NEXT_PUBLIC_API_URL` explicitly to the browser-reachable API URL; the backend CORS configuration must then allow the frontend origin.

The backend chat budget is controlled by `CHAT_DEADLINE_SECONDS` (default `75`, seconds; must be greater than `0` and no greater than `300`). It is the server budget for `POST /api/v1/chat` and must remain below the client `NEXT_PUBLIC_CHAT_TIMEOUT_MS` (default `120000` milliseconds).

1. Prepare a local `.env` from [`.env.example`](../.env.example). Set at least the Supabase URL/keys and `OPENROUTER_API_KEY`; set frontend public Supabase values and `NEXT_PUBLIC_API_URL` for the address that the browser can actually reach when using cross-origin transport. Never commit `.env`.

```bash
docker compose -f deploy/compose/compose.release.yml up -d --build
```

3. Inspect service state and logs:

```bash
docker compose -f deploy/compose/compose.release.yml ps
docker compose -f deploy/compose/compose.release.yml logs --tail=100 backend
docker compose -f deploy/compose/compose.release.yml logs --tail=100 qdrant
docker compose -f deploy/compose/compose.release.yml logs --tail=100 frontend
```

4. Stop the release stack without deleting its named Qdrant volume:

```bash
docker compose -f deploy/compose/compose.release.yml down
```

5. Remove the Qdrant volume only when deliberately discarding the serving index:

```bash
docker compose -f deploy/compose/compose.release.yml down -v
```

This deployment is not public-hardening. The compose file does not configure TLS, an ingress, firewall policy, rate limiting, a secret manager, network allowlists, or a public authentication boundary. Keep the published backend port on a private interface and place any public exposure behind separately operated controls. Do not claim those controls are active merely because the application authenticates through Supabase.

## 3. Configuration and build-time caveats

The release backend loads `../../.env` through `env_file` and overrides `QDRANT_URL` with the Docker service address. The relevant runtime settings are:

- `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`: external Auth/REST and persistence configuration;
- `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL`, `GENERATION_MODEL`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`: external model calls and vector shape;
- `QDRANT_COLLECTION` and optional `QDRANT_API_KEY`/`QDRANT_TIMEOUT`: collection and client settings. In release, `QDRANT_URL` is supplied by compose and `QDRANT_PATH` is not the serving store;
- `LEGAL_MANIFEST` and `LEGAL_CHUNKS`: corpus/chunk paths used by the ingestion/index scripts, not an upload API.

Frontend values beginning with `NEXT_PUBLIC_` are Docker build arguments in the release compose and are compiled into the Next.js image. Changing `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_SUPABASE_URL`, or `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` requires rebuilding the frontend image; changing only the running container environment does not rewrite already-built browser code. `BACKEND_INTERNAL_URL` is used by the root compose's same-origin rewrite configuration and is not declared by the release compose.

The release compose accepts `${BACKEND_PORT:-8000}` and `${APP_VERSION:-dev}`. `APP_VERSION` labels the built images; it is not evidence of a verified release. The current repository does not provide an automated migration service, release manifest publisher, or production secret-management integration.

## 4. Health and readiness

The backend implements these actual endpoints in [`backend/app/main.py`](../backend/app/main.py):

```bash
curl -i http://127.0.0.1:8000/api/v1/health/live
curl -i http://127.0.0.1:8000/api/v1/health/ready
```

Liveness checks only that the backend process is serving:

```json
{"status":"ok"}
```

Readiness checks Supabase REST reachability/configuration and the configured Qdrant collection. When both checks pass, it returns HTTP 200:

```json
{"status":"ok","supabase":true,"qdrant":true}
```

When either check fails, it returns HTTP 503 and preserves the boolean details, for example:

```json
{"status":"unavailable","supabase":false,"qdrant":true}
```

The release backend healthcheck calls `/api/v1/health/ready`; the frontend healthcheck requests `/`. Qdrant's compose healthcheck opens its internal TCP port 6333. Readiness does not prove OpenRouter generation/embedding calls, answer quality, citation validity, browser reachability, or full evaluation. A green container healthcheck is therefore necessary but not sufficient for release readiness.

## 5. Corpus ingestion and indexing

The active ingestion path is manual and local. The executable scripts are:

- [`backend/scripts/fetch_sources.py`](../backend/scripts/fetch_sources.py): loads the existing manifest and local Markdown corpus, writing `data/processed/chunks.jsonl`;
- [`backend/scripts/index.py`](../backend/scripts/index.py): reads that JSONL and creates a Qdrant hybrid dense+sparse collection.

With the backend environment installed, run from the repository root:

```bash
uv run --project backend python backend/scripts/fetch_sources.py
uv run --project backend python backend/scripts/index.py
```

Useful explicit-path forms are also supported by the scripts:

```bash
uv run --project backend python backend/scripts/fetch_sources.py \
  --manifest data/sources/manifest.json \
  --local-dir data/corpus/mds \
  --output data/processed/chunks.jsonl

uv run --project backend python backend/scripts/index.py \
  --chunks data/processed/chunks.jsonl \
  --collection traffic_law
```

`--force-recreate` requires an explicitly named collection and destroys/recreates that collection; use it only when intentionally rebuilding:

```bash
uv run --project backend python backend/scripts/index.py \
  --chunks data/processed/chunks.jsonl \
  --collection traffic_law \
  --force-recreate
```

The loader currently reads the 17-entry `data/sources/manifest.json` and Markdown files under `data/corpus/mds`; this is runtime evidence, not proof of the frozen 14-PDF release contract. The index script uses `OpenAIEmbeddings` through the configured OpenRouter-compatible endpoint and FastEmbed `Qdrant/bm25`, then checks the collection point count. Provider credentials and the serving Qdrant location must be available to the process running the script. In the release container, Qdrant is reached at `http://qdrant:6333`; host-side ingestion must instead use a reachable Qdrant URL or a deliberately configured local path.

- The release backend port uses `${BACKEND_PORT:-8000}:8000` without an explicit host-interface restriction. Treat it as private-network only and enforce host firewall/network policy outside Compose.
- The root compose binds `127.0.0.1` and is reachable only from the local machine by default. Local `dev.sh` uses same-origin browser transport by default; set `NEXT_PUBLIC_API_URL` only when intentionally using a backend on another origin, and then configure backend CORS for the frontend origin.
- In release, the frontend is not published. A browser must be able to reach the URL compiled into `NEXT_PUBLIC_API_URL`, and that URL must route to the published backend. Docker's internal hostname `backend` is not a browser-reachable public URL.
- Supabase and OpenRouter are outside the Compose health dependency graph. Their credentials, network access, quotas, and outages can make the application unusable while all local containers remain healthy.
- The named `qdrant_data` volume is the release serving index. Recreating containers without `down -v` preserves it; deleting the volume loses the index unless the corpus can be reindexed.
- No TLS termination, firewall, rate limiting, secret rotation, audit export, or failover is configured by these files. These are deployment blockers for any public or multi-tenant exposure, not completed security features.

## 7. Backup and recovery facts

The repository provides no backup script or restore script. The only executable recovery path present is rebuilding the derived Qdrant index from the local corpus and manifest with the two scripts above. Preserve these inputs outside disposable containers:

- `data/sources/manifest.json`;
- the required files under `data/corpus/mds`;
- the generated `data/processed/chunks.jsonl` when retaining a reproducible chunk artifact;
- the exact `.env` values through an approved secret store or protected operator backup (never commit them).

For a release stack whose Qdrant volume is lost, restore the corpus artifacts, start the three services, point the index script at the reachable Qdrant endpoint, and rerun ingestion/indexing. There is no repository command for Qdrant snapshot export, PostgreSQL dump, MinIO mirror, alias rollback, or clean-room restore; do not document those as executable recovery procedures.

## 8. Release status and explicit blockers

The 2026-09-14 release candidate is **release-ready for the covered corpus and
current MVP runtime**. Verification evidence:

- Backend Ruff, format, mypy, and 161 tests passed.
- Frontend lint (0 errors), typecheck, production build, and format check passed.
- Authenticated API smoke returned HTTP 200 with citations.
- Final 40-row evaluation contained 34 covered rows and 6 explicitly
  `CORPUS_NOT_COVERED` rows (`00`, `15`–`19`).
- Covered-case request errors: 0; citation validity: 1.0; invalid citation
  rate: 0%; abstention accuracy: 0.9118.

This status does not claim complete traffic-law coverage or full semantic
certification. `answer_correctness_manual` remains N/A because full human
semantic review was not supplied. Public deployment remains blocked until TLS,
firewall, rate limiting, secret rotation, backup/restore, and operational
monitoring are deliberately provided outside this local MVP compose boundary.

### Deferred target architecture (not active)

Earlier design material mentions Parser Router/Docling/MinerU, Canonical IR, legal relation storage, PostgreSQL as a source of truth, Redis/Dramatiq workers, MinIO, LangGraph/Langfuse, production reranking, multi-layer verification, aliases, migrations, and upload/reviewer flows. Those are target or historical design items only. They are not services, commands, healthchecks, backup procedures, or release guarantees in the current compose and script set.
