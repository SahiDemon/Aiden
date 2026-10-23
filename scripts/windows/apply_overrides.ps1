# Requires -RunAsAdministrator
# Aiden Quick Overrides Tool

if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "==========================================================" -ForegroundColor Yellow
    Write-Host "  Requesting elevation... Please approve the UAC prompt." -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    Exit
}

Clear-Host
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "             APPLYING SLEEP & HIBERNATE FIXES             " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# Apply Overrides
Write-Host "Applying overrides for active drivers and processes..." -ForegroundColor Gray

powercfg /requestsoverride DRIVER "USB Audio Device" SYSTEM
powercfg /requestsoverride DRIVER "USB\VID_0C76&PID_1619&MI_00\a&1fc2104f&1&0000" SYSTEM
powercfg /requestsoverride DRIVER "USB Audio Device (USB\VID_0C76&PID_1619&MI_00\a&1fc2104f&1&0000)" SYSTEM
powercfg /requestsoverride DRIVER "Realtek(R) Audio" SYSTEM
powercfg /requestsoverride DRIVER "Realtek High Definition Audio" SYSTEM
powercfg /requestsoverride DRIVER "USB PnP Audio Device" SYSTEM
powercfg /requestsoverride DRIVER "FxSound Audio Enhancer" SYSTEM

powercfg /requestsoverride PROCESS "python.exe" SYSTEM
powercfg /requestsoverride PROCESS "audiodg.exe" SYSTEM
powercfg /requestsoverride PROCESS "ViewPower.exe" SYSTEM
powercfg /requestsoverride PROCESS "SignalRgb.exe" DISPLAY SYSTEM
powercfg /requestsoverride PROCESS "jellyfin.exe" SYSTEM
powercfg /requestsoverride PROCESS "qbittorrent.exe" SYSTEM
powercfg /requestsoverride PROCESS "wallpaper64.exe" SYSTEM
powercfg /requestsoverride PROCESS "MoUsoCoreWorker.exe" EXECUTION SYSTEM

Write-Host "Overrides applied!" -ForegroundColor Green
Write-Host ""
Write-Host "--- CURRENT OVERRIDES LIST ---" -ForegroundColor Cyan
powercfg /requestsoverride
Write-Host ""
Write-Host "Press any key to close this window..."
[void][System.Console]::ReadKey()
