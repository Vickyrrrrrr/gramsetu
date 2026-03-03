# ============================================================
# GramSetu — Start All MCP Servers (One Command)
# ============================================================
# Starts all 4 MCP tool servers in background PowerShell jobs.
# Run from project root:  .\start_mcp.ps1
#
# Servers started:
#   WhatsApp MCP  → http://localhost:8100
#   Browser MCP   → http://localhost:8101
#   Audit MCP     → http://localhost:8102
#   DigiLocker MCP→ http://localhost:8103
#
# To stop everything: .\start_mcp.ps1 -Stop
# ============================================================

param(
    [switch]$Stop
)

$ROOT   = Split-Path -Parent $MyInvocation.MyCommand.Path
$PYTHON = Join-Path $ROOT ".venv\Scripts\python.exe"

if (-not (Test-Path $PYTHON)) {
    Write-Host "[Error] Virtual environment not found. Run .\start.ps1 first to set it up." -ForegroundColor Red
    exit 1
}

# ── Stop all MCP jobs ────────────────────────────────────────
if ($Stop) {
    Write-Host "[MCP] Stopping all MCP servers..." -ForegroundColor Yellow
    Get-Job -Name "mcp_*" -ErrorAction SilentlyContinue | Stop-Job | Remove-Job
    Write-Host "[MCP] All MCP servers stopped." -ForegroundColor Green
    exit 0
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  GramSetu — Starting All 4 MCP Tool Servers" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ── Kill any previous MCP jobs ───────────────────────────────
Get-Job -Name "mcp_*" -ErrorAction SilentlyContinue | Stop-Job | Remove-Job

# ── Define all 4 servers ─────────────────────────────────────
$servers = @(
    @{ Name = "mcp_whatsapp";   Module = "backend.mcp_servers.whatsapp_mcp";   Port = 8100; Label = "WhatsApp MCP " },
    @{ Name = "mcp_browser";    Module = "backend.mcp_servers.browser_mcp";    Port = 8101; Label = "Browser MCP  " },
    @{ Name = "mcp_audit";      Module = "backend.mcp_servers.audit_mcp";      Port = 8102; Label = "Audit MCP    " },
    @{ Name = "mcp_digilocker"; Module = "backend.mcp_servers.digilocker_mcp"; Port = 8103; Label = "DigiLocker MCP" }
)

# ── Start each server as a background job ────────────────────
foreach ($s in $servers) {
    $job = Start-Job -Name $s.Name -ScriptBlock {
        param($python, $module, $root)
        Set-Location $root
        & $python -m $module
    } -ArgumentList $PYTHON, $s.Module, $ROOT

    Write-Host "  [OK] $($s.Label) → http://localhost:$($s.Port)  (Job: $($job.Id))" -ForegroundColor Green
}

Write-Host ""
Write-Host "  All 4 MCP servers are running in the background." -ForegroundColor White
Write-Host "  To view logs:  Receive-Job -Name mcp_whatsapp  (or other name)" -ForegroundColor Gray
Write-Host "  To stop all:   .\start_mcp.ps1 -Stop" -ForegroundColor Gray
Write-Host ""

# ── Monitor until Ctrl+C ─────────────────────────────────────
Write-Host "  Press Ctrl+C to stop monitoring (servers keep running)." -ForegroundColor DarkGray
Write-Host ""

try {
    while ($true) {
        Start-Sleep 10
        $dead = Get-Job -Name "mcp_*" | Where-Object { $_.State -ne "Running" }
        foreach ($d in $dead) {
            Write-Host "  [WARN] $($d.Name) stopped unexpectedly. Restarting..." -ForegroundColor Yellow
            $srv = $servers | Where-Object { $_.Name -eq $d.Name }
            if ($srv) {
                Remove-Job $d -Force
                $job = Start-Job -Name $srv.Name -ScriptBlock {
                    param($python, $module, $root)
                    Set-Location $root
                    & $python -m $module
                } -ArgumentList $PYTHON, $srv.Module, $ROOT
                Write-Host "  [OK] $($srv.Label) restarted (Job: $($job.Id))" -ForegroundColor Green
            }
        }
    }
} catch {
    Write-Host ""
    Write-Host "  Monitoring stopped. MCP servers are still running in background jobs." -ForegroundColor DarkGray
    Write-Host "  To stop all: .\start_mcp.ps1 -Stop" -ForegroundColor Gray
}
