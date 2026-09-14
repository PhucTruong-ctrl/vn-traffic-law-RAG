#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

printf '==> Formatting Python with Ruff\n'
uv run --directory "$ROOT/backend" ruff format "$ROOT/backend/app" "$ROOT/backend/tests"

printf '==> Formatting frontend\n'
(
  cd "$ROOT/frontend"
  npm run format
)

printf '==> Formatting complete\n'
