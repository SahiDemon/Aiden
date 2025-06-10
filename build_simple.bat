@echo off
echo ====================================
echo Building Aiden AI Assistant Executable
echo ====================================

echo Installing build dependencies...
pip install PyInstaller pystray Pillow win10toast

echo Building executable...
pyinstaller aiden_tray.py --name=Aiden --onefile --windowed --noconsole --distpath=dist --workpath=build

echo Creating additional directories...
if not exist "dist\temp" mkdir "dist\temp"
if not exist "dist\logs" mkdir "dist\logs"

echo Creating run script...
echo @echo off > "dist\run_aiden.bat"
echo echo Starting Aiden AI Assistant... >> "dist\run_aiden.bat"
echo start "" "Aiden.exe" >> "dist\run_aiden.bat"
echo echo Aiden is now running in the system tray! >> "dist\run_aiden.bat"
echo pause >> "dist\run_aiden.bat"

echo.
echo ====================================
echo Build completed successfully!
echo ====================================
echo.
echo To run Aiden:
echo 1. Go to the 'dist' folder
echo 2. Run 'Aiden.exe' or 'run_aiden.bat'
echo 3. Look for the Aiden icon in your system tray
echo 4. Right-click the icon to activate the assistant
echo.
pause 