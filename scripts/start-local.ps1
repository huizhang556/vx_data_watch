$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host "        VX Data Watch - Local start" -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Cyan

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw '未找到 uv，请先安装：https://docs.astral.sh/uv/'
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw '未找到 Node.js 24 或更高版本。'
}

Write-Host "[INFO] Syncing dependencies and building frontend..." -ForegroundColor Blue
uv sync --extra ocr
Push-Location frontend
try {
    npm.cmd install
    npm.cmd run build
} finally {
    Pop-Location
}

Write-Host "[OK] Build completed; starting service." -ForegroundColor Green
& "$projectRoot\.venv\Scripts\uvicorn.exe" app.main:app --app-dir backend --host 0.0.0.0 --port 8000
