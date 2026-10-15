# ClaimTrace dev stack launcher: hybrid (5002) -> backend (8000) -> frontend (3000)
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File claimtrace\dev.ps1
#
# Ctrl+C stops every service the script started. Services already running
# (healthy endpoints) are reused instead of started twice.

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot
$ClaimDir = $PSScriptRoot
$VenvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$HybridExe = Join-Path $RepoRoot ".venv\Scripts\opendataloader-pdf-hybrid.exe"

$children = New-Object System.Collections.ArrayList

function Test-Healthy([string]$Url) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3
    return $response.StatusCode -eq 200
  } catch {
    return $false
  }
}

function Wait-Healthy([string]$Name, [string]$Url, [int]$TimeoutSeconds) {
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Healthy $Url) {
      Write-Host "[dev] $Name ready: $Url" -ForegroundColor Green
      return
    }
    Start-Sleep -Seconds 1
  }
  throw "$Name did not become ready within $TimeoutSeconds seconds: $Url"
}

function Start-IfNeeded([string]$Name, [string]$HealthUrl, [scriptblock]$Start) {
  if (Test-Healthy $HealthUrl) {
    Write-Host "[dev] $Name already running, reusing it." -ForegroundColor Yellow
    return
  }
  Write-Host "[dev] Starting $Name..." -ForegroundColor Cyan
  & $Start
}

# 1. Hybrid AI service (port 5002) — PYTHONUTF8=1 is required on Chinese-locale
#    Windows, otherwise docling model loading fails with a GBK decoding error.
Start-IfNeeded "hybrid (5002)" "http://localhost:5002/health" {
  $env:PYTHONUTF8 = "1"
  $proc = Start-Process -FilePath $HybridExe -ArgumentList "--port", "5002" -WorkingDirectory $ClaimDir -PassThru
  [void]$children.Add($proc)
}
Wait-Healthy "hybrid (5002)" "http://localhost:5002/health" 180

# 2. FastAPI backend (port 8000), hot reload on source changes.
Start-IfNeeded "backend (8000)" "http://localhost:8000/health" {
  $proc = Start-Process -FilePath $VenvPython -ArgumentList "-m", "uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload" -WorkingDirectory (Join-Path $ClaimDir "backend") -PassThru
  [void]$children.Add($proc)
}
Wait-Healthy "backend (8000)" "http://localhost:8000/health" 60

# 3. Vite frontend (port 3000), hot reload on source changes.
Start-IfNeeded "frontend (3000)" "http://localhost:3000/" {
  $proc = Start-Process -FilePath "npm.cmd" -ArgumentList "run", "dev" -WorkingDirectory (Join-Path $ClaimDir "frontend") -PassThru
  [void]$children.Add($proc)
}
Wait-Healthy "frontend (3000)" "http://localhost:3000/" 90

Write-Host ""
Write-Host "ClaimTrace dev stack is up:" -ForegroundColor Green
Write-Host "  Frontend : http://localhost:3000"
Write-Host "  Backend  : http://localhost:8000  (docs: http://localhost:8000/docs)"
Write-Host "  Hybrid   : http://localhost:5002  (health: /health)"
Write-Host ""
Write-Host "Press Ctrl+C to stop everything." -ForegroundColor Yellow

try {
  while ($true) { Start-Sleep -Seconds 2 }
} finally {
  Write-Host "[dev] Stopping started services..." -ForegroundColor Cyan
  foreach ($proc in $children) {
    if ($proc -and -not $proc.HasExited) {
      # /T kills the whole tree (uvicorn reloader worker, vite node process).
      & taskkill /PID $proc.Id /T /F 2>$null | Out-Null
    }
  }
  Write-Host "[dev] All services stopped."
}
