# Unified App Finder & Launcher
# Combines the best features from findapp.ps1 and findapp_advanced.ps1

function Find-AppPath {
    param(
        [string]$AppName
    )

    # Helper function to check if an executable is unwanted (installer, uninstaller, etc.)
    function Test-IsUnwantedExecutable {
        param([string]$ExePath)
        
        $fileName = [System.IO.Path]::GetFileNameWithoutExtension($ExePath).ToLower()
        $unwantedPatterns = @(
            'uninstall', 'unins', 'uninst', 'remove', 'cleanup',
            'installer', 'install', 'setup', 'updater', 'update',
            'launcher', 'bootstrapper', 'downloader', 'helper',
            'crash', 'error', 'report', 'feedback', 'diagnostic'
        )
        
        foreach ($pattern in $unwantedPatterns) {
            if ($fileName -like "*$pattern*") {
                return $true
            }
        }
        return $false
    }
    
    # Helper function to find the best executable in a directory (fast approach)
    function Get-BestExecutable {
        param(
            [string]$InstallPath,
            [string]$AppName
        )
        
        if (-not (Test-Path $InstallPath)) {
            return $null
        }
        
        # Get all executables, sorted by last write time (most recent first)
        $allExes = Get-ChildItem -Path $InstallPath -Recurse -Filter "*.exe" -ErrorAction SilentlyContinue | 
                   Where-Object { -not (Test-IsUnwantedExecutable $_.FullName) } |
                   Sort-Object -Property LastWriteTime -Descending
        
        if (-not $allExes) {
            return $null
        }
        
        # Quick check for exact name match first
        $appNameClean = $AppName.ToLower() -replace '[^a-z0-9]', ''
        $exactMatch = $allExes | Where-Object { 
            [System.IO.Path]::GetFileNameWithoutExtension($_.Name).ToLower() -eq $appNameClean 
        } | Select-Object -First 1
        
        if ($exactMatch) {
            return $exactMatch.FullName
        }
        
        # Look for name containing the app name
        $partialMatch = $allExes | Where-Object { 
            [System.IO.Path]::GetFileNameWithoutExtension($_.Name).ToLower() -like "*$appNameClean*" 
        } | Select-Object -First 1
        
        if ($partialMatch) {
            return $partialMatch.FullName
        }
        
        # Return the most recent executable as fallback
        return $allExes[0].FullName
    }
    
    # Helper function for common system applications
    function Get-CommonAppExecutable {
        param([string]$AppName)
        
        $commonApps = @{
            'calculator' = 'calc.exe'
            'calc' = 'calc.exe'
            'notepad' = 'notepad.exe'
            'paint' = 'mspaint.exe'
            'explorer' = 'explorer.exe'
            'cmd' = 'cmd.exe'
            'powershell' = 'powershell.exe'
            'chrome' = 'chrome.exe'
            'firefox' = 'firefox.exe'
            'edge' = 'msedge.exe'
            'steam' = 'steam.exe'
            'discord' = 'discord.exe'
            'spotify' = 'spotify.exe'
            'code' = 'code.exe'
            'vscode' = 'code.exe'
            'visualstudiocode' = 'code.exe'
            'git' = 'git.exe'
            'everything' = 'everything.exe'
            'vlc' = 'vlc.exe'
        }
        
        $appKey = $AppName.ToLower() -replace '[^a-z0-9]', ''
        
        # Handle special cases for common app variations
        if ($appKey -like "*vscode*" -or $appKey -like "*visualstudio*" -or $appKey -eq "code") {
            $appKey = "code"
        }
        if ($appKey -like "*spotify*") {
            $appKey = "spotify"
        }
        if ($appKey -eq "steam") {
            $appKey = "steam"
        }
        
        if ($commonApps.ContainsKey($appKey)) {
            $exeName = $commonApps[$appKey]
            
            # Try to find it in PATH first
            $pathExe = Get-Command $exeName -ErrorAction SilentlyContinue
            if ($pathExe) {
                return $pathExe.Source
            }
            
            # Try specific known locations first (fastest)
            $specificPaths = @()
            
            if ($exeName -eq "code.exe") {
                $specificPaths = @(
                    "$env:LOCALAPPDATA\Programs\Microsoft VS Code\Code.exe",
                    "$env:ProgramFiles\Microsoft VS Code\Code.exe",
                    "$env:ProgramFiles(x86)\Microsoft VS Code\Code.exe"
                )
            }
                         elseif ($exeName -eq "spotify.exe") {
                $specificPaths = @(
                    "$env:APPDATA\Spotify\Spotify.exe",
                    "$env:LOCALAPPDATA\Microsoft\WindowsApps\Spotify.exe"
                )
            }
            elseif ($exeName -eq "steam.exe") {
                $specificPaths = @(
                    "$env:ProgramFiles(x86)\Steam\steam.exe",
                    "$env:ProgramFiles\Steam\steam.exe"
                )
            }
            
            # Check specific paths first
            foreach ($specificPath in $specificPaths) {
                if (Test-Path $specificPath) {
                    return $specificPath
                }
            }
            
            # Try common installation locations (slower fallback)
            $commonPaths = @(
                "$env:ProgramFiles\*\$exeName",
                "$env:ProgramFiles(x86)\*\$exeName",
                "$env:LOCALAPPDATA\*\$exeName",
                "$env:APPDATA\*\$exeName",
                "$env:LOCALAPPDATA\Programs\*\$exeName"
            )
            
            foreach ($path in $commonPaths) {
                $found = Get-ChildItem -Path $path -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
                if ($found) {
                    return $found.FullName
                }
            }
        }
        
        return $null
    }

    # Main search logic starts here
    Write-Host "Searching for: $AppName" -ForegroundColor Cyan
    
    # 1. Check common system applications first (FAST)
    $commonApp = Get-CommonAppExecutable -AppName $AppName
    if ($commonApp) {
        Write-Host "[FOUND] System App: $AppName" -ForegroundColor Green
        Write-Host "Path: $commonApp"
        return $commonApp
    }
    
    # 2. Quick PATH search for common executables
    $quickExe = Get-Command "$AppName.exe" -ErrorAction SilentlyContinue
    if ($quickExe) {
        Write-Host "[FOUND] PATH App: $AppName" -ForegroundColor Green
        Write-Host "Path: $($quickExe.Source)"
        return $quickExe.Source
    }

    # 3. Search Steam games FIRST (before registry to catch Steam games properly)
    # Skip Steam games search if looking for Steam application itself
    if ($AppName.ToLower() -ne "steam") {
    try {
        $steamPath = (Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
        if ($steamPath) {
            $libraryFoldersFile = Join-Path -Path $steamPath -ChildPath "steamapps/libraryfolders.vdf"
            if (Test-Path $libraryFoldersFile) {
                $libraryPaths = @($steamPath) + (Get-Content $libraryFoldersFile | Select-String -Pattern '"path"' | ForEach-Object { $_.Line.Split('"')[3].Replace('\\', '\') })

                foreach ($library in $libraryPaths) {
                    $steamAppsPath = Join-Path -Path $library -ChildPath "steamapps/common"
                    if (Test-Path $steamAppsPath) {
                        $gameManifests = Get-ChildItem -Path (Join-Path -Path $library -ChildPath "steamapps") -Filter "appmanifest_*.acf" -ErrorAction SilentlyContinue
                        
                        foreach ($manifest in $gameManifests) {
                            try {
                                $manifestContent = Get-Content $manifest.FullName
                                $gameNameLine = $manifestContent | Select-String -Pattern '"name"'
                                $installDirLine = $manifestContent | Select-String -Pattern '"installdir"'

                                if ($gameNameLine -and $installDirLine) {
                                    $gameName = $gameNameLine.Line.Split('"')[3]
                                    if ($gameName -like "*$AppName*") {
                                        # Extract Steam App ID from manifest filename
                                        $steamAppId = [System.IO.Path]::GetFileNameWithoutExtension($manifest.Name).Replace("appmanifest_", "")
                                        
                                        $installDir = $installDirLine.Line.Split('"')[3]
                                        $gamePath = Join-Path -Path $steamAppsPath -ChildPath $installDir
                                        $gameExe = Get-BestExecutable -InstallPath $gamePath -AppName $AppName
                                        
                                        if ($gameExe) {
                                            # Return Steam launch URL instead of direct exe path
                                            $steamLaunchUrl = "steam://launch/$steamAppId"
                                            Write-Host "[FOUND] Steam Game: $gameName" -ForegroundColor Cyan
                                            Write-Host "Steam ID: $steamAppId"
                                            Write-Host "Launch URL: $steamLaunchUrl"
                                            Write-Host "Game Path: $gameExe"
                                            return $steamLaunchUrl
                                        }
                                    }
                                }
                            }
                            catch {
                                continue
                            }
                        }
                    }
                }
            }
        }
    }
    catch {
        # Skip Steam search if there are issues
    }
    } # End of Steam games search skip

    # 4. Search Windows Registry for installed applications (with timeout)
    $registryStartTime = Get-Date
    $registryTimeout = 3000 # 3 seconds max
    
    $uninstallKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    )

    foreach ($key in $uninstallKeys) {
        # Check timeout
        if (((Get-Date) - $registryStartTime).TotalMilliseconds -gt $registryTimeout) {
            Write-Host "Registry search timeout, skipping remaining keys..." -ForegroundColor Yellow
            break
        }
        
        try {
            $apps = Get-ItemProperty -Path "$key\*" -ErrorAction SilentlyContinue | 
                    Where-Object { 
                        $_.DisplayName -like "*$AppName*" -and 
                        $_.InstallLocation -and
                        -not ($_.DisplayName -like "*uninstall*") -and
                        -not ($_.DisplayName -like "*remove*") -and
                        -not ($_.DisplayName -like "*setup*")
                    } | Select-Object -First 5  # Limit to first 5 matches for speed
            
            if ($apps) {
                foreach($app in $apps) {
                    $bestExe = Get-BestExecutable -InstallPath $app.InstallLocation -AppName $AppName
                    if ($bestExe) {
                        Write-Host "[FOUND] Standard App: $($app.DisplayName)" -ForegroundColor Green
                        Write-Host "Path: $bestExe"
                        return $bestExe
                    }
                }
            }
        }
        catch {
            # Skip problematic registry keys
            continue
        }
    }
    
    # 5. Search Microsoft Store (UWP) applications
    try {
        $uwpApp = Get-AppxPackage | Where-Object { 
            $_.Name -like "*$AppName*" -or 
            $_.PackageFamilyName -like "*$AppName*" -or
            $_.DisplayName -like "*$AppName*"
        } | Select-Object -First 1
        
        if ($uwpApp) {
            $shellCommand = "explorer.exe shell:appsFolder\$($uwpApp.PackageFamilyName)!App"
            $displayName = if ($uwpApp.DisplayName) { $uwpApp.DisplayName } else { $uwpApp.Name }
            Write-Host "[FOUND] Microsoft Store App: $displayName" -ForegroundColor Magenta
            Write-Host "Command: $shellCommand"
            return $shellCommand
        }
    }
    catch {
        # Skip UWP search if there are issues
    }

    Write-Host "[NOT FOUND] Could not find an executable for '$AppName'." -ForegroundColor Red
    return $null
}

function Search-App {
    param([string]$AppName)
    
    if ([string]::IsNullOrWhiteSpace($AppName)) {
        Write-Host "Please provide an app name to search for." -ForegroundColor Red
        return
    }
    
    # Trim whitespace to avoid issues
    $AppName = $AppName.Trim()
    
    Write-Host "=========================================="
    $startTime = Get-Date
    $path = Find-AppPath -AppName $AppName
    $endTime = Get-Date
    $duration = ($endTime - $startTime).TotalMilliseconds
    
    Write-Host ""
    if ($path) {
        Write-Host "APPLICATION FOUND!" -ForegroundColor Green
        Write-Host "Search completed in: $([math]::Round($duration, 2))ms" -ForegroundColor Gray
        
        # Determine application type
        if ($path -like "*shell:appsFolder*") {
            Write-Host "Type: Microsoft Store (UWP) App" -ForegroundColor Magenta
        } elseif ($path -like "steam://launch/*") {
            Write-Host "Type: Steam Game (via Steam Protocol)" -ForegroundColor Cyan
        } elseif ($path -like "*steamapps*") {
            Write-Host "Type: Steam Game (Direct)" -ForegroundColor Cyan
        } else {
            Write-Host "Type: Standard Application" -ForegroundColor Green
        }
    } else {
        Write-Host "APPLICATION NOT FOUND" -ForegroundColor Red
        Write-Host "Search completed in: $([math]::Round($duration, 2))ms" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Suggestions:" -ForegroundColor Yellow
        Write-Host "   - Try a shorter or partial name (e.g., 'chrome' instead of 'Google Chrome')"
        Write-Host "   - Check if the application is actually installed"
        Write-Host "   - Try searching for the publisher name"
    }
    Write-Host ""
}

function Launch-App {
    param([string]$AppName)
    
    if ([string]::IsNullOrWhiteSpace($AppName)) {
        Write-Host "Please provide an app name to launch." -ForegroundColor Red
        return
    }
    
    # Trim whitespace to avoid issues
    $AppName = $AppName.Trim()
    
    Write-Host "Searching and launching: $AppName" -ForegroundColor Cyan
    Write-Host "=========================================="
    
    $path = Find-AppPath -AppName $AppName
    
    if ($path) {
        Write-Host ""
        Write-Host "Launching application..." -ForegroundColor Yellow
        
        try {
            if ($path -like "*shell:appsFolder*") {
                # UWP app - use the shell command
                Start-Process -FilePath "explorer.exe" -ArgumentList $path.Replace("explorer.exe ", "")
                Write-Host "UWP application launched successfully!" -ForegroundColor Green
            } elseif ($path -like "steam://launch/*") {
                # Steam game - use Steam protocol
                Start-Process -FilePath $path
                Write-Host "Steam game launched successfully!" -ForegroundColor Green
            } else {
                # Regular executable
                Start-Process -FilePath $path
                Write-Host "Application launched successfully!" -ForegroundColor Green
            }
        }
        catch {
            Write-Host "Failed to launch application: $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "Could not find application: $AppName" -ForegroundColor Red
    }
    Write-Host ""
}

function Show-Menu {
    Clear-Host
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "           APP FINDER & LAUNCHER           " -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Yellow
    Write-Host "  search <app_name>  - Search for an application" -ForegroundColor White
    Write-Host "  launch <app_name>  - Search and launch an application" -ForegroundColor White
    Write-Host "  help              - Show this menu" -ForegroundColor White
    Write-Host "  clear             - Clear screen and show menu" -ForegroundColor White
    Write-Host "  exit              - Exit the program" -ForegroundColor White
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Green
    Write-Host "  search chrome" -ForegroundColor Gray
    Write-Host "  launch steam" -ForegroundColor Gray
    Write-Host "  search calculator" -ForegroundColor Gray
    Write-Host ""
}

function Start-InteractiveMode {
    Show-Menu
    
    while ($true) {
        Write-Host "Enter command: " -ForegroundColor Yellow -NoNewline
        $input = Read-Host
        
        if ([string]::IsNullOrWhiteSpace($input)) {
            continue
        }
        
        $parts = $input.Split(' ', 2)
        $command = $parts[0].ToLower()
        $argument = if ($parts.Length -gt 1) { $parts[1] } else { "" }
        
        switch ($command) {
            "search" {
                if ([string]::IsNullOrWhiteSpace($argument)) {
                    Write-Host "Usage: search <app_name>" -ForegroundColor Red
                } else {
                    Search-App -AppName $argument
                }
            }
            "launch" {
                if ([string]::IsNullOrWhiteSpace($argument)) {
                    Write-Host "Usage: launch <app_name>" -ForegroundColor Red
                } else {
                    Launch-App -AppName $argument
                }
            }
            "help" {
                Show-Menu
            }
            "exit" {
                Write-Host "Goodbye!" -ForegroundColor Green
                return
            }
            "clear" {
                Show-Menu
            }
            default {
                Write-Host "Unknown command: $command" -ForegroundColor Red
                Write-Host "Type 'help' to see available commands." -ForegroundColor Yellow
            }
        }
    }
}

# Main execution logic
if ($args.Count -gt 0) {
    $command = $args[0].ToLower()
    $appName = if ($args.Count -gt 1) { $args[1..($args.Count-1)] -join ' ' } else { "" }
    
    switch ($command) {
        "search" {
            if ([string]::IsNullOrWhiteSpace($appName)) {
                Write-Host "Usage: .\app_finder.ps1 search <app_name>" -ForegroundColor Red
            } else {
                Search-App -AppName $appName
            }
        }
        "launch" {
            if ([string]::IsNullOrWhiteSpace($appName)) {
                Write-Host "Usage: .\app_finder.ps1 launch <app_name>" -ForegroundColor Red
            } else {
                Launch-App -AppName $appName
            }
        }
        default {
            Write-Host "Unknown command: $command" -ForegroundColor Red
            Write-Host "Available commands: search, launch" -ForegroundColor Yellow
            Write-Host "Usage: .\app_finder.ps1 <command> <app_name>" -ForegroundColor Yellow
        }
    }
} else {
    # Start interactive mode if no arguments provided
    Start-InteractiveMode
} 