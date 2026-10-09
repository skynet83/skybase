@echo off
REM ===================================================================
REM SkyBase - Проверка и автономная установка Python
REM ===================================================================
chcp 65001 >nul
cd /d "%~dp0"
call tools\ensure_python.bat
if %errorlevel% neq 0 (
    echo [!] Ошибка инициализации Python.
    pause
    exit /b %errorlevel%
)
echo Python готов: %PYTHON_EXE%
pause
