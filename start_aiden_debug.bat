@echo off
echo 🔍 Debugging Aiden Startup...
cd /d "G:\GitHub\Aiden"
echo ✅ Changed to directory: %CD%

rem Check if virtual environment exists
if exist ".venv\Scripts\activate.bat" (
    echo ✅ Virtual environment found
) else (
    echo ❌ Virtual environment not found at .venv\Scripts\activate.bat
    pause
    exit /b 1
)

rem Activate virtual environment
echo 🔄 Activating virtual environment...
call .venv\Scripts\activate.bat

rem Check if activation was successful
if %ERRORLEVEL% neq 0 (
    echo ❌ Failed to activate virtual environment
    pause
    exit /b 1
)

echo ✅ Virtual environment activated

rem Check Python version and location
echo 🐍 Python information:
python --version
where python

rem Check if required packages are available
echo 📦 Checking dependencies...
python -c "import vosk; print('✅ Vosk available')" 2>nul || echo "❌ Vosk not available"
python -c "import pyaudio; print('✅ PyAudio available')" 2>nul || echo "❌ PyAudio not available"
python -c "import pygame; print('✅ Pygame available')" 2>nul || echo "❌ Pygame not available"

rem Run Aiden
echo 🚀 Starting Aiden...
python aiden_tray.py

echo 🏁 Aiden has stopped
pause 