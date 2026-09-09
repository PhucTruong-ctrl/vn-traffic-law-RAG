#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$ROOT"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE; copy .env.example to .env and fill required values." >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a
export QDRANT_URL="${QDRANT_URL/qdrant/127.0.0.1}"
export S3_ENDPOINT="${S3_ENDPOINT/minio/127.0.0.1}"
export MINIO_ENDPOINT="${MINIO_ENDPOINT/minio/127.0.0.1}"
export DATABASE_URL="${DATABASE_URL/@postgres:5432\//@127.0.0.1:5432/}"
if [[ "${REDIS_URL:-}" == redis://redis:* ]]; then
  export REDIS_URL="${REDIS_URL/redis:\/\/redis:/redis:\/\/127.0.0.1:}"
fi

if [[ "${1:-}" == "test-integration" ]]; then
  shift
  exec env uv run --directory "$ROOT/backend" pytest tests/integration "$@"
fi

stale_patterns=("$ROOT/backend.*uvicorn" "$ROOT/backend.*dramatiq" "$ROOT/frontend.*next dev")
stale_pids() { local pattern; for pattern in "${stale_patterns[@]}"; do pgrep -f "$pattern" || true; done | sort -u; }
leftovers=$(stale_pids)
if [[ -n "$leftovers" ]]; then
  echo "==> stopping stale dev.sh processes:"
  ps -o pid=,lstart=,cmd= -p $leftovers | cut -c1-160 | sed 's/^/    /'
  kill $leftovers 2>/dev/null || true
else
  echo "==> no stale dev.sh processes"
fi
fuser -k 8000/tcp 3000/tcp 2>/dev/null || true
for _ in $(seq 1 25); do leftovers=$(stale_pids); [[ -z "$leftovers" ]] && break; sleep 0.2; done
if [[ -n "$leftovers" ]]; then echo "Could not stop stale processes; refusing to serve older code:" >&2; ps -o pid=,cmd= -p $leftovers >&2; exit 1; fi

child_pids=()
cleanup() { trap - INT TERM EXIT; ((${#child_pids[@]})) && kill "${child_pids[@]}" 2>/dev/null || true; wait "${child_pids[@]}" 2>/dev/null || true; }
trap cleanup INT TERM EXIT

docker compose --env-file "$ENV_FILE" up -d postgres qdrant redis minio
for _ in $(seq 1 60); do
  postgres_state=$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' vnlaw-postgres 2>/dev/null || true)
  redis_state=$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' vnlaw-redis 2>/dev/null || true)
  qdrant_state=$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' vnlaw-qdrant 2>/dev/null || true)
  minio_state=$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' vnlaw-minio 2>/dev/null || true)
  [[ "$postgres_state" == "running healthy" && "$redis_state" == "running healthy" && "$qdrant_state" == "running healthy" && "$minio_state" == "running healthy" ]] && break
  [[ "$postgres_state" == "exited" || "$redis_state" == "exited" || "$qdrant_state" == "exited" || "$minio_state" == "exited" ]] && break
  sleep 1
done
if [[ "$postgres_state" != "running healthy" ]]; then echo "PostgreSQL did not become healthy: ${postgres_state:-not found}" >&2; exit 1; fi
if [[ "$redis_state" != "running healthy" ]]; then echo "Redis did not become healthy: ${redis_state:-not found}" >&2; exit 1; fi
if [[ "$qdrant_state" != "running healthy" ]]; then echo "Qdrant did not become healthy: ${qdrant_state:-not found}" >&2; exit 1; fi
if [[ "$minio_state" != "running healthy" ]]; then echo "MinIO did not become healthy: ${minio_state:-not found}" >&2; exit 1; fi

redis_ip=$(docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' vnlaw-redis)
if [[ -z "$redis_ip" ]]; then echo "Could not determine vnlaw-redis container IP" >&2; exit 1; fi
if ! docker run --rm --network container:vnlaw-redis redis:7-alpine redis-cli -h 127.0.0.1 ping >/dev/null 2>&1; then echo "Redis is healthy but not reachable from its container network namespace" >&2; exit 1; fi
(
  cd "$ROOT/backend"
  env DATABASE_URL="$DATABASE_URL" uv run --env-file /dev/null python -m alembic upgrade head
)
(
  cd "$ROOT/backend"
  exec env PYTHONPATH=. QDRANT_URL="$QDRANT_URL" QDRANT_API_KEY="${QDRANT_API_KEY:-}" S3_ENDPOINT="$S3_ENDPOINT" MINIO_ENDPOINT="$MINIO_ENDPOINT" DATABASE_URL="$DATABASE_URL" REDIS_URL="redis://127.0.0.1:6379/0" uv run --env-file /dev/null python -m uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
) > >(sed -u 's/^/[api] /') 2>&1 &
api_pid=$!; child_pids+=("$api_pid")
api_ready=false
for _ in $(seq 1 120); do
  if curl -fsS http://127.0.0.1:8000/api/v1/health/live >/dev/null 2>&1; then api_ready=true; break; fi
  kill -0 "$api_pid" 2>/dev/null || break
  sleep 1
done
if [[ "$api_ready" != true ]]; then echo "API did not become ready on http://127.0.0.1:8000/api/v1/health/live" >&2; exit 1; fi
(
  cd "$ROOT/backend"
  exec env PYTHONPATH=. REDIS_URL="redis://${redis_ip}:6379/0" uv run --env-file /dev/null python -m dramatiq --processes 1 --threads 1 app.ingestion.actors
) > >(sed -u 's/^/[worker] /') 2>&1 &
child_pids+=("$!")
(
  cd "$ROOT/frontend"
  exec env NEXT_PUBLIC_API_URL="http://localhost:8000" npm run dev -- --hostname 127.0.0.1 --port 3000
) > >(sed -u 's/^/[frontend] /') 2>&1 &
child_pids+=("$!")

echo "==> http://localhost:3000"
echo "==> API http://localhost:8000"
echo "==> MinIO http://localhost:9001"
wait
