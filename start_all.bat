@echo off
title EcoWell IoT Simulator — Startup
echo.
echo ====================================================
echo   EcoWell Smart Water Softener — IoT Dashboard
echo ====================================================
echo.
echo Starting all 4 components:
echo   [1] MQTT Broker       (port 1883) — Pure Python, no install needed
echo   [2] FastAPI Backend   (port 8000)
echo   [3] Flask Dashboard   (port 5000)
echo   [4] Device Simulator  (console)
echo.
echo Press any key to start...
pause >nul

:: [1] Start MQTT Broker (pure Python, no Mosquitto needed)
echo [1/4] Starting Python MQTT Broker on port 1883...
start "EcoWell MQTT Broker" cmd /k "cd /d %~dp0 && python broker.py"
timeout /t 2 /nobreak >nul

:: [2] Start Backend
echo [2/4] Starting FastAPI backend on port 8000...
start "EcoWell Backend" cmd /k "cd /d %~dp0backend && python -m uvicorn main:app --port 8000"
timeout /t 3 /nobreak >nul

:: [3] Start Dashboard
echo [3/4] Starting Flask dashboard on port 5000...
start "EcoWell Dashboard" cmd /k "cd /d %~dp0dashboard && python app.py"
timeout /t 2 /nobreak >nul

:: [4] Start Device Simulator
echo [4/4] Starting Device Simulator...
start "EcoWell Device" cmd /k "cd /d %~dp0device && python simulator.py"

:: Open browser
timeout /t 4 /nobreak >nul
echo.
echo ======================================================
echo  All components started!
echo  Dashboard: http://localhost:5000
echo  Backend API: http://localhost:8000/docs
echo ======================================================
start http://localhost:5000
