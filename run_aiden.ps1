# run_aiden.ps1 — Fixed Aiden launcher
param([switch]$Debug)

# Use script directory as working directory
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Single-instance guard (named mutex)
$mutexName = "Global\AidenAI_Assistant_Mutex"
try {
    $mutex = New-Object System.Threading.Mutex($false, $mutexName)
    $hasHandle = $mutex.WaitOne(0, $false)
} catch {
    $hasHandle = $false
}
if (-not $hasHandle) {
    Write-Host "Aiden is already running (another instance detected). Exiting." -ForegroundColor Yellow
    exit 0
}

Write-Host "Starting Aiden AI Assistant..." -ForegroundColor Cyan

# Locate python executable inside venv (build paths as simple strings)
$possiblePythons = @(
    Join-Path -Path $ScriptDir -ChildPath ".venv\Scripts\python.exe"
    Join-Path -Path $ScriptDir -ChildPath "venv\Scripts\python.exe"
)

$pythonPath = $possiblePythons | Where-Object { Test-Path $_ } | Select-Object -First 1

if (-not $pythonPath) {
    Write-Host "ERROR: Virtual environment python not found. Run install.ps1 first." -ForegroundColor Red
    if ($hasHandle) { $mutex.ReleaseMutex() }
    exit 1
}

# Check .env
if (-not (Test-Path (Join-Path $ScriptDir ".env"))) {
    Write-Host "ERROR: .env file not found. Please create it from .env.example" -ForegroundColor Red
    if ($hasHandle) { $mutex.ReleaseMutex() }
    exit 1
}

# Build dashboard if missing
$dashboardIndex = Join-Path $ScriptDir "dashboard\build\index.html"
if (-not (Test-Path $dashboardIndex)) {
    Write-Host "Building dashboard for production..." -ForegroundColor Yellow
    Push-Location (Join-Path $ScriptDir "dashboard")
    npm run build
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Dashboard build failed (npm run build returned non-zero)." -ForegroundColor Red
        Pop-Location
        if ($hasHandle) { $mutex.ReleaseMutex() }
        exit 1
    }
    Pop-Location
    Write-Host "✓ Dashboard build complete" -ForegroundColor Green
}

Write-Host "Dashboard will be served from http://localhost:5000" -ForegroundColor Cyan

# Launch Aiden
$scriptEntry = Join-Path $ScriptDir "src\main.py"
if (-not (Test-Path $scriptEntry)) {
    Write-Host "ERROR: Entry script not found at src\main.py" -ForegroundColor Red
    if ($hasHandle) { $mutex.ReleaseMutex() }
    exit 1
}

if ($Debug) {
    Write-Host "Running in DEBUG mode (console visible)..." -ForegroundColor Yellow
    & $pythonPath $scriptEntry
    $exitCode = $LASTEXITCODE
} else {
    Write-Host "Running in NORMAL mode (hidden)..." -ForegroundColor Green
    Start-Process -FilePath $pythonPath -ArgumentList $scriptEntry -WorkingDirectory $ScriptDir -WindowStyle Hidden
    $exitCode = 0
}

if ($hasHandle) { $mutex.ReleaseMutex() }
exit $exitCode
