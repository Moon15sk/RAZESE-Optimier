@echo off
cd /d "%~dp0"
python --version >nul 2>&1
if errorlevel 1 goto nopython

echo === RAZESE Optimizer - building ===
echo === Installing packages ===
python -m pip install --upgrade customtkinter pillow pyinstaller psutil
echo === Creating icon in folder bcg ===
python make_icon.py
echo === Building EXE ===
python -m PyInstaller --noconfirm --onefile --windowed --uac-admin --name "RAZESE Optimizer" --icon "bcg\icon.ico" --add-data "bcg\icon.ico;bcg" --hidden-import psutil --collect-all customtkinter optimizer.py
copy /Y "dist\RAZESE Optimizer.exe" "bcg\RAZESE Optimizer.exe" >nul
echo.
echo DONE - your EXE is in the folder: bcg\RAZESE Optimizer.exe
pause
exit /b

:nopython
echo Python is not installed. Install it from python.org and tick "Add python.exe to PATH", then run this again.
pause
