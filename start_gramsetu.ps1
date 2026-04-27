# GramSetu Startup Script (PowerShell)

Write-Host "Starting GramSetu..." -ForegroundColor Cyan
Write-Host ""

# Start Backend (port 8000) in a new window
Write-Host "[1/2] Starting Backend API on port 8000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Documents\GitHub\Gramsetu\gramsetu'; python -m uvicorn whatsapp_bot.main:app --host 0.0.0.0 --port 8000"

Start-Sleep -Seconds 3

# Start Frontend (port 3000) in a new window  
Write-Host "[2/2] Starting Frontend on port 3000..." -ForegroundColor Yellow
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd 'C:\Documents\GitHub\Gramsetu\gramsetu\webapp'; npm run dev"

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "GramSetu is starting!" -ForegroundColor Green
Write-Host "  Backend API: http://localhost:8000" -ForegroundColor White
Write-Host "  Frontend:    http://localhost:3000" -ForegroundColor White
Write-Host "  API Docs:    http://localhost:8000/docs" -ForegroundColor White
Write-Host "==============================================" -ForegroundColor Green