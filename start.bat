@echo off
title AarthiAI Local Stack
color 0A
cls
echo.
echo  +==========================================================+
echo  ^|           AarthiAI  --  Local Development Stack          ^|
echo  ^|                                                          ^|
echo  ^|  AARTHI Landing Backend  : http://localhost:8000         ^|
echo  ^|  Dashboard Backend       : http://localhost:8001         ^|
echo  ^|  Dashboard Frontend      : http://localhost:3000         ^|
echo  ^|  Landing Page Frontend   : http://localhost:3001         ^|
echo  +==========================================================+
echo.

REM ─── Kill anything already on these ports ────────────────────────────────────
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 :8001 :3000 :3001" 2^>nul') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 1 /nobreak >nul

REM ─── 1. AARTHI Landing Backend (port 8000) ───────────────────────────────────
echo [1/4] Starting AARTHI Landing Backend on port 8000...
start "AARTHI Landing Backend" cmd /k ^
  "cd /d c:\Lang\Aarthi-AI\AARTHI\backend && call ..\..\backend\venv\Scripts\activate.bat && uvicorn main:app --host 0.0.0.0 --port 8000 --reload && pause"
timeout /t 3 /nobreak >nul

REM ─── 2. AarthiAI Dashboard Backend (port 8001) ───────────────────────────────
echo [2/4] Starting AarthiAI Dashboard Backend on port 8001...
start "AarthiAI Dashboard Backend" cmd /k ^
  "cd /d c:\Lang\Aarthi-AI\backend && call venv\Scripts\activate.bat && uvicorn app:app --host 0.0.0.0 --port 8001 --reload && pause"
timeout /t 3 /nobreak >nul

REM ─── 3. Dashboard Frontend (port 3000) ───────────────────────────────────────
echo [3/4] Starting Dashboard Frontend on port 3000...
start "AarthiAI Dashboard Frontend" cmd /k ^
  "cd /d c:\Lang\Aarthi-AI\frontend && python -m http.server 3000 && pause"
timeout /t 2 /nobreak >nul

REM ─── 4. Landing Page Frontend (port 3001) ────────────────────────────────────
echo [4/4] Starting Landing Page Frontend on port 3001...
start "AarthiAI Landing Frontend" cmd /k ^
  "cd /d c:\Lang\Aarthi-AI\AARTHI\frontend && python -m http.server 3001 && pause"
timeout /t 3 /nobreak >nul

echo.
echo  Opening browsers...
start http://localhost:3001/index.html
timeout /t 1 /nobreak >nul
start http://localhost:3000/index.html

echo.
echo  +==========================================================+
echo  ^|  All 4 servers are running in separate windows.          ^|
echo  ^|  Close those windows individually to stop each server.   ^|
echo  ^|                                                          ^|
echo  ^|  API DOCS:                                               ^|
echo  ^|    Dashboard  ->  http://localhost:8001/docs             ^|
echo  ^|    Landing    ->  http://localhost:8000/docs             ^|
echo  +==========================================================+
echo.
pause
