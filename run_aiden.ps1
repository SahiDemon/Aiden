# Aiden AI Assistant - Launcher Script
# Run Aiden in the background with system tray

param(
    [switch]$Debug
)

Write-Host "Starting Aiden AI Assistant..." -ForegroundColor Cyan

# Activate virtual environment
if (Test-Path ".venv\Scripts\Activate.ps1") {
    & ".venv\Scripts\Activate.ps1"
} elseif (Test-Path "venv\Scripts\Activate.ps1") {
    & "venv\Scripts\Activate.ps1"
} else {
    Write-Host "ERROR: Virtual environment not found. Run install.ps1 first." -ForegroundColor Red
    exit 1
}

# Check .env file
if (-not (Test-Path ".env")) {
    Write-Host "ERROR: .env file not found. Please create it from .env.example" -ForegroundColor Red
    exit 1
}

# Check if dashboard build exists
if (-not (Test-Path "dashboard\build\index.html")) {
    Write-Host "Building dashboard for production..." -ForegroundColor Yellow
    Push-Location dashboard
    npm run build
    Pop-Location
    Write-Host "✓ Dashboard build complete" -ForegroundColor Green
}

Write-Host "Dashboard will be served from http://localhost:5000" -ForegroundColor Cyan

# Determine Python executable path
$pythonPath = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "venv\Scripts\python.exe" }

# Run Aiden
if ($Debug) {
    # Debug mode - show console output
    Write-Host "Running in DEBUG mode (console visible)..." -ForegroundColor Yellow
    & $pythonPath src\main.py
} else {
    # Normal mode - hidden window
    Write-Host "Running in NORMAL mode..." -ForegroundColor Green
    Write-Host "Check system tray for Aiden icon" -ForegroundColor Green
    
    # Run with hidden console
    Start-Process -FilePath $pythonPath -ArgumentList "src\main.py" -WindowStyle Hidden
    
    
    Write-Host "✓ Aiden is starting..." -ForegroundColor Green
    Write-Host "  - Look for the tray icon" -ForegroundColor White
    Write-Host "  - Say 'Aiden' or use hotkey to activate" -ForegroundColor White
    Write-Host "  - Dashboard: http://localhost:5000" -ForegroundColor White
    Write-Host "  - Opening dashboard automatically..." -ForegroundColor Cyan
}
