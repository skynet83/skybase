# -*- coding: utf-8 -*-
"""
Модуль базы данных устройств и закрепленных паролей (Device & Password Registry).
Обеспечивает:
1. Хранение реестра клиентских устройств (ID, MAC-адрес, сигнатура ПК, имя клиента, заметки).
2. Хранение полной истории ВСЕХ паролей/ключей, выданных каждому устройству:
   - Пароль №1 (первичная выдача)
   - Пароль №2 (переустановка Windows, продление тарифа или замена)
   - Последующие пароли с датами, статусами (активен, заменен, архив) и причинами.
3. Сверку при вводе ID кода:
   - Быстрый поиск устройства по ID коду, MAC-адресу или ранее выданному паролю.
   - Определение, зарегистрировано ли устройство ранее.
   - Возможность закрепить второй/следующий пароль за найденным устройством.
"""

import os
import sys
import json
import re
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple

# Каталог данных с надежным автоматическим поиском
def find_data_dir() -> str:
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.extend([
            os.path.join(exe_dir, "data"),
            os.path.join(exe_dir, "SITE", "data"),
            os.path.join(os.path.dirname(exe_dir), "SITE", "data"),
            os.path.join(os.path.dirname(exe_dir), "data"),
        ])

    file_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.extend([
        os.path.join(file_dir, "data"),
        os.path.join(file_dir, "SITE", "data"),
        os.path.join(os.path.dirname(file_dir), "SITE", "data"),
        os.path.join(os.path.dirname(file_dir), "data"),
    ])

    for c in candidates:
        if os.path.exists(c) and (
            os.path.exists(os.path.join(c, "devices.json")) or 
            os.path.exists(os.path.join(c, "dispensed_keys.json")) or 
            os.path.exists(os.path.join(c, "users.json")) or 
            os.path.exists(os.path.join(c, "license_keys.json"))
        ):
            return c

    for c in candidates:
        if os.path.exists(c):
            return c

    fallback = os.path.join(file_dir, "data")
    os.makedirs(fallback, exist_ok=True)
    return fallback

DATA_DIR = find_data_dir()
DEVICES_JSON_PATH = os.path.join(DATA_DIR, "devices.json")
DISPENSED_PATH = os.path.join(DATA_DIR, "dispensed_keys.json")

def decode_key_valid_until(key_str: str) -> Tuple[str, str]:
    """Декодирует срок действия и наименование тарифа из ключа (поддерживает V3 с минутами, V2 и VIP)."""
    clean = re.sub(r"[^0-9A-Za-z]", "", key_str or "").upper()
    if clean.startswith("VIPX") or (len(clean) >= 8 and clean[4:8] == "FFFF"):
        return "Бессрочно (VIP)", "👑 VIP"
    if clean.startswith("EB30") and len(clean) == 20:
        import datetime as dt_mod
        base_epoch_dt = dt_mod.datetime(2026, 1, 1, 0, 0, 0)
        # 1. Формат V3: 6 hex-символов минут от 2026-01-01 00:00
        try:
            mins = int(clean[4:10], 16)
            if 0 < mins < 16777215:
                exp_dt = base_epoch_dt + dt_mod.timedelta(minutes=mins)
                if 2026 <= exp_dt.year <= 2057:
                    return f"{exp_dt.strftime('%Y-%m-%d %H:%M:%S')}", f"До {exp_dt.strftime('%d.%m.%Y %H:%M')}"
        except Exception:
            pass

        # 2. Формат V2: 4 hex-символа дней
        try:
            days = int(clean[4:8], 16)
            exp_date = dt_mod.date(2026, 1, 1) + dt_mod.timedelta(days=days)
            return f"{exp_date.strftime('%Y-%m-%d')} 23:59:59", f"До {exp_date.strftime('%d.%m.%Y')}"
        except Exception:
            pass
    return "—", "Стандарт"

def load_devices() -> Dict[str, Any]:
    """Загружает базу устройств из JSON файла."""
    if not os.path.exists(DEVICES_JSON_PATH):
        # Если файла нет, пытаемся инициализировать из dispensed_keys.json
        init_data = _migrate_from_dispensed()
        save_devices(init_data)
        return init_data
    try:
        with open(DEVICES_JSON_PATH, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
        for dev in data.values():
            pwds = dev.get("passwords", [])
            for p in pwds:
                if not p.get("valid_until"):
                    vu, _ = decode_key_valid_until(p.get("key", ""))
                    p["valid_until"] = vu

            if pwds:
                # Пароль считается активным только если он реально активирован на сайте (activated_on_site == True)
                truly_active = None
                for p in reversed(pwds):
                    if p.get("activated_on_site") and p.get("status") == "active":
                        truly_active = p
                        break
                if not truly_active:
                    for p in reversed(pwds):
                        if p.get("activated_on_site"):
                            truly_active = p
                            break

                if truly_active:
                    dev["active_key"] = truly_active.get("key", "")
                    dev["active_valid_until"] = truly_active.get("valid_until", "")
                    dev["active_tier"] = truly_active.get("tier", "30_days")
                    dev["active_tier_name"] = truly_active.get("tier_name", "")
                else:
                    dev["active_key"] = ""
                    dev["active_valid_until"] = ""
                    dev["active_tier_name"] = "Ожидает активации"
            else:
                if not dev.get("active_valid_until") or not dev.get("active_tier_name"):
                    vu, tn = decode_key_valid_until(dev.get("active_key", ""))
                    if not dev.get("active_valid_until"):
                        dev["active_valid_until"] = vu
                    if not dev.get("active_tier_name"):
                        dev["active_tier_name"] = tn
        return data
    except Exception as e:
        print(f"[ERR] Ошибка чтения {DEVICES_JSON_PATH}: {e}")
        return {}

def save_devices(data: Dict[str, Any]):
    """Атомарно сохраняет базу устройств в JSON файл и синхронизирует общий реестр."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp_path = DEVICES_JSON_PATH + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            if os.path.exists(DEVICES_JSON_PATH):
                os.replace(tmp_path, DEVICES_JSON_PATH)
            else:
                os.rename(tmp_path, DEVICES_JSON_PATH)
        except PermissionError:
            with open(DEVICES_JSON_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[ERR] Ошибка сохранения {DEVICES_JSON_PATH}: {e}")

    # Двусторонняя синхронизация общего реестра (сайт и KeyManager)
    base_parent = os.path.dirname(os.path.abspath(__file__))
    proj_root = os.path.dirname(base_parent)
    alt_paths = [
        os.path.join(proj_root, "SkyBase_KeyManager", "data", "devices.json"),
        os.path.join(base_parent, "data", "devices.json"),
        r"C:\ins\Avito-Parser2\skybase\data\devices.json",
        r"C:\ins\Avito-Parser2\SkyBase_KeyManager\data\devices.json",
        r"C:\ins\Avito-Parser\skybase\data\devices.json",
        r"C:\ins\Avito-Parser\SkyBase_KeyManager\data\devices.json",
        r"C:\ins\skybase\data\devices.json",
        r"C:\ins\SkyBase_KeyManager\data\devices.json"
    ]
    for alt in alt_paths:
        try:
            if os.path.abspath(alt).lower() != os.path.abspath(DEVICES_JSON_PATH).lower():
                alt_dir = os.path.dirname(alt)
                if os.path.exists(alt_dir):
                    alt_tmp = alt + ".tmp"
                    with open(alt_tmp, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                    if os.path.exists(alt):
                        os.replace(alt_tmp, alt)
                    else:
                        os.rename(alt_tmp, alt)
        except Exception:
            pass

def _migrate_from_dispensed() -> Dict[str, Any]:
    """Миграция существующих записей из dispensed_keys.json в структуру базы устройств."""
    devices = {}
    if not os.path.exists(DISPENSED_PATH):
        return devices
    try:
        with open(DISPENSED_PATH, "r", encoding="utf-8-sig") as f:
            disp = json.load(f)
        for key_str, item in disp.items():
            req_id = item.get("request_id") or ""
            mac = item.get("mac") or ""
            mac_clean = re.sub(r"[^0-9A-Fa-f]", "", mac).upper()
            mac_tail = mac_clean[-4:] if len(mac_clean) >= 4 else "0000"
            sig_match = re.search(r"EBID-[0-9A-Fa-f]{4}-([0-9A-Fa-f]{4})", req_id)
            hw_sig = sig_match.group(1).upper() if sig_match else "0000"

            dev_id = f"DEV-{mac_tail}-{hw_sig}"
            tier = item.get("tier", "30_days")
            client = item.get("activated_by") or item.get("client_note") or "Клиент"

            devices[dev_id] = {
                "device_id": dev_id,
                "mac": mac or f"**:**:**:**:{mac_tail[:2]}:{mac_tail[2:]}",
                "mac_tail": mac_tail,
                "hw_sig": hw_sig,
                "request_id": req_id,
                "client_name": client,
                "notes": item.get("client_note", "Основной ПК"),
                "first_registered_at": item.get("dispensed_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "last_updated_at": item.get("dispensed_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "active_key": key_str,
                "active_tier": tier,
                "passwords": [
                    {
                        "index": 1,
                        "key": key_str,
                        "tier": tier,
                        "tier_name": "Бессрочно (VIP)" if tier == "unlimited" else "+30 дней",
                        "issued_at": item.get("dispensed_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "status": "active",
                        "reason": "Первичная активация",
                        "request_id": req_id,
                        "activated": bool(item.get("activated_by")),
                        "activated_at": item.get("dispensed_at") or ""
                    }
                ]
            }
    except Exception as ex:
        print(f"[WARN] Ошибка миграции dispensed_keys: {ex}")
    return devices

def normalize_key(k: str) -> str:
    """Нормализует 20-значный ключ с дефисами."""
    c = re.sub(r"[^0-9A-Za-z]", "", k or "").upper()
    if len(c) == 20:
        return f"{c[0:4]}-{c[4:8]}-{c[8:12]}-{c[12:16]}-{c[16:20]}"
    return c

def normalize_req_id(req: str) -> str:
    """Нормализует 20-значный ID код запроса (EBID-... или EBMOB-...)."""
    s = str(req or "").strip().upper()
    is_mob = s.startswith("EBMOB")
    if s.startswith("EBID"):
        s = s[4:].lstrip("-: ").strip()
    elif s.startswith("EBMOB"):
        s = s[5:].lstrip("-: ").strip()
    c = re.sub(r"[^0-9A-Fa-f]", "", s)
    if len(c) == 20:
        prefix = "EBMOB" if is_mob else "EBID"
        return f"{prefix}-{c[0:4]}-{c[4:8]}-{c[8:12]}-{c[12:16]}-{c[16:20]}"
    return req

def extract_device_identity(req_id_str: str) -> Tuple[str, str, str, str]:
    """
    Извлекает из ID кода (EBID-... или EBMOB-...):
    - dev_id: DEV-XXXX-YYYY или MOB-XXXX-YYYY
    - mac_tail (4 hex)
    - hw_sig (6 hex / первые 4 hex во второй секции)
    - dev_type: 'phone' или 'pc'
    """
    s = str(req_id_str or "").strip().upper()
    is_mob = s.startswith("EBMOB")
    if s.startswith("EBID"):
        s = s[4:].lstrip("-: ").strip()
    elif s.startswith("EBMOB"):
        s = s[5:].lstrip("-: ").strip()
    clean = re.sub(r"[^0-9A-Fa-f]", "", s)
    if len(clean) >= 8:
        mac_tail = clean[0:4]
        hw_sig = clean[4:8]
        if is_mob or mac_tail.startswith("MO"):
            dev_id = f"MOB-{mac_tail}-{hw_sig}"
            dev_type = "phone"
        else:
            dev_id = f"DEV-{mac_tail}-{hw_sig}"
            dev_type = "pc"
        return dev_id, mac_tail, hw_sig, dev_type
    return "DEV-UNKNOWN", "0000", "0000", "pc"

def find_device_by_req_id(req_id_str: str) -> Optional[Dict[str, Any]]:
    """Ищет устройство по ID коду запроса (по точному совпадению или по dev_id)."""
    devices = load_devices()
    norm_req = normalize_req_id(req_id_str)
    dev_id, mac_tail, hw_sig, dev_type = extract_device_identity(req_id_str)

    # 1. По точному dev_id
    if dev_id in devices:
        return devices[dev_id]

    # 2. По сохраненному request_id
    for dev in devices.values():
        if dev.get("request_id") == norm_req:
            return dev
        if dev.get("mac_tail") == mac_tail and mac_tail not in ("0000", "????"):
            if dev.get("device_type", "pc") == dev_type:
                return dev

    return None

def find_device_by_key(key_str: str) -> Optional[Tuple[Dict[str, Any], Dict[str, Any]]]:
    """
    Ищет устройство по любому когда-либо выданному ключу/паролю.
    Возвращает (устройство, запись_пароля).
    """
    devices = load_devices()
    norm_k = normalize_key(key_str)
    clean_k = re.sub(r"[^0-9A-Za-z]", "", key_str or "").upper()

    for dev in devices.values():
        for pwd in dev.get("passwords", []):
            p_k = pwd.get("key", "")
            if p_k == norm_k or re.sub(r"[^0-9A-Za-z]", "", p_k).upper() == clean_k:
                return dev, pwd

    return None

def search_devices(query: str) -> List[Dict[str, Any]]:
    """Полнотекстовый поиск устройств по ID, MAC, клиенту, заметкам или ключам."""
    devices = load_devices()
    q = (query or "").strip().lower()
    if not q:
        return list(devices.values())

    clean_q = re.sub(r"[^0-9a-zа-яё]", "", q)
    results = []

    for dev in devices.values():
        score = 0
        dev_id = dev.get("device_id", "").lower()
        client = dev.get("client_name", "").lower()
        notes = dev.get("notes", "").lower()
        mac = dev.get("mac", "").lower()
        req_id = dev.get("request_id", "").lower()

        if q in dev_id or q in client or q in notes or q in mac or q in req_id:
            score += 10
        if clean_q and (clean_q in re.sub(r"[^0-9a-zа-яё]", "", dev_id) or
                        clean_q in re.sub(r"[^0-9a-zа-яё]", "", client) or
                        clean_q in re.sub(r"[^0-9a-zа-яё]", "", mac)):
            score += 5

        # Поиск по паролям устройства
        for pwd in dev.get("passwords", []):
            pk = pwd.get("key", "").lower()
            if q in pk or (clean_q and clean_q in re.sub(r"[^0-9a-z]", "", pk)):
                score += 8
                break

        if score > 0:
            results.append((score, dev))

    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results]

def register_or_bind_password(
    req_id_str: str,
    new_key: str,
    tier: str = "30_days",
    client_name: str = "",
    notes: str = "",
    reason: str = "Выдача пароля",
    existing_dev_id: Optional[str] = None,
    tier_name: Optional[str] = None,
    exact_valid_until: Optional[str] = None,
    is_activated: bool = False
) -> Dict[str, Any]:
    """
    Основная операция выдачи и закрепления пароля за устройством:
    - Если устройство уже есть в базе:
      Закрепляет НОВЫЙ (второй / следующий) пароль за этим устройством,
      архивирует предыдущий активный пароль, обновляет данные.
    - Если устройство новое:
      Создает новую карточку устройства в базе и закрепляет за ним Пароль №1.
    """
    devices = load_devices()
    norm_req = normalize_req_id(req_id_str)
    norm_key = normalize_key(new_key)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Определение целевого устройства
    dev = None
    if existing_dev_id and existing_dev_id in devices:
        dev = devices[existing_dev_id]
    else:
        dev = find_device_by_req_id(req_id_str)

    is_new = (dev is None)
    if not tier_name:
        tier_name = "Бессрочно (VIP)" if tier in ("unlimited", "vip", "vipx") else "+30 дней"

    if is_new:
        dev_id, mac_tail, hw_sig, dev_type = extract_device_identity(req_id_str)
        default_notes = "Мобильное устройство (Телефон)" if dev_type == "phone" else "Первичное добавление устройства"
        dev = {
            "device_id": dev_id,
            "device_type": dev_type,
            "mac": f"**:**:**:**:{mac_tail[:2]}:{mac_tail[2:]}" if dev_type == "pc" else f"MOB-ID:{mac_tail}",
            "mac_tail": mac_tail,
            "hw_sig": hw_sig,
            "request_id": norm_req,
            "client_name": client_name or "skynet83",
            "notes": notes or default_notes,
            "first_registered_at": now_str,
            "last_updated_at": now_str,
            "active_key": norm_key if is_activated else "",
            "active_tier": tier,
            "active_tier_name": tier_name if is_activated else "Ожидает активации",
            "active_valid_until": "",
            "passwords": []
        }
        devices[dev_id] = dev
    else:
        dev_id = dev["device_id"]
        _, _, _, dev_type = extract_device_identity(req_id_str)
        if "device_type" not in dev:
            dev["device_type"] = dev_type
        dev["last_updated_at"] = now_str
        dev["request_id"] = norm_req
        if client_name:
            dev["client_name"] = client_name
        if notes:
            dev["notes"] = notes
        if is_activated:
            for p in dev.get("passwords", []):
                if p.get("status") == "active":
                    p["status"] = "replaced"
                    p["replaced_at"] = now_str
                    p["replaced_by"] = norm_key
            dev["active_key"] = norm_key
            dev["active_tier"] = tier
            dev["active_tier_name"] = tier_name

    # Расчет даты истечения действия
    if tier in ("unlimited", "vip", "vipx"):
        valid_until_str = "Бессрочно (VIP)"
    elif exact_valid_until:
        valid_until_str = exact_valid_until
    else:
        dec_vu, dec_tn = decode_key_valid_until(norm_key)
        if dec_vu and dec_vu != "—":
            valid_until_str = dec_vu
        else:
            from datetime import timedelta
            valid_until_str = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

    # Проверяем, является ли данный тариф пробным периодом (триалом на 3 дня)
    is_trial_key = bool(
        tier in ("trial", "trial_3_days") or
        "триал" in (tier_name or "").lower() or
        "3 дн" in (tier_name or "").lower() or
        "пробн" in (reason or "").lower() or
        "триал" in (reason or "").lower()
    )
    if is_activated:
        dev["active_valid_until"] = valid_until_str
        if is_trial_key:
            dev["trial_used"] = True
            dev["trial_issued_at"] = now_str
            dev["trial_activated_at"] = now_str
    else:
        if is_trial_key:
            dev["trial_issued_at"] = now_str

    # Добавляем новый закрепленный пароль со статусом pending (ожидает активации) или active
    passwords = dev.setdefault("passwords", [])
    next_index = len(passwords) + 1
    new_pwd_entry = {
        "index": next_index,
        "key": norm_key,
        "tier": tier,
        "tier_name": tier_name,
        "issued_at": now_str,
        "valid_until": valid_until_str,
        "status": "active" if is_activated else "pending",
        "reason": reason or ("Первичная выдача" if is_new else f"Второй/новый пароль (пароль #{next_index})"),
        "request_id": norm_req,
        "activated": is_activated,
        "activated_at": now_str if is_activated else None,
        "activated_by": (client_name or "Администратор") if is_activated else None,
        "is_trial": is_trial_key
    }
    passwords.append(new_pwd_entry)

    save_devices(devices)

    # Синхронизация с dispensed_keys.json для совместимости со старыми модулями
    try:
        disp_data = {}
        if os.path.exists(DISPENSED_PATH):
            with open(DISPENSED_PATH, "r", encoding="utf-8-sig") as f:
                disp_data = json.load(f)
        disp_data[norm_key] = {
            "client_note": f"{dev.get('client_name')} [{reason}]",
            "dispensed_at": now_str,
            "type": "hardware_bound",
            "tier": tier,
            "mac": dev.get("mac"),
            "request_id": norm_req,
            "device_id": dev_id,
            "password_index": next_index,
            "is_trial": is_trial_key
        }
        with open(DISPENSED_PATH, "w", encoding="utf-8") as f:
            json.dump(disp_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] Ошибка обновления dispensed_keys.json: {e}")

    return {
        "success": True,
        "is_new": is_new,
        "device": dev,
        "password_entry": new_pwd_entry,
        "password_index": next_index,
        "message": f"Пароль #{next_index} ({tier_name}) успешно закреплен за устройством {dev_id} ({dev.get('client_name')})!"
    }

def record_key_activation_on_site(key_str: str, username: str = "", real_mac: str = "", request_id: str = ""):
    """Вызывается сайтом при успешной активации ключа для обновления статуса в базе устройств."""
    devices = load_devices()
    norm_k = normalize_key(key_str)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    found = False
    for dev in devices.values():
        for pwd in dev.get("passwords", []):
            if pwd.get("key") == norm_k:
                pwd["activated"] = True
                pwd["activated_on_site"] = True
                pwd["activated_at"] = now_str
                pwd["activated_by"] = username
                pwd["status"] = "active"
                if pwd.get("is_trial"):
                    dev["trial_used"] = True
                    dev["trial_activated_at"] = now_str
                if real_mac and dev.get("mac", "").startswith("**:**"):
                    dev["mac"] = real_mac
                dev["last_updated_at"] = now_str
                dev["active_key"] = norm_k
                dev["active_tier"] = pwd.get("tier", dev.get("active_tier", "30_days"))
                dev["active_tier_name"] = pwd.get("tier_name", dev.get("active_tier_name", ""))
                dev["active_valid_until"] = pwd.get("valid_until", dev.get("active_valid_until", ""))
                dev["activated_on_site"] = True
                found = True
                break
        if found:
            # Предыдущие активные пароли этого устройства помечаем как замененные
            for p in dev.get("passwords", []):
                if p.get("key") != norm_k and p.get("status") == "active":
                    p["status"] = "replaced"
                    p["replaced_at"] = now_str
                    p["replaced_by"] = norm_k
            break

    if not found and request_id:
        # Автоматическая фиксация и регистрация устройства в базе
        vu, tn = decode_key_valid_until(norm_k)
        tier_type = "unlimited" if "VIP" in tn else "30_days"
        res = register_or_bind_password(
            request_id,
            norm_k,
            tier=tier_type,
            client_name=username or "skynet83",
            notes="Мобильное устройство (Телефон)" if request_id.startswith("EBMOB") else "ПК",
            reason="Активация на сайте",
            tier_name=tn,
            exact_valid_until=vu,
            is_activated=True
        )
        # Отмечаем как активированный
        if res.get("device"):
            dev_target = res["device"]
            for p in dev_target.get("passwords", []):
                if p.get("key") == norm_k:
                    p["activated"] = True
                    p["activated_on_site"] = True
                    p["activated_at"] = now_str
                    p["activated_by"] = username
                    p["status"] = "active"
                    dev_target["active_key"] = norm_k
                    dev_target["active_tier"] = p.get("tier", "30_days")
                    dev_target["active_tier_name"] = p.get("tier_name", "")
                    dev_target["active_valid_until"] = p.get("valid_until", "")
            dev_target["activated_on_site"] = True
            cur_devices = load_devices()
            target_dev_id = dev_target.get("device_id")
            if target_dev_id:
                cur_devices[target_dev_id] = dev_target
                save_devices(cur_devices)
        # Синхронизируем статус активации в dispensed_keys.json для KeyManager
        _sync_dispensed_activation(norm_k, username, now_str)
        return

    if found:
        save_devices(devices)
        _sync_dispensed_activation(norm_k, username, now_str)

def has_device_used_trial(req_id_or_dev_id: str) -> bool:
    """
    Проверяет, использовало ли данное устройство пробный период (3 дня)
    или был ли на данном ПК ранее установлен/активирован любой ключ.
    Проверяет:
    1. Локальные скрытые метки Windows (реестр, ProgramData, LocalAppData)
    2. Базу данных SQLite Telegram-бота (таблица hwid_trials)
    3. Базу данных устройств devices.json и историю выданных ключей dispensed_keys.json
    Возвращает True, если устройству уже когда-либо выдавался или активировался ключ/триал.
    """
    if not req_id_or_dev_id:
        return False

    norm_req = normalize_req_id(req_id_or_dev_id)

    # 1. Проверка системных скрытых меток Windows (защита от удаления папки)
    try:
        import hwid_security
        is_loc_used, _ = hwid_security.check_local_trial_used()
        if is_loc_used:
            return True
    except Exception:
        pass

    # 2. Проверка по базе SQLite Telegram-бота
    try:
        import sqlite3
        bot_db_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "avito_bot", "avito_bot.db"))
        if os.path.exists(bot_db_path):
            with sqlite3.connect(bot_db_path) as c:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS hwid_trials (
                        hwid TEXT PRIMARY KEY,
                        client_name TEXT,
                        telegram_id INTEGER,
                        trial_key TEXT,
                        ip_address TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TEXT
                    )
                """)
                r = c.execute("SELECT hwid FROM hwid_trials WHERE hwid = ?", (norm_req,)).fetchone()
                if r:
                    return True
    except Exception:
        pass

    # 3. Проверка по реестру devices.json
    try:
        dev = find_device_by_req_id(req_id_or_dev_id)
        if not dev:
            dev_id, _, _, _ = extract_device_identity(req_id_or_dev_id)
            dev = load_devices().get(dev_id)

        if dev:
            if dev.get("trial_used") or dev.get("active_key") or dev.get("activated_on_site"):
                return True
            for p in dev.get("passwords", []):
                # Любой пароль, когда-либо активированный или выданный на этом ПК
                if p.get("is_trial") or p.get("activated_on_site") or p.get("status") == "active" or p.get("key"):
                    return True
                tn = (p.get("tier_name") or "").lower()
                rs = (p.get("reason") or "").lower()
                if "триал" in tn or "3 дн" in tn or "пробн" in rs or "триал" in rs:
                    return True
    except Exception:
        pass

    # 4. Дополнительная проверка по архиву выданных ключей dispensed_keys.json
    try:
        if os.path.exists(DISPENSED_PATH):
            with open(DISPENSED_PATH, "r", encoding="utf-8-sig") as f:
                disp = json.load(f)
            for item in disp.values():
                if item.get("request_id") == norm_req or item.get("device_id") == req_id_or_dev_id:
                    return True
    except Exception:
        pass

    return False

def record_device_trial_activation(req_id: str, key: str, exp_dt_str: str, client_ip: str = "", username: str = ""):
    """
    Фиксирует активацию триал-ключа (3 дня) сразу на всех уровнях:
    1. В реестре Windows, ProgramData и LocalAppData (через hwid_security)
    2. В devices.json и dispensed_keys.json
    3. В базе данных SQLite Telegram-бота (таблица hwid_trials)
    """
    norm_req = normalize_req_id(req_id)
    norm_key = normalize_key(key) if key and key != "ALREADY_ACTIVATED" else "ALREADY_ACTIVATED"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 1. Скрытые метки ОС Windows
    try:
        import hwid_security
        hwid_security.record_local_trial_activation(expires_at_str=exp_dt_str)
    except Exception:
        pass

    # 2. Регистрация пароля и отметка устройства
    if norm_key != "ALREADY_ACTIVATED" and len(norm_key) == 20:
        try:
            register_or_bind_password(
                req_id_str=norm_req,
                password_str=norm_key,
                tier="3_days",
                reason="Активация триала на сайте",
                client_name=username or norm_req,
                valid_until=exp_dt_str,
                is_trial=True,
                custom_note=f"Триал 3 дня до {exp_dt_str} (IP: {client_ip})"
            )
        except Exception:
            pass

    # Отмечаем статус trial_used на устройстве
    try:
        devs = load_devices()
        dev = find_device_by_req_id(norm_req)
        if dev:
            dev_id = dev.get("device_id")
            if dev_id and dev_id in devs:
                devs[dev_id]["trial_used"] = True
                devs[dev_id]["trial_activated_at"] = devs[dev_id].get("trial_activated_at") or now_str
                if norm_key != "ALREADY_ACTIVATED":
                    devs[dev_id]["trial_key"] = norm_key
                    devs[dev_id]["trial_expires_at"] = exp_dt_str
                save_devices(devs)
    except Exception:
        pass

    # 3. База данных SQLite Telegram-бота
    try:
        import sqlite3
        bot_db_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "avito_bot", "avito_bot.db"))
        if os.path.exists(bot_db_path):
            with sqlite3.connect(bot_db_path) as c:
                c.execute("""
                    CREATE TABLE IF NOT EXISTS hwid_trials (
                        hwid TEXT PRIMARY KEY,
                        client_name TEXT,
                        telegram_id INTEGER,
                        trial_key TEXT,
                        ip_address TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        expires_at TEXT
                    )
                """)
                c.execute("""
                    INSERT OR REPLACE INTO hwid_trials (hwid, client_name, trial_key, ip_address, created_at, expires_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (norm_req, username or norm_req, norm_key, client_ip, now_str, exp_dt_str))
                c.commit()
    except Exception as e:
        print(f"[ERR] Ошибка записи в hwid_trials SQLite: {e}")

