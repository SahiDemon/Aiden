function Find-AppPath {
    param(
        [string]$AppName
    )

    # --- 1. Search for Standard Installed Applications (from Registry) ---
    Write-Host "Searching for standard applications..."
    $uninstallKeys = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    )

    foreach ($key in $uninstallKeys) {
        $apps = Get-ItemProperty -Path "$key\*" -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -like "*$AppName*" -and $_.InstallLocation }
        if ($apps) {
            foreach($app in $apps) {
                # Try to find the most likely executable
                $exePath = Get-ChildItem -Path $app.InstallLocation -Recurse -Filter "*.exe" | Sort-Object -Property LastWriteTime -Descending | Select-Object -First 1
                if ($exePath) {
                    Write-Host "[FOUND] Standard App: $($app.DisplayName)" -ForegroundColor Green
                    Write-Host "Path: $($exePath.FullName)"
                    return $exePath.FullName
                }
            }
        }
    }

    # --- 2. Search for Steam Games ---
    Write-Host "Searching for Steam games..."
    $steamPath = (Get-ItemProperty -Path "HKCU:\Software\Valve\Steam" -ErrorAction SilentlyContinue).SteamPath
    if ($steamPath) {
        $libraryFoldersFile = Join-Path -Path $steamPath -ChildPath "steamapps/libraryfolders.vdf"
        if (Test-Path $libraryFoldersFile) {
            $libraryPaths = @($steamPath) + (Get-Content $libraryFoldersFile | Select-String -Pattern '"path"' | ForEach-Object { $_.Line.Split('"')[3].Replace('\\', '\') })

            foreach ($library in $libraryPaths) {
                $steamAppsPath = Join-Path -Path $library -ChildPath "steamapps/common"
                $gameManifests = Get-ChildItem -Path (Join-Path -Path $library -ChildPath "steamapps") -Filter "appmanifest_*.acf"
                
                foreach ($manifest in $gameManifests) {
                    $manifestContent = Get-Content $manifest.FullName
                    $gameNameLine = $manifestContent | Select-String -Pattern '"name"'
                    $installDirLine = $manifestContent | Select-String -Pattern '"installdir"'

                    if ($gameNameLine -and $installDirLine) {
                        $gameName = $gameNameLine.Line.Split('"')[3]
                        if ($gameName -like "*$AppName*") {
                            $installDir = $installDirLine.Line.Split('"')[3]
                            $gamePath = Join-Path -Path $steamAppsPath -ChildPath $installDir
                            $gameExe = Get-ChildItem -Path $gamePath -Recurse -Filter "*.exe" | Sort-Object -Property LastWriteTime -Descending | Select-Object -First 1
                            
                            if ($gameExe) {
                                Write-Host "[FOUND] Steam Game: $gameName" -ForegroundColor Cyan
                                Write-Host "Path: $($gameExe.FullName)"
                                return $gameExe.FullName
                            }
                        }
                    }
                }
            }
        }
    } else {
        Write-Host "Steam installation not found in registry." -ForegroundColor Yellow
    }
    
    # --- 3. Search for Microsoft Store (UWP) Apps ---
    Write-Host "Searching for Microsoft Store apps..."
    $uwpApp = Get-AppxPackage | Where-Object { $_.Name -like "*$AppName*" -or $_.PackageFamilyName -like "*$AppName*" } | Select-Object -First 1
    if ($uwpApp) {
        Write-Host "[FOUND] Microsoft Store App: $($uwpApp.Name)" -ForegroundColor Magenta
        # For UWP apps, you open them with a special shell command, not a direct path
        $shellCommand = "explorer.exe shell:appsFolder\$($uwpApp.PackageFamilyName)!App"
        Write-Host "Open Command: $shellCommand"
        return $shellCommand
    }


    Write-Host "[NOT FOUND] Could not find an executable path for '$AppName'." -ForegroundColor Red
    return $null
}