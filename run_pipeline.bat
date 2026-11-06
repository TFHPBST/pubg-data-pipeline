@echo off
cd /d "%~dp0"
if not exist logs mkdir logs

set PYTHON=C:\Users\ccr18\AppData\Local\Programs\Python\Python314\python.exe
set PYTHONIOENCODING=utf-8

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set STAMP=%%i
set OUT=logs\run_%STAMP%.txt

echo [START] %DATE% %TIME% >> "%OUT%"

if "%PUBG_PLAYER_NAME%"=="" (
    echo [ERROR] PUBG_PLAYER_NAME is not set >> "%OUT%"
    exit /b 2
)

docker compose up -d --wait >> "%OUT%" 2>&1
if errorlevel 1 (
    echo [ERROR] docker compose up failed >> "%OUT%"
    exit /b 3
)

"%PYTHON%" pipeline.py "%PUBG_PLAYER_NAME%" --limit 20 >> "%OUT%" 2>&1
set CODE=%ERRORLEVEL%

echo [END] exit code %CODE% >> "%OUT%"
exit /b %CODE%