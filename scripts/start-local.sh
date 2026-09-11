#!/usr/bin/env sh
set -eu
PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_ROOT"
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  BLUE='\033[1;34m'; GREEN='\033[1;32m'; RED='\033[1;31m'; RESET='\033[0m'
else
  BLUE=''; GREEN=''; RED=''; RESET=''
fi
printf '\n%s----------------------------------------%s\n' "$BLUE" "$RESET"
printf '%s        VX Data Watch - 本地启动%s\n' "$BLUE" "$RESET"
printf '%s----------------------------------------%s\n\n' "$BLUE" "$RESET"
command -v uv >/dev/null 2>&1 || { printf '%s[错误] uv is required: https://docs.astral.sh/uv/%s\n' "$RED" "$RESET" >&2; exit 1; }
command -v node >/dev/null 2>&1 || { printf '%s[错误] Node.js 24+ is required%s\n' "$RED" "$RESET" >&2; exit 1; }
[ -f .env ] && { set -a; . ./.env; set +a; }
uv sync --extra ocr
printf '%s[信息] 正在同步 Python 依赖和前端资源...%s\n' "$BLUE" "$RESET"
(cd frontend && npm install && npm run build)
printf '%s[成功] 本地构建完成，正在启动服务。%s\n' "$GREEN" "$RESET"
exec .venv/bin/uvicorn app.main:app --app-dir backend \
  --host "${VX_BIND_ADDRESS:-0.0.0.0}" \
  --port "${VX_PORT:-8000}"
