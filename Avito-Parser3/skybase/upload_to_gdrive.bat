@echo off
chcp 65001 >nul
setlocal

echo ======================================================================
echo           ВЫГРУЗКА ПРОЕКТА SKYBASE НА GOOGLE ДИСК
echo ======================================================================
echo.
echo Аккаунт: skynet.system83@gmail.com
echo Папка на диске: Backups/skybase
echo Исходная папка: %~dp0
echo.
echo Выберите режим выгрузки:
echo   [1] - Быстрая синхронизация папки (выгружаются файлы проекта как есть)
echo   [2] - Создать ZIP-архив с датой и закачать архив на Google Диск
echo   [3] - Выход
echo.

set /p CHOICE="Ваш выбор (1, 2 или 3, по умолчанию 1): "
if "%CHOICE%"=="" set CHOICE=1

if "%CHOICE%"=="1" goto :SYNC_FILES
if "%CHOICE%"=="2" goto :MAKE_ARCHIVE
if "%CHOICE%"=="3" exit /b 0

:SYNC_FILES
echo.
echo ----------------------------------------------------------------------
echo Синхронизация файлов проекта...
echo Лишние временные папки (build, dist, __pycache__, logs) пропускаются.
echo ----------------------------------------------------------------------
echo.

"C:\tools\rclone.exe" copy "%~dp0." "gdrive:Backups/skybase" ^
  --progress ^
  --exclude "build/**" ^
  --exclude "dist/**" ^
  --exclude "__pycache__/**" ^
  --exclude "browsers/**" ^
  --exclude "*.log" ^
  --exclude ".git/**" ^
  --transfers 4

if %ERRORLEVEL% equ 0 (
    echo.
    echo ======================================================================
    echo [УСПЕХ] Все файлы успешно закачаны на Google Диск!
    echo ======================================================================
) else (
    echo.
    echo ======================================================================
    echo [ОШИБКА] Не удалось выполнить выгрузку. Проверьте интернет-соединение.
    echo ======================================================================
)
goto :END

:MAKE_ARCHIVE
echo.
echo ----------------------------------------------------------------------
echo Создание ZIP-архива с датой и временем...
echo ----------------------------------------------------------------------
echo.

for /f "tokens=2 delims==" %%I in ('wmic os get localdatetime /value') do set "dt=%%I"
set "TIMESTAMP=%dt:~0,4%-%dt:~4,2%-%dt:~6,2%_%dt:~8,2%-%dt:~10,2%"
set "ARCHIVE_NAME=skybase_%TIMESTAMP%.zip"

powershell -NoProfile -Command ^
  "$exclude = @('build', 'dist', '__pycache__', 'browsers', '*.log', '*.tmp');" ^
  "$files = Get-ChildItem -Path '%~dp0' -Exclude $exclude | Where-Object { $_.Name -notin $exclude };" ^
  "Compress-Archive -Path $files.FullName -DestinationPath '%TEMP%\%ARCHIVE_NAME%' -Force"

if not exist "%TEMP%\%ARCHIVE_NAME%" (
    echo [ОШИБКА] Не удалось создать архив!
    goto :END
)

echo Закачка архива %ARCHIVE_NAME% на Google Диск...
"C:\tools\rclone.exe" copy "%TEMP%\%ARCHIVE_NAME%" "gdrive:Backups/skybase_archives" --progress

del /f /q "%TEMP%\%ARCHIVE_NAME%" >nul

if %ERRORLEVEL% equ 0 (
    echo.
    echo ======================================================================
    echo [УСПЕХ] Архив сохранен в Google Диске: Backups/skybase_archives/%ARCHIVE_NAME%
    echo ======================================================================
) else (
    echo.
    echo [ОШИБКА] Ошибка при загрузке архива.
)

:END
echo.
pause
