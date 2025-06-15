param(
    [string]$AppName
)

Write-Host "Test script called with: $AppName"
Write-Host "Args count: $($args.Count)"
Write-Host "All args: $args"

if ($AppName -eq "discord") {
    Write-Host "Discord found at: C:\Users\gsahi\AppData\Local\Discord\app-1.0.9195\Discord.exe"
    Write-Host "Application launched successfully!"
} else {
    Write-Host "App not found: $AppName"
}

# Exit explicitly
exit 0
