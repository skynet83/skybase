@echo off
chcp 65001 >nul
title Сброс триала и лицензии AvitoHunter

echo =======================================================
echo    СБРОС ТРИАЛА И ЛИЦЕНЗИЙ AVITOHUNTER (Windows 11)
echo =======================================================
echo.

echo [*] Остановка запущенных процессов AvitoHunter...
taskkill /f /im AvitoHunter.exe >nul 2>&1
taskkill /f /im app_launcher.exe >nul 2>&1
taskkill /f /im python.exe >nul 2>&1
timeout /t 1 /nobreak >nul

echo [*] Очистка веток системного реестра Windows (HKCU)...
reg delete "HKCU\Software\SkyBaseAudit" /f >nul 2>&1
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\CLSID\{e8b91a7d-5a91-4c92-bf31-92b4a3a5f82c}" /f >nul 2>&1

echo [*] Удаление скрытых файлов защиты...
if exist "C:\ProgramData\SkyBase\.sys_hwid_trial.dat" del /f /q "C:\ProgramData\SkyBase\.sys_hwid_trial.dat" >nul 2>&1
if exist "%LOCALAPPDATA%\SkyBase\sys_audit.json" del /f /q "%LOCALAPPDATA%\SkyBase\sys_audit.json" >nul 2>&1

echo [*] Очистка локальных баз данных и облачного Telegram-реестра...
set PY_BIN=
if exist "C:\Program Files (x86)\AvitoHunter\python.exe" (
    set PY_BIN="C:\Program Files (x86)\AvitoHunter\python.exe"
) else (
    where python >nul 2>&1 && set PY_BIN=python
)

if defined PY_BIN (
    if exist "%~dp0reset_trial_and_license.py" (
        %PY_BIN% "%~dp0reset_trial_and_license.py"
    ) else if exist "E:\ins\skybase\skybotparser\reset_trial_and_license.py" (
        %PY_BIN% "E:\ins\skybase\skybotparser\reset_trial_and_license.py"
    )
)

echo.
echo =======================================================
echo [ГОТОВО] Все следы триала полностью удалены!
echo Вы можете запустить AvitoHunter и активировать триал заново.
echo =======================================================
echo.
pause
