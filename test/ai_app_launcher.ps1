# AI Assistant App Launcher System
# Enhanced version with listing, timeouts, and dashboard integration

# Import the core app finder functions
. "$PSScriptRoot\app_finder.ps1"

function Get-TopCommonApps {
    return @(
        @{ Name = "Chrome"; Description = "Google Chrome Browser"; Command = "chrome" },
        @{ Name = "VS Code"; Description = "Visual Studio Code Editor"; Command = "code" },
        @{ Name = "Steam"; Description = "Steam Gaming Platform"; Command = "steam" },
        @{ Name = "Discord"; Description = "Discord Chat Application"; Command = "discord" },
        @{ Name = "Spotify"; Description = "Spotify Music Player"; Command = "spotify" },
        @{ Name = "Notepad"; Description = "Windows Notepad"; Command = "notepad" },
        @{ Name = "Calculator"; Description = "Windows Calculator"; Command = "calculator" },
        @{ Name = "Explorer"; Description = "Windows File Explorer"; Command = "explorer" },
        @{ Name = "Firefox"; Description = "Mozilla Firefox Browser"; Command = "firefox" },
        @{ Name = "VLC"; Description = "VLC Media Player"; Command = "vlc" }
    )
}

function Get-InstalledAppsList {
    param(
        [int]$MaxResults = 50,
        [int]$TimeoutSeconds = 10
    )
    
    Write-Host "Scanning for installed applications..." -ForegroundColor Yellow
    $startTime = Get-Date
    $apps = @()
    
    # Quick common apps first
    $commonApps = Get-TopCommonApps
    foreach ($app in $commonApps) {
        $path = Find-AppPath -AppName $app.Command
        if ($path) {
            $apps += [PSCustomObject]@{
                Name = $app.Name
                Description = $app.Description
                Command = $app.Command
                Path = $path
                Type = "Common"
            }
        }
    }
    
    # Registry scan with timeout
    $uninstallKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    )
    
    foreach ($key in $uninstallKeys) {
        if (((Get-Date) - $startTime).TotalSeconds -gt $TimeoutSeconds) {
            Write-Host "Timeout reached, stopping scan..." -ForegroundColor Yellow
            break
        }
        
        try {
            $regApps = Get-ItemProperty -Path "$key\*" -ErrorAction SilentlyContinue | 
                      Where-Object { 
                          $_.DisplayName -and 
                          $_.InstallLocation -and
                          -not ($_.DisplayName -like "*uninstall*") -and
                          -not ($_.DisplayName -like "*remove*") -and
                          -not ($_.DisplayName -like "*setup*") -and
                          -not ($_.DisplayName -like "*update*")
                      } | Select-Object -First 20
            
            foreach ($regApp in $regApps) {
                if ($apps.Count -ge $MaxResults) { break }
                
                # Skip if already in common apps
                if ($apps | Where-Object { $_.Name -eq $regApp.DisplayName }) { continue }
                
                $apps += [PSCustomObject]@{
                    Name = $regApp.DisplayName
                    Description = "Installed Application"
                    Command = $regApp.DisplayName.ToLower() -replace '[^a-z0-9]', ''
                    Path = $regApp.InstallLocation
                    Type = "Registry"
                }
            }
        }
        catch {
            continue
        }
    }
    
    # UWP Apps
    try {
        $uwpApps = Get-AppxPackage | Where-Object { 
            $_.Name -notlike "*Microsoft*" -and 
            $_.Name -notlike "*Windows*" -and
            $_.DisplayName
        } | Select-Object -First 10
        
        foreach ($uwpApp in $uwpApps) {
            if ($apps.Count -ge $MaxResults) { break }
            
            $apps += [PSCustomObject]@{
                Name = if ($uwpApp.DisplayName) { $uwpApp.DisplayName } else { $uwpApp.Name }
                Description = "Microsoft Store App"
                Command = $uwpApp.Name.ToLower() -replace '[^a-z0-9]', ''
                Path = "shell:appsFolder\$($uwpApp.PackageFamilyName)!App"
                Type = "UWP"
            }
        }
    }
    catch {
        # Skip UWP if there are issues
    }
    
    Write-Host "Found $($apps.Count) applications in $([math]::Round(((Get-Date) - $startTime).TotalSeconds, 2)) seconds" -ForegroundColor Green
    return $apps | Sort-Object Name
}

function Show-AppsList {
    param(
        [string]$Filter = "",
        [switch]$TopCommonOnly
    )
    
    if ($TopCommonOnly) {
        Write-Host "===============================================" -ForegroundColor Cyan
        Write-Host "           TOP 10 COMMON APPLICATIONS         " -ForegroundColor Cyan
        Write-Host "===============================================" -ForegroundColor Cyan
        
        $commonApps = Get-TopCommonApps
        for ($i = 0; $i -lt $commonApps.Count; $i++) {
            $app = $commonApps[$i]
            Write-Host "$($i + 1). $($app.Name)" -ForegroundColor Green
            Write-Host "   Command: $($app.Command)" -ForegroundColor Gray
            Write-Host "   Description: $($app.Description)" -ForegroundColor Gray
            Write-Host ""
        }
        return $commonApps
    }
    
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "           INSTALLED APPLICATIONS LIST         " -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    
    $apps = Get-InstalledAppsList
    
    if ($Filter) {
        $apps = $apps | Where-Object { $_.Name -like "*$Filter*" }
        Write-Host "Filtered by: $Filter" -ForegroundColor Yellow
        Write-Host ""
    }
    
    if ($apps.Count -eq 0) {
        Write-Host "No applications found." -ForegroundColor Red
        return @()
    }
    
    for ($i = 0; $i -lt [Math]::Min($apps.Count, 50); $i++) {
        $app = $apps[$i]
        Write-Host "$($i + 1). $($app.Name)" -ForegroundColor Green
        Write-Host "   Type: $($app.Type)" -ForegroundColor Gray
        Write-Host "   Command: $($app.Command)" -ForegroundColor Gray
        Write-Host ""
    }
    
    if ($apps.Count -gt 50) {
        Write-Host "... and $($apps.Count - 50) more applications" -ForegroundColor Yellow
    }
    
    return $apps
}

function Find-AppWithTimeout {
    param(
        [string]$AppName,
        [int]$TimeoutSeconds = 15,
        [scriptblock]$FallbackFunction = $null
    )
    
    Write-Host "Primary search for: $AppName" -ForegroundColor Cyan
    
    # Start primary search in background job
    $job = Start-Job -ScriptBlock {
        param($AppName, $ScriptPath)
        . $ScriptPath
        Find-AppPath -AppName $AppName
    } -ArgumentList $AppName, "$PSScriptRoot\app_finder.ps1"
    
    # Wait for job with timeout
    $result = Wait-Job -Job $job -Timeout $TimeoutSeconds
    
    if ($result) {
        $path = Receive-Job -Job $job
        Remove-Job -Job $job
        
        if ($path) {
            Write-Host "[PRIMARY] Found: $AppName" -ForegroundColor Green
            return $path
        }
    } else {
        Write-Host "[TIMEOUT] Primary search timed out after $TimeoutSeconds seconds" -ForegroundColor Yellow
        Stop-Job -Job $job
        Remove-Job -Job $job
        
        if ($FallbackFunction) {
            Write-Host "[FALLBACK] Using fallback search method..." -ForegroundColor Yellow
            return & $FallbackFunction $AppName
        }
    }
    
    return $null
}

function Launch-AppWithAI {
    param(
        [string]$AppName,
        [switch]$Interactive,
        [switch]$ShowDashboard
    )
    
    if ([string]::IsNullOrWhiteSpace($AppName)) {
        if ($Interactive -or $ShowDashboard) {
            Show-InteractiveAppSelector
            return
        } else {
            Write-Host "Please provide an app name to launch." -ForegroundColor Red
            return
        }
    }
    
    # Trim and clean app name
    $AppName = $AppName.Trim()
    
    Write-Host "AI Assistant App Launcher" -ForegroundColor Cyan
    Write-Host "=========================================="
    
    # Try primary search with timeout (15 seconds)
    $timeoutSeconds = 15
    $startTime = Get-Date
    
    Write-Host "Primary search for: $AppName" -ForegroundColor Cyan
    $path = Find-AppPath -AppName $AppName
    
    $searchTime = ((Get-Date) - $startTime).TotalSeconds
    
    # If primary search takes too long or fails, use fallback
    if (-not $path -or $searchTime -gt $timeoutSeconds) {
        if ($searchTime -gt $timeoutSeconds) {
            Write-Host "[TIMEOUT] Primary search timed out after $timeoutSeconds seconds" -ForegroundColor Yellow
        }
        
        Write-Host "[FALLBACK] Using simple search method..." -ForegroundColor Yellow
        $cmd = Get-Command "$AppName.exe" -ErrorAction SilentlyContinue
        if ($cmd) { 
            $path = $cmd.Source 
            Write-Host "[FALLBACK] Found: $AppName" -ForegroundColor Green
        }
    } else {
        Write-Host "[PRIMARY] Found: $AppName in $([math]::Round($searchTime, 2))s" -ForegroundColor Green
    }
    
    if ($path) {
        Write-Host ""
        Write-Host "Launching application..." -ForegroundColor Yellow
        
        try {
            if ($path -like "*shell:appsFolder*") {
                Start-Process -FilePath "explorer.exe" -ArgumentList $path.Replace("explorer.exe ", "")
                Write-Host "UWP application launched successfully!" -ForegroundColor Green
            } elseif ($path -like "steam://launch/*") {
                Start-Process -FilePath $path
                Write-Host "Steam game launched successfully!" -ForegroundColor Green
            } else {
                Start-Process -FilePath $path
                Write-Host "Application launched successfully!" -ForegroundColor Green
            }
            
            return @{
                Success = $true
                AppName = $AppName
                Path = $path
                Message = "Application launched successfully"
                SearchTime = $searchTime
            }
        }
        catch {
            Write-Host "Failed to launch application: $($_.Exception.Message)" -ForegroundColor Red
            return @{
                Success = $false
                AppName = $AppName
                Path = $path
                Message = "Failed to launch: $($_.Exception.Message)"
                SearchTime = $searchTime
            }
        }
    } else {
        Write-Host "Could not find application: $AppName" -ForegroundColor Red
        
        if ($Interactive) {
            Write-Host ""
            Write-Host "Would you like to see available applications? (y/n): " -ForegroundColor Yellow -NoNewline
            $response = Read-Host
            
            if ($response -eq 'y' -or $response -eq 'Y') {
                Show-InteractiveAppSelector
            }
        }
        
        return @{
            Success = $false
            AppName = $AppName
            Path = $null
            Message = "Application not found"
            SearchTime = $searchTime
        }
    }
}

function Show-InteractiveAppSelector {
    Clear-Host
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "           INTERACTIVE APP SELECTOR           " -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "1. Show top 10 common applications" -ForegroundColor White
    Write-Host "2. List all installed applications" -ForegroundColor White
    Write-Host "3. Search for specific application" -ForegroundColor White
    Write-Host "4. Exit" -ForegroundColor White
    Write-Host ""
    
    while ($true) {
        Write-Host "Select option (1-4): " -ForegroundColor Yellow -NoNewline
        $choice = Read-Host
        
        switch ($choice) {
            "1" {
                $apps = Show-AppsList -TopCommonOnly
                Write-Host "Enter app number to launch (1-10) or 'back': " -ForegroundColor Yellow -NoNewline
                $selection = Read-Host
                
                if ($selection -eq 'back') { continue }
                
                $appIndex = [int]$selection - 1
                if ($appIndex -ge 0 -and $appIndex -lt $apps.Count) {
                    $selectedApp = $apps[$appIndex]
                    Launch-AppWithAI -AppName $selectedApp.Command
                    return
                }
            }
            "2" {
                $apps = Show-AppsList
                Write-Host "Enter app number to launch or 'back': " -ForegroundColor Yellow -NoNewline
                $selection = Read-Host
                
                if ($selection -eq 'back') { continue }
                
                $appIndex = [int]$selection - 1
                if ($appIndex -ge 0 -and $appIndex -lt $apps.Count) {
                    $selectedApp = $apps[$appIndex]
                    Launch-AppWithAI -AppName $selectedApp.Command
                    return
                }
            }
            "3" {
                Write-Host "Enter application name to search: " -ForegroundColor Yellow -NoNewline
                $searchTerm = Read-Host
                if ($searchTerm) {
                    Launch-AppWithAI -AppName $searchTerm -Interactive
                    return
                }
            }
            "4" {
                Write-Host "Goodbye!" -ForegroundColor Green
                return
            }
            default {
                Write-Host "Invalid option. Please select 1-4." -ForegroundColor Red
            }
        }
    }
}

# API Functions for AI Assistant Integration
function Invoke-AIAppLauncher {
    param(
        [Parameter(Mandatory=$true)]
        [string]$Command,
        [string]$AppName = "",
        [switch]$Interactive,
        [switch]$ShowDashboard,
        [string]$Filter = ""
    )
    
    switch ($Command.ToLower()) {
        "launch" {
            return Launch-AppWithAI -AppName $AppName -Interactive:$Interactive -ShowDashboard:$ShowDashboard
        }
        "search" {
            $startTime = Get-Date
            $path = Find-AppPath -AppName $AppName
            $searchTime = ((Get-Date) - $startTime).TotalSeconds
            
            return @{
                Success = ($path -ne $null)
                AppName = $AppName
                Path = $path
                Message = if ($path) { "Application found" } else { "Application not found" }
                SearchTime = $searchTime
            }
        }
        "list" {
            if ($Filter -eq "common") {
                return Show-AppsList -TopCommonOnly
            } else {
                return Show-AppsList -Filter $Filter
            }
        }
        "interactive" {
            Show-InteractiveAppSelector
            return @{ Success = $true; Message = "Interactive mode completed" }
        }
        "dashboard" {
            Show-InteractiveAppSelector
            return @{ Success = $true; Message = "Dashboard opened" }
        }
        default {
            return @{
                Success = $false
                Message = "Unknown command. Available: launch, search, list, interactive, dashboard"
            }
        }
    }
}

# Export functions for AI Assistant
Export-ModuleMember -Function @(
    'Invoke-AIAppLauncher',
    'Launch-AppWithAI', 
    'Find-AppWithTimeout',
    'Show-AppsList',
    'Show-InteractiveAppSelector',
    'Get-TopCommonApps',
    'Get-InstalledAppsList'
)

# Main execution for standalone usage
if ($args.Count -gt 0) {
    $command = $args[0].ToLower()
    $appName = if ($args.Count -gt 1) { $args[1..($args.Count-1)] -join ' ' } else { "" }
    
    switch ($command) {
        "launch" {
            if ($appName) {
                Launch-AppWithAI -AppName $appName -Interactive
            } else {
                Write-Host "Usage: .\ai_app_launcher.ps1 launch <app_name>" -ForegroundColor Red
            }
        }
        "search" {
            if ($appName) {
                $result = Invoke-AIAppLauncher -Command "search" -AppName $appName
                Write-Host "Result: $($result.Message)" -ForegroundColor $(if ($result.Success) { "Green" } else { "Red" })
            } else {
                Write-Host "Usage: .\ai_app_launcher.ps1 search <app_name>" -ForegroundColor Red
            }
        }
        "list" {
            Show-AppsList
        }
        "common" {
            Show-AppsList -TopCommonOnly
        }
        "interactive" {
            Show-InteractiveAppSelector
        }
        "dashboard" {
            Show-InteractiveAppSelector
        }
        default {
            Show-InteractiveAppSelector
        }
    }
} else {
    # Default to interactive mode
    Show-InteractiveAppSelector
} 