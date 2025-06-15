# Interactive App Finder Test Script (Advanced Version)
# This script provides an interactive interface to test the advanced Find-AppPath function

# Import the advanced Find-AppPath function
. .\findapp_advanced.ps1

function Show-Menu {
    Clear-Host
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "    Advanced App Finder Test Tool v2.0        " -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "🚀 Now with intelligent executable detection!" -ForegroundColor Green
    Write-Host ""
    Write-Host "Commands:" -ForegroundColor Yellow
    Write-Host "  search <app_name>  - Search for an application"
    Write-Host "  launch <app_name>  - Search and launch an application"
    Write-Host "  test               - Run predefined tests"
    Write-Host "  problem            - Test previously problematic apps"
    Write-Host "  help               - Show this menu"
    Write-Host "  exit               - Exit the tool"
    Write-Host ""
    Write-Host "Examples:" -ForegroundColor Green
    Write-Host "  search steam"
    Write-Host "  launch calculator"
    Write-Host "  search chrome"
    Write-Host "  launch notepad"
    Write-Host ""
}

function Test-PredefinedApps {
    Write-Host "Running predefined tests..." -ForegroundColor Yellow
    Write-Host ""
    
    $testApps = @(
        "Steam",
        "Calculator", 
        "Everything",
        "Chrome",
        "Firefox",
        "Notepad",
        "Visual Studio Code",
        "Discord",
        "Spotify",
        "Postman",
        "Git",
        "OBS",
        "VLC"
    )
    
    $results = @()
    
    foreach ($app in $testApps) {
        Write-Host "Testing: $app" -ForegroundColor Cyan
        Write-Host "----------------------------------------"
        
        $startTime = Get-Date
        $path = Find-AppPath -AppName $app
        $endTime = Get-Date
        $duration = ($endTime - $startTime).TotalMilliseconds
        
        $result = [PSCustomObject]@{
            AppName = $app
            Found = $path -ne $null
            Path = $path
            SearchTime = "$([math]::Round($duration, 2))ms"
        }
        
        $results += $result
        
        if ($path) {
            Write-Host "✅ FOUND" -ForegroundColor Green
            Write-Host "Path: $path" -ForegroundColor Gray
        } else {
            Write-Host "❌ NOT FOUND" -ForegroundColor Red
        }
        
        Write-Host "Search time: $($result.SearchTime)" -ForegroundColor Gray
        Write-Host ""
    }
    
    # Summary
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "                   SUMMARY                     " -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    
    $found = ($results | Where-Object { $_.Found }).Count
    $total = $results.Count
    $avgTime = [math]::Round(($results | Measure-Object -Property SearchTime -Average | Select-Object -ExpandProperty Average), 2)
    
    Write-Host "Apps found: $found/$total" -ForegroundColor $(if ($found -gt $total/2) { "Green" } else { "Yellow" })
    Write-Host "Average search time: ${avgTime}ms" -ForegroundColor Gray
    Write-Host ""
    
    # Detailed results table
    $results | Format-Table -AutoSize
    
    Write-Host "Press any key to continue..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Test-ProblematicApps {
    Write-Host "Testing previously problematic applications..." -ForegroundColor Yellow
    Write-Host "These apps used to find uninstallers instead of the actual app." -ForegroundColor Gray
    Write-Host ""
    
    $problematicApps = @(
        @{ Name = "Everything"; Expected = "everything.exe"; Issue = "Found Uninstall.exe instead" },
        @{ Name = "Steam"; Expected = "steam.exe"; Issue = "Found uninstaller" },
        @{ Name = "Calculator"; Expected = "calc.exe"; Issue = "Found wrong app" },
        @{ Name = "Chrome"; Expected = "chrome.exe"; Issue = "Found installer" }
    )
    
    $results = @()
    
    foreach ($app in $problematicApps) {
        Write-Host "🔍 Testing: $($app.Name)" -ForegroundColor Cyan
        Write-Host "   Previous issue: $($app.Issue)" -ForegroundColor Red
        Write-Host "   Expected: $($app.Expected)" -ForegroundColor Green
        Write-Host "   ----------------------------------------"
        
        $startTime = Get-Date
        $path = Find-AppPath -AppName $app.Name
        $endTime = Get-Date
        $duration = ($endTime - $startTime).TotalMilliseconds
        
        $success = $false
        $actualExe = ""
        
        if ($path) {
            $actualExe = [System.IO.Path]::GetFileName($path).ToLower()
            $expectedExe = $app.Expected.ToLower()
            
            # Check if we got the right executable
            if ($actualExe -eq $expectedExe -or $actualExe.Contains($expectedExe.Replace('.exe', ''))) {
                $success = $true
                Write-Host "   ✅ SUCCESS: Found correct executable!" -ForegroundColor Green
            } else {
                Write-Host "   ⚠️  PARTIAL: Found different executable: $actualExe" -ForegroundColor Yellow
            }
        } else {
            Write-Host "   ❌ FAILED: No executable found" -ForegroundColor Red
        }
        
        $result = [PSCustomObject]@{
            AppName = $app.Name
            Expected = $app.Expected
            Found = $actualExe
            Success = $success
            Path = $path
            SearchTime = "$([math]::Round($duration, 2))ms"
        }
        
        $results += $result
        Write-Host "   Search time: $($result.SearchTime)" -ForegroundColor Gray
        Write-Host ""
    }
    
    # Summary
    Write-Host "===============================================" -ForegroundColor Cyan
    Write-Host "            PROBLEMATIC APPS SUMMARY           " -ForegroundColor Cyan
    Write-Host "===============================================" -ForegroundColor Cyan
    
    $successful = ($results | Where-Object { $_.Success }).Count
    $total = $results.Count
    
    Write-Host "Successfully fixed: $successful/$total" -ForegroundColor $(if ($successful -eq $total) { "Green" } elseif ($successful -gt 0) { "Yellow" } else { "Red" })
    Write-Host ""
    
    # Detailed results
    $results | Format-Table AppName, Expected, Found, Success, SearchTime -AutoSize
    
    Write-Host "Press any key to continue..." -ForegroundColor Yellow
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
}

function Search-App {
    param([string]$AppName)
    
    if ([string]::IsNullOrWhiteSpace($AppName)) {
        Write-Host "Please provide an app name to search for." -ForegroundColor Red
        return
    }
    
    Write-Host "Searching for: $AppName" -ForegroundColor Cyan
    Write-Host "=========================================="
    
    $startTime = Get-Date
    $path = Find-AppPath -AppName $AppName
    $endTime = Get-Date
    $duration = ($endTime - $startTime).TotalMilliseconds
    
    Write-Host ""
    if ($path) {
        Write-Host "✅ APPLICATION FOUND!" -ForegroundColor Green
        Write-Host "Path: $path" -ForegroundColor White
        Write-Host "Search completed in: $([math]::Round($duration, 2))ms" -ForegroundColor Gray
        
        # Check if it's a UWP app or regular executable
        if ($path -like "*shell:appsFolder*") {
            Write-Host "Type: Microsoft Store (UWP) App" -ForegroundColor Magenta
        } elseif ($path -like "*steamapps*") {
            Write-Host "Type: Steam Game" -ForegroundColor Cyan
        } else {
            Write-Host "Type: Standard Application" -ForegroundColor Green
        }
    } else {
        Write-Host "❌ APPLICATION NOT FOUND" -ForegroundColor Red
        Write-Host "Search completed in: $([math]::Round($duration, 2))ms" -ForegroundColor Gray
        Write-Host ""
        Write-Host "Suggestions:" -ForegroundColor Yellow
        Write-Host "- Try a shorter or partial name"
        Write-Host "- Check if the application is actually installed"
        Write-Host "- Try searching for the publisher name"
    }
    Write-Host ""
}

function Launch-App {
    param([string]$AppName)
    
    if ([string]::IsNullOrWhiteSpace($AppName)) {
        Write-Host "Please provide an app name to launch." -ForegroundColor Red
        return
    }
    
    Write-Host "Searching and launching: $AppName" -ForegroundColor Cyan
    Write-Host "=========================================="
    
    $path = Find-AppPath -AppName $AppName
    
    if ($path) {
        Write-Host "✅ Found application!" -ForegroundColor Green
        Write-Host "Path: $path" -ForegroundColor White
        Write-Host ""
        Write-Host "Launching application..." -ForegroundColor Yellow
        
        try {
            if ($path -like "*shell:appsFolder*") {
                # UWP app - use the shell command
                Start-Process -FilePath "explorer.exe" -ArgumentList $path.Replace("explorer.exe ", "")
            } else {
                # Regular executable
                Start-Process -FilePath $path
            }
            Write-Host "✅ Application launched successfully!" -ForegroundColor Green
        }
        catch {
            Write-Host "❌ Failed to launch application: $($_.Exception.Message)" -ForegroundColor Red
        }
    } else {
        Write-Host "❌ Could not find application: $AppName" -ForegroundColor Red
    }
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
                Search-App -AppName $argument
            }
            "launch" {
                Launch-App -AppName $argument
            }
            "test" {
                Test-PredefinedApps
                Show-Menu
            }
            "problem" {
                Test-ProblematicApps
                Show-Menu
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
                Write-Host ""
            }
        }
    }
}

# Check if Find-AppPath function is available
if (Get-Command Find-AppPath -ErrorAction SilentlyContinue) {
    Write-Host "✅ Advanced Find-AppPath function loaded successfully!" -ForegroundColor Green
    Write-Host "🔧 Features: Intelligent executable detection, installer filtering, scoring system" -ForegroundColor Cyan
    Write-Host ""
    Start-InteractiveMode
} else {
    Write-Host "❌ Error: Find-AppPath function not found!" -ForegroundColor Red
    Write-Host "Make sure findapp_advanced.ps1 is in the same directory and contains the Find-AppPath function." -ForegroundColor Yellow
} 