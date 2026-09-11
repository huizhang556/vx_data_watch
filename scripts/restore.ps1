param([Parameter(Mandatory = $true)][string]$BackupPath)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $projectRoot
$resolvedBackup = (Resolve-Path -LiteralPath $BackupPath).Path
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host "        VX Data Watch - Restore" -ForegroundColor Cyan
Write-Host "----------------------------------------" -ForegroundColor Cyan
Write-Host "[INFO] Restoring backup..." -ForegroundColor Blue
Write-Host '恢复前必须停止正在运行的 VX Data 应用。'
& "$projectRoot\.venv\Scripts\python.exe" -m app.cli restore $resolvedBackup
Write-Host "[OK] Restore completed." -ForegroundColor Green
