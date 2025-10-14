@echo off
REM Aiden AI Assistant - Batch Launcher
REM Calls the PowerShell script to start Aiden

echo Starting Aiden AI Assistant...
powershell -ExecutionPolicy Bypass -File "%~dp0run_aiden.ps1"

REM Keep window open only if there's an error
if %ERRORLEVEL% neq 0 (
    echo.
    echo An error occurred. Press any key to exit...
    pause >nul
)
