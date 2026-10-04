# Requires -RunAsAdministrator
<#
.SYNOPSIS
    Aiden Sleep Diagnostics and Overrides tool.
    Helps diagnose why a Windows PC is staying awake overnight and offers
    one-click fixes to override common sleep-blocking processes and drivers.
.DESCRIPTION
    This script checks Windows sleep states, active wake-armed devices,
    identifies running sleep-blocking processes (Aiden, ViewPower, SignalRGB, etc.),
    queries current power requests, and applies powercfg request overrides.
#>

# 1. Elevate to Administrator if not already elevated
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "==========================================================" -ForegroundColor Yellow
    Write-Host "  This tool requires Administrator privileges." -ForegroundColor Yellow
    Write-Host "  Requesting elevation... Please approve the UAC prompt." -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    Exit
}

# Clear the screen and setup colors
Clear-Host
$host.UI.RawUI.WindowTitle = "Aiden - Windows Sleep Diagnostics"

# Helper function to print headers
function Write-Header ($text) {
    Write-Host ""
    Write-Host "=== $text ===" -ForegroundColor Cyan
}

# Helper function to print warning alert
function Write-Alert ($text) {
    Write-Host " [!] $text" -ForegroundColor DarkYellow
}

# Helper function to print success
function Write-Success ($text) {
    Write-Host " [v] $text" -ForegroundColor Green
}

# Helper function to print info
function Write-Info ($text) {
    Write-Host " [*] $text" -ForegroundColor Gray
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       AIDEN ASSISTANT - WINDOWS SLEEP DIAGNOSTICS        " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Info "Local Time: $(Get-Date)"
Write-Info "Computer Name: $env:COMPUTERNAME"

# 2. Check Supported Sleep States
Write-Header "Supported Sleep States"
$sleepStates = powercfg /a
$supportsS3 = $false
foreach ($line in $sleepStates) {
    Write-Host "  $line"
    if ($line -like "*Standby (S3)*" -and $line -notlike "*not available*") {
        $supportsS3 = $true
    }
}

if ($supportsS3) {
    Write-Success "Traditional Standby (S3) is supported. The hardware is capable of complete sleep (fans turning off)."
} else {
    Write-Alert "Traditional Standby (S3) is NOT supported or disabled in BIOS. System might be using Modern Standby (S0), which keeps fans running."
}

# 3. Check Active Power Requests (requires Admin)
Write-Header "Active Windows Power Requests"
$requests = powercfg /requests
$hasRequests = $false
foreach ($line in $requests) {
    Write-Host "  $line"
    if ($line.Trim() -ne "" -and $line -notlike "*[SERVICE]*" -and $line -notlike "*[PROCESS]*" -and $line -notlike "*[DRIVER]*" -and $line -notlike "*None*") {
        $hasRequests = $true
    }
}

if (-not $hasRequests) {
    Write-Success "No active sleep blockers reported by powercfg /requests at this very moment."
} else {
    Write-Alert "One or more active requests are currently blocking sleep! (See details above)"
}

# 4. Check Wake-Armed Devices
Write-Header "Devices Armed to Wake the PC"
$wakeArmed = powercfg /devicequery wake_armed
if ($wakeArmed.Count -eq 0 -or [string]::IsNullOrEmpty($wakeArmed)) {
    Write-Success "No devices are armed to wake the PC. Excellent."
} else {
    foreach ($dev in $wakeArmed) {
        if ($dev.Trim() -ne "") {
            Write-Host "  - $dev" -ForegroundColor Yellow
        }
    }
    Write-Info "If your PC wakes up unexpectedly, one of the above devices (often mouse movement or network card) is the trigger."
}

# 5. Check Known Sleep-Blocking Processes
Write-Header "Checking for Known Sleep-Blocking Applications"
$suspectedApps = @{
    "ViewPower"      = "ViewPower.exe"
    "SignalRgb"      = "SignalRgb.exe"
    "Jellyfin"       = "jellyfin.exe"
    "qBittorrent"    = "qbittorrent.exe"
    "WallpaperEngine"= "wallpaper64.exe"
    "Aiden / Python" = "python.exe"
    "Audio Service"  = "audiodg.exe"
}

$runningSuspects = @()
foreach ($appName in $suspectedApps.Keys) {
    $procName = $suspectedApps[$appName]
    $proc = Get-Process -Name ($procName -replace "\.exe$", "") -ErrorAction SilentlyContinue
    if ($proc) {
        $cpuText = ""
        try {
            $cpu = [Math]::Round(($proc | Measure-Object -Property CPU -Sum).Sum, 1)
            $cpuText = " (Active CPU: $cpu)"
        } catch {}
        Write-Alert "$appName ($procName) is currently RUNNING$cpuText."
        $runningSuspects += $procName
    } else {
        Write-Info "$appName ($procName) is not running."
    }
}

if ($runningSuspects.Count -gt 0) {
    Write-Host ""
    Write-Host "   - Analysis:" -ForegroundColor Cyan
    if ($runningSuspects -contains "python.exe") {
        Write-Host "   - Aiden (Python) keeps a continuous audio capture stream open to listen for the wake word." -ForegroundColor Gray
        Write-Host "     This keeps the audio driver active and blocks automatic sleep." -ForegroundColor Gray
    }
    if ($runningSuspects -contains "ViewPower.exe") {
        Write-Host "   - ViewPower runs a UPS monitoring web-server that keeps a power request to prevent sleep." -ForegroundColor Gray
    }
    if ($runningSuspects -contains "SignalRgb.exe") {
        Write-Host "   - SignalRGB runs active lighting engines that can block display and system sleep." -ForegroundColor Gray
    }
}

# 6. Current Overrides
Write-Header "Current Power Request Overrides"
powercfg /requestsoverride

# 7. Menu Options
while ($true) {
    Write-Host ""
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host "                      CHOOSE AN ACTION                    " -ForegroundColor Cyan
    Write-Host "==========================================================" -ForegroundColor Cyan
    Write-Host " [1] Apply Sleep Overrides (Recommended Fix)" -ForegroundColor Green
    Write-Host " [2] Restore Default Overrides (Clean Slate)" -ForegroundColor Yellow
    Write-Host " [3] Save Detailed Diagnostics Report to File" -ForegroundColor White
    Write-Host " [4] Exit" -ForegroundColor Red
    Write-Host ""
    $choice = Read-Host "Select an option [1-4]"

    switch ($choice) {
        "1" {
            Write-Header "Applying Sleep Overrides..."
            
            # Common drivers to override
            $drivers = @("Realtek(R) Audio", "Realtek High Definition Audio", "USB Audio Device", "USB\VID_0C76&PID_1619&MI_00\a&1fc2104f&1&0000", "USB Audio Device (USB\VID_0C76&PID_1619&MI_00\a&1fc2104f&1&0000)")
            foreach ($driver in $drivers) {
                Write-Info "Overriding DRIVER: $driver"
                powercfg /requestsoverride DRIVER "$driver" SYSTEM
            }

            # Common processes to override
            $processes = @("python.exe", "audiodg.exe", "ViewPower.exe", "SignalRgb.exe", "jellyfin.exe", "qbittorrent.exe", "wallpaper64.exe", "MoUsoCoreWorker.exe")
            foreach ($proc in $processes) {
                Write-Info "Overriding PROCESS: $proc"
                powercfg /requestsoverride PROCESS "$proc" SYSTEM
                if ($proc -eq "SignalRgb.exe") {
                    powercfg /requestsoverride PROCESS "$proc" DISPLAY SYSTEM
                }
                if ($proc -eq "MoUsoCoreWorker.exe") {
                    powercfg /requestsoverride PROCESS "$proc" EXECUTION SYSTEM
                }
            }

            Write-Success "Sleep overrides applied successfully!"
            Write-Host "Windows will now ignore sleep-blocking requests from these apps and audio streams,"
            Write-Host "allowing the PC to enter true S3 sleep when idle timeouts occur."
            Write-Host ""
            Write-Host "Updated Overrides:" -ForegroundColor Cyan
            powercfg /requestsoverride
        }
        "2" {
            Write-Header "Restoring Default Overrides..."
            
            # Drivers to remove
            $drivers = @("Realtek(R) Audio", "Realtek High Definition Audio", "USB Audio Device", "USB\VID_0C76&PID_1619&MI_00\a&1fc2104f&1&0000", "USB Audio Device (USB\VID_0C76&PID_1619&MI_00\a&1fc2104f&1&0000)", "USB PnP Audio Device", "FxSound Audio Enhancer")
            foreach ($driver in $drivers) {
                Write-Info "Removing override for DRIVER: $driver"
                powercfg /requestsoverride DRIVER "$driver"
            }

            # Processes to remove
            $processes = @("python.exe", "audiodg.exe", "ViewPower.exe", "SignalRgb.exe", "jellyfin.exe", "qbittorrent.exe", "wallpaper64.exe", "MoUsoCoreWorker.exe")
            foreach ($proc in $processes) {
                Write-Info "Removing override for PROCESS: $proc"
                powercfg /requestsoverride PROCESS "$proc"
            }

            # Re-apply FxSound since it was there originally
            Write-Info "Restoring original FxSound Audio Enhancer override..."
            powercfg /requestsoverride DRIVER "FxSound Audio Enhancer" SYSTEM

            Write-Success "Overrides restored to original defaults."
            Write-Host ""
            Write-Host "Current Overrides:" -ForegroundColor Cyan
            powercfg /requestsoverride
        }
        "3" {
            $reportPath = Join-Path $PSScriptRoot "sleep_diagnostics.txt"
            Write-Info "Generating detailed report to $reportPath..."
            
            $report = @()
            $report += "=========================================================="
            $report += "       AIDEN ASSISTANT - SLEEP DIAGNOSTICS REPORT        "
            $report += "=========================================================="
            $report += "Generated on: $(Get-Date)"
            $report += "Computer Name: $env:COMPUTERNAME"
            $report += ""
            $report += "--- SUPPORTED SLEEP STATES ---"
            $report += powercfg /a
            $report += ""
            $report += "--- ACTIVE POWER REQUESTS ---"
            $report += powercfg /requests
            $report += ""
            $report += "--- WAKE ARMED DEVICES ---"
            $report += powercfg /devicequery wake_armed
            $report += ""
            $report += "--- RUNNING KNOWN SLEEP BLOCKERS ---"
            foreach ($appName in $suspectedApps.Keys) {
                $procName = $suspectedApps[$appName]
                $proc = Get-Process -Name ($procName -replace "\.exe$", "") -ErrorAction SilentlyContinue
                if ($proc) {
                    $report += "  [Running] $appName ($procName)"
                } else {
                    $report += "  [Not Running] $appName ($procName)"
                }
            }
            $report += ""
            $report += "--- CURRENT OVERRIDES ---"
            $report += powercfg /requestsoverride
            
            $report | Out-File -FilePath $reportPath -Encoding utf8
            Write-Success "Report saved successfully to sleep_diagnostics.txt!"
        }
        "4" {
            Write-Host "Exiting. Have a great day!"
            break
        }
        default {
            Write-Host "Invalid choice. Please select 1, 2, 3, or 4." -ForegroundColor Red
        }
    }
}
