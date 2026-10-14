#!/usr/bin/env bash
set -euo pipefail
RG_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$RG_ROOT"
export UV_CACHE_DIR="${UV_CACHE_DIR:-/workspace/.cache/uv}"
uv sync --project backend --frozen
cd frontend
npm ci --cache /workspace/.cache/npm
npm run build
