@echo off
REM ===================================================================
REM SkyBase Python Auto-Detector & Offline Installer
REM ===================================================================
chcp 65001 >nul

set "SKYBASE_DIR=%~dp0.."
pushd "%SKYBASE_DIR%"
set "SKYBASE_DIR=%CD%"
popd

set "PY_EXE="

REM 1. Проверяем локальный встроенный python-embed в каталоге приложения (наивысший приоритет, без внешних установок)
if exist "%SKYBASE_DIR%\python-embed\python.exe" call :VERIFY_PY "%SKYBASE_DIR%\python-embed\python.exe"
if defined PY_EXE goto :SUCCESS

if exist "%SKYBASE_DIR%\python.exe" call :VERIFY_PY "%SKYBASE_DIR%\python.exe"
if defined PY_EXE goto :SUCCESS

REM 2. Проверяем переменную окружения PYTHON_EXE
if defined PYTHON_EXE call :VERIFY_PY "%PYTHON_EXE%"
if defined PY_EXE goto :SUCCESS

REM 3. Проверяем стандартные каталоги установки (Python 3.11 x64 в приоритете)
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" call :VERIFY_PY "%LocalAppData%\Programs\Python\Python311\python.exe"
if defined PY_EXE goto :SUCCESS

if exist "%ProgramFiles%\Python311\python.exe" call :VERIFY_PY "%ProgramFiles%\Python311\python.exe"
if defined PY_EXE goto :SUCCESS

if exist "%ProgramFiles(x86)%\Python311\python.exe" call :VERIFY_PY "%ProgramFiles(x86)%\Python311\python.exe"
if defined PY_EXE goto :SUCCESS

if exist "%LocalAppData%\Programs\Python\Python312\python.exe" call :VERIFY_PY "%LocalAppData%\Programs\Python\Python312\python.exe"
if defined PY_EXE goto :SUCCESS

if exist "%ProgramFiles%\Python312\python.exe" call :VERIFY_PY "%ProgramFiles%\Python312\python.exe"
if defined PY_EXE goto :SUCCESS

if exist "%LocalAppData%\Programs\Python\Python310\python.exe" call :VERIFY_PY "%LocalAppData%\Programs\Python\Python310\python.exe"
if defined PY_EXE goto :SUCCESS

if exist "%ProgramFiles%\Python310\python.exe" call :VERIFY_PY "%ProgramFiles%\Python310\python.exe"
if defined PY_EXE goto :SUCCESS

REM 3. Поиск python в PATH с игнорированием Microsoft Store (WindowsApps)
for /f "delims=" %%I in ('where python 2^>nul') do call :CHECK_PATH_ITEM "%%I"
if defined PY_EXE goto :SUCCESS

for /f "delims=" %%I in ('where python3 2^>nul') do call :CHECK_PATH_ITEM "%%I"
if defined PY_EXE goto :SUCCESS

for /f "delims=" %%I in ('where py 2^>nul') do call :CHECK_PATH_ITEM "%%I"
if defined PY_EXE goto :SUCCESS

REM 4. Python не найден - поиск автономного установщика
set "INSTALLER="
if exist "%SKYBASE_DIR%\installer\python-installer.exe" set "INSTALLER=%SKYBASE_DIR%\installer\python-installer.exe"
if not defined INSTALLER if exist "%SKYBASE_DIR%\avito_bot\installer\python-installer.exe" set "INSTALLER=%SKYBASE_DIR%\avito_bot\installer\python-installer.exe"
if not defined INSTALLER if exist "C:\ins\skybase\installer\python-installer.exe" set "INSTALLER=C:\ins\skybase\installer\python-installer.exe"
if not defined INSTALLER if exist "C:\ins\Avito-Parser\skybase\installer\python-installer.exe" set "INSTALLER=C:\ins\Avito-Parser\skybase\installer\python-installer.exe"
if not defined INSTALLER if exist "D:\TEMP\SITE\avito_bot\installer\python-installer.exe" set "INSTALLER=D:\TEMP\SITE\avito_bot\installer\python-installer.exe"

if defined INSTALLER goto :DO_INSTALL

REM Локальный установщик отсутствует - автоматически скачиваем
echo ===================================================================
echo   [*] Python не обнаружен в системе [чистая Windows].
echo   [*] Локальный установщик не найден.
echo   [*] Скачивание Python 3.11.9 [64-bit] с python.org...
echo ===================================================================
if not exist "%SKYBASE_DIR%\installer" mkdir "%SKYBASE_DIR%\installer" >nul 2>&1
set "INSTALLER=%SKYBASE_DIR%\installer\python-installer.exe"

curl.exe -fSL --connect-timeout 20 --retry 3 -o "%INSTALLER%" "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
if not exist "%INSTALLER%" goto :TRY_PS_DOWNLOAD
goto :DO_INSTALL

:TRY_PS_DOWNLOAD
echo   [*] Попытка загрузки через PowerShell...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe', '%INSTALLER%')"

:DO_INSTALL
if not exist "%INSTALLER%" (
    echo ===================================================================
    echo   [ОШИБКА] Не удалось обнаружить или скачать python-installer.exe!
    echo   Поместите установщик вручную в: %SKYBASE_DIR%\installer\python-installer.exe
    echo ===================================================================
    exit /b 1
)

echo ===================================================================
echo   [!] Python не обнаружен в системе [чистая Windows].
echo   [*] Найден автономный установщик:
echo       %INSTALLER%
echo   [*] Запуск автоматической тихой установки Python 3.11...
echo   [*] Пожалуйста, подождите 15-30 секунд...
echo ===================================================================

start /wait "" "%INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 SimpleInstall=1

REM Даем Windows обновить пути
timeout /t 2 /nobreak >nul 2>&1

if exist "%LocalAppData%\Programs\Python\Python311\python.exe" call :VERIFY_PY "%LocalAppData%\Programs\Python\Python311\python.exe"
if defined PY_EXE goto :POST_INSTALL

if exist "%ProgramFiles%\Python311\python.exe" call :VERIFY_PY "%ProgramFiles%\Python311\python.exe"
if defined PY_EXE goto :POST_INSTALL

if exist "%ProgramFiles(x86)%\Python311\python.exe" call :VERIFY_PY "%ProgramFiles(x86)%\Python311\python.exe"
if defined PY_EXE goto :POST_INSTALL

for /f "delims=" %%I in ('where python 2^>nul') do call :CHECK_PATH_ITEM "%%I"
if defined PY_EXE goto :POST_INSTALL

echo   [ОШИБКА] Установка завершена, но рабочий python.exe не найден.
exit /b 1

:POST_INSTALL
echo   [+] Python 3.11 успешно установлен в систему!
set "PACKAGES_DIR="
if exist "%SKYBASE_DIR%\installer\packages" set "PACKAGES_DIR=%SKYBASE_DIR%\installer\packages"
if not defined PACKAGES_DIR if exist "%SKYBASE_DIR%\avito_bot\installer\packages" set "PACKAGES_DIR=%SKYBASE_DIR%\avito_bot\installer\packages"

if defined PACKAGES_DIR (
    "%PY_EXE%" -c "import sys; sys.path.insert(0, r'%SKYBASE_DIR%\lib'); import aiogram, curl_cffi, bs4, aiosqlite, aiohttp_socks, playwright" >nul 2>&1
    if errorlevel 1 (
        echo   [*] Автоустановка модулей из локального кэша колес...
        if exist "%SKYBASE_DIR%\avito_bot\requirements.txt" (
            "%PY_EXE%" -m pip install --no-index --find-links="%PACKAGES_DIR%" -r "%SKYBASE_DIR%\avito_bot\requirements.txt" >nul 2>&1
        )
        echo   [+] Модули подготовлены.
    )
)

echo ===================================================================
echo   [+] Все компоненты готовы к работе! SkyBase продолжает запуск...
echo ===================================================================
echo.

:SUCCESS
set "PYTHON_EXE=%PY_EXE%"
exit /b 0

:CHECK_PATH_ITEM
set "RAW_ITEM=%~1"
echo %RAW_ITEM% | findstr /i "WindowsApps" >nul
if not errorlevel 1 exit /b 0
call :VERIFY_PY "%RAW_ITEM%"
exit /b 0

:VERIFY_PY
set "CAND=%~1"
if not exist "%CAND%" (
    "%CAND%" -c "import sys; sys.exit(0 if sys.version_info[0] == 3 and sys.version_info[1] >= 10 else 1)" >nul 2>&1
    if not errorlevel 1 set "PY_EXE=%CAND%"
    exit /b 0
)
"%CAND%" -c "import sys; sys.exit(0 if sys.version_info[0] == 3 and sys.version_info[1] >= 10 else 1)" >nul 2>&1
if not errorlevel 1 (
    set "PY_EXE=%CAND%"
    for %%D in ("%CAND%\..") do set "PATH=%%~fD;%%~fD\Scripts;%PATH%"
)
exit /b 0
