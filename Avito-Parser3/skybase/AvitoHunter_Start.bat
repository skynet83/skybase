@echo off
chcp 65001 >nul
title AvitoHunter
cd /d "%~dp0"
echo [*] Запуск AvitoHunter...
if exist "%~dp0python.exe" (
    "%~dp0python.exe" gateway.py
) else (
    python.exe gateway.py
)
if %errorlevel% neq 0 (
    echo.
    echo [!] Программа завершилась с кодом ошибки: %errorlevel%
    pause
)

