@echo off
title Smart Review Test Tracker
cd /d "%~dp0"
echo ============================================
echo   Smart Review Test Tracker
echo   URL: http://localhost:9091
echo ============================================
echo.

if exist "TrackerServer.exe" (
    TrackerServer.exe
) else (
    python app.py
)

pause
