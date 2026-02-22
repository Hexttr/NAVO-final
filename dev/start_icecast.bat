@echo off
REM NAVO RADIO — запуск Icecast с конфигом проекта
REM Запускать из корня проекта: dev\start_icecast.bat
set ICECAST_DIR=C:\Program Files\Icecast
set CONFIG=%~dp0..\config\icecast.xml

if not exist "%ICECAST_DIR%\bin\icecast.exe" (
    echo Icecast not found at %ICECAST_DIR%
    echo Install from https://icecast.org/download/
    pause
    exit /b 1
)

echo Starting Icecast (port 8001, mount /live)...
echo Stream URL: http://localhost:8001/live
mkdir "%~dp0icecast_logs" 2>nul
cd /d "%ICECAST_DIR%"
"%ICECAST_DIR%\bin\icecast.exe" -c "%CONFIG%"
pause
