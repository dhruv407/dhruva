#!/usr/bin/env bash
set -euo pipefail
RG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -z "${DATABASE_URL:-}" ]]; then
  "$RG_ROOT/scripts/database.sh"
fi
export RG_DATA_DIR="${RG_DATA_DIR:-$RG_ROOT/data}"
cd "$RG_ROOT/backend"
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 &
RG_API_PID=$!
cd "$RG_ROOT/frontend"
node node_modules/vite/bin/vite.js --host 0.0.0.0 --strictPort &
RG_UI_PID=$!
trap 'kill "$RG_API_PID" "$RG_UI_PID" 2>/dev/null || true' EXIT INT TERM
wait -n "$RG_API_PID" "$RG_UI_PID"
