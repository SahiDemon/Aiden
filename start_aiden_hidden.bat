@echo off
cd /d "G:\GitHub\Aiden"
rem Try local Python installation first
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" (
    start /min "" "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" aiden_tray.py
) else (
    rem Fallback to system Python
    start /min "" python aiden_tray.py
)
exit 