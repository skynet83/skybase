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

print("[*] Starting complete reset of trial marks and licenses in Windows 11 and program data...")

# 1. Реестр Windows (HKCU)
if sys.platform == "win32":
    import winreg
    reg_paths = [
        r"Software\SkyBaseAudit",
        r"Software\Microsoft\Windows\CurrentVersion\Explorer\CLSID\{e8b91a7d-5a91-4c92-bf31-92b4a3a5f82c}"
    ]
    for rpath in reg_paths:
        try:
            # Сначала пробуем удалить сам ключ
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, rpath)
            print(f"  [+] Deleted registry key: HKCU\\{rpath}")
        except FileNotFoundError:
            print(f"  [-] Registry key not found: HKCU\\{rpath}")
        except Exception:
            # Если не удалось удалить ключ целиком, удаляем значения
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rpath, 0, winreg.KEY_SET_VALUE) as k:
                    for val_name in ["trial_sig", "trial_expires", "trial_activated", "hw_sig"]:
                        try:
                            winreg.DeleteValue(k, val_name)
                            print(f"  [+] Deleted reg value {val_name} in HKCU\\{rpath}")
                        except Exception:
                            pass
            except Exception as e:
                print(f"  [!] Reg cleanup note for HKCU\\{rpath}: {e}")

# 2. ProgramData
pdata_dir = os.environ.get("ProgramData", r"C:\ProgramData")
sb_pdata = os.path.join(pdata_dir, "SkyBase")
trial_pdata_file = os.path.join(sb_pdata, ".sys_hwid_trial.dat")
if os.path.exists(trial_pdata_file):
    try:
        os.remove(trial_pdata_file)
        print(f"  [+] Deleted: {trial_pdata_file}")
    except Exception as e:
        print(f"  [!] Error deleting {trial_pdata_file}: {e}")
if os.path.exists(sb_pdata) and not os.listdir(sb_pdata):
    try:
        shutil.rmtree(sb_pdata)
        print(f"  [+] Removed empty dir: {sb_pdata}")
    except Exception:
        pass

# 3. LocalAppData
local_app_data = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
sb_local = os.path.join(local_app_data, "SkyBase")
audit_file = os.path.join(sb_local, "sys_audit.json")
if os.path.exists(audit_file):
    try:
        os.remove(audit_file)
        print(f"  [+] Deleted: {audit_file}")
    except Exception as e:
        print(f"  [!] Error deleting {audit_file}: {e}")

# 4. Базы данных SQLite (hwid_trials) во всех каталогах проекта и установленной программы
db_paths = [
    r"D:\ins\skybase\Avito-Parser3\skybase\avito_bot\avito_bot.db",
    r"D:\ins\skybase\skybotparser\app\avito_bot\avito_bot.db",
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
                    print(f"  [+] Cleared hwid_trials table in: {db_p}")
        except Exception as e:
            print(f"  [!] Error clearing {db_p}: {e}")

# 5. Каталоги data (devices.json, dispensed_keys.json, activation_locks.json, users.json, license.json)
data_dirs = [
    r"D:\ins\skybase\Avito-Parser3\skybase\data",
    r"D:\ins\skybase\skybotparser\app\data",
    r"C:\Program Files (x86)\AvitoHunter\data"
]
for ddir in data_dirs:
    if not os.path.exists(ddir):
        continue
    # devices.json
    dev_f = os.path.join(ddir, "devices.json")
    try:
        with open(dev_f, "w", encoding="utf-8") as f:
            f.write("{}\n")
        print(f"  [+] Reset {dev_f}")
    except Exception as e:
        print(f"  [!] Note on {dev_f}: {e}")

    # dispensed_keys.json
    disp_f = os.path.join(ddir, "dispensed_keys.json")
    if os.path.exists(disp_f):
        try:
            with open(disp_f, "w", encoding="utf-8") as f:
                f.write("{}\n")
            print(f"  [+] Reset {disp_f}")
        except Exception as e:
            print(f"  [!] Note on {disp_f}: {e}")

    # activation_locks.json
    locks_f = os.path.join(ddir, "activation_locks.json")
    try:
        with open(locks_f, "w", encoding="utf-8") as f:
            f.write("{}\n")
        print(f"  [+] Reset {locks_f}")
    except Exception as e:
        print(f"  [!] Note on {locks_f}: {e}")

    # license.json
    lic_f = os.path.join(ddir, "license.json")
    if os.path.exists(lic_f):
        try:
            os.remove(lic_f)
            print(f"  [+] Removed {lic_f}")
        except Exception as e:
            print(f"  [!] Note on {lic_f}: {e}")

    # users.json
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
                perms["avito_duration"] = "expired"
                perms["is_expired"] = True
            with open(users_f, "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
            print(f"  [+] Reset license fields in {users_f}")
        except Exception as e:
            print(f"  [!] Note on {users_f}: {e}")

# 6. Очистка облачной базы в закрытом Telegram-канале AvitoHunter Лицензии
try:
    import urllib.request, urllib.parse
    token = '8501191397:AAHwEhKIn745c2XocTq-WX_lcXMEEqsSjeg'
    chat_id = '-1003716161270'
    proxy_h = urllib.request.ProxyHandler({'https': 'http://85.8.47.207:7080', 'http': 'http://85.8.47.207:7080'})
    opener = urllib.request.build_opener(proxy_h)
    res_chat = json.loads(opener.open(f'https://api.telegram.org/bot{token}/getChat?chat_id={chat_id}', timeout=8).read())
    pm = res_chat['result'].get('pinned_message')
    if pm:
        mid = pm['message_id']
        clean_text = '🛡️ ОБЛАЧНАЯ БАЗА ЛИЦЕНЗИЙ AVITOHUNTER\n[HWID_REGISTRY:ACTIVE]\n[]'
        edit_data = urllib.parse.urlencode({'chat_id': chat_id, 'message_id': mid, 'text': clean_text}).encode()
        try:
            opener.open(f'https://api.telegram.org/bot{token}/editMessageText', data=edit_data, timeout=8)
            print("  [+] Облачная база в Telegram-канале успешно очищена: []")
        except urllib.error.HTTPError as he:
            err_b = he.read().decode('utf-8', errors='ignore')
            if "message is not modified" in err_b:
                print("  [+] Облачная база в Telegram-канале уже чистая: []")
            else:
                print(f"  [!] Telegram error: {err_b}")
except Exception as e:
    print(f"  [!] Примечание по Telegram: {e}")

print("\n[SUCCESS] Все метки триала в Windows 11 и облаке Telegram сброшены в состояние 0!")
