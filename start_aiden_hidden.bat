@echo off
cd /d "G:\GitHub\Aiden"

rem Use Python from virtual environment if available
if exist ".venv\Scripts\python.exe" (
    echo Using Python from virtual environment...
    start /min "" ".venv\Scripts\python.exe" aiden_tray.py
) else (
    echo Virtual environment not found, using system Python...
    start /min "" python aiden_tray.py
)

exit 