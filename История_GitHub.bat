@echo off
chcp 65001 >nul
title История сохранений в GitHub
cd /d "%~dp0"

echo ============================================================
echo   SkyBase / AvitoHunter — История контрольных точек
echo ============================================================
echo.

"C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe" "tools\github_mcp_server.py" list

echo.
echo ============================================================
pause
