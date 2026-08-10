@echo off
cd /d "%~dp0"
python -m pip install -q pyinstaller pillow
REM Blank/transparent icon — EXE looks generic, no camera badge on Desktop
python -c "from PIL import Image; Image.new('RGBA',(256,256),(0,0,0,0)).save('app_icon.ico', sizes=[(256,256),(128,128),(64,64),(32,32),(16,16)])"
for /f "delims=" %%I in ('powershell -NoProfile -Command "[Environment]::GetFolderPath('Desktop')"') do set DESK=%%I
python -m PyInstaller --noconfirm --clean --onefile --noconsole --name ScreenTelegram --icon "%~dp0app_icon.ico" --distpath "%DESK%" --workpath "%~dp0build\pyi" --specpath "%~dp0build" "%~dp0launch_desktop.py"
echo.
echo EXE: %DESK%\ScreenTelegram.exe
echo Stealth + machine lock baked in owner_lock.py
pause
