# ==========================================
# GramSetu Setup Script (Run once on Windows)
# ==========================================

Write-Host "Installing GramSetu dependencies..." -ForegroundColor Cyan

# Install Python dependencies
Write-Host "Installing Python packages..." -ForegroundColor Yellow
pip install -r requirements.txt

# Install Node.js dependencies for frontend
Write-Host "Installing Frontend dependencies..." -ForegroundColor Yellow
cd webapp
npm install

Write-Host ""
Write-Host "==============================================" -ForegroundColor Green
Write-Host "Setup complete!" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Green