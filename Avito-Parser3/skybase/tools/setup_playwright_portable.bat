@echo off
chcp 65001 >nul
title Playwright Portable Setup & Diagnostics
cd /d "%~dp0\.."

call "%~dp0ensure_python.bat"
if %errorlevel% neq 0 (
    echo [ОШИБКА] Не удалось инициализировать Python!
    pause
    exit /b %errorlevel%
)

"%PY_EXE%" tools\setup_playwright_portable.py
pause
