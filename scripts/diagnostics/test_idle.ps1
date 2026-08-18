# Requires -RunAsAdministrator
# Aiden Smart Idle and Hibernate Monitor
# Monitors and displays both Display Off and Hibernate timeouts separately.
# Logs diagnostics to idle_debug.log on resets or failures.

# 1. Elevate to Administrator if not already elevated
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Host "==========================================================" -ForegroundColor Yellow
    Write-Host "  This tool requires Administrator privileges." -ForegroundColor Yellow
    Write-Host "  Requesting elevation... Please approve the UAC prompt." -ForegroundColor Yellow
    Write-Host "==========================================================" -ForegroundColor Yellow
    Start-Process powershell -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    Exit
}


Add-Type @'
using System;
using System.Runtime.InteropServices;

public class Win32 {
    [StructLayout(LayoutKind.Sequential)]
    public struct LASTINPUTINFO {
        public uint cbSize;
        public uint dwTime;
    }

    [DllImport("user32.dll")]
    public static extern bool GetLastInputInfo(ref LASTINPUTINFO plii);
}
'@

$lastInputInfo = New-Object Win32+LASTINPUTINFO
$lastInputInfo.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf($lastInputInfo)

$logPath = Join-Path $PSScriptRoot "idle_debug.log"
$displayTarget = 60
$hibernateTarget = 120

# Clear previous log
if (Test-Path $logPath) { Remove-Item $logPath }

function Log-Message ($msg, $color = "Gray") {
    $timestamp = Get-Date -Format "HH:mm:ss.fff"
    $formattedMsg = "[$timestamp] $msg"
    $formattedMsg | Out-File -FilePath $logPath -Append -Encoding utf8
}

# Write initial headers to log
Log-Message "=== IDLE DIAGNOSTICS STARTED ==="
Log-Message "Display Target: $displayTarget s"
Log-Message "Hibernate Target: $hibernateTarget s"
$initialRequests = powercfg /requests
$initialRequests | Out-File -FilePath $logPath -Append -Encoding utf8

# Setup Console UI
Clear-Host
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "       AIDEN ASSISTANT - SMART IDLE & HIBERNATE MONITOR    " -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host " Log File: $logPath" -ForegroundColor Gray
Write-Host " Instructions: Keep mouse/keyboard still. Watch the bars." -ForegroundColor Gray
Write-Host " Press Ctrl+C to exit." -ForegroundColor Gray
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host ""

# Save cursor position so we can overwrite lines dynamically
$startRow = [Console]::CursorTop

$previousIdle = 0.0
$displayOffLogged = $false
$hibernateLogged = $false

function Draw-Bar ($label, $current, $target, $colorName) {
    $percent = [Math]::Min(100, [Math]::Round(($current / $target) * 100))
    $filledChars = [int]($percent / 5) # 20 chars total bar length
    $emptyChars = 20 - $filledChars
    $progressBar = "[" + ("#" * $filledChars) + ("." * $emptyChars) + "]"
    
    $padLabel = $label.PadRight(15)
    $timeStr = "{0:F1}s / {1}s" -f $current, $target
    $padTime = $timeStr.PadRight(14)
    
    Write-Host "  $padLabel : " -NoNewline -ForegroundColor White
    Write-Host "$progressBar " -NoNewline -ForegroundColor $colorName
    Write-Host "$padTime ($percent%)" -ForegroundColor $colorName
}

while ($true) {
    $tickCount = [Environment]::TickCount
    if ([Win32]::GetLastInputInfo([ref]$lastInputInfo)) {
        $idleMs = $tickCount - $lastInputInfo.dwTime
        if ($idleMs -lt 0) {
            $idleMs = [uint32]::MaxValue - $lastInputInfo.dwTime + $tickCount
        }
        
        $idleSec = [Math]::Round($idleMs / 1000, 1)
        
        # 1. Detect Idle Reset
        if ($idleSec -lt $previousIdle -and $previousIdle -gt 1.5) {
            [Console]::CursorTop = $startRow + 3
            [Console]::CursorLeft = 0
            
            $phase = "Display Countdown"
            if ($previousIdle -ge $displayTarget) {
                $phase = "Hibernate Countdown"
            }
            
            $alertMsg = "[!] Reset at $($previousIdle)s - Interrupted $phase at $(Get-Date -Format "HH:mm:ss")"
            Write-Host $alertMsg.PadRight(60) -ForegroundColor Red
            Log-Message "RESET: $alertMsg"
            
            # Capture power requests at reset moment
            Log-Message "Capturing requests at reset..."
            $requests = powercfg /requests
            $requests | Out-File -FilePath $logPath -Append -Encoding utf8
            
            # Query recent system log events
            $recentEvents = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddSeconds(-10)} -ErrorAction SilentlyContinue | 
                            Where-Object { $_.ProviderName -like "*Kernel-Power*" -or $_.ProviderName -like "*Power-Troubleshooter*" -or $_.Id -eq 1 }
            if ($recentEvents) {
                foreach ($e in $recentEvents) {
                    Log-Message "  Event ID $($e.Id) ($($e.ProviderName)): $($e.Message -replace "`r`n", " ")"
                }
            }
            
            # Reset logs
            $displayOffLogged = $false
            $hibernateLogged = $false
            Start-Sleep -Seconds 1 # Pause to let user see the reset alert
        }
        
        # 2. Check Milestones
        if ($idleSec -ge $displayTarget -and -not $displayOffLogged) {
            Log-Message "MILESTONE: Display Timeout ($displayTarget s) reached."
            $displayOffLogged = $true
        }
        
        if ($idleSec -ge $hibernateTarget -and -not $hibernateLogged) {
            Log-Message "MILESTONE: Hibernate Target ($hibernateTarget s) reached. System should hibernate now."
            $hibernateLogged = $true
            
            # Query requests since PC is still awake
            Log-Message "PC awake past Hibernate target. Capturing blockers..."
            $requests = powercfg /requests
            $requests | Out-File -FilePath $logPath -Append -Encoding utf8
        }
        
        # 3. Draw UI
        [Console]::CursorTop = $startRow
        [Console]::CursorLeft = 0
        
        # Display Bar
        $dispColor = "Yellow"
        if ($idleSec -ge $displayTarget) { $dispColor = "Green" }
        Draw-Bar "Display Turn-off" $idleSec $displayTarget $dispColor
        
        # Hibernate Bar
        $hibColor = "Yellow"
        if ($idleSec -ge $hibernateTarget) { $hibColor = "Green" }
        Draw-Bar "Hibernate Mode" $idleSec $hibernateTarget $hibColor
        
        Write-Host "" # Spacer line
        
        $previousIdle = $idleSec
    }
    Start-Sleep -Milliseconds 200
}
