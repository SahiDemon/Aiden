param([switch]$RunAfterBuild)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

$pythonExe = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path $scriptDir "venv\Scripts\python.exe"
}
if (-not (Test-Path $pythonExe)) {
    throw "Virtual environment not found. Run .\install.ps1 first."
}

Write-Host "Installing PyInstaller if missing..." -ForegroundColor Cyan
& $pythonExe -m pip show pyinstaller *> $null
if ($LASTEXITCODE -ne 0) {
    & $pythonExe -m pip install pyinstaller
}

Write-Host "Starting backend build with PyInstaller spec..." -ForegroundColor Cyan
& $pythonExe -m PyInstaller --noconfirm Aiden.spec

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=== Build Successful! ===" -ForegroundColor Green
    Write-Host "Your executable can be found in the '$scriptDir\dist\Aiden' folder." -ForegroundColor Yellow
    Write-Host "You can run Aiden by double-clicking 'Aiden.exe' in that folder." -ForegroundColor Yellow
    
    $envFile = Join-Path $scriptDir ".env"
    if (Test-Path $envFile) {
        Copy-Item $envFile (Join-Path $scriptDir "dist\Aiden\.env") -Force
        Write-Host ".env copied to dist\Aiden" -ForegroundColor Green
    } else {
        Write-Host "WARNING: .env not found — backend will use defaults/env vars only" -ForegroundColor Yellow
    }

    if ($RunAfterBuild) {
        Write-Host "Starting Aiden now..." -ForegroundColor Cyan
        Start-Process "$scriptDir\dist\Aiden\Aiden.exe"
    }
} else {
    Write-Host "Build failed with exit code $LASTEXITCODE." -ForegroundColor Red
}
