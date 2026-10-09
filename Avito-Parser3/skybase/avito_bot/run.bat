@echo off
chcp 65001 >nul
title Avito Telegram Monitor Bot
cd /d "%~dp0"

echo ===================================================
echo             Avito Telegram Monitor Bot
echo ===================================================
echo.

REM 1. Detect / Install Python
call "%~dp0..\tools\ensure_python.bat"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to initialize Python!
    pause
    exit /b %errorlevel%
)
set "PY=%PY_EXE%"

REM 3. Check dependencies
"%PY%" -c "import aiogram, curl_cffi, bs4, aiosqlite, aiohttp_socks" >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo [*] Installing dependencies...
    if exist "installer\packages" (
        echo [*] Installing from offline bundle...
        "%PY%" -m pip install --no-index --find-links=installer\packages -r requirements.txt
    ) else (
        echo [*] Installing from PyPI network...
        "%PY%" -m pip install -r requirements.txt
    )
    echo [+] Dependencies ready.
    echo.
)

REM 4. Start bot
echo ===================================================
echo [*] Starting bot...
echo ===================================================
echo.
"%PY%" bot.py

echo.
pause
