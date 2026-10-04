# Run the NovelBridge backend (Windows / PowerShell).
#
#   .\run.ps1              # default engine (Ollama), port 8000
#   .\run.ps1 -Mock        # offline deterministic mock engine
#   .\run.ps1 -Port 9000   # custom port
#
# Uses the project virtualenv at .\.venv so you don't type the full python path.

param(
    [switch]$Mock,
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"
$python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "venv not found at $python. Create it first: python -m venv .venv; .\.venv\Scripts\python.exe -m pip install -r requirements.txt"
}

if ($Mock) {
    $env:NB_ENGINE = "mock"
    Write-Host "Starting backend with the MOCK engine (offline) on port $Port" -ForegroundColor Yellow
} else {
    Write-Host "Starting backend on port $Port" -ForegroundColor Green
}

& $python -m uvicorn app.main:app --port $Port
