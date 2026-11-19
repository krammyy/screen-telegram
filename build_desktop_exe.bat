@echo off
setlocal
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --name ScreenTelegram main.py
exit /b %ERRORLEVEL%
