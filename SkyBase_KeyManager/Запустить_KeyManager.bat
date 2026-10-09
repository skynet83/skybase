@echo off
chcp 65001 >nul
title KeyManager - Генератор лицензий SkyBase
cd /d "%~dp0"

set "PY="
if exist "%~dp0..\skybase\tools\ensure_python.bat" (
    call "%~dp0..\skybase\tools\ensure_python.bat" >nul 2>&1
    set "PY=%PY_EXE%"
)

if not defined PY (
    if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
        set "PY=%LocalAppData%\Programs\Python\Python311\python.exe"
    ) else if exist "%ProgramFiles%\Python311\python.exe" (
        set "PY=%ProgramFiles%\Python311\python.exe"
    ) else (
        set "PY=python"
    )
)

if exist "%~dp0src\key_manager.py" (
    start "" "%PY%" "%~dp0src\key_manager.py"
) else if exist "%~dp0KeyManager.exe" (
    start "" "%~dp0KeyManager.exe"
) else (
    echo [ОШИБКА] Файлы KeyManager не найдены.
    pause
)