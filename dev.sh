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
# Host-launched processes use Compose's published localhost ports.
export DATABASE_URL="${DATABASE_URL/@postgres:5432\//@127.0.0.1:5432/}"
if [[ "$REDIS_URL" == redis://redis:* ]]; then
  export REDIS_URL="${REDIS_URL/redis:\/\/redis:/redis:\/\/127.0.0.1:}"
fi
export QDRANT_URL="${QDRANT_URL/qdrant/127.0.0.1}"
export S3_ENDPOINT="${S3_ENDPOINT/minio/127.0.0.1}"
export MINIO_ENDPOINT="${MINIO_ENDPOINT/minio/127.0.0.1}"

stale_patterns=("$ROOT/backend.*uvicorn" "$ROOT/backend.*dramatiq" "$ROOT/frontend.*next dev")
stale_pids() {
  local pattern
  for pattern in "${stale_patterns[@]}"; do pgrep -f "$pattern" || true; done | sort -u
}
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
if [[ -n "$leftovers" ]]; then
  echo "Could not stop stale processes; refusing to serve older code:" >&2
  ps -o pid=,cmd= -p $leftovers >&2
  exit 1
fi

child_pids=()
cleanup() { trap - INT TERM EXIT; ((${#child_pids[@]})) && kill "${child_pids[@]}" 2>/dev/null || true; wait "${child_pids[@]}" 2>/dev/null || true; }
trap cleanup INT TERM EXIT

docker compose --env-file "$ENV_FILE" up -d postgres qdrant redis minio
(
  cd "$ROOT/backend"
  exec env PYTHONPATH=. uv run --env-file "$ENV_FILE" python -m alembic upgrade head
)
(
  cd "$ROOT/backend"
  exec env PYTHONPATH=. uv run --env-file "$ENV_FILE" uvicorn app.main:app --reload --reload-dir app --host 127.0.0.1 --port 8000
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
  exec env PYTHONPATH=. uv run --env-file "$ENV_FILE" python -m app.ingestion.worker && exec python -m dramatiq --processes 1 --threads 1 app.ingestion.actors
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
