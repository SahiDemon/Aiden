@echo off
setlocal
REM Run from the repository root, including when double-clicked elsewhere.
pushd "%~dp0..\.." || exit /b 1
set "AIDEN_DEBUG_PYTHON=.venv\Scripts\python.exe"
if not exist "%AIDEN_DEBUG_PYTHON%" set "AIDEN_DEBUG_PYTHON=venv\Scripts\python.exe"
if not exist "%AIDEN_DEBUG_PYTHON%" (
    echo Virtual environment not found. Run install.ps1 first.
    popd
    pause
    exit /b 1
)
echo Starting the advanced wake-word debugger. Stop Aiden first to release the microphone.
"%AIDEN_DEBUG_PYTHON%" scripts\debug_wake_word_advanced.py
set "AIDEN_DEBUG_EXIT=%ERRORLEVEL%"
popd
pause
exit /b %AIDEN_DEBUG_EXIT%
