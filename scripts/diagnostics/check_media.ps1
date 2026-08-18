# Aiden Live Media Playback Detection Inspector
# Run this script to see all audio devices, playing media apps, browser tabs, and Jellyfin sessions.

$pythonPath = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $pythonPath)) {
    $pythonPath = "python"
}

& $pythonPath "src/utils/check_media_status.py"
