@echo off
setlocal

title FULL BACKUP C:\ins\skybase to Google Drive
color 0B

echo ======================================================================
echo           POLNAYA VYGRUZKA VSEY PAPKI C:\ins\skybase
echo ======================================================================
echo Account: skynet.system83@gmail.com
echo Target:  Google Drive: Backups/skybase
echo Source:  C:\ins\skybase
echo.
echo [START] Zagruzka zapushena avtomaticheski...
echo.

"C:\tools\rclone.exe" copy "C:\ins\skybase" "gdrive:Backups/skybase" -P --stats 1s --transfers 8 --fast-list

if %ERRORLEVEL% equ 0 (
    echo.
    color 0A
    echo ======================================================================
    echo [USPEH 100%%] Vse fayly uspeshno zakachany na Google Disk!
    echo ======================================================================
) else (
    echo.
    color 0C
    echo ======================================================================
    echo [OSHIBKA] Proizoshel sboy pri peredache.
    echo ======================================================================
)

echo.
echo Nazhmite lyubuyu klavishu dlya zakrytiya okna...
pause >nul