# -*- coding: utf-8 -*-
"""
Скрипт локальной очистки меток триала и лицензий ТОЛЬКО на компьютере с Windows 11.
ВНИМАНИЕ: Облачная база в Telegram-канале НЕ затрагивается, что позволяет проверить
работу облачной защиты от повторной активации триала после удаления файлов.
"""

import os
import sys
import json
import shutil
import sqlite3

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

print("[*] Запуск локальной очистки меток триала в Windows 11 (облако Telegram НЕ затрагивается)...")

# 1. Реестр Windows (HKCU)
if sys.platform == "win32":
    import winreg
    reg_paths = [
        r"Software\SkyBaseAudit",
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\CLSID\{e8b91a7d-5a91-4c92-bf31-92b4a3a5f82c}"
    ]
    for rpath in reg_paths:
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rpath)
            print(f"  [+] Удален раздел реестра: HKCU\\{rpath}")
        except FileNotFoundError:
            print(f"  [-] Раздел реестра не найден: HKCU\\{rpath}")
        except Exception:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rpath, 0, winreg.KEY_SET_VALUE) as k:
                    for val_name in ["trial_sig", "trial_expires", "trial_activated", "hw_sig"]:
                        try:
                            winreg.DeleteValue(k, val_name)
                            print(f"  [+] Удален параметр {val_name} в HKCU\\{rpath}")
                        except Exception:
                            pass
            except Exception as e:
                print(f"  [!] Очистка реестра HKCU\\{rpath}: {e}")

# 2. ProgramData
pdata_dir = os.environ.get("ProgramData", r"C:\ProgramData")
sb_pdata = os.path.join(pdata_dir, "SkyBase")
trial_pdata_file = os.path.join(sb_pdata, ".sys_hwid_trial.dat")
if os.path.exists(trial_pdata_file):
    try:
        os.remove(trial_pdata_file)
        print(f"  [+] Удален файл: {trial_pdata_file}")
    except Exception as e:
        print(f"  [!] Ошибка удаления {trial_pdata_file}: {e}")
if os.path.exists(sb_pdata) and not os.listdir(sb_pdata):
    try:
        shutil.rmtree(sb_pdata)
        print(f"  [+] Удалена пустая папка: {sb_pdata}")
    except Exception:
        pass

# 3. LocalAppData
local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
sb_local = os.path.join(local_app_data, "SkyBase")
audit_file = os.path.join(sb_local, "sys_audit.json")
if os.path.exists(audit_file):
    try:
        os.remove(audit_file)
        print(f"  [+] Удален файл: {audit_file}")
    except Exception as e:
        print(f"  [!] Ошибка удаления {audit_file}: {e}")

# 4. Базы данных SQLite (hwid_trials)
db_paths = [
    r"E:\ins\skybase\Avito-Parser3\skybase\avito_bot\avito_bot.db",
    r"E:\ins\skybase\skybotparser\app\avito_bot\avito_bot.db",
    r"C:\Program Files (x86)\AvitoHunter\avito_bot\avito_bot.db"
]
for db_p in db_paths:
    if os.path.exists(db_p):
        try:
            with sqlite3.connect(db_p) as conn:
                cur = conn.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hwid_trials'")
                if cur.fetchone():
                    cur.execute("DELETE FROM hwid_trials")
                    conn.commit()
                    cur.execute("VACUUM")
                    print(f"  [+] Очищена таблица hwid_trials в: {db_p}")
        except Exception as e:
            print(f"  [!] Ошибка в {db_p}: {e}")

# 5. Каталоги data (devices.json, dispensed_keys.json, activation_locks.json, users.json)
data_dirs = [
    r"E:\ins\skybase\Avito-Parser3\skybase\data",
    r"E:\ins\skybase\skybotparser\app\data",
    r"C:\Program Files (x86)\AvitoHunter\data"
]
for ddir in data_dirs:
    if not os.path.exists(ddir):
        continue
    dev_f = os.path.join(ddir, "devices.json")
    try:
        with open(dev_f, "w", encoding="utf-8") as f:
            f.write("{}\n")
        print(f"  [+] Сброшен: {dev_f}")
    except Exception as e:
        print(f"  [!] Примечание по {dev_f}: {e}")

    disp_f = os.path.join(ddir, "dispensed_keys.json")
    if os.path.exists(disp_f):
        try:
            with open(disp_f, "w", encoding="utf-8") as f:
                f.write("{}\n")
            print(f"  [+] Сброшен: {disp_f}")
        except Exception as e:
            print(f"  [!] Примечание по {disp_f}: {e}")

    locks_f = os.path.join(ddir, "activation_locks.json")
    try:
        with open(locks_f, "w", encoding="utf-8") as f:
            f.write("{}\n")
        print(f"  [+] Сброшен: {locks_f}")
    except Exception as e:
        print(f"  [!] Примечание по {locks_f}: {e}")

    users_f = os.path.join(ddir, "users.json")
    if os.path.exists(users_f):
        try:
            with open(users_f, "r", encoding="utf-8-sig") as f:
                users = json.load(f)
            for u in users:
                perms = u.get("permissions", {})
                perms.pop("active_key", None)
                perms.pop("hwid_token", None)
                perms.pop("hwid_mac", None)
                perms.pop("hwid_request_id", None)
                perms.pop("avito_expires_at", None)
                perms.pop("is_expired", None)
                perms.pop("unlimited", None)
            with open(users_f, "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
            print(f"  [+] Сброшены поля лицензий в: {users_f}")
        except Exception as e:
            print(f"  [!] Примечание по {users_f}: {e}")

print("\n[ВНИМАНИЕ] Облачная база в Telegram сохранена БЕЗ изменений!")
print("[ВНИМАНИЕ] При запуске AvitoHunter облачный сервис защитит триал от повторной активации.")
print("\n[SUCCESS] Локальные файлы Windows полностью удалены!")
