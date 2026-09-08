param(
    [string]$Distro = 'Ubuntu-24.04'
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ($repositoryRoot -notmatch '^(?<Drive>[A-Za-z]):(?<Relative>\\.*)$') {
    throw "Expected a drive-qualified Windows repository path, got '$repositoryRoot'."
}
$drive = $Matches.Drive.ToLowerInvariant()
$relativePath = $Matches.Relative.Replace('\', '/')
$wslRepositoryRoot = "/mnt/$drive$relativePath"

$trainingConfig = "$wslRepositoryRoot/scripts/diagnostics/wake_word_v3.yml"
$trainingScript = "$wslRepositoryRoot/scripts/diagnostics/train_wake_word_v2.sh"
$command = @(
    "cd '$wslRepositoryRoot'"
    'AIDEN_WAKE_TRAINING_ROOT=/opt/aiden-wake-training'
    'AIDEN_WAKE_MODEL_NAME=aiden_v3'
    "AIDEN_WAKE_TRAINING_CONFIG='$trainingConfig'"
    "bash '$trainingScript'"
) -join ' && '

Write-Host 'Aiden v3 wake-model training' -ForegroundColor Cyan
Write-Host "WSL distro: $Distro"
Write-Host 'Training root: /opt/aiden-wake-training'
Write-Host 'Target: Aiden (including Aidan/Ayden pronunciation variants)'
Write-Host 'This window shows the real generator, augmentation, and GPU-training progress.'
Write-Host ''

& wsl.exe -d $Distro -u root -- bash -lc $command
$trainingExitCode = $LASTEXITCODE

if ($trainingExitCode -ne 0) {
    throw "Aiden v3 training failed with exit code $trainingExitCode. Keep this window open for diagnosis."
}

Write-Host ''
Write-Host 'Aiden v3 model training completed successfully.' -ForegroundColor Green
Write-Host "Model: $repositoryRoot\vosk_models\aiden_v3.onnx"
