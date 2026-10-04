@echo off
REM Wake Word Debugger - Quick Launcher
REM Double-click this file to run the wake word debugger

echo.
echo ========================================
echo Wake Word False Positive Debugger
echo ========================================
echo.

REM Check if PowerShell script exists
if not exist "run_wake_word_debug.ps1" (
    echo ERROR: run_wake_word_debug.ps1 not found!
    echo Please make sure you're in the Aiden project directory.
    echo.
    pause
    exit /b 1
)

REM Run PowerShell script
powershell.exe -ExecutionPolicy Bypass -File "run_wake_word_debug.ps1"

REM Check exit code
if %ERRORLEVEL% neq 0 (
    echo.
    echo Debugger exited with error code %ERRORLEVEL%
    echo.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo Debugger completed successfully!
echo Check the logs/ folder for results.
echo.
pause
