@echo off
echo Starting Aiden...
cd /d "G:\GitHub\Aiden"

rem Check if virtual environment exists
if exist ".venv\Scripts\activate.bat" (
    echo ✅ Virtual environment found
    call .venv\Scripts\activate.bat
    
    rem Check if activation was successful
    if %ERRORLEVEL% neq 0 (
        echo ❌ Failed to activate virtual environment
        pause
        exit /b 1
    )
    
    echo ✅ Virtual environment activated
) else (
    echo ❌ Virtual environment not found at .venv\Scripts\activate.bat
    echo Please run the setup script first or check your installation
    pause
    exit /b 1
)

rem Start Aiden
echo 🚀 Starting Aiden...
python aiden_tray.py

echo 🏁 Aiden has stopped
pause 