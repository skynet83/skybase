@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0tools\ensure_python.bat"
if %errorlevel% neq 0 exit /b %errorlevel%
"%PY_EXE%" "%~dp0tools\ctl.py" %*
