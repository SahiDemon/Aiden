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

# 1. Build the single Aiden.exe (console=False, tray mode)
Write-Host "Building Aiden.exe with PyInstaller..." -ForegroundColor Cyan
& $pythonExe -m PyInstaller --noconfirm Aiden.spec

if ($LASTEXITCODE -ne 0) {
    Write-Host "Build failed with exit code $LASTEXITCODE." -ForegroundColor Red
    exit $LASTEXITCODE
}

$distDir = Join-Path $scriptDir "dist\Aiden"

# 2. Copy .env next to the EXE
$envFile = Join-Path $scriptDir ".env"
if (Test-Path $envFile) {
    Copy-Item $envFile (Join-Path $distDir ".env") -Force
    Write-Host ".env copied to dist\Aiden" -ForegroundColor Green
} else {
    Write-Host "WARNING: .env not found - backend will use defaults/env vars only" -ForegroundColor Yellow
}

# 3. Create aiden.cmd so typing 'aiden' in PowerShell runs Aiden.exe --debug.
#    AttachConsole(-1) in main.py pipes output back into the caller's terminal.
$cmdPath = Join-Path $distDir "aiden.cmd"
$line1 = "@echo off"
$line2 = '"%~dp0Aiden.exe" --debug %*'
Set-Content  -Path $cmdPath -Value $line1 -Encoding ASCII
Add-Content  -Path $cmdPath -Value $line2 -Encoding ASCII
Write-Host "aiden.cmd created in dist\Aiden\" -ForegroundColor Green

# 4. Add dist\Aiden to the user PATH (persistent, current user only)
$userPath   = [System.Environment]::GetEnvironmentVariable("Path", "User")
$distDirNorm = $distDir.TrimEnd('\')

if ($userPath -notlike "*$distDirNorm*") {
    $newPath = "$userPath;$distDirNorm"
    [System.Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    Write-Host "Added dist\Aiden to your user PATH." -ForegroundColor Green
    Write-Host "  Path: $distDirNorm" -ForegroundColor DarkGray
    Write-Host "  Restart PowerShell to use 'aiden' immediately." -ForegroundColor Yellow
} else {
    Write-Host "dist\Aiden is already in your user PATH." -ForegroundColor DarkGray
}

Write-Host ""
Write-Host "=== Build Successful! ===" -ForegroundColor Green
Write-Host ""
Write-Host "  Double-click tray mode : $distDir\Aiden.exe" -ForegroundColor Yellow
Write-Host "  PowerShell debug mode  : aiden   (runs Aiden.exe --debug)" -ForegroundColor Yellow
Write-Host ""

if ($RunAfterBuild) {
    Write-Host "Starting Aiden now..." -ForegroundColor Cyan
    Start-Process "$distDir\Aiden.exe"
}
