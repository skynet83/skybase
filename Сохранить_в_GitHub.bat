@echo off
chcp 65001 >nul
title Сохранение контрольной точки в GitHub
cd /d "%~dp0"

echo ============================================================
echo   SkyBase / AvitoHunter — Создание снимка в GitHub
echo ============================================================
echo.

set /p MSG="Введите описание сохранения (Enter для авто-имени): "
if "%MSG%"=="" set MSG=Быстрое сохранение %DATE% %TIME%

"C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe" "tools\github_mcp_server.py" save "%MSG%"

echo.
echo ============================================================
pause
