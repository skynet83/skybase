@echo off
chcp 65001 >nul
title Sbros Triala Tolko v Windows (Test Oblaka)

echo =======================================================
echo   SBROS TRIALA TOLKO V WINDOWS (TEST OBLAKA TELEGRAM)
echo =======================================================
echo.
echo [*] Udalyayutsya klyuchi tolko na etom PK.
echo [*] Baza v Telegram-kanale SOHRANYAETSYA bez izmeneniy.
echo.

echo [*] Stopping running processes...
taskkill /f /im AvitoHunter.exe >nul 2>&1
taskkill /f /im app_launcher.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
timeout /t 1 /nobreak >nul 2>&1
if errorlevel 1 ping 127.0.0.1 -n 2 >nul

echo [*] Cleaning Windows registry...
reg delete "HKCU\Software\SkyBaseAudit" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\CLSID\{e8b91a7d-5a91-4c92-bf31-92b4a3a5f82c}" /f >nul 2>&1

echo [*] Deleting protection files...
if exist "%ProgramData%\SkyBase\.sys_hwid_trial.dat" del /f /q "%ProgramData%\SkyBase\.sys_hwid_trial.dat" >nul 2>&1
if exist "%LOCALAPPDATA%\SkyBase\sys_audit.json" del /f /q "%LOCALAPPDATA%\SkyBase\sys_audit.json" >nul 2>&1

echo [*] Cleaning local databases (Telegram cloud remains untouched)...
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

set PY_EXE=
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set PY_EXE="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY_EXE if exist "C:\Program Files (x86)\AvitoHunter\python.exe" set PY_EXE="C:\Program Files (x86)\AvitoHunter\python.exe"
if not defined PY_EXE set PY_EXE=python

set RESET_SCRIPT=
if exist "%~dp0reset_local_only.py" set RESET_SCRIPT="%~dp0reset_local_only.py"
if not defined RESET_SCRIPT if exist "C:\Program Files (x86)\AvitoHunter\reset_local_only.py" set RESET_SCRIPT="C:\Program Files (x86)\AvitoHunter\reset_local_only.py"
if not defined RESET_SCRIPT if exist "E:\ins\skybase\skybotparser\reset_local_only.py" set RESET_SCRIPT="E:\ins\skybase\skybotparser\reset_local_only.py"

if defined RESET_SCRIPT (
    %PY_EXE% %RESET_SCRIPT%
)

echo.
echo =======================================================
echo [GOTOVO] Lokalny sbros v Windows 11 zavershen!
echo Zapustite AvitoHunter i proverit zashitu oblaka.
echo =======================================================
echo.
pause
