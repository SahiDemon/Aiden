param(
    [string]$Distro = 'Ubuntu-24.04',
    [string]$LinuxWorkRoot = '/opt/aiden-wake-training'
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$linuxRepo = '/mnt/' + $repoRoot.Substring(0, 1).ToLowerInvariant() + $repoRoot.Substring(2).Replace('\', '/')

$status = (& wsl.exe --status 2>&1 | Out-String)
if ($LASTEXITCODE -ne 0 -or $status -notmatch 'Default Version:\s+2') {
    throw 'WSL2 is not available. Enable Virtual Machine Platform and WSL2 before running GPU model training.'
}

$distros = (& wsl.exe --list --quiet 2>&1 | Out-String) -replace "`0", ''
if ($distros -notmatch "(?m)^$([regex]::Escape($Distro))\s*$") {
    throw "WSL distribution '$Distro' is not installed."
}

& wsl.exe -d $Distro -u root -- env "AIDEN_WAKE_TRAINING_ROOT=$LinuxWorkRoot" bash "$linuxRepo/scripts/diagnostics/train_wake_word_v2.sh"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host 'Base model training complete.'
Write-Host 'Next: run train_personal_verifier.py and calibrate_wake_word_v2.py.'
