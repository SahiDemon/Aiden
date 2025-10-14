# Stop Aiden AI Assistant
# Gracefully stop all Aiden processes

Write-Host "Stopping Aiden AI Assistant..." -ForegroundColor Yellow

# Find and kill Aiden processes
$processes = Get-Process | Where-Object { $_.Path -like "*aiden*" -or $_.CommandLine -like "*src\main.py*" }

if ($processes.Count -eq 0) {
    Write-Host "No Aiden processes found running" -ForegroundColor Green
} else {
    foreach ($proc in $processes) {
        Write-Host "Stopping process: $($proc.Name) (PID: $($proc.Id))" -ForegroundColor Yellow
        Stop-Process -Id $proc.Id -Force
    }
    Write-Host "✓ Aiden stopped" -ForegroundColor Green
}

