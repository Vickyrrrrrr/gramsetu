# ============================================================
# GramSetu -- One-Click Startup Script (Windows PowerShell)
# ============================================================
# Run from project root:
#   .\start.ps1            # Start server (MCP servers embedded in-process)
#   .\start.ps1 -Ngrok     # + ngrok tunnel for Twilio
#   .\start.ps1 -Dashboard # + Streamlit dashboard
#   .\start.ps1 -Webapp    # + Next.js web app
#   .\start.ps1 -All       # Everything
#   .\start.ps1 -Prod      # Disable hot-reload (stable for demos)
#
# NOTE: MCP servers (WhatsApp / Browser / Audit / DigiLocker) are now
# started AUTOMATICALLY as in-process threads when the FastAPI server
# boots. You do NOT need -MCP flag anymore.
# ============================================================

param(
    [switch]$Ngrok,
    [switch]$Dashboard,
    [switch]$MCP,
    [switch]$Webapp,
    [switch]$All,
    [switch]$Prod
)

$ROOT   = Split-Path -Parent $MyInvocation.MyCommand.Path
$VENV   = Join-Path $ROOT ".venv\Scripts"
$PYTHON = Join-Path $VENV "python.exe"
$PIP    = Join-Path $VENV "pip.exe"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  GramSetu v3 -- Autonomous Government Form-Filling Agent" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

# -- Create venv if missing --------------------------------------------------
if (-not (Test-Path $PYTHON)) {
    Write-Host "[Setup] Creating virtual environment..." -ForegroundColor Yellow
    python -m venv .venv
}

# -- Install Python dependencies ---------------------------------------------
Write-Host "[Setup] Checking Python dependencies..." -ForegroundColor Cyan
& $PIP install -q -r requirements.txt 2>$null | Out-Null
Write-Host "[Setup] Dependencies OK" -ForegroundColor Green

# -- Create data directories -------------------------------------------------
New-Item -ItemType Directory -Force -Path "$ROOT\data\voice_cache" | Out-Null
New-Item -ItemType Directory -Force -Path "$ROOT\data\screenshots"  | Out-Null

# -- MCP Servers — auto-started by FastAPI (no separate processes needed) ----
if ($MCP -or $All) {
    Write-Host ""
    Write-Host "[MCP] MCP servers start AUTOMATICALLY inside the backend." -ForegroundColor Green
    Write-Host "[MCP] No separate processes are needed." -ForegroundColor Green
    Write-Host "[MCP] (WhatsApp:8100, Browser:8101, Audit:8102, DigiLocker:8103)" -ForegroundColor Gray
}

# -- ngrok tunnel (optional) -------------------------------------------------
if ($Ngrok -or $All) {
    Write-Host ""
    Write-Host "[ngrok] Starting tunnel on port 8000..." -ForegroundColor Cyan
    Start-Process -NoNewWindow -FilePath "ngrok" -ArgumentList "http 8000" -WorkingDirectory $ROOT
    Start-Sleep 3
    try {
        $tunnels = Invoke-RestMethod "http://localhost:4040/api/tunnels" -ErrorAction Stop
        $https   = $tunnels.tunnels | Where-Object { $_.proto -eq "https" } | Select-Object -First 1
        if ($https) {
            $url = $https.public_url
            Write-Host ""
            Write-Host "  ========================================"  -ForegroundColor Yellow
            Write-Host "  TWILIO WEBHOOK URL:"                       -ForegroundColor Yellow
            Write-Host "  $url/webhook"                              -ForegroundColor White
            Write-Host "  ========================================"  -ForegroundColor Yellow
            Write-Host "  Set this in Twilio Console -> Messaging -> Sandbox"
            Write-Host "  field: 'WHEN A MESSAGE COMES IN'"
            Write-Host ""
        }
    }
    catch {
        Write-Host "[ngrok] Could not get URL -- check http://localhost:4040" -ForegroundColor Yellow
    }
}

# -- Next.js Webapp (optional) -----------------------------------------------
if ($Webapp -or $All) {
    Write-Host ""
    Write-Host "[Webapp] Starting Next.js on port 3000..." -ForegroundColor Cyan
    $webappPath = Join-Path $ROOT "webapp"
    if (-not (Test-Path (Join-Path $webappPath "node_modules"))) {
        Write-Host "[Webapp] Installing npm packages (first run)..." -ForegroundColor Yellow
        Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "install" -WorkingDirectory $webappPath -Wait
    }
    Start-Process -NoNewWindow -FilePath "npm" -ArgumentList "run", "dev" -WorkingDirectory $webappPath
    Start-Sleep 2
    Write-Host "[Webapp] http://localhost:3000" -ForegroundColor Green
}

# -- Streamlit Dashboard (optional) ------------------------------------------
if ($Dashboard -or $All) {
    Write-Host ""
    Write-Host "[Dashboard] Starting Streamlit on port 8501..." -ForegroundColor Cyan
    $streamlit = Join-Path $VENV "streamlit.exe"
    Start-Process -NoNewWindow -FilePath $streamlit -ArgumentList "run", "dashboard\app.py", "--server.port", "8501" -WorkingDirectory $ROOT
    Write-Host "[Dashboard] http://localhost:8501" -ForegroundColor Green
}

# -- FastAPI Server (foreground, blocking) ------------------------------------
Write-Host ""
Write-Host "[Server] Starting GramSetu FastAPI server..." -ForegroundColor Cyan
Write-Host "  MCP servers will auto-start inside the process" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Swagger UI:  http://localhost:8000/docs"                           -ForegroundColor White
Write-Host "  Chat API:    POST http://localhost:8000/api/chat"                  -ForegroundColor White
Write-Host "  WhatsApp:    POST http://localhost:8000/webhook"                   -ForegroundColor White
Write-Host "  Health:      http://localhost:8000/api/health"                     -ForegroundColor White
Write-Host "  MCP Status:  http://localhost:8000/api/mcp-status"                 -ForegroundColor White
Write-Host "  Web App:     http://localhost:3000  (start with -Webapp)"          -ForegroundColor White
Write-Host "  Mock Portal: http://localhost:8000/static/public/mock_portal.html" -ForegroundColor White
Write-Host ""
Write-Host "  Press Ctrl+C to stop" -ForegroundColor Gray
Write-Host ""

# -- Check .env exists -------------------------------------------------------
if (-not (Test-Path (Join-Path $ROOT ".env"))) {
    Write-Host "[WARNING] .env file not found!" -ForegroundColor Red
    Write-Host "  Copy .env.example to .env and add your API keys:" -ForegroundColor Yellow
    Write-Host "    GROQ_API_KEY   = from https://console.groq.com" -ForegroundColor Yellow
    Write-Host "    NVIDIA_API_KEY = from https://build.nvidia.com" -ForegroundColor Yellow
    Write-Host ""
}

Set-Location $ROOT

if ($Prod -or $All) {
    Write-Host "  [PROD] Hot-reload DISABLED -- stable for demos" -ForegroundColor Yellow
    Write-Host ""
    & $PYTHON -m uvicorn whatsapp_bot.main:app --host 0.0.0.0 --port 8000 --workers 2
}
else {
    Write-Host "  [DEV]  Hot-reload ON -- code changes auto-restart server"         -ForegroundColor DarkGray
    Write-Host "  TIP:   For demos use: .\start.ps1 -Prod -Ngrok -Webapp"           -ForegroundColor DarkGray
    Write-Host ""
    & $PYTHON -m uvicorn whatsapp_bot.main:app --host 0.0.0.0 --port 8000 --reload
}
