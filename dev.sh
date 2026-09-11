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
export QDRANT_URL="${QDRANT_URL/http:\/\/qdrant/http:\/\/127.0.0.1}"

if [[ "${1:-}" == "test" ]]; then
  shift
  exec uv run --directory "$ROOT/backend" pytest "$@"
fi

stale_patterns=("$ROOT/backend.*uvicorn" "$ROOT/frontend.*next dev")
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
if [[ -n "$leftovers" ]]; then echo "Could not stop stale processes; refusing to serve older code:" >&2; exit 1; fi

docker compose --env-file "$ENV_FILE" up -d postgres qdrant
for _ in $(seq 1 60); do
  postgres_state=$(docker compose --env-file "$ENV_FILE" ps --format '{{.State}}' postgres 2>/dev/null || true)
  qdrant_state=$(docker compose --env-file "$ENV_FILE" ps --format '{{.State}}' qdrant 2>/dev/null || true)
  [[ "$postgres_state" == running* && "$qdrant_state" == running* ]] && break
  sleep 1
done
if [[ "$postgres_state" != running* ]]; then echo "PostgreSQL did not become ready: ${postgres_state:-not found}" >&2; exit 1; fi
if [[ "$qdrant_state" != running* ]]; then echo "Qdrant did not become ready: ${qdrant_state:-not found}" >&2; exit 1; fi

child_pids=()
cleanup() { trap - INT TERM EXIT; ((${#child_pids[@]})) && kill "${child_pids[@]}" 2>/dev/null || true; wait "${child_pids[@]}" 2>/dev/null || true; }
trap cleanup INT TERM EXIT
(
  exec env PYTHONPATH=. DATABASE_URL="${DATABASE_URL:-}" QDRANT_URL="$QDRANT_URL" QDRANT_API_KEY="${QDRANT_API_KEY:-}" \
    OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}" \
    uv run --env-file /dev/null --project "$ROOT/backend" python -m uvicorn app.main:app --reload --reload-dir "$ROOT/backend/app" --app-dir "$ROOT/backend" --host 127.0.0.1 --port 8000
) > >(sed -u 's/^/[api] /') 2>&1 &
child_pids+=("$!")
(
  cd "$ROOT/frontend"
  exec env NEXT_PUBLIC_API_URL="http://localhost:8000" npm run dev -- --hostname 127.0.0.1 --port 3000
) > >(sed -u 's/^/[frontend] /') 2>&1 &
child_pids+=("$!")

echo "==> http://localhost:3000"
echo "==> API http://localhost:8000"
wait
