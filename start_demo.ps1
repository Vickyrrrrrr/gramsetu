# ============================================================
# GramSetu -- Demo Launcher (processes survive VS Code close)
# ============================================================
# Run from project root in a plain PowerShell window:
#   .\start_demo.ps1
#
# Each service opens its OWN separate PowerShell window, so
# closing VS Code will NOT kill the servers.
# ============================================================

$ROOT   = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV   = Join-Path $ROOT ".venv\Scripts"
$PYTHON = Join-Path $VENV "python.exe"
$WEBAPP = Join-Path $ROOT "webapp"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  GramSetu -- Detached Demo Launcher" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "All servers will open in SEPARATE windows." -ForegroundColor Yellow
Write-Host "Closing THIS window or VS Code will NOT stop them." -ForegroundColor Yellow
Write-Host ""

# -- Create data directories -------------------------------------------------
New-Item -ItemType Directory -Force -Path "$ROOT\data\voice_cache" | Out-Null
New-Item -ItemType Directory -Force -Path "$ROOT\data\screenshots"  | Out-Null

# -- Python Backend (FastAPI / uvicorn) -- separate window -------------------
Write-Host "[1/2] Starting Python backend on port 8000..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command",
    "Set-Location '$ROOT'; Write-Host 'GramSetu Backend - port 8000' -ForegroundColor Green; & '$PYTHON' -m uvicorn whatsapp_bot.main:app --host 0.0.0.0 --port 8000 --timeout-keep-alive 300" `
    -WindowStyle Normal

Start-Sleep 3

# -- Next.js Webapp -- separate window --------------------------------------
Write-Host "[2/2] Starting Next.js webapp on port 3000..." -ForegroundColor Cyan

if (-not (Test-Path (Join-Path $WEBAPP "node_modules"))) {
    Write-Host "  Installing npm packages (first run, please wait)..." -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "Set-Location '$WEBAPP'; npm install; npm run dev" `
        -WindowStyle Normal
} else {
    Start-Process powershell -ArgumentList "-NoExit", "-Command",
        "Set-Location '$WEBAPP'; Write-Host 'GramSetu Webapp - port 3000' -ForegroundColor Green; npm run dev" `
        -WindowStyle Normal
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Both services are now running in their own windows." -ForegroundColor Green
Write-Host ""
Write-Host "  Backend:  http://localhost:8000"  -ForegroundColor White
Write-Host "  Webapp:   http://localhost:3000"  -ForegroundColor White
Write-Host "  API docs: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "  You can close VS Code now - servers will keep running." -ForegroundColor Yellow
Write-Host "  To stop: close the two PowerShell windows that opened." -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""
