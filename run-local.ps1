# Precision AI - one-command local run on Windows (SQLite, no Docker needed).
#   .\run-local.ps1            migrate, seed on first run, build the UI if needed, serve on http://localhost:8000
#   .\run-local.ps1 -Reset     wipe the local SQLite DB + FAISS indexes and start fresh
#   .\run-local.ps1 -Dev       also start the Vite dev server (hot reload) on http://localhost:5173
param([switch]$Reset, [switch]$Dev)
$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
if (Test-Path "C:\Program Files\nodejs") { $env:Path = "C:\Program Files\nodejs;" + $env:Path }

Push-Location "$root\backend"
try {
    if (-not (Test-Path "venv\Scripts\python.exe")) {
        Write-Host "Creating Python virtual environment..."
        python -m venv venv
        .\venv\Scripts\python.exe -m pip install --upgrade pip
        .\venv\Scripts\python.exe -m pip install torch --index-url https://download.pytorch.org/whl/cpu
        .\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    }
    if (-not (Test-Path ".env")) { Copy-Item "$root\.env.example" ".env"; Add-Content ".env" "`nDATABASE_URL=sqlite+aiosqlite:///./precision_ai.db`nLOG_FORMAT=console" }
    if ($Reset) {
        Remove-Item precision_ai.db, precision_ai.db-shm, precision_ai.db-wal -ErrorAction SilentlyContinue
        Remove-Item "$root\faiss_indexes\*.faiss", "$root\faiss_indexes\*.json" -ErrorAction SilentlyContinue
    }
    $fresh = -not (Test-Path "precision_ai.db")
    .\venv\Scripts\alembic.exe upgrade head
    if ($fresh) { .\venv\Scripts\python.exe -m app.database.seed }
} finally { Pop-Location }

if (-not (Test-Path "$root\frontend\dist\index.html") -or $Dev) {
    Push-Location "$root\frontend"
    if (-not (Test-Path "node_modules")) { npm install }
    if (-not $Dev) { npm run build }
    Pop-Location
}
if ($Dev) { Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; `$env:Path='C:\Program Files\nodejs;'+`$env:Path; npm run dev" }

Write-Host "`nPrecision AI -> http://localhost:8000   (API docs: /docs)   Ctrl+C to stop" -ForegroundColor Cyan
Push-Location "$root\backend"
try { .\venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 } finally { Pop-Location }
