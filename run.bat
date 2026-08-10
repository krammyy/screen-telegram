@echo off
cd /d "%~dp0"
REM Delegates to VBS so no CMD stays on the taskbar
wscript //nologo "%~dp0run_silent.vbs"
