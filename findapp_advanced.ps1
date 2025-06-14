function Find-AppPath {
    param(
        [string]$AppName
    )

    # --- Helper Functions ---
    
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
    
    function Get-BestExecutable {
        param(
            [string]$InstallPath,
            [string]$AppName
        )
        
        if (-not (Test-Path $InstallPath)) {
            return $null
        }
        
        Write-Host "  Analyzing executables in: $InstallPath" -ForegroundColor Gray
        
        # Get all executables in the install directory and subdirectories
        $allExes = Get-ChildItem -Path $InstallPath -Recurse -Filter "*.exe" -ErrorAction SilentlyContinue
        
        if (-not $allExes) {
            Write-Host "  No executables found" -ForegroundColor Yellow
            return $null
        }
        
        Write-Host "  Found $($allExes.Count) executables, filtering..." -ForegroundColor Gray
        
        # Filter out unwanted executables
        $goodExes = $allExes | Where-Object { -not (Test-IsUnwantedExecutable $_.FullName) }
        
        if (-not $goodExes) {
            Write-Host "  Warning: Only installer/uninstaller executables found" -ForegroundColor Yellow
            return $null
        }
        
        Write-Host "  $($goodExes.Count) valid executables after filtering" -ForegroundColor Gray
        
        # Scoring system to find the best executable
        $scoredExes = @()
        
        foreach ($exe in $goodExes) {
            $score = 0
            $fileName = [System.IO.Path]::GetFileNameWithoutExtension($exe.Name).ToLower()
            $appNameClean = $AppName.ToLower() -replace '[^a-z0-9]', ''
            
            # Exact name match (highest priority)
            if ($fileName -eq $appNameClean) {
                $score += 100
            }
            
            # App name is in filename
            if ($fileName -like "*$appNameClean*") {
                $score += 80
            }
            
            # Filename starts with app name
            if ($fileName.StartsWith($appNameClean)) {
                $score += 70
            }
            
            # Common main executable patterns
            $mainExePatterns = @('main', 'app', 'client', 'gui', 'ui')
            foreach ($pattern in $mainExePatterns) {
                if ($fileName -like "*$pattern*") {
                    $score += 30
                }
            }
            
            # Prefer executables in root directory over subdirectories
            $relativePath = $exe.FullName.Substring($InstallPath.Length)
            $depth = ($relativePath.Split('\').Length - 2)
            if ($depth -eq 0) {
                $score += 20
            } elseif ($depth -eq 1) {
                $score += 10
            }
            
            # Prefer larger files (main executables are usually larger)
            if ($exe.Length -gt 1MB) {
                $score += 15
            } elseif ($exe.Length -gt 100KB) {
                $score += 10
            }
            
            # Prefer newer files
            $daysSinceModified = (Get-Date) - $exe.LastWriteTime
            if ($daysSinceModified.Days -lt 30) {
                $score += 5
            }
            
            $scoredExes += [PSCustomObject]@{
                Path = $exe.FullName
                Name = $exe.Name
                Score = $score
                Size = $exe.Length
                LastModified = $exe.LastWriteTime
            }
        }
        
        # Show top candidates
        $topCandidates = $scoredExes | Sort-Object Score -Descending | Select-Object -First 3
        Write-Host "  Top candidates:" -ForegroundColor Gray
        foreach ($candidate in $topCandidates) {
            Write-Host "    $($candidate.Name) (Score: $($candidate.Score))" -ForegroundColor Gray
        }
        
        # Return the highest scoring executable
        $bestExe = $scoredExes | Sort-Object Score -Descending | Select-Object -First 1
        
        if ($bestExe) {
            Write-Host "  Selected: $($bestExe.Name) (Score: $($bestExe.Score))" -ForegroundColor Green
            return $bestExe.Path
        }
        
        return $null
    }
    
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
            'git' = 'git.exe'
            'everything' = 'everything.exe'
        }
        
        $appKey = $AppName.ToLower() -replace '[^a-z0-9]', ''
        
        if ($commonApps.ContainsKey($appKey)) {
            $exeName = $commonApps[$appKey]
            
            # Try to find it in PATH
            $pathExe = Get-Command $exeName -ErrorAction SilentlyContinue
            if ($pathExe) {
                return $pathExe.Source
            }
            
            # Try common locations
            $commonPaths = @(
                "$env:ProgramFiles\*\$exeName",
                "$env:ProgramFiles(x86)\*\$exeName",
                "$env:LOCALAPPDATA\*\$exeName",
                "$env:APPDATA\*\$exeName"
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

    # --- Main Search Logic ---
    
    Write-Host "🔍 Advanced Search for: $AppName" -ForegroundColor Cyan
    Write-Host "============================================"
    
    # First, try common system apps
    Write-Host "1. Checking common system applications..." -ForegroundColor Yellow
    $commonApp = Get-CommonAppExecutable -AppName $AppName
    if ($commonApp) {
        Write-Host "[FOUND] System App: $AppName" -ForegroundColor Green
        Write-Host "Path: $commonApp"
        return $commonApp
    }

    # --- 2. Search for Standard Installed Applications (from Registry) ---
    Write-Host "2. Searching for standard applications..." -ForegroundColor Yellow
    $uninstallKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    )

    $foundApps = @()
    
    foreach ($key in $uninstallKeys) {
        try {
            $apps = Get-ItemProperty -Path "$key\*" -ErrorAction SilentlyContinue | 
                    Where-Object { 
                        $_.DisplayName -like "*$AppName*" -and 
                        $_.InstallLocation -and
                        -not ($_.DisplayName -like "*uninstall*") -and
                        -not ($_.DisplayName -like "*remove*") -and
                        -not ($_.DisplayName -like "*setup*")
                    }
            
            if ($apps) {
                foreach($app in $apps) {
                    Write-Host "  Found registry entry: $($app.DisplayName)" -ForegroundColor Gray
                    $bestExe = Get-BestExecutable -InstallPath $app.InstallLocation -AppName $AppName
                    if ($bestExe) {
                        $foundApps += [PSCustomObject]@{
                            Name = $app.DisplayName
                            Path = $bestExe
                            InstallLocation = $app.InstallLocation
                            Type = "Standard"
                            Score = 100
                        }
                    }
                }
            }
        }
        catch {
            Write-Host "  Warning: Could not access registry key $key" -ForegroundColor Yellow
        }
    }

    # --- 3. Search for Steam Games ---
    Write-Host "3. Searching for Steam games..." -ForegroundColor Yellow
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
                                        $installDir = $installDirLine.Line.Split('"')[3]
                                        $gamePath = Join-Path -Path $steamAppsPath -ChildPath $installDir
                                        $gameExe = Get-BestExecutable -InstallPath $gamePath -AppName $AppName
                                        
                                        if ($gameExe) {
                                            $foundApps += [PSCustomObject]@{
                                                Name = $gameName
                                                Path = $gameExe
                                                InstallLocation = $gamePath
                                                Type = "Steam Game"
                                                Score = 90
                                            }
                                        }
                                    }
                                }
                            }
                            catch {
                                # Skip problematic manifest files
                                continue
                            }
                        }
                    }
                }
            }
        } else {
            Write-Host "  Steam not found" -ForegroundColor Gray
        }
    }
    catch {
        Write-Host "  Warning: Could not search Steam games" -ForegroundColor Yellow
    }
    
    # --- 4. Search for Microsoft Store (UWP) Apps ---
    Write-Host "4. Searching for Microsoft Store apps..." -ForegroundColor Yellow
    try {
        $uwpApp = Get-AppxPackage | Where-Object { 
            $_.Name -like "*$AppName*" -or 
            $_.PackageFamilyName -like "*$AppName*" -or
            $_.DisplayName -like "*$AppName*"
        } | Select-Object -First 1
        
        if ($uwpApp) {
            $shellCommand = "explorer.exe shell:appsFolder\$($uwpApp.PackageFamilyName)!App"
            $foundApps += [PSCustomObject]@{
                Name = if ($uwpApp.DisplayName) { $uwpApp.DisplayName } else { $uwpApp.Name }
                Path = $shellCommand
                InstallLocation = "Microsoft Store"
                Type = "UWP App"
                Score = 80
            }
        } else {
            Write-Host "  No UWP apps found" -ForegroundColor Gray
        }
    }
    catch {
        Write-Host "  Warning: Could not search Microsoft Store apps" -ForegroundColor Yellow
    }

    # --- 5. Return Results ---
    if ($foundApps.Count -eq 0) {
        Write-Host ""
        Write-Host "[NOT FOUND] ❌ Could not find an executable for '$AppName'." -ForegroundColor Red
        Write-Host ""
        Write-Host "💡 Suggestions:" -ForegroundColor Yellow
        Write-Host "   • Try a shorter or partial name (e.g., 'chrome' instead of 'Google Chrome')"
        Write-Host "   • Check if the application is actually installed"
        Write-Host "   • Try searching for the publisher name"
        Write-Host "   • Make sure the app isn't a portable/standalone version"
        return $null
    }
    
    # Sort by score and type preference
    $sortedApps = $foundApps | Sort-Object Score -Descending
    
    # If multiple apps found, show options and pick the best one
    if ($foundApps.Count -gt 1) {
        Write-Host ""
        Write-Host "📋 Multiple applications found:" -ForegroundColor Yellow
        for ($i = 0; $i -lt [Math]::Min($foundApps.Count, 5); $i++) {
            $app = $sortedApps[$i]
            Write-Host "   $($i + 1). $($app.Name) [$($app.Type)]" -ForegroundColor Gray
        }
        Write-Host "   Selecting the best match..." -ForegroundColor Yellow
    }
    
    $selectedApp = $sortedApps[0]
    Write-Host ""
    Write-Host "[FOUND] ✅ $($selectedApp.Type): $($selectedApp.Name)" -ForegroundColor Green
    Write-Host "Path: $($selectedApp.Path)" -ForegroundColor White
    Write-Host ""
    
    return $selectedApp.Path
}