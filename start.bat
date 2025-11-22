@echo off
:: Auto-elevate to Administrator
>nul 2>&1 net session
if %errorlevel% neq 0 (
    echo Requesting admin privileges...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

REM Aiden AI Assistant - Batch Launcher
REM Calls the PowerShell script to start Aiden

echo Starting Aiden AI Assistant...
powershell -ExecutionPolicy Bypass -File "%~dp0run_aiden.ps1"

if %ERRORLEVEL% neq 0 (
    echo.
    echo An error occurred. Press any key to exit...
    pause >nul
)
