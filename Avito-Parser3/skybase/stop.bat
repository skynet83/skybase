@echo off
chcp 65001 >nul
cd /d "%~dp0"

call "%~dp0tools\ensure_python.bat"
if %errorlevel% neq 0 (
    echo.
    echo [ОШИБКА] Не удалось инициализировать Python!
    pause
    exit /b %errorlevel%
)

"%PY_EXE%" tools\ctl.py stop
pause
