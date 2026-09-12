#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$ROOT"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing $ENV_FILE; copy .env.example to .env and fill required values." >&2
  exit 1
fi

# Import KEY=VALUE entries without executing arbitrary shell from .env.
# Values may be quoted and may contain `=`; comments are only recognized when
# they begin a line, so URL fragments and keys containing `#` remain intact.
while IFS= read -r line || [[ -n "$line" ]]; do
  line="${line%$'\r'}"
  [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
  if [[ ! "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
    echo "Invalid .env entry (expected KEY=VALUE): $line" >&2
    exit 1
  fi
  key="${BASH_REMATCH[1]}"
  value="${BASH_REMATCH[2]}"
  value="${value#"${value%%[![:space:]]*}"}"
  value="${value%"${value##*[![:space:]]}"}"
  if [[ "$value" == \"*\" && "$value" == *\" ]]; then
    value="${value:1:${#value}-2}"
  elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
    value="${value:1:${#value}-2}"
  fi
  export "$key=$value"
done < "$ENV_FILE"
BACKEND_INTERNAL_URL="${BACKEND_INTERNAL_URL:-http://127.0.0.1:8000}"
NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://127.0.0.1:8000}"
export BACKEND_INTERNAL_URL NEXT_PUBLIC_API_URL


required_env=(SUPABASE_URL OPENROUTER_API_KEY QDRANT_PATH)
for key in "${required_env[@]}"; do
  if [[ -z "${!key:-}" ]]; then
    echo "Missing required environment variable: $key" >&2
    exit 1
  fi
done
if [[ -z "${SUPABASE_SERVICE_ROLE_KEY:-}" && -z "${SUPABASE_ANON_KEY:-}" && -z "${SUPABASE_PUBLISHABLE_KEY:-}" ]]; then
  echo "Missing required environment variable: SUPABASE_ANON_KEY or SUPABASE_PUBLISHABLE_KEY or SUPABASE_SERVICE_ROLE_KEY" >&2
  exit 1
fi
if [[ -z "${SUPABASE_ANON_KEY:-}" ]]; then
  export SUPABASE_ANON_KEY="${SUPABASE_PUBLISHABLE_KEY:-}"
fi

# Next.js reads frontend/.env.local for direct launches. Keep the generated
# file restricted and preserve a user-managed nonempty file unless the root
# .env explicitly supplied the public values. Local dev defaults to the host
# FastAPI URL; set NEXT_PUBLIC_API_URL to intentionally override it.
NEXT_PUBLIC_SUPABASE_URL="${NEXT_PUBLIC_SUPABASE_URL:-$SUPABASE_URL}"
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="${NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY:-${SUPABASE_PUBLISHABLE_KEY:-${SUPABASE_ANON_KEY:-}}}"
frontend_env="$ROOT/frontend/.env.local"
if [[ ! -s "$frontend_env" || -n "${SUPABASE_URL:-}" || -n "${SUPABASE_PUBLISHABLE_KEY:-}" || -n "${SUPABASE_ANON_KEY:-}" || -n "${NEXT_PUBLIC_API_URL:-}" ]]; then
  umask 077
  printf 'NEXT_PUBLIC_API_URL=%s\nNEXT_PUBLIC_SUPABASE_URL=%s\nNEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=%s\n' \
    "$NEXT_PUBLIC_API_URL" "$NEXT_PUBLIC_SUPABASE_URL" "$NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY" > "$frontend_env"
  chmod 600 "$frontend_env"
fi

# Pass the validated values explicitly so child processes cannot fall back to
# unrelated environment files or inherited values.
export NEXT_PUBLIC_API_URL NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY BACKEND_INTERNAL_URL
for key in NEXT_PUBLIC_SUPABASE_URL NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY BACKEND_INTERNAL_URL; do
  if [[ -z "${!key:-}" ]]; then
    echo "Missing required environment variable: $key" >&2
    exit 1
  fi
done
export QDRANT_PATH="$ROOT/${QDRANT_PATH#"$ROOT/"}"
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


child_pids=()
cleanup() { trap - INT TERM EXIT; ((${#child_pids[@]})) && kill "${child_pids[@]}" 2>/dev/null || true; wait "${child_pids[@]}" 2>/dev/null || true; }
trap cleanup INT TERM EXIT
(
  cd "$ROOT/backend"
  exec env PYTHONPATH=. \
    SUPABASE_URL="$SUPABASE_URL" SUPABASE_ANON_KEY="${SUPABASE_ANON_KEY:-}" SUPABASE_SERVICE_ROLE_KEY="${SUPABASE_SERVICE_ROLE_KEY:-}" \
    QDRANT_PATH="$QDRANT_PATH" QDRANT_COLLECTION="${QDRANT_COLLECTION:-traffic_law}" \
    OPENROUTER_API_KEY="$OPENROUTER_API_KEY" OPENROUTER_BASE_URL="${OPENROUTER_BASE_URL:-https://openrouter.ai/api/v1}" \
    GENERATION_MODEL="${GENERATION_MODEL:-deepseek/deepseek-v4-flash-0731}" EMBEDDING_MODEL="${EMBEDDING_MODEL:-openai/text-embedding-3-small}" \
    TEST_USER_EMAIL="${TEST_USER_EMAIL:-}" TEST_USER_PASSWORD="${TEST_USER_PASSWORD:-}" \
    TEST_USER_B_EMAIL="${TEST_USER_B_EMAIL:-}" TEST_USER_B_PASSWORD="${TEST_USER_B_PASSWORD:-}" \
    uv run --env-file /dev/null --directory "$ROOT/backend" python -m uvicorn app.main:app --reload --reload-dir "$ROOT/backend/app" --app-dir "$ROOT/backend" --host 127.0.0.1 --port 8000
) > >(sed -u 's/^/[api] /') 2>&1 &
child_pids+=("$!")
(
  cd "$ROOT/frontend"
  exec env BACKEND_INTERNAL_URL="$BACKEND_INTERNAL_URL" NEXT_PUBLIC_API_URL="$NEXT_PUBLIC_API_URL" \
    NEXT_PUBLIC_SUPABASE_URL="$NEXT_PUBLIC_SUPABASE_URL" \
    NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY="$NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY" \
    npm run dev -- --hostname 127.0.0.1 --port 3000
) > >(sed -u 's/^/[frontend] /') 2>&1 &
child_pids+=("$!")

for _ in $(seq 1 100); do
  if curl --fail --silent --max-time 1 http://127.0.0.1:8000/api/v1/health/ready >/dev/null &&
    curl --fail --silent --max-time 1 http://127.0.0.1:3000/ >/dev/null; then
    echo "==> http://localhost:3000"
    echo "==> API http://localhost:8000"
    wait -n "${child_pids[@]}"
    exit $?
  fi
  kill -0 "${child_pids[0]}" "${child_pids[1]}" 2>/dev/null || {
    echo "A development service exited before readiness." >&2
    exit 1
  }
  sleep 0.1
done
echo "Development services did not become ready within 10 seconds." >&2
exit 1
