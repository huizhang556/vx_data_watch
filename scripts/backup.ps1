$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host "        VX Data Watch - Backup" -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host "[INFO] Creating backup..." -ForegroundColor Blue
& "$projectRoot\.venv\Scripts\python.exe" -m app.cli backup
Write-Host "[OK] Backup completed." -ForegroundColor Green
