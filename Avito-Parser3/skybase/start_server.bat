@echo off
chcp 65001 >nul
title SkyBase Server
cd /d "%~dp0"

set "TARGET_PORT=%~1"
if "%TARGET_PORT%"=="" (
    if defined SERVER_PORT (
        set "TARGET_PORT=%SERVER_PORT%"
    ) else (
        set "TARGET_PORT=80"
    )
)

net session >nul 2>&1
if %errorlevel% equ 0 (
    netsh advfirewall firewall show rule name="ElectroBase Port 80" >nul 2>&1
    if %errorlevel% neq 0 (
        netsh advfirewall firewall add rule name="ElectroBase Port 80" dir=in action=allow protocol=TCP localport=80 profile=any >nul 2>&1
    )
    netsh http show urlacl url=http://+:80/ >nul 2>&1
    if %errorlevel% neq 0 (
        netsh http add urlacl url=http://+:80/ sddl="D:(A;;GX;;;WD)" >nul 2>&1
    )
    netsh advfirewall firewall show rule name="ElectroBase Port 8080" >nul 2>&1
    if %errorlevel% neq 0 (
        netsh advfirewall firewall add rule name="ElectroBase Port 8080" dir=in action=allow protocol=TCP localport=8080 profile=any >nul 2>&1
    )
    netsh http show urlacl url=http://+:8080/ >nul 2>&1
    if %errorlevel% neq 0 (
        netsh http add urlacl url=http://+:8080/ sddl="D:(A;;GX;;;WD)" >nul 2>&1
    )
)

cls
call "%~dp0tools\ensure_python.bat"
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось инициализировать Python!
    pause
    exit /b %errorlevel%
)
set "PY=%PY_EXE%"

echo =======================================================
echo          Starting SkyBase Server (Port %TARGET_PORT%)
echo =======================================================

REM ── Запуск сервера (Telegram-бот поднимается автоматически в фоне) ──
echo   [*] Запуск SkyBase Server и фонового Telegram-бота...
echo =======================================================

set "PYTHON_EXE=%PY%"
if exist "%~dp0server.py" (
    "%PY%" "%~dp0server.py" --port %TARGET_PORT%
) else (
    "%PY%" -c "import os; p=r'%~dp0server.ps1'; b=open(p,'rb').read() if os.path.exists(p) else b''; open(p,'wb').write(b'\xef\xbb\xbf'+b) if b and not b.startswith(b'\xef\xbb\xbf') else None" >nul 2>&1
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File server.ps1 -Port %TARGET_PORT%
)

REM ── Сервер остановлен — завершаем фонового бота ────────────
echo.
echo   [*] Сервер остановлен. Завершаем фоновый Avito Bot...
"%PY%" avito_api_helper.py bot-toggle stop >nul 2>&1
if exist "avito_bot\bot.pid" (
    for /f "usebackq tokens=*" %%i in ("avito_bot\bot.pid") do (
        taskkill /PID %%i /F >nul 2>&1
    )
    del "avito_bot\bot.pid" >nul 2>&1
)
if exist "lan_proxy.pid" (
    for /f "usebackq tokens=*" %%i in ("lan_proxy.pid") do (
        taskkill /PID %%i /F >nul 2>&1
    )
    del "lan_proxy.pid" >nul 2>&1
)
echo   [+] Telegram-бот и сетевые службы остановлены.
echo =======================================================

pause
