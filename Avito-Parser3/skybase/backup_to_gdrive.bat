@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================================
echo     РЕЗЕРВНОЕ КОПИРОВАНИЕ SKYBASE НА GOOGLE ДИСК
echo ========================================================
echo.

:: 1. Поиск подключенного диска Google Drive (обычно G:, H: и т.д.)
set "GDRIVE_LETTER="
for %%D in (G H I J K L M N O P Q R S T U V W X Y Z D E) do (
    if exist "%%D:\Мой диск\" (
        set "GDRIVE_LETTER=%%D"
        set "TARGET_FOLDER=%%D:\Мой диск\Backups\skybase"
        goto :found
    )
    if exist "%%D:\My Drive\" (
        set "GDRIVE_LETTER=%%D"
        set "TARGET_FOLDER=%%D:\My Drive\Backups\skybase"
        goto :found
    )
)

:found
if "%GDRIVE_LETTER%"=="" (
    echo [ВНИМАНИЕ] Google Диск пока не подключен как диск в системе!
    echo Убедитесь, что вы вошли в аккаунт в приложении Google Drive.
    echo.
    pause
    exit /b 1
)

echo Обнаружен Google Диск: %GDRIVE_LETTER%:\
echo Целевая папка: %TARGET_FOLDER%
echo.

if not exist "%TARGET_FOLDER%" mkdir "%TARGET_FOLDER%"

:: 2. Формирование имени архива с датой и временем
for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "dt=%%I"
set "TIMESTAMP=%dt:~0,4%-%dt:~4,2%-%dt:~6,2%_%dt:~8,2%-%dt:~10,2%"
set "ARCHIVE_NAME=skybase_%TIMESTAMP%.zip"

echo [1/2] Архивирование проекта (без лишних кэшей и логов)...
powershell -NoProfile -Command ^
  "$exclude = @('build', 'dist', '__pycache__', 'browsers', '*.log', '*.tmp');" ^
  "$files = Get-ChildItem -Path 'c:\ins\skybase' -Exclude $exclude | Where-Object { $_.Name -notin $exclude };" ^
  "Compress-Archive -Path $files.FullName -DestinationPath '%TEMP%\%ARCHIVE_NAME%' -Force"

if not exist "%TEMP%\%ARCHIVE_NAME%" (
    echo [ОШИБКА] Не удалось создать архив!
    pause
    exit /b 1
)

echo [2/2] Копирование архива на Google Диск...
copy /y "%TEMP%\%ARCHIVE_NAME%" "%TARGET_FOLDER%\" >nul
del /f /q "%TEMP%\%ARCHIVE_NAME%" >nul

echo.
echo ========================================================
echo [УСПЕХ] Архив сохранен на Google Диске:
echo %TARGET_FOLDER%\%ARCHIVE_NAME%
echo ========================================================
echo.
pause
