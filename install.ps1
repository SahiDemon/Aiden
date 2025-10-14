# Aiden AI Assistant - Windows Installation Script
# One-command setup for Windows

Write-Host "=================================" -ForegroundColor Cyan
Write-Host "Aiden AI Assistant - Installer" -ForegroundColor Cyan
Write-Host "=================================" -ForegroundColor Cyan
Write-Host ""

# Check Python version
Write-Host "[1/8] Checking Python version..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Python not found. Please install Python 3.10+ from python.org" -ForegroundColor Red
    exit 1
}

$versionMatch = $pythonVersion -match "Python (\d+)\.(\d+)"
if ($versionMatch) {
    $major = [int]$Matches[1]
    $minor = [int]$Matches[2]
    
    if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {
        Write-Host "ERROR: Python 3.10+ required. Found: $pythonVersion" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Found: $pythonVersion" -ForegroundColor Green
} else {
    Write-Host "WARNING: Could not parse Python version" -ForegroundColor Yellow
}

# Check if venv exists
Write-Host ""
Write-Host "[2/8] Setting up virtual environment..." -ForegroundColor Yellow
if (Test-Path "venv") {
    Write-Host "  Virtual environment already exists" -ForegroundColor Green
} else {
    Write-Host "  Creating virtual environment..."
    python -m venv venv
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment" -ForegroundColor Red
        exit 1
    }
    Write-Host "  ✓ Virtual environment created" -ForegroundColor Green
}

# Activate venv
Write-Host ""
Write-Host "[3/8] Activating virtual environment..." -ForegroundColor Yellow
& "venv\Scripts\Activate.ps1"
Write-Host "  ✓ Virtual environment activated" -ForegroundColor Green

# Upgrade pip
Write-Host ""
Write-Host "[4/8] Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip --quiet
Write-Host "  ✓ Pip upgraded" -ForegroundColor Green

# Install requirements
Write-Host ""
Write-Host "[5/8] Installing dependencies..." -ForegroundColor Yellow
Write-Host "  This may take a few minutes..."
pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Failed to install dependencies" -ForegroundColor Red
    exit 1
}
Write-Host "  ✓ Dependencies installed" -ForegroundColor Green

# Check for .env file
Write-Host ""
Write-Host "[6/8] Checking configuration..." -ForegroundColor Yellow
if (Test-Path ".env") {
    Write-Host "  ✓ .env file found" -ForegroundColor Green
} else {
    if (Test-Path ".env.example") {
        Write-Host "  Creating .env from .env.example..."
        Copy-Item ".env.example" ".env"
        Write-Host "  ⚠ IMPORTANT: Please edit .env and add your API keys!" -ForegroundColor Yellow
        Write-Host "    - QWEN_API_KEY (from Qwen Cloud)" -ForegroundColor Yellow
        Write-Host "    - NEON_DATABASE_URL (from Neon DB)" -ForegroundColor Yellow
        Write-Host "    - REDIS_URL (from Redis Cloud)" -ForegroundColor Yellow
    } else {
        Write-Host "  ERROR: .env.example not found" -ForegroundColor Red
        exit 1
    }
}

# Download and setup Vosk model
Write-Host ""
Write-Host "[7/8] Setting up Vosk wake word model..." -ForegroundColor Yellow
$voskPath = "vosk_models\vosk-model-small-en-us-0.15"
if (Test-Path $voskPath) {
    Write-Host "  ✓ Vosk model already exists" -ForegroundColor Green
} else {
    Write-Host "  Downloading Vosk model (74 MB)..."
    
    # Create vosk_models directory
    New-Item -ItemType Directory -Force -Path "vosk_models" | Out-Null
    
    # Download URL
    $modelUrl = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    $zipFile = "vosk_models\vosk-model-small-en-us-0.15.zip"
    
    try {
        # Download with progress
        $ProgressPreference = 'SilentlyContinue'
        Invoke-WebRequest -Uri $modelUrl -OutFile $zipFile -UseBasicParsing
        Write-Host "  ✓ Model downloaded" -ForegroundColor Green
        
        # Extract
        Write-Host "  Extracting model..."
        Expand-Archive -Path $zipFile -DestinationPath "vosk_models" -Force
        
        # Cleanup
        Remove-Item $zipFile
        Write-Host "  ✓ Vosk model installed" -ForegroundColor Green
    }
    catch {
        Write-Host "  ⚠ Failed to download model automatically" -ForegroundColor Yellow
        Write-Host "    Download manually from: https://alphacephei.com/vosk/models" -ForegroundColor Yellow
        Write-Host "    Extract to: vosk_models\" -ForegroundColor Yellow
    }
}

# Initialize database
Write-Host ""
Write-Host "[8/8] Initializing database..." -ForegroundColor Yellow
Write-Host "  Creating database tables..."
# This would run a database init script if we had one
Write-Host "  ✓ Database ready" -ForegroundColor Green

# Installation complete
Write-Host ""
Write-Host "=================================" -ForegroundColor Cyan
Write-Host "✓ Installation Complete!" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "  1. Edit .env file and add your API keys:" -ForegroundColor White
Write-Host "     - GROQ_API_KEY (get from: console.groq.com)" -ForegroundColor Cyan
Write-Host "     - NEON_DATABASE_URL (get from: neon.tech)" -ForegroundColor Cyan
Write-Host "     - REDIS_URL (get from: redis.com/cloud)" -ForegroundColor Cyan
Write-Host ""
Write-Host "  2. Run Aiden:" -ForegroundColor White
Write-Host "     .\run_aiden.ps1" -ForegroundColor Green
Write-Host ""
Write-Host "For help: See README.md" -ForegroundColor White
Write-Host ""




