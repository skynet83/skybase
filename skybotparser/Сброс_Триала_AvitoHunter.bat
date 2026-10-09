@echo off
chcp 65001 >nul
title Sbros Triala AvitoHunter

echo =======================================================
echo    SBROS TRIALA I LICENZIY AVITOHUNTER (Windows 11)
echo =======================================================
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

echo [*] Cleaning local databases and cloud Telegram registry...
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

set PY_EXE=
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" set PY_EXE="%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
if not defined PY_EXE if exist "C:\Program Files (x86)\AvitoHunter\python.exe" set PY_EXE="C:\Program Files (x86)\AvitoHunter\python.exe"
if not defined PY_EXE set PY_EXE=python

set RESET_SCRIPT=
if exist "%~dp0reset_trial_and_license.py" set RESET_SCRIPT="%~dp0reset_trial_and_license.py"
if not defined RESET_SCRIPT if exist "C:\Program Files (x86)\AvitoHunter\reset_trial_and_license.py" set RESET_SCRIPT="C:\Program Files (x86)\AvitoHunter\reset_trial_and_license.py"
if not defined RESET_SCRIPT if exist "E:\ins\skybase\skybotparser\reset_trial_and_license.py" set RESET_SCRIPT="E:\ins\skybase\skybotparser\reset_trial_and_license.py"

if defined RESET_SCRIPT (
    %PY_EXE% %RESET_SCRIPT%
)

echo.
echo =======================================================
echo [GOTOVO] Vse sledy triala polnostyu udaleny!
echo Zapustite AvitoHunter i nazhmite 'Aktivirovat trial'.
echo =======================================================
echo.
pause
