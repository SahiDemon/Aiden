# Install Aiden from source without changing an existing .env.
[CmdletBinding()]
param(
    [switch]$Dev,
    [switch]$IncludeOverlay,
    [switch]$SkipModel,
    [switch]$SkipDashboard,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'

function Invoke-Native {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Command failed with exit code $LASTEXITCODE. Resolve the error above and rerun install.ps1."
    }
}

Push-Location $PSScriptRoot
try {
    Write-Host 'Aiden | Windows source setup' -ForegroundColor Cyan
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        throw 'Install Python 3.10 or newer and enable Add Python to PATH. Python 3.11 is recommended.'
    }
    $pythonVersion = & python --version
    if ($LASTEXITCODE -ne 0 -or $pythonVersion -notmatch '^Python (\d+)\.(\d+)') {
        throw 'Could not read the Python version. Check the Python installation and PATH.'
    }
    if ([int]$Matches[1] -lt 3 -or ([int]$Matches[1] -eq 3 -and [int]$Matches[2] -lt 10)) {
        throw 'Python 3.10 or newer is required.'
    }
    Write-Host $pythonVersion

    if (-not $SkipDashboard -or $IncludeOverlay) {
        if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
            throw 'Install Node.js 22.12 or newer, then reopen PowerShell.'
        }
        $nodeVersion = & node --version
        if ($LASTEXITCODE -ne 0 -or $nodeVersion -notmatch '^v(\d+)\.(\d+)') {
            throw 'Could not read the Node.js version. Check the Node installation and PATH.'
        }
        if ([int]$Matches[1] -lt 22 -or ([int]$Matches[1] -eq 22 -and [int]$Matches[2] -lt 12)) {
            throw 'Node.js 22.12 or newer is required.'
        }
        Write-Host "Node $nodeVersion"
        Invoke-Native -Command npm.cmd -Arguments @('--version')
    }

    # Match run_aiden.ps1: reuse .venv first, then venv; create .venv for new clones.
    $pythonExe = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    $legacyPython = Join-Path $PSScriptRoot 'venv\Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $pythonExe) -and (Test-Path -LiteralPath $legacyPython)) {
        $pythonExe = $legacyPython
    }
    if ($CheckOnly) {
        Write-Host "Prerequisites passed. Selected environment: $pythonExe" -ForegroundColor Green
        Write-Host 'CheckOnly made no changes. Run install.ps1 without this switch to install.'
        return
    }

    if (-not (Test-Path -LiteralPath $pythonExe)) {
        Invoke-Native -Command python -Arguments @('-m', 'venv', '.venv')
    }
    Invoke-Native -Command $pythonExe -Arguments @('-m', 'pip', 'install', '--upgrade', 'pip')
    $requirements = if ($Dev) { 'requirements-dev.txt' } else { 'requirements.txt' }
    Invoke-Native -Command $pythonExe -Arguments @('-m', 'pip', 'install', '-r', $requirements)

    if (-not (Test-Path -LiteralPath '.env')) {
        Copy-Item -LiteralPath '.env.example' -Destination '.env'
        Write-Host 'Created .env. Add GROQ_API_KEY, NEON_DATABASE_URL, and REDIS_URL before starting.' -ForegroundColor Yellow
    } else {
        Write-Host 'Kept your existing .env.' -ForegroundColor Green
    }

    if (-not $SkipModel) {
        $modelDir = Join-Path $PSScriptRoot 'vosk_models'
        $modelFile = Join-Path $modelDir 'vosk-model-small-en-us-0.15\am\final.mdl'
        if (-not (Test-Path -LiteralPath $modelFile)) {
            New-Item -ItemType Directory -Force -Path $modelDir | Out-Null
            $archive = Join-Path $modelDir 'vosk-model-small-en-us-0.15.zip'
            Write-Host 'Downloading the English Vosk wake-word model...' -ForegroundColor Cyan
            Invoke-WebRequest -Uri 'https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip' -OutFile $archive -UseBasicParsing
            Expand-Archive -LiteralPath $archive -DestinationPath $modelDir -Force
            if (-not (Test-Path -LiteralPath $modelFile)) {
                throw 'Vosk model extraction did not produce am/final.mdl. See docs/setup.md.'
            }
            Remove-Item -LiteralPath $archive
        }
    }

    $projects = @()
    if (-not $SkipDashboard) { $projects += 'dashboard' }
    if ($IncludeOverlay) { $projects += 'overlay' }
    foreach ($project in $projects) {
        Push-Location (Join-Path $PSScriptRoot $project)
        try {
            Invoke-Native -Command npm.cmd -Arguments @('ci')
            $build = if ($project -eq 'overlay') { 'build:app' } else { 'build' }
            Invoke-Native -Command npm.cmd -Arguments @('run', $build)
        } finally {
            Pop-Location
        }
    }

    Write-Host 'Setup complete. Configure .env, then run .\run_aiden.ps1 -Debug.' -ForegroundColor Green
    Write-Host 'Database tables are initialized by the app at startup; setup does not verify service credentials.'
    Write-Host 'Open http://localhost:5000 after startup. Help: docs/setup.md and docs/troubleshooting.md.'
} finally {
    Pop-Location
}
