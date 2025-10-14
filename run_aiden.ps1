# Aiden AI Assistant - Launcher Script
# Run Aiden in the background with system tray

param(
    [switch]$Debug
)

Write-Host "Starting Aiden AI Assistant..." -ForegroundColor Cyan

# Activate virtual environment
if (Test-Path "venv\Scripts\Activate.ps1") {
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

# Run Aiden
if ($Debug) {
    # Debug mode - show console output
    Write-Host "Running in DEBUG mode (console visible)..." -ForegroundColor Yellow
    python src\main.py
} else {
    # Normal mode - minimized window (tray icon needs visible window on Windows)
    Write-Host "Running in NORMAL mode..." -ForegroundColor Green
    Write-Host "Check system tray for Aiden icon" -ForegroundColor Green
    
    # Run with minimized console (pythonw breaks tray icons on Windows)
    Start-Process -FilePath "python" -ArgumentList "src\main.py" -WindowStyle Minimized
    
    Write-Host "✓ Aiden is starting..." -ForegroundColor Green
    Write-Host "  - Look for the tray icon" -ForegroundColor White
    Write-Host "  - Say 'Aiden' or use hotkey to activate" -ForegroundColor White
    Write-Host "  - Dashboard: http://localhost:5000" -ForegroundColor White
}
