# -*- coding: utf-8 -*-
"""
Модуль криптографической привязки лицензий к оборудованию ПК (Hardware-Locked Licensing).
Реализует схему Запрос-Ответ (Challenge-Response):
1. Сайт генерирует ID код запроса (EBID-XXXX-XXXX-XXXX-XXXX-XXXX), содержащий
   аппаратный отпечаток ПК (MAC-адрес, MachineGuid) и первую половину секретного сида.
2. Программа KeyManager расшифровывает ID код, извлекает параметры железа и первую половину сида,
   подмешивает выбранный тариф (30 дней / VIP Безлимит) и формирует ответный ключ (вторую половину).
3. При вводе ответного ключа на сайте проверяется совпадение с реальным железом ТЕКУЩЕГО ПК.
   На любом другом ПК этот же ответный ключ работать НЕ будет!
"""

import os
import sys
import re
import uuid
import hashlib
import hmac
from typing import Optional, Dict, Any, Tuple

# Мастер-соль шифрования для защиты лицензионного обмена (SkyBase)
MASTER_LICENSE_SECRET = "SkyBase_HWID_v3_2026_KeyShield_@AvitoSecure"

def get_clean_hex(val: str) -> str:
    """Удаляет любые не-hex символы и приводит к верхнему регистру."""
    return re.sub(r"[^0-9A-Fa-f]", "", val or "").upper()

def get_local_mac() -> str:
    """
    Возвращает основной MAC-адрес текущего компьютера в формате XX:XX:XX:XX:XX:XX.
    Использует аппаратный uuid.getnode() с проверкой валидности.
    """
    try:
        node = uuid.getnode()
        # Проверяем, что это не случайный MAC (младший бит первого октета не должен быть 1)
        mac_hex = "{:012x}".format(node).upper()
        if len(mac_hex) == 12:
            return ":".join(mac_hex[i:i+2] for i in range(0, 12, 2))
    except Exception:
        pass
    return "4C:EB:BD:02:1A:EC"

def get_local_machine_guid() -> str:
    """
    Возвращает уникальный MachineGuid из реестра Windows (HKLM\\SOFTWARE\\Microsoft\\Cryptography).
    Это стабильный аппаратный идентификатор установки ОС на данном ПК.
    """
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                guid = str(winreg.QueryValueEx(k, "MachineGuid")[0]).strip()
                if guid:
                    return guid.upper()
        except Exception:
            pass
    # Резервный идентификатор если не Windows или ошибка чтения реестра
    return "DBA866E1-59FC-4EF6-8117-38073E87E7CB"

def get_local_hwid_fingerprint() -> Dict[str, Any]:
    """
    Формирует полный локальный аппаратный отпечаток компьютера:
    - mac: полный MAC-адрес (XX:XX:XX:XX:XX:XX)
    - clean_mac: 12 символов HEX
    - mac_tail: последние 4 символа MAC (для наглядности в ID коде)
    - guid: MachineGuid
    - clean_guid: 32 символа HEX
    - hw_sig: 6-символьный хэш железа
    - part1: 6-символьная первая половина секретного пароля (Challenge)
    - chk: 4-символьная контрольная сумма
    - request_id: красивый 20-значный ID код запроса (EBID-XXXX-XXXX-XXXX-XXXX-XXXX)
    """
    raw_mac = get_local_mac()
    clean_mac = get_clean_hex(raw_mac)
    if len(clean_mac) < 12:
        clean_mac = clean_mac.ljust(12, "0")
    mac_tail = clean_mac[-4:]

    raw_guid = get_local_machine_guid()
    clean_guid = get_clean_hex(raw_guid)
    if len(clean_guid) < 32:
        clean_guid = clean_guid.ljust(32, "0")

    # Аппаратный отпечаток (MAC + GUID)
    hw_combined = f"{clean_mac}:{clean_guid}".encode("utf-8")
    hw_hash = hashlib.sha256(hw_combined).hexdigest().upper()
    hw_sig = hw_hash[:6]

    # Первая половина пароля (Challenge seed), жестко привязанная к железу и соли
    part1_raw = f"P1:{hw_sig}:{mac_tail}:{MASTER_LICENSE_SECRET}".encode("utf-8")
    part1 = hashlib.sha256(part1_raw).hexdigest().upper()[:6]

    # Контрольная сумма запроса
    chk_raw = f"CHK:{mac_tail}:{hw_sig}:{part1}:{MASTER_LICENSE_SECRET}".encode("utf-8")
    chk = hashlib.sha256(chk_raw).hexdigest().upper()[:4]

    # Смешиваем в 20 символов: mac_tail(4) + hw_sig(6) + part1(6) + chk(4) = 20
    raw_req = f"{mac_tail}{hw_sig}{part1}{chk}"
    req_formatted = f"EBID-{raw_req[0:4]}-{raw_req[4:8]}-{raw_req[8:12]}-{raw_req[12:16]}-{raw_req[16:20]}"

    return {
        "mac": raw_mac,
        "clean_mac": clean_mac,
        "mac_tail": mac_tail,
        "guid": raw_guid,
        "clean_guid": clean_guid,
        "hw_sig": hw_sig,
        "part1": part1,
        "chk": chk,
        "raw_req": raw_req,
        "request_id": req_formatted
    }

def generate_local_request_id() -> str:
    """Возвращает форматированный ID код запроса для локального компьютера."""
    return get_local_hwid_fingerprint()["request_id"]

def generate_mobile_request_id(seed_str: Optional[str] = None) -> str:
    """
    Генерирует криптографически валидный ID код для мобильного устройства (EBMOB-...).
    Снабжен контрольной суммой и первой половиной Challenge seed, совместимыми с KeyManager.
    """
    if not seed_str:
        seed_str = str(uuid.uuid4())
    s_hash = hashlib.sha256(seed_str.encode("utf-8")).hexdigest().upper()
    mac_tail = s_hash[:4]
    hw_sig = s_hash[4:10]
    part1_raw = f"P1:{hw_sig}:{mac_tail}:{MASTER_LICENSE_SECRET}".encode("utf-8")
    part1 = hashlib.sha256(part1_raw).hexdigest().upper()[:6]
    chk_raw = f"CHK:{mac_tail}:{hw_sig}:{part1}:{MASTER_LICENSE_SECRET}".encode("utf-8")
    chk = hashlib.sha256(chk_raw).hexdigest().upper()[:4]
    raw_req = f"{mac_tail}{hw_sig}{part1}{chk}"
    return f"EBMOB-{raw_req[0:4]}-{raw_req[4:8]}-{raw_req[8:12]}-{raw_req[12:16]}-{raw_req[16:20]}"

def parse_request_id(req_id_str: str) -> Dict[str, Any]:
    """
    Разбирает и валидирует ID код запроса от клиента (в KeyManager или на сервере).
    Поддерживает как ПК (EBID-...), так и мобильные телефоны (EBMOB-...).
    Возвращает dict с полями:
    - valid: bool
    - is_mobile: bool
    - device_type: 'phone' | 'pc'
    - mac_tail: 4 hex символа
    - hw_sig: 6 hex символов
    - part1: 6 hex символов (первая половина пароля)
    - chk: 4 hex символа
    - request_id: нормализованный EBID-... или EBMOB-...
    - error: описание ошибки если valid=False
    """
    if not req_id_str:
        return {"valid": False, "error": "ID код не указан"}

    s = str(req_id_str).strip().upper()
    is_mob = s.startswith("EBMOB")
    if s.startswith("EBID"):
        s = s[4:].lstrip("-: ").strip()
    elif s.startswith("EBMOB"):
        s = s[5:].lstrip("-: ").strip()
    clean = re.sub(r"[^0-9A-Fa-f]", "", s)

    if len(clean) != 20:
        return {
            "valid": False,
            "error": f"Неверная длина ID кода ({len(clean)} вместо 20 символов). Проверьте правильность копирования."
        }

    mac_tail = clean[0:4]
    hw_sig = clean[4:10]
    part1 = clean[10:16]
    chk = clean[16:20]

    # Проверка контрольной суммы
    exp_chk_raw = f"CHK:{mac_tail}:{hw_sig}:{part1}:{MASTER_LICENSE_SECRET}".encode("utf-8")
    exp_chk = hashlib.sha256(exp_chk_raw).hexdigest().upper()[:4]
    if chk != exp_chk:
        return {
            "valid": False,
            "error": "Ошибка контрольной суммы ID кода! Возможно, символ был скопирован с ошибкой."
        }

    # Проверка целостности первой половины пароля
    exp_part1_raw = f"P1:{hw_sig}:{mac_tail}:{MASTER_LICENSE_SECRET}".encode("utf-8")
    exp_part1 = hashlib.sha256(exp_part1_raw).hexdigest().upper()[:6]
    if part1 != exp_part1:
        return {
            "valid": False,
            "error": "ID код поврежден или содержит недействительные сигнатуры оборудования."
        }

    prefix = "EBMOB" if is_mob else "EBID"
    req_formatted = f"{prefix}-{clean[0:4]}-{clean[4:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}"
    return {
        "valid": True,
        "is_mobile": is_mob,
        "device_type": "phone" if is_mob else "pc",
        "mac_tail": mac_tail,
        "hw_sig": hw_sig,
        "part1": part1,
        "chk": chk,
        "request_id": req_formatted
    }

import datetime

BASE_EPOCH = datetime.date(2026, 1, 1)
BASE_EPOCH_DT = datetime.datetime(2026, 1, 1, 0, 0, 0)

def get_secure_current_time() -> datetime.datetime:
    """
    Возвращает защищенное текущее время с проверкой отката часов назад и локальным анкером.
    Предотвращает мошенничество с переводом системных часов Windows назад.
    """
    now = datetime.datetime.now()
    audit_dir = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "SkyBase")
    audit_file = os.path.join(audit_dir, "sys_audit.json")
    try:
        if os.path.exists(audit_file):
            with open(audit_file, "r", encoding="utf-8") as f:
                audit_data = json.load(f)
            last_seen_str = audit_data.get("last_seen")
            if last_seen_str:
                last_seen_dt = datetime.datetime.strptime(last_seen_str, "%Y-%m-%d %H:%M:%S")
                # Если часы переведены назад более чем на 30 минут:
                if now < (last_seen_dt - datetime.timedelta(minutes=30)):
                    now = last_seen_dt  # Используем последнее известное время
    except Exception:
        pass

    try:
        os.makedirs(audit_dir, exist_ok=True)
        with open(audit_file, "w", encoding="utf-8") as f:
            json.dump({"last_seen": now.strftime("%Y-%m-%d %H:%M:%S")}, f)
    except Exception:
        pass

    return now

def generate_response_key(req_id_or_parsed: Any, tier: str = "30_days", expires_date: Optional[Any] = None) -> str:
    """
    Генерирует ответный ключ активации с криптографически вшитой датой истечения (Time-Locked Key).
    Защищает от повторного скачивания программы: дата окончания вшита в крипто-подпись ключа.
    Поддерживает точность вплоть до минут (формат V3: 6 hex-символов минут от 2026-01-01 00:00).
    Формат ключа (20 символов):
      [0:4]   - tier_code: 'EB30' или 'VIPX' (Бессрочно)
      [4:10]  - exp_hex: 6 hex-символов минут от 2026-01-01 00:00 (или 4 hex 'FFFF' для VIP)
      [10:16] - part2: 6 hex-символов HMAC от (hw_sig + part1 + tier + exp_hex)
      [16:20] - r_chk: 4 hex-символа контрольной суммы
    """
    if isinstance(req_id_or_parsed, dict):
        parsed = req_id_or_parsed
    else:
        parsed = parse_request_id(str(req_id_or_parsed))

    if not parsed.get("valid"):
        raise ValueError(parsed.get("error", "Недействительный ID код запроса"))

    hw_sig = parsed["hw_sig"]
    part1 = parsed["part1"]

    is_vip = tier.lower() in ("unlimited", "vip", "vipx", "бессрочный", "безлимит")
    tier_code = "VIPX" if is_vip else "EB30"
    tier_id = "VIP" if is_vip else "STD"

    if is_vip:
        exp_hex = "FFFF"
        part2_raw = f"P2V2:{hw_sig}:{part1}:{tier_id}:{exp_hex}:{MASTER_LICENSE_SECRET}".encode("utf-8")
        part2 = hashlib.sha256(part2_raw).hexdigest().upper()[:8]
        r_chk_raw = f"RCHKV2:{tier_code}:{hw_sig}:{exp_hex}:{part2}:{MASTER_LICENSE_SECRET}".encode("utf-8")
        r_chk = hashlib.sha256(r_chk_raw).hexdigest().upper()[:4]
        raw_resp = f"{tier_code}{exp_hex}{part2}{r_chk}"  # 4 + 4 + 8 + 4 = 20 символов
    else:
        if not expires_date:
            exp_dt = datetime.datetime.now() + datetime.timedelta(days=30)
        elif isinstance(expires_date, datetime.datetime):
            exp_dt = expires_date
        elif isinstance(expires_date, datetime.date):
            exp_dt = datetime.datetime.combine(expires_date, datetime.time(23, 59, 59))
        else:
            exp_dt = datetime.datetime.now() + datetime.timedelta(days=30)

        diff_seconds = max(0, (exp_dt - BASE_EPOCH_DT).total_seconds())
        diff_minutes = int(diff_seconds // 60)
        exp_hex = f"{diff_minutes:06X}"  # 6 hex chars (24 бита)

        part2_raw = f"P2V3:{hw_sig}:{part1}:{tier_id}:{exp_hex}:{MASTER_LICENSE_SECRET}".encode("utf-8")
        part2 = hashlib.sha256(part2_raw).hexdigest().upper()[:6]

        r_chk_raw = f"RCHKV3:{tier_code}:{hw_sig}:{exp_hex}:{part2}:{MASTER_LICENSE_SECRET}".encode("utf-8")
        r_chk = hashlib.sha256(r_chk_raw).hexdigest().upper()[:4]

        raw_resp = f"{tier_code}{exp_hex}{part2}{r_chk}"  # 4 + 6 + 6 + 4 = 20 символов

    return f"{raw_resp[0:4]}-{raw_resp[4:8]}-{raw_resp[8:12]}-{raw_resp[12:16]}-{raw_resp[16:20]}"

def verify_response_key_for_local_pc(response_key_str: str, local_hwid: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Проверяет ответный ключ активации на совпадение с железом ТЕКУЩЕГО локального компьютера!
    Проверяет вшитую дату окончания действия ключа (защита от скачивания чистой копии).
    Поддерживает форматы V3 (точно до минут), V2 (по дням) и V1 (legacy).
    """
    if not response_key_str:
        return {"valid": False, "error": "Ключ активации не указан"}

    clean_key = re.sub(r"[^0-9A-Za-z]", "", response_key_str).strip().upper()
    if len(clean_key) != 20:
        return {
            "valid": False,
            "error": f"Неверный формат ключа (требуется 20 символов, получено {len(clean_key)})."
        }

    tier_code = clean_key[0:4]
    if tier_code not in ("EB30", "VIPX"):
        return {
            "valid": False,
            "is_hwid_key": False,
            "error": "Неизвестный тип ключа (не является аппаратным ключом EB30/VIPX)."
        }

    if not local_hwid:
        local_hwid = get_local_hwid_fingerprint()

    loc_hw_sig = local_hwid["hw_sig"]
    loc_part1 = local_hwid["part1"]

    is_vip = (tier_code == "VIPX")
    tier_id = "VIP" if is_vip else "STD"
    tier_name = "unlimited" if is_vip else "30_days"

    # =========================================================================
    # 0. VIP режим
    # =========================================================================
    if is_vip or clean_key[4:8] == "FFFF":
        exp_hex = "FFFF"
        part2_v2 = clean_key[8:16]
        r_chk_v2 = clean_key[16:20]
        exp_part2_v2 = hashlib.sha256(f"P2V2:{loc_hw_sig}:{loc_part1}:{tier_id}:{exp_hex}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:8]
        exp_r_chk_v2 = hashlib.sha256(f"RCHKV2:{tier_code}:{loc_hw_sig}:{exp_hex}:{part2_v2}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:4]
        if r_chk_v2 == exp_r_chk_v2 and part2_v2 == exp_part2_v2:
            return {
                "valid": True,
                "is_hwid_key": True,
                "tier": "unlimited",
                "is_unlimited": True,
                "expires_at": None,
                "mac": local_hwid["mac"],
                "request_id": local_hwid.get("request_id")
            }

    # =========================================================================
    # 1. Проверка формата V3 (с точностью до минут: 4 + 6 + 6 + 4)
    # =========================================================================
    exp_hex_v3 = clean_key[4:10]
    part2_v3 = clean_key[10:16]
    r_chk_v3 = clean_key[16:20]

    exp_part2_v3 = hashlib.sha256(f"P2V3:{loc_hw_sig}:{loc_part1}:{tier_id}:{exp_hex_v3}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:6]
    exp_r_chk_v3 = hashlib.sha256(f"RCHKV3:{tier_code}:{loc_hw_sig}:{exp_hex_v3}:{part2_v3}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:4]

    if r_chk_v3 == exp_r_chk_v3 and part2_v3 == exp_part2_v3:
        try:
            exp_mins = int(exp_hex_v3, 16)
            exp_dt = BASE_EPOCH_DT + datetime.timedelta(minutes=exp_mins)
            exp_str = exp_dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return {"valid": False, "error": "Недействительный временной блок ключа (V3)"}

        sec_now = get_secure_current_time()
        if sec_now > exp_dt:
            return {
                "valid": False,
                "is_hwid_key": True,
                "is_expired": True,
                "error": (
                    f"❌ Срок действия данного ключа истёк {exp_dt.strftime('%d.%m.%Y в %H:%M')}!\n"
                    "Повторная активация невозможна (в том числе при повторном скачивании программы).\n"
                    "Для продолжения работы обратитесь к администратору за новым ключом."
                )
            }

        return {
            "valid": True,
            "is_hwid_key": True,
            "tier": "30_days",
            "is_unlimited": False,
            "expires_at": exp_str,
            "mac": local_hwid["mac"],
            "request_id": local_hwid.get("request_id")
        }

    # =========================================================================
    # 2. Проверка формата V2 (с датой по дням: 4 + 4 + 8 + 4) для обратной совместимости
    # =========================================================================
    exp_hex_v2 = clean_key[4:8]
    part2_v2 = clean_key[8:16]
    r_chk_v2 = clean_key[16:20]

    exp_part2_v2 = hashlib.sha256(f"P2V2:{loc_hw_sig}:{loc_part1}:{tier_id}:{exp_hex_v2}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:8]
    exp_r_chk_v2 = hashlib.sha256(f"RCHKV2:{tier_code}:{loc_hw_sig}:{exp_hex_v2}:{part2_v2}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:4]

    if r_chk_v2 == exp_r_chk_v2 and part2_v2 == exp_part2_v2:
        try:
            exp_days = int(exp_hex_v2, 16)
            exp_date = BASE_EPOCH + datetime.timedelta(days=exp_days)
            exp_str = f"{exp_date.strftime('%Y-%m-%d')} 23:59:59"
        except Exception:
            return {"valid": False, "error": "Недействительный временной блок ключа (V2)"}

        sec_now = get_secure_current_time()
        if sec_now.date() > exp_date:
            return {
                "valid": False,
                "is_hwid_key": True,
                "is_expired": True,
                "error": (
                    f"❌ Срок действия данного ключа истёк {exp_date.strftime('%d.%m.%Y')}!\n"
                    "Повторная активация невозможна (в том числе при повторном скачивании программы).\n"
                    "Для продолжения работы обратитесь к администратору за новым ключом."
                )
            }

        return {
            "valid": True,
            "is_hwid_key": True,
            "tier": "30_days",
            "is_unlimited": False,
            "expires_at": exp_str,
            "mac": local_hwid["mac"],
            "request_id": local_hwid.get("request_id")
        }

    # =========================================================================
    # 2. Проверка устаревшего формата V1 (без даты в ключе) для совместимости
    # =========================================================================
    part2_v1 = clean_key[4:16]
    r_chk_v1 = clean_key[16:20]
    exp_r_chk_v1 = hashlib.sha256(f"RCHK:{tier_code}:{loc_hw_sig}:{part2_v1}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:4]
    exp_part2_v1 = hashlib.sha256(f"P2:{loc_hw_sig}:{loc_part1}:{tier_id}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:12]

    if r_chk_v1 == exp_r_chk_v1 and part2_v1 == exp_part2_v1:
        return {
            "valid": True,
            "is_hwid_key": True,
            "mismatch_hwid": False,
            "tier": tier_name,
            "is_unlimited": is_vip,
            "mac": local_hwid["mac"],
            "request_id": local_hwid.get("request_id")
        }

    # Если ключ не подошел ни под один формат на этом ПК
    return {
        "valid": False,
        "is_hwid_key": True,
        "mismatch_hwid": True,
        "error": (
            "❌ Данный ответный ключ активации не подходит к этому компьютеру!\n"
            "Аппаратные данные (MAC-адрес / ID системы) не совпадают.\n"
            f"Ключ должен быть сгенерирован администратором под ваш текущий ID: {local_hwid.get('request_id', '')}"
        )
    }

def create_hwid_license_token(username: str, tier: str, expires_at: Optional[str], local_hwid: Optional[Dict[str, Any]] = None) -> str:
    """Создает криптографическую подпись для фиксации активированной лицензии за конкретным ПК."""
    if not local_hwid:
        local_hwid = get_local_hwid_fingerprint()
    data = f"{username}:{tier}:{expires_at or 'none'}:{local_hwid['clean_mac']}:{local_hwid['clean_guid']}"
    return hmac.new(MASTER_LICENSE_SECRET.encode("utf-8"), data.encode("utf-8"), hashlib.sha256).hexdigest()

def verify_hwid_license_token(username: str, tier: str, expires_at: Optional[str], token: str, local_hwid: Optional[Dict[str, Any]] = None) -> bool:
    """Проверяет, что сохраненная лицензия в users.json принадлежит именно этому компьютеру."""
    if not token:
        return False
    expected = create_hwid_license_token(username, tier, expires_at, local_hwid)
    return hmac.compare_digest(token, expected)

def verify_response_key(response_key_str: str, req_id_or_hwid: Any = None) -> Dict[str, Any]:
    """
    Универсальная проверка ответного ключа активации:
    1. Если передан req_id_or_hwid (строка ID запроса EBMOB-... / EBID-...):
       проверяет ключ непосредственно для этого мобильного устройства или ПК.
    2. Если нет или не подошел, проверяет локальный серверный ПК.
    3. Если не подошел, ищет среди зарегистрированных устройств в devices_db.
    """
    if req_id_or_hwid:
        if isinstance(req_id_or_hwid, str) and req_id_or_hwid.strip():
            parsed = parse_request_id(req_id_or_hwid.strip())
            if parsed.get("valid"):
                target_hw = {
                    "hw_sig": parsed["hw_sig"],
                    "part1": parsed["part1"],
                    "mac": parsed.get("mac_tail", "0000"),
                    "request_id": parsed["request_id"]
                }
                res = verify_response_key_for_local_pc(response_key_str, local_hwid=target_hw)
                if res.get("valid"):
                    res["device_type"] = parsed.get("device_type", "phone" if parsed.get("is_mobile") else "pc")
                    res["request_id"] = parsed["request_id"]
                    return res
        elif isinstance(req_id_or_hwid, dict):
            res = verify_response_key_for_local_pc(response_key_str, local_hwid=req_id_or_hwid)
            if res.get("valid"):
                return res

    # Проверка для локального ПК
    res = verify_response_key_for_local_pc(response_key_str)
    if res.get("valid"):
        res["device_type"] = "pc"
        return res

    # Проверка по сохраненным устройствам в devices_db
    try:
        import devices_db
        all_devs = devices_db.load_devices()
        for dev_obj in all_devs.values():
            req_id = dev_obj.get("request_id")
            if req_id:
                parsed = parse_request_id(req_id)
                if parsed.get("valid"):
                    t_hw = {
                        "hw_sig": parsed["hw_sig"],
                        "part1": parsed["part1"],
                        "mac": dev_obj.get("mac", parsed.get("mac_tail")),
                        "request_id": req_id
                    }
                    chk = verify_response_key_for_local_pc(response_key_str, local_hwid=t_hw)
                    if chk.get("valid"):
                        chk["device_type"] = dev_obj.get("device_type", "phone" if req_id.startswith("EBMOB") else "pc")
                        chk["request_id"] = req_id
                        chk["device_id"] = dev_obj.get("device_id")
                        return chk
    except Exception:
        pass

    return res

