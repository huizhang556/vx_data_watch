#!/usr/bin/env sh
set -eu
PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
command -v node >/dev/null 2>&1 || { echo "Node.js 24+ is required" >&2; exit 1; }
uv sync --extra ocr
(cd frontend && npm install && npm run build)
exec .venv/bin/uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
