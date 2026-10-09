@echo off
chcp 65001 >nul
title SkyBase - Открытие сетевого доступа
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Запрос прав Администратора для открытия сетевого порта...
    powershell.exe -NoProfile -Command "Start-Process cmd -ArgumentList '/c \"\"%~dp0enable_network.bat\"\"' -Verb RunAs"
    exit /b
)

echo =======================================================
echo   Настройка постоянного сетевого доступа ElectroBase
echo =======================================================
netsh advfirewall firewall add rule name="ElectroBase Port 8080" dir=in action=allow protocol=TCP localport=8080 profile=any
netsh http add urlacl url=http://+:8080/ sddl="D:(A;;GX;;;WD)"
netsh http add urlacl url=http://192.168.1.139:8080/ sddl="D:(A;;GX;;;WD)"
echo =======================================================
echo   [+] Настройка успешно завершена! Порт 8080 открыт.
echo =======================================================
pause
