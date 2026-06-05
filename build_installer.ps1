param(
    [string]$Version = "",
    [switch]$SkipNodeInstall
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
& (Join-Path $scriptDir "build_release.ps1") -Version $Version -SkipNodeInstall:$SkipNodeInstall

