# start.ps1 — Starts backend (FastAPI) and frontend (Vite) in separate terminals.
# Run from the project root: .\start.ps1

param(
    [int]$BackendPort  = 8000,
    [int]$FrontendPort = 5173
)

$root = $PSScriptRoot

# Resolve the Python executable inside the venv
$python = Join-Path $root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    Write-Error "Python venv not found at backend\.venv. Run: cd backend; python -m venv .venv; .venv\Scripts\pip install -r requirements.txt"
    exit 1
}

# Check that the frontend has been installed
$nodeModules = Join-Path $root "frontend\node_modules"
if (-not (Test-Path $nodeModules)) {
    Write-Error "Frontend dependencies not installed. Run: cd frontend; npm install"
    exit 1
}

Write-Host ""
Write-Host "  Starting Portfolio Manager" -ForegroundColor Cyan
Write-Host "  Backend  → http://localhost:$BackendPort" -ForegroundColor Blue
Write-Host "  Frontend → http://localhost:$FrontendPort" -ForegroundColor Green
Write-Host "  API docs → http://localhost:$BackendPort/docs" -ForegroundColor Blue
Write-Host ""

# Backend window
$backendCmd = "Set-Location '$root\backend'; & '$python' -m uvicorn app.main:app --reload --port $BackendPort"
Start-Process pwsh -ArgumentList "-NoExit", "-Command", $backendCmd `
    -WindowStyle Normal

# Give the backend a moment to bind the port before the frontend dev server starts
Start-Sleep -Seconds 2

# Frontend window
$frontendCmd = "Set-Location '$root\frontend'; npm run dev -- --port $FrontendPort"
Start-Process pwsh -ArgumentList "-NoExit", "-Command", $frontendCmd `
    -WindowStyle Normal

Write-Host "  Both processes started. Close their windows (or Ctrl+C inside each) to stop." -ForegroundColor Gray
Write-Host ""
