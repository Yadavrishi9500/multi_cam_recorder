@echo off
REM One-click launcher for Windows.
REM Double-click this file to install dependencies (first run only) and
REM start the dashboard. It will open your browser automatically.

cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python not found. Please install Python 3.10+ from https://python.org and try again.
    pause
    exit /b 1
)

echo Installing/checking dependencies...
python -m pip install -r requirements.txt --quiet

echo Starting Rig Control dashboard...
python web\app.py

pause
