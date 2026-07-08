param(
    [string]$Version = "",
    [switch]$SkipNodeInstall,
    [switch]$SkipDashboardBuild,
    [switch]$SkipBackendBuild,
    [switch]$SkipOverlayInstall
)

$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Title,
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "== $Title ==" -ForegroundColor Cyan
    & $Action
}

function Assert-NativeSuccess {
    param([string]$Command)

    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE`: $Command"
    }
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $scriptDir

$buildTempDir = Join-Path $scriptDir ".build-tmp"
$electronCacheDir = Join-Path $scriptDir ".electron-builder-cache"
New-Item -ItemType Directory -Force -Path $buildTempDir, $electronCacheDir | Out-Null
$env:TEMP = $buildTempDir
$env:TMP = $buildTempDir
$env:ELECTRON_BUILDER_CACHE = $electronCacheDir

$pythonExe = Join-Path $scriptDir ".venv\Scripts\python.exe"
if (-not (Test-Path $pythonExe)) {
    $pythonExe = Join-Path $scriptDir "venv\Scripts\python.exe"
}
if (-not (Test-Path $pythonExe)) {
    throw "Virtual environment not found. Run .\install.ps1 first."
}

$dashboardDir = Join-Path $scriptDir "dashboard"
$overlayDir = Join-Path $scriptDir "overlay"

if ($Version) {
    Invoke-Step "Set overlay installer version to $Version" {
        Push-Location $overlayDir
        npm pkg set version=$Version
        Assert-NativeSuccess "npm pkg set version=$Version"
        Pop-Location
    }
}

if (-not $SkipDashboardBuild) {
    Invoke-Step "Build dashboard assets" {
        Push-Location $dashboardDir
        if (-not $SkipNodeInstall) {
            npm install
            Assert-NativeSuccess "npm install"
        }
        npm run build
        Assert-NativeSuccess "npm run build"
        Pop-Location
    }
}

if (-not $SkipBackendBuild) {
    Invoke-Step "Ensure PyInstaller is available" {
        & $pythonExe -m pip show pyinstaller *> $null
        if ($LASTEXITCODE -ne 0) {
            & $pythonExe -m pip install pyinstaller
            Assert-NativeSuccess "$pythonExe -m pip install pyinstaller"
        }
    }

    Invoke-Step "Build Aiden backend executable" {
        & $pythonExe -m PyInstaller --noconfirm Aiden.spec
        Assert-NativeSuccess "$pythonExe -m PyInstaller --noconfirm Aiden.spec"
    }

    Invoke-Step "Copy .env to backend build and create aiden.cmd" {
        $distDir = Join-Path $scriptDir "dist\Aiden"
        $envFile = Join-Path $scriptDir ".env"
        if (Test-Path $envFile) {
            Copy-Item $envFile (Join-Path $distDir ".env") -Force
            Write-Host "  .env copied to dist\Aiden" -ForegroundColor Green
        } else {
            Write-Host "  WARNING: .env not found at $envFile - backend will use defaults/env vars only" -ForegroundColor Yellow
        }

        # Create aiden.cmd so typing 'aiden' in PowerShell runs debug mode.
        $cmdPath2 = Join-Path $distDir "aiden.cmd"
        "@echo off" | Set-Content -Path $cmdPath2 -Encoding ASCII
        '"%~dp0Aiden.exe" --debug %*' | Add-Content -Path $cmdPath2 -Encoding ASCII
        Write-Host "  aiden.cmd created in dist\Aiden\" -ForegroundColor Green

        # Add dist\Aiden to user PATH if not already present.
        $distDirNorm = $distDir.TrimEnd('\')
        $userPath = [System.Environment]::GetEnvironmentVariable("Path", "User")
        if ($userPath -notlike "*$distDirNorm*") {
            [System.Environment]::SetEnvironmentVariable("Path", "$userPath;$distDirNorm", "User")
            Write-Host "  Added dist\Aiden to user PATH. Restart PowerShell to use 'aiden'." -ForegroundColor Yellow
        } else {
            Write-Host "  dist\Aiden already in user PATH." -ForegroundColor DarkGray
        }
    }
}

Invoke-Step "Build overlay installer" {
    Push-Location $overlayDir
    if (-not $SkipNodeInstall -and -not $SkipOverlayInstall) {
        npm install
        Assert-NativeSuccess "npm install"
    }
    npm run build
    Assert-NativeSuccess "npm run build"
    Pop-Location
}

$installer = Get-ChildItem -Path (Join-Path $overlayDir "dist") -Filter "Aiden-Setup-*.exe" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

Write-Host ""
Write-Host "=== Aiden release build complete ===" -ForegroundColor Green
Write-Host "Backend exe : $scriptDir\dist\Aiden\Aiden.exe" -ForegroundColor Yellow
Write-Host "Debug cmd   : aiden   (runs Aiden.exe --debug in your terminal)" -ForegroundColor Yellow
if ($installer) {
    Write-Host "Installer   : $($installer.FullName)" -ForegroundColor Yellow
    Write-Host "Installer registers Aiden under HKCU\Software\Microsoft\Windows\CurrentVersion\Run." -ForegroundColor Yellow
} else {
    Write-Host "Installer was not found under $overlayDir\dist." -ForegroundColor Red
}
