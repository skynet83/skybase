import os
import shutil
import sqlite3

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.dirname(BASE_DIR)
candidate_src = os.path.join(PARENT_DIR, "Avito-Parser3", "skybase")
SRC_DIR = candidate_src if os.path.exists(candidate_src) else r"C:\G\ins\Avito-Parser3\skybase"
PYD_DIR = os.path.join(BASE_DIR, "test_pyd")
APP_DIR = os.path.join(BASE_DIR, "app")


print("[*] Assembling AvitoHunter in:", APP_DIR)

if os.path.exists(APP_DIR):
    shutil.rmtree(APP_DIR)
os.makedirs(APP_DIR, exist_ok=True)

# 1. Копируем python-embed в корень app
embed_src = os.path.join(SRC_DIR, "python-embed")
if os.path.exists(embed_src):
    for item in os.listdir(embed_src):
        s = os.path.join(embed_src, item)
        d = os.path.join(APP_DIR, item)
        if os.path.isdir(s):
            shutil.copytree(s, d)
        else:
            shutil.copy2(s, d)
    print("  [+] python-embed copied")

# 2. Копируем сторонние библиотеки (lib)
lib_src = os.path.join(SRC_DIR, "lib")
if os.path.exists(lib_src):
    shutil.copytree(lib_src, os.path.join(APP_DIR, "lib"), dirs_exist_ok=True)
    print("  [+] lib/ copied")

# 3. Копируем веб-ассеты (HTML, JS, CSS, Sound, Img)
for folder in ["js", "css", "sound", "img", "images", "fonts"]:
    f_src = os.path.join(SRC_DIR, folder)
    if os.path.exists(f_src):
        shutil.copytree(f_src, os.path.join(APP_DIR, folder))
        print(f"  [+] {folder}/ copied")

for f in ["index.html", "favicon.ico", "manifest.json", "sw.js"]:
    f_path = os.path.join(SRC_DIR, f)
    if os.path.exists(f_path):
        shutil.copy2(f_path, os.path.join(APP_DIR, f))
        print(f"  [+] {f} copied")

# Копируем app_launcher.py если есть
launcher_py = os.path.join(SRC_DIR, "app_launcher.py")
if os.path.exists(launcher_py):
    shutil.copy2(launcher_py, os.path.join(APP_DIR, "app_launcher.py"))
    print("  [+] app_launcher.py copied")

# 4. Копируем скомпилированные .pyd файлы в корень app
core_pyds = [
    "gateway.cp311-win_amd64.pyd",
    "server.cp311-win_amd64.pyd",
    "avito_api_helper.cp311-win_amd64.pyd",
    "avito_sniper.cp311-win_amd64.pyd",
    "devices_db.cp311-win_amd64.pyd",
    "hwid_security.cp311-win_amd64.pyd",
    "app_launcher.cp311-win_amd64.pyd",
    "cloud_license.cp311-win_amd64.pyd",
]

for p in core_pyds:
    src_p = os.path.join(PYD_DIR, p)
    if os.path.exists(src_p):
        shutil.copy2(src_p, os.path.join(APP_DIR, p))
        print(f"  [+] Compiled binary: {p}")

# 5. Папка avito_bot со скомпилированными модулями
bot_dir = os.path.join(APP_DIR, "avito_bot")
os.makedirs(bot_dir, exist_ok=True)

# Копируем скомпилированные модули бота (bot, proxy_worker, database, filters, parser)
bot_pyds = [
    "bot.cp311-win_amd64.pyd",
    "proxy_worker.cp311-win_amd64.pyd",
    "database.cp311-win_amd64.pyd",
    "filters.cp311-win_amd64.pyd",
    "parser.cp311-win_amd64.pyd"
]
for bp in bot_pyds:
    src_bp = os.path.join(PYD_DIR, bp)
    if os.path.exists(src_bp):
        shutil.copy2(src_bp, os.path.join(bot_dir, bp))
        print(f"  [+] Bot binary: {bp}")

# Копируем вспомогательные файлы для бота (config.py, no_photo.jpg, proxies.txt, avito_bot.db) если они есть
for extra in ["config.py", "no_photo.jpg", "proxies.txt", "avito_bot.db"]:
    e_src = os.path.join(SRC_DIR, "avito_bot", extra)
    if os.path.exists(e_src):
        shutil.copy2(e_src, os.path.join(bot_dir, extra))
        print(f"  [+] Bot extra: {extra}")

# Очищаем avito_bot.db внутри сборки app (оставляя структуру таблиц)
target_db = os.path.join(bot_dir, "avito_bot.db")
if os.path.exists(target_db):
    try:
        conn = sqlite3.connect(target_db)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        tables = [t[0] for t in cur.fetchall()]
        for tbl in tables:
            cur.execute(f"DELETE FROM [{tbl}]")
        conn.commit()
        cur.execute("VACUUM")
        conn.close()
        print("  [+] Cleaned and vacuumed app/avito_bot/avito_bot.db")
    except Exception as e:
        print(f"  [!] Note on db cleanup: {e}")

# Создаем пустую папку data с чистыми базами данных «из коробки»
os.makedirs(os.path.join(APP_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(APP_DIR, "data", "backups"), exist_ok=True)
with open(os.path.join(APP_DIR, "data", "users.json"), "w", encoding="utf-8") as f:
    f.write("[]\n")
with open(os.path.join(APP_DIR, "data", "devices.json"), "w", encoding="utf-8") as f:
    f.write("{}\n")
with open(os.path.join(APP_DIR, "data", "dispensed_keys.json"), "w", encoding="utf-8") as f:
    f.write("{}\n")
with open(os.path.join(APP_DIR, "data", "activation_locks.json"), "w", encoding="utf-8") as f:
    f.write("{}\n")
with open(os.path.join(APP_DIR, "data", "chat_messages.json"), "w", encoding="utf-8") as f:
    f.write("[]\n")
lic_in_app = os.path.join(APP_DIR, "data", "license.json")
if os.path.exists(lic_in_app):
    try: os.remove(lic_in_app)
    except Exception: pass
print("  [+] Clean initial data files created")

# Копируем утилиты полного сброса триала в app
for util in ["reset_trial_and_license.py", "Reset_Trial_License.bat", "Reset_Windows_Only.bat", "reset_local_only.py"]:
    u_src = os.path.join(BASE_DIR, util)
    if os.path.exists(u_src):
        shutil.copy2(u_src, os.path.join(APP_DIR, util))
        print(f"  [+] Reset utility copied: {util}")

# Копируем cloud_license.py если есть
cloud_lic = os.path.join(SRC_DIR, "cloud_license.py")
if os.path.exists(cloud_lic):
    shutil.copy2(cloud_lic, os.path.join(APP_DIR, "cloud_license.py"))
    print("  [+] cloud_license.py copied")

# 6. Обновляем python311._pth для добавления avito_bot
pth_file = os.path.join(APP_DIR, "python311._pth")
if os.path.exists(pth_file):
    with open(pth_file, "r", encoding="utf-8") as f:
        pth_content = f.read()
    if "avito_bot" not in pth_content:
        pth_lines = [line.strip() for line in pth_content.splitlines() if line.strip()]
        if "." in pth_lines:
            idx = pth_lines.index(".") + 1
            pth_lines.insert(idx, "avito_bot")
        else:
            pth_lines.append("avito_bot")
        with open(pth_file, "w", encoding="utf-8") as f:
            f.write("\n".join(pth_lines) + "\n")
        print("  [+] avito_bot added to python311._pth")

# 7. Создаем минимальные надежные загрузочные скрипты-обертки
gw_wrapper = '''import sys, os
cur_dir = os.path.dirname(os.path.abspath(__file__))
if cur_dir not in sys.path:
    sys.path.insert(0, cur_dir)

import importlib.util
pyd_path = os.path.join(cur_dir, "gateway.cp311-win_amd64.pyd")
if os.path.exists(pyd_path):
    spec = importlib.util.spec_from_file_location("gateway", pyd_path)
    gw_mod = importlib.util.module_from_spec(spec)
    sys.modules["gateway"] = gw_mod
    spec.loader.exec_module(gw_mod)
else:
    import gateway as gw_mod

if __name__ == "__main__":
    gw_mod.main()
'''
with open(os.path.join(APP_DIR, "gateway.py"), "w", encoding="utf-8") as f:
    f.write(gw_wrapper)

srv_wrapper = '''import sys, os
cur_dir = os.path.dirname(os.path.abspath(__file__))
if cur_dir not in sys.path:
    sys.path.insert(0, cur_dir)

import importlib.util
pyd_path = os.path.join(cur_dir, "server.cp311-win_amd64.pyd")
if os.path.exists(pyd_path):
    spec = importlib.util.spec_from_file_location("server", pyd_path)
    srv_mod = importlib.util.module_from_spec(spec)
    sys.modules["server"] = srv_mod
    spec.loader.exec_module(srv_mod)
else:
    import server as srv_mod

if __name__ == "__main__":
    srv_mod.main()
'''
with open(os.path.join(APP_DIR, "server.py"), "w", encoding="utf-8") as f:
    f.write(srv_wrapper)

bot_wrapper_code = '''import sys, os
cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
for p in (cur_dir, parent_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

import importlib.util
pyd_path = os.path.join(cur_dir, "bot.cp311-win_amd64.pyd")
if os.path.exists(pyd_path):
    spec = importlib.util.spec_from_file_location("bot", pyd_path)
    bot_mod = importlib.util.module_from_spec(spec)
    sys.modules["bot"] = bot_mod
    spec.loader.exec_module(bot_mod)
else:
    import bot as bot_mod

import asyncio

if __name__ == "__main__":
    if hasattr(bot_mod, "acquire_single_instance_mutex"):
        bot_mod.acquire_single_instance_mutex()
    if hasattr(bot_mod, "write_pid_file"):
        bot_mod.write_pid_file()
    try:
        asyncio.run(bot_mod.main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        if hasattr(bot_mod, "remove_pid_file"):
            bot_mod.remove_pid_file()
'''
with open(os.path.join(bot_dir, "bot.py"), "w", encoding="utf-8") as f:
    f.write(bot_wrapper_code)

pw_wrapper_code = '''import sys, os
cur_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(cur_dir)
for p in (cur_dir, parent_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

import importlib.util
pyd_path = os.path.join(cur_dir, "proxy_worker.cp311-win_amd64.pyd")
if os.path.exists(pyd_path):
    spec = importlib.util.spec_from_file_location("proxy_worker", pyd_path)
    pw_mod = importlib.util.module_from_spec(spec)
    sys.modules["proxy_worker"] = pw_mod
    spec.loader.exec_module(pw_mod)
else:
    import proxy_worker as pw_mod

if __name__ == "__main__":
    pw_mod.main()
'''
with open(os.path.join(bot_dir, "proxy_worker.py"), "w", encoding="utf-8") as f:
    f.write(pw_wrapper_code)

# 8. Создаем быстрый лаунчер запуска AvitoHunter
bat_content = '''@echo off
chcp 65001 >nul
title AvitoHunter Server [Console]
cd /d "%~dp0"
echo [*] Запуск AvitoHunter...
if exist "%~dp0python.exe" (
    "%~dp0python.exe" gateway.py
) else (
    python.exe gateway.py
)
if %errorlevel% neq 0 (
    echo.
    echo [!] Программа завершилась с кодом ошибки: %errorlevel%
    pause
)
'''
with open(os.path.join(APP_DIR, "AvitoHunter_Start.bat"), "w", encoding="utf-8") as f:
    f.write(bat_content)
with open(os.path.join(APP_DIR, "SkyBot_Start.bat"), "w", encoding="utf-8") as f:
    f.write(bat_content)

print("\n[SUCCESS] Сборка завершена в:", APP_DIR)
