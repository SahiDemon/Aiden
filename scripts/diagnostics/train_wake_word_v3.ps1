param(
    [string]$Distro = 'Ubuntu-24.04',
    [string]$ModelName = 'aiden_v3',
    [string]$ConfigFile = 'wake_word_v3.yml'
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($repositoryRoot -notmatch '^(?<Drive>[A-Za-z]):(?<Relative>\\.*)$') {
    throw "Expected a drive-qualified Windows repository path, got '$repositoryRoot'."
}
$drive = $Matches.Drive.ToLowerInvariant()
$relativePath = $Matches.Relative.Replace('\', '/')
$wslRepositoryRoot = "/mnt/$drive$relativePath"

$trainingConfig = "$wslRepositoryRoot/scripts/diagnostics/$ConfigFile"
$trainingScript = "$wslRepositoryRoot/scripts/diagnostics/train_wake_word_v2.sh"
$logDirectory = Join-Path $repositoryRoot '.local\wake-word'
$logPath = Join-Path $logDirectory "$ModelName-training.log"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$command = @(
    "cd '$wslRepositoryRoot' &&"
    'AIDEN_WAKE_TRAINING_ROOT=/opt/aiden-wake-training'
    "AIDEN_WAKE_MODEL_NAME='$ModelName'"
    "AIDEN_WAKE_TRAINING_CONFIG='$trainingConfig'"
    "bash '$trainingScript'"
) -join ' '

Write-Host "$ModelName wake-model training" -ForegroundColor Cyan
Write-Host "WSL distro: $Distro"
Write-Host 'Training root: /opt/aiden-wake-training'
Write-Host 'Target: Aiden and Hey Aiden'
Write-Host 'This window shows the real generator, augmentation, and GPU-training progress.'
Write-Host "Saved log: $logPath"
Write-Host ''

& wsl.exe -d $Distro -u root -- bash -lc $command 2>&1 |
    Tee-Object -FilePath $logPath -Append
$trainingExitCode = $LASTEXITCODE

if ($trainingExitCode -ne 0) {
    throw "$ModelName training failed with exit code $trainingExitCode. Keep this window open for diagnosis."
}

Write-Host ''
Write-Host "$ModelName training completed successfully." -ForegroundColor Green
Write-Host "Model: $repositoryRoot\vosk_models\$ModelName.onnx"
