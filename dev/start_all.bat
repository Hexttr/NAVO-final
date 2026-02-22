@echo off
REM NAVO RADIO — запуск всех компонентов в отдельных окнах
REM Запускать из корня проекта: dev\start_all.bat

for %%I in ("%~dp0..") do set "PROJECT=%%~fI"

echo NAVO RADIO — запуск...
echo.

REM 1. Icecast
start "NAVO Icecast" cmd /k "cd /d %PROJECT% && dev\start_icecast.bat"

REM 2. Подождать, чтобы Icecast успел стартовать
timeout /t 2 /nobreak >nul

REM 3. Backend (FastAPI)
start "NAVO Backend" cmd /k "cd /d %PROJECT%\backend && (if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat && uvicorn main:app --reload) else (echo Создаю venv... && python -m venv venv && call venv\Scripts\activate.bat && pip install -r requirements.txt && uvicorn main:app --reload))"

REM 4. Icecast Source (стримит эфир)
timeout /t 3 /nobreak >nul
start "NAVO Icecast Source" cmd /k "cd /d %PROJECT%\backend && (if exist venv\Scripts\activate.bat (call venv\Scripts\activate.bat && python icecast_source.py) else (echo Запустите backend первым для создания venv))"

REM 5. Frontend
timeout /t 2 /nobreak >nul
start "NAVO Frontend" cmd /k "cd /d %PROJECT%\frontend && (if exist node_modules (npm run dev) else (echo Устанавливаю зависимости... && npm install && npm run dev))"

echo.
echo Все окна запущены:
echo   - Icecast (порт 8001)
echo   - Backend (порт 8000)
echo   - Icecast Source (стримит эфир)
echo   - Frontend (порт 5173)
echo.
echo Откройте http://localhost:5173 — плеер
echo Откройте http://localhost:5173/admin — админка (сгенерируйте эфир)
echo.
pause
