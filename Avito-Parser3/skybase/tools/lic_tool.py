# -*- coding: utf-8 -*-
"""
ElectroBase / SkyBase License & Developer Micro-Tool (lic_tool.py)
Ускоряет разработку, тестирование и экономит контекст/токены LLM-агента.

Команды:
  python tools/lic_tool.py status           - Компактный статус (сервер, бот, лицензия, триал, чат)
  python tools/lic_tool.py reset            - Полная очистка баз, ключей, истории чата и сброс на "неактивирован"
  python tools/lic_tool.py gen [req_id] [d] - Генерация валидного V3 ключа (по умолч. 3 дня триал для локального ПК)
  python tools/lic_tool.py activate <key>   - Тестовая активация ключа через API
  python tools/lic_tool.py test-flow        - Полный автотест цикла: сброс -> генерация -> pending -> активация -> проверка
  python tools/lic_tool.py chat             - Просмотр последних сообщений чата окна активации
  python tools/lic_tool.py logs             - Компактный просмотр последних значимых событий (без спама прокси)
"""

import os
import sys
import json
import re
import datetime
import urllib.request
import urllib.error

# Настройка UTF-8 вывода
try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

DATA_DIR = os.path.join(BASE_DIR, "data")
KM_DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "SkyBase_KeyManager", "data")

try:
    import hwid_security
except ImportError:
    hwid_security = None

try:
    import devices_db
except ImportError:
    devices_db = None


def get_local_id() -> str:
    """Возвращает аппаратный request_id текущего ПК."""
    if hwid_security:
        try:
            return hwid_security.get_local_hwid_fingerprint().get("request_id", "EBID-UNKNOWN")
        except Exception:
            pass
    return "EBID-1AEC-084C-7AE5-B16D-FABF"


def cmd_status():
    """Компактный статус системы в одну сводку."""
    req_id = get_local_id()
    
    # 1. Проверка API лицензии
    lic_info = {}
    try:
        url = f"http://127.0.0.1:8081/api/license/status?username=skynet83&request_id={req_id}&device_type=pc"
        req = urllib.request.Request(url, headers={"User-Agent": "lic_tool"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            lic_info = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        lic_info = {"error": str(e)}

    # 2. База устройств
    devs = {}
    if devices_db:
        try:
            devs = devices_db.load_devices()
        except Exception:
            pass

    # 3. Чат
    chat_path = os.path.join(DATA_DIR, "chat_messages.json")
    chat_count = 0
    if os.path.exists(chat_path):
        try:
            with open(chat_path, "r", encoding="utf-8-sig") as f:
                chat_count = len(json.load(f))
        except Exception:
            pass

    # 4. Процесс бота через psutil
    bot_info = "⚪ НЕ ОБНАРУЖЕН"
    try:
        import psutil
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmd = " ".join(p.info.get('cmdline') or []).lower()
                if "bot.py" in cmd and "python" in p.info.get('name', '').lower():
                    bot_info = f"🟢 ЗАПУЩЕН (PID {p.info['pid']})"
                    break
            except Exception:
                pass
    except Exception:
        pass

    print("=" * 60)
    print(f"🖥️  ID ПК:       {req_id}")
    print(f"🤖 Telegram Бот: {bot_info}")
    print(f"🌐 HTTP 8081:   {'🟢 ДОСТУПЕН' if 'error' not in lic_info else '🔴 НЕДОСТУПЕН'}")
    print("-" * 60)
    print(f"📋 Лицензия:    {lic_info.get('tariff_label', 'Н/Д')} (Истек: {lic_info.get('is_expired')})")
    print(f"🔑 Активный ключ: {lic_info.get('active_key') or '—'}")
    print(f"🎁 Триал использ: {lic_info.get('trial_used', False)}")
    print(f"🔒 Блокировка:   {lic_info.get('is_blocked', False)} (попыток: {lic_info.get('attempts', 0)}/3)")
    print(f"💾 Устройств:    {len(devs)} в реестре devices.json")
    print(f"💬 Сообщений:    {chat_count} в chat_messages.json")
    print("=" * 60)


def cmd_reset():
    """Полный сброс всех данных для чистого теста триала (ПК, Телефон, KeyManager)."""
    # 0. Останавливаем процессы KeyManager, если они запущены в памяти
    try:
        import subprocess
        subprocess.run(["taskkill", "/F", "/IM", "KeyManager.exe"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass

    targets_empty_obj = [
        os.path.join(DATA_DIR, "devices.json"),
        os.path.join(KM_DATA_DIR, "devices.json"),
        os.path.join(DATA_DIR, "dispensed_keys.json"),
        os.path.join(KM_DATA_DIR, "dispensed_keys.json"),
        os.path.join(DATA_DIR, "activation_lock.json"),
        os.path.join(DATA_DIR, "activation_locks.json")
    ]
    for p in targets_empty_obj:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write("{}")

    with open(os.path.join(DATA_DIR, "activated_devices.json"), "w", encoding="utf-8") as f:
        json.dump({"devices": []}, f, indent=2)

    with open(os.path.join(DATA_DIR, "activation_history.json"), "w", encoding="utf-8") as f:
        json.dump({"history": []}, f, indent=2)

    with open(os.path.join(DATA_DIR, "license.json"), "w", encoding="utf-8") as f:
        json.dump({"status": "unactivated", "expires_at": None, "tariff_name": "Не активирован", "is_expired": True}, f, ensure_ascii=False, indent=2)

    with open(os.path.join(DATA_DIR, "chat_messages.json"), "w", encoding="utf-8-sig") as f:
        f.write("[]")

    km_state_path = os.path.join(KM_DATA_DIR, "key_manager_state.json")
    if os.path.exists(km_state_path):
        try:
            with open(km_state_path, "w", encoding="utf-8") as f:
                json.dump({
                    "total_activations": 0,
                    "total_passwords_issued": 0,
                    "last_activity": None,
                    "server_start_time": None,
                    "uptime_days": 0,
                    "version": "2.1.0",
                    "auto_backup": True,
                    "backup_interval_hours": 24,
                    "last_backup": None
                }, f, indent=2)
        except Exception:
            pass

    u_path = os.path.join(DATA_DIR, "users.json")
    if os.path.exists(u_path):
        with open(u_path, "r", encoding="utf-8") as f:
            users = json.load(f)
        for u in users:
            perms = u.setdefault("permissions", {})
            perms["avito"] = False
            perms["avito_bot"] = False
            perms["avito_duration"] = "expired"
            perms["avito_expires_at"] = None
            perms["is_expired"] = True
            perms["active_key"] = None
            perms["monitoring"] = False
            perms["tg_bot"] = False
            perms["hwid_token"] = None
            perms["hwid_mac"] = None
            perms["hwid_request_id"] = None
            u["sessions"] = {}
            if u.get("username") == "skynet83":
                u["telegram_chat_id"] = 5680198246
                u["telegram_username"] = "skynet19081983"
        with open(u_path, "w", encoding="utf-8") as f:
            json.dump(users, f, ensure_ascii=False, indent=2)

    print("✅ ВСЕ ДАННЫЕ ОЧИЩЕНЫ: устройства, ключи, блокировки, чат сброшены на исходный 'неактивирован'.")
    print("   В KeyManager база устройств и список выданных ключей полностью очищены.")


def cmd_gen_key(req_id: str = None, days: int = 3, bind_pending: bool = True):
    """Генерирует ответный ключ V3 и опционально регистрирует его как pending."""
    target_id = req_id or get_local_id()
    if not hwid_security:
        print("❌ Ошибка: модуль hwid_security недоступен.")
        return None

    now = datetime.datetime.now()
    exp_dt = now + datetime.timedelta(days=int(days))
    is_vip = (days >= 9999)

    tier = "unlimited" if is_vip else f"{days}_days"
    key = hwid_security.generate_response_key(target_id, tier=tier, expires_date=exp_dt)
    
    tier_name = f"Триал {days} дн." if days <= 3 else f"{days} дней"
    if is_vip:
        tier_name = "👑 VIP Безлимит"

    if bind_pending and devices_db:
        devices_db.register_or_bind_password(
            req_id_str=target_id,
            new_key=key,
            tier=tier,
            client_name="skynet83",
            notes="Выдан через lic_tool",
            reason="Тестовая выдача ключа",
            tier_name=tier_name,
            exact_valid_until=exp_dt.strftime("%Y-%m-%d %H:%M:%S") if not is_vip else "Бессрочно (VIP)",
            is_activated=False
        )

    print(f"🔑 Сгенерирован ключ ({tier_name}): {key}")
    print(f"📌 Закреплен в статусе: {'PENDING (ожидает активации на сайте)' if bind_pending else 'ТОЛЬКО ВЫВОД'}")
    return key


def cmd_activate(key: str, req_id: str = None):
    """Активирует ключ через локальный API."""
    target_id = req_id or get_local_id()
    url = "http://127.0.0.1:8081/api/license/activate"
    payload = json.dumps({
        "key": key,
        "username": "skynet83",
        "request_id": target_id,
        "device_type": "pc"
    }).encode("utf-8")

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print("Результат активации:", json.dumps(data, ensure_ascii=False, indent=2))
            return data
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="ignore")
        print(f"❌ Ошибка {e.code}: {err_body}")
        return {"error": err_body}
    except Exception as e:
        print(f"❌ Ошибка подключения: {e}")
        return {"error": str(e)}


def cmd_test_flow():
    """Полный сквозной автотест триала (сброс -> pending -> ручная активация -> проверка)."""
    print("▶️ [Шаг 1/5] Сброс всех баз на 'чистый лист'...")
    cmd_reset()

    req_id = get_local_id()
    print(f"\n▶️ [Шаг 2/5] Проверка исходного статуса (должен быть unactivated)...")
    url_st = f"http://127.0.0.1:8081/api/license/status?username=skynet83&request_id={req_id}&device_type=pc"
    with urllib.request.urlopen(url_st, timeout=2) as r:
        st = json.loads(r.read().decode("utf-8"))
    assert st.get("is_expired") is True, f"ОШИБКА: is_expired={st.get('is_expired')} (ожидалось True)"
    assert st.get("trial_used") is False, f"ОШИБКА: trial_used={st.get('trial_used')} (ожидалось False)"
    print("  ✅ Исходный статус корректен: Требуется активация, триал не использован.")

    print(f"\n▶️ [Шаг 3/5] Генерация и выдача триал-ключа (3 дня)...")
    key = cmd_gen_key(req_id, days=3, bind_pending=True)
    assert key, "Ключ не сгенерирован!"

    print(f"\n▶️ [Шаг 4/5] Проверка статуса ДО активации (НЕ должен активироваться сам!)...")
    with urllib.request.urlopen(url_st, timeout=2) as r:
        st_pre = json.loads(r.read().decode("utf-8"))
    assert st_pre.get("is_expired") is True, "ОШИБКА: ключ активировался сам до ввода пользователем!"
    assert st_pre.get("trial_used") is False, "ОШИБКА: trial_used стал True до активации!"
    print("  ✅ Ключ ожидает ввода (pending), сайт НЕ активировался сам!")

    print(f"\n▶️ [Шаг 5/5] Эмуляция ручной активации ключа пользователем на сайте...")
    act_res = cmd_activate(key, req_id)
    assert act_res.get("success") is True, f"ОШИБКА активации: {act_res}"

    with urllib.request.urlopen(url_st, timeout=2) as r:
        st_post = json.loads(r.read().decode("utf-8"))
    assert st_post.get("is_expired") is False, "ОШИБКА: лицензия не стала активной!"
    assert st_post.get("trial_used") is True, "ОШИБКА: trial_used не стал True после активации!"
    assert st_post.get("active_key") == key, f"ОШИБКА: active_key не совпадает: {st_post.get('active_key')}"
    print(f"  ✅ УСПЕХ: Лицензия активна, триал зафиксирован, ключ {key} принят!")
    print("\n🎉 ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО! Ручной цикл триала работает на 100%.")


def cmd_chat_test():
    """Проверяет строгую изоляцию чата между ПК и Телефоном через API сервера."""
    test_ids = [
        ("ПК", "EBID-1AEC-084C-7AE5-B16D-FABF"),
        ("Телефон", "EBMOB-7D21-C3F9-23C2-AFC1-6F53")
    ]
    print("=== [ТЕСТ ИЗОЛЯЦИИ ЧАТА УСТРОЙСТВ] ===")
    for dev_type, rid in test_ids:
        url = f"http://127.0.0.1:8081/api/chat/messages?username=skynet83&request_id={rid}"
        req = urllib.request.Request(url, headers={"User-Agent": "lic_tool"})
        try:
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                msgs = data.get("messages", [])
                print(f"\n📱 Устройство: {dev_type} ({rid})")
                print(f"   Сообщений в диалоге: {len(msgs)}, Непрочитанных: {data.get('unread_count')}")
                for m in msgs:
                    s = m.get("sender", "")
                    r = m.get("recipient", "")
                    sid = m.get("sender_id", "")
                    txt = m.get("text", "")[:50].replace("\n", " ")
                    # Проверяем, что нет утечки чужого ID
                    other_id = [x[1] for x in test_ids if x[1] != rid][0]
                    if other_id.lower() in str(m).lower():
                        print(f"   ❌ УТЕЧКА! Сообщение содержит чужой ID {other_id}: {txt}")
                    else:
                        print(f"   ✅ [{s}] -> [{r}]: {txt}")
        except Exception as e:
            print(f"   ❌ Ошибка запроса к серверу: {e}")
    print("\n=== Проверка изоляции завершена ===")


def cmd_chat_send(text: str, sender: str = "skynet83", recipient: str = "admin"):
    """Отправляет тестовое сообщение в чат."""
    chat_path = os.path.join(DATA_DIR, "chat_messages.json")
    msgs = []
    if os.path.exists(chat_path):
        try:
            with open(chat_path, "r", encoding="utf-8-sig") as f:
                msgs = json.load(f)
        except Exception:
            msgs = []
    
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    msg_id = f"msg_{int(datetime.datetime.now().timestamp()*1000)}_{len(msgs)+1}"
    new_m = {
        "id": msg_id,
        "sender": sender,
        "sender_id": sender,
        "sender_name": "Администратор" if sender in ("admin", "skynet83") else f"ПК ({sender[:10]}...)",
        "recipient": recipient,
        "text": text,
        "created_at": now_str,
        "is_read": False
    }
    msgs.append(new_m)
    with open(chat_path, "w", encoding="utf-8-sig") as f:
        json.dump(msgs, f, ensure_ascii=False, indent=2)
    print(f"✉️ Сообщение добавлено в чат (ID: {msg_id}): {text}")



def cmd_logs(n: int = 15):
    """Показывает последние значимые логи бота без спама проверки прокси."""
    log_path = os.path.join(BASE_DIR, "avito_bot", "bot.log")
    if not os.path.exists(log_path):
        print("Файл bot.log не найден.")
        return
    with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    
    meaningful = [
        l.strip() for l in lines 
        if not any(skip in l for skip in ["Добор прокси", "Таймаут одного раунда", "Саморегуляция скорости", "Следующий цикл опроса"])
    ]
    print(f"--- Последние {min(n, len(meaningful))} событий из bot.log ---")
    for l in meaningful[-n:]:
        print(l)


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("status", "st"):
        cmd_status()
    elif args[0] in ("reset", "clean"):
        cmd_reset()
    elif args[0] in ("gen", "gen-key"):
        req = args[1] if len(args) > 1 else None
        days = int(args[2]) if len(args) > 2 else 3
        cmd_gen_key(req, days=days)
    elif args[0] in ("activate", "act"):
        if len(args) < 2:
            print("Использование: python tools/lic_tool.py activate <KEY> [REQ_ID]")
            return
        cmd_activate(args[1], args[2] if len(args) > 2 else None)
    elif args[0] in ("test-flow", "test"):
        cmd_test_flow()
    elif args[0] in ("chat-test", "chat_test", "iso-test"):
        cmd_chat_test()
    elif args[0] in ("chat", "msgs"):
        n = int(args[1]) if len(args) > 1 else 5
        cmd_chat(n)
    elif args[0] in ("chat-send", "send"):
        if len(args) < 2:
            print("Использование: python tools/lic_tool.py chat-send <TEXT> [SENDER] [RECIPIENT]")
            return
        snd = args[2] if len(args) > 2 else "skynet83"
        rcp = args[3] if len(args) > 3 else "admin"
        cmd_chat_send(args[1], sender=snd, recipient=rcp)
    elif args[0] in ("logs", "log"):
        n = int(args[1]) if len(args) > 1 else 15
        cmd_logs(n)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
