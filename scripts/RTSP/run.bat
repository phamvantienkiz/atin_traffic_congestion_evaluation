@echo off
chcp 65001 > nul
echo ========================================================
echo   Starting RTSP Multi-Camera Video Wall Server...
echo ========================================================

cd /d "%~dp0..\.."

if exist ".venv\Scripts\python.exe" (
    echo [OK] Using local virtual environment .venv
    ".venv\Scripts\python.exe" scripts\RTSP\server.py
) else (
    echo [INFO] Running via uv...
    uv run python scripts\RTSP\server.py
)

pause
