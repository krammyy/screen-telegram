@echo off
cd /d "%~dp0"
echo. > stop.flag
echo Создан stop.flag — watchdog остановится после текущего цикла.
echo Если нужно убить прямо сейчас: taskkill /f /im python.exe
