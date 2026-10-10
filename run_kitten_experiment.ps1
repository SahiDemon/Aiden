param([switch]$Baseline)

# Process-local selectors leave normal launches on the configured baseline.
$taskRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
$taskPreviousEnvironment = @{}
foreach ($taskName in @('SPEECH_KITTEN_EXPERIMENT', 'SPEECH_TTS_PROVIDER', 'SPEECH_STT_PROVIDER')) {
    $taskPreviousEnvironment[$taskName] = [Environment]::GetEnvironmentVariable($taskName, 'Process')
}
try {
    $env:SPEECH_KITTEN_EXPERIMENT = 'true'
    $env:SPEECH_TTS_PROVIDER = $(if ($Baseline) { 'edge' } else { 'kitten' })
    $env:SPEECH_STT_PROVIDER = $(if ($Baseline) { 'groq' } else { 'kitten' })
    Write-Host "Speech experiment: TTS=$env:SPEECH_TTS_PROVIDER STT=$env:SPEECH_STT_PROVIDER"
    & (Join-Path $taskRoot 'run_aiden.ps1') -Debug
} finally {
    foreach ($taskName in $taskPreviousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($taskName, $taskPreviousEnvironment[$taskName], 'Process')
    }
}
