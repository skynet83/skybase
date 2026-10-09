@echo off
chcp 65001 >nul
echo ========================================================
echo   НАСТРОЙКА ПОДКЛЮЧЕНИЯ К GOOGLE ДИСКУ (RCLONE)
echo ========================================================
echo.
echo Сейчас откроется окно настройки rclone.
echo.
echo Быстрые шаги:
echo  1. Введите n (New remote) и Enter.
echo  2. Введите имя: gdrive и Enter.
echo  3. Введите: drive (или номер Google Drive) и Enter.
echo  4. client_id / client_secret: нажмите Enter дважды (оставить пустыми).
echo  5. Scope: введите 1 (Full access) и Enter.
echo  6. service_account_file: пустой (Enter).
echo  7. Edit advanced config: n (Enter).
echo  8. Use web browser: y (Enter) - откроется браузер для входа в Google.
echo  9. Shared Drive: n (Enter).
echo 10. Подтвердить: y (Enter), затем q для выхода.
echo.
pause
"C:\tools\rclone.exe" config
echo.
echo Настройка завершена!
pause
