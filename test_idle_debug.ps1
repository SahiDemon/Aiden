# Aiden Idle and Hibernate Diagnostics Tool
# Monitors the idle timer, logs state transitions, active power requests, and writes to idle_debug.log.

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
$target = 120
$monitorTimeout = 60

# Clear previous log
if (Test-Path $logPath) { Remove-Item $logPath }

function Log-Message ($msg, $color = "Gray") {
    $timestamp = Get-Date -Format "HH:mm:ss.fff"
    $formattedMsg = "[$timestamp] $msg"
    Write-Host $formattedMsg -ForegroundColor $color
    $formattedMsg | Out-File -FilePath $logPath -Append -Encoding utf8
}

Clear-Host
Log-Message "==========================================================" "Cyan"
Log-Message "     AIDEN ASSISTANT - HIBERNATE DIAGNOSTIC MONITOR       " "Cyan"
Log-Message "==========================================================" "Cyan"
Log-Message "Saving logs to: $logPath" "Gray"
Log-Message "Display Timeout Target: $monitorTimeout seconds" "Gray"
Log-Message "Hibernate Timeout Target: $target seconds" "Gray"
Log-Message "Leave the mouse and keyboard completely still." "Yellow"
Log-Message "==========================================================" "Cyan"
Log-Message ""

$previousIdle = 0.0
$maxIdleReached = 0.0
$displayOffLogged = $false

# Fetch initial requests
Log-Message "Checking initial power requests..." "Gray"
$req = powercfg /requests
$req | Out-File -FilePath $logPath -Append -Encoding utf8

while ($true) {
    $tickCount = [Environment]::TickCount
    if ([Win32]::GetLastInputInfo([ref]$lastInputInfo)) {
        $idleMs = $tickCount - $lastInputInfo.dwTime
        if ($idleMs -lt 0) {
            $idleMs = [uint32]::MaxValue - $lastInputInfo.dwTime + $tickCount
        }
        
        $idleSec = [Math]::Round($idleMs / 1000, 1)
        
        # Track maximum idle time reached
        if ($idleSec -gt $maxIdleReached) {
            $maxIdleReached = $idleSec
        }
        
        # Log when monitor should have turned off
        if ($idleSec -ge $monitorTimeout -and -not $displayOffLogged) {
            Log-Message "--- Display Timeout Threshold Reached ($monitorTimeout s) ---" "Green"
            $displayOffLogged = $true
        }
        
        # Detect if timer reset back to 0
        if ($idleSec -lt $previousIdle -and $previousIdle -gt 2.0) {
            Log-Message "--- TIMER RESET DETECTED! ---" "Red"
            Log-Message "Timer fell from $($previousIdle)s to $($idleSec)s" "Red"
            
            # Query powercfg requests at the exact moment of reset
            Log-Message "Capturing power requests at reset..." "Yellow"
            $requests = powercfg /requests
            $requests | Out-File -FilePath $logPath -Append -Encoding utf8
            
            # Check for recent wake/input events in system log
            $recentEvents = Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=(Get-Date).AddSeconds(-10)} -ErrorAction SilentlyContinue | 
                            Where-Object { $_.ProviderName -like "*Kernel-Power*" -or $_.ProviderName -like "*Power-Troubleshooter*" -or $_.Id -eq 1 }
            
            if ($recentEvents) {
                Log-Message "Recent system power events found:" "Yellow"
                foreach ($e in $recentEvents) {
                    Log-Message "  Event ID $($e.Id) ($($e.ProviderName)): $($e.Message -replace "`r`n", " ")" "DarkYellow"
                }
            } else {
                Log-Message "No recent Kernel-Power event found. Reset was likely caused by physical mouse/keyboard/controller movement." "Yellow"
            }
            
            $displayOffLogged = $false
        }
        
        # If we reach target but don't hibernate
        if ($idleSec -ge $target -and ($idleSec -as [int]) % 10 -eq 0 -and $idleSec -ne $previousIdle) {
            Log-Message "System idle time is at $($idleSec)s (Target: ${target}s). PC should have hibernated." "Red"
            Log-Message "Querying active requests blocking hibernation..." "Yellow"
            $requests = powercfg /requests
            $requests | Out-File -FilePath $logPath -Append -Encoding utf8
        }
        
        # Periodic idle status logging (every 10s of idle progression)
        if (($idleSec -as [int]) % 10 -eq 0 -and ($idleSec -as [int]) -ne ($previousIdle -as [int]) -and $idleSec -gt 0) {
            Log-Message "Idle Time: $($idleSec)s..." "Gray"
        }
        
        $previousIdle = $idleSec
    }
    Start-Sleep -Milliseconds 250
}
