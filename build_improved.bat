@echo off
title Aiden Build Process
echo ================================
echo   Aiden AI Assistant Builder
echo ================================
echo.
echo This will create a standalone executable for Aiden
echo.

REM Change to script directory
cd /d "%~dp0"

echo Checking Python installation...
python --version > nul 2>&1
if errorlevel 1 (
    echo ❌ Python not found! Please install Python first.
    pause
    exit /b 1
)

echo ✅ Python found
echo.

echo Starting build process...
python build_improved.py

echo.
echo Build process completed!
echo.
if exist "dist\Aiden.exe" (
    echo ✅ Success! Your executable is ready in the 'dist' folder.
    echo.
    echo To run Aiden:
    echo 1. Go to the 'dist' folder
    echo 2. Double-click 'Start_Aiden.bat'
    echo 3. Look for the AI icon in your system tray!
    echo.
    set /p choice="Would you like to open the dist folder? (y/n): "
    if /i "%choice%"=="y" explorer "dist"
) else (
    echo ❌ Build may have failed. Check output above for errors.
)

echo.
pause 