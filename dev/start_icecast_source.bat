@echo off
REM NAVO RADIO — только icecast_source (стримит эфир в Icecast)
REM Запускать из корня проекта: dev\start_icecast_source.bat
cd /d "%~dp0..\backend"
if exist venv\Scripts\activate.bat (
    call venv\Scripts\activate.bat && python icecast_source.py
) else (
    echo Создайте venv: cd backend && python -m venv venv
    pause
)
