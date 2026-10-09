# -*- coding: utf-8 -*-
"""
Модуль облачной синхронизации и защиты триал-лицензий AvitoHunter через закрытый Telegram-канал.
Канал: -1003716161270
Бот: 8501191397:AAHwEhKIn745c2XocTq-WX_lcXMEEqsSjeg
"""

import json
import logging
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime

logger = logging.getLogger("cloud_license")

BOT_TOKEN = "8501191397:AAHwEhKIn745c2XocTq-WX_lcXMEEqsSjeg"
AUDIT_CHANNEL_ID = "-1003716161270"
ADMIN_CHAT_ID = "5680198246"
TELEGRAM_PROXY = "http://85.8.47.207:7080"
REGISTRY_HEADER = "🛡️ ОБЛАЧНАЯ БАЗА ЛИЦЕНЗИЙ AVITOHUNTER"


def _get_telegram_opener():
    proxies = {}
    if TELEGRAM_PROXY:
        proxies["https"] = TELEGRAM_PROXY
        proxies["http"] = TELEGRAM_PROXY
    return urllib.request.build_opener(urllib.request.ProxyHandler(proxies))


def _telegram_api_call(method: str, data: dict = None, timeout: int = 7) -> dict:
    opener = _get_telegram_opener()
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    try:
        if data:
            enc_data = urllib.parse.urlencode(data).encode("utf-8")
            req = urllib.request.Request(url, data=enc_data, headers={"User-Agent": "AvitoHunter/CloudSecurity"})
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "AvitoHunter/CloudSecurity"})
        with opener.open(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as he:
        try:
            err_body = he.read().decode("utf-8", errors="ignore")
            err_json = json.loads(err_body)
            desc_lower = (err_json.get("description") or "").lower()
            if "not modified" in desc_lower or "exactly the same" in desc_lower:
                return {"ok": True, "result": True, "note": "not_modified"}
            logger.warning(f"Telegram API call {method} HTTPError {he.code}: {desc_lower}")
            return err_json
        except Exception:
            return {"ok": False, "error": str(he)}
    except Exception as e:
        logger.warning(f"Telegram API call {method} error: {e}")
        return {"ok": False, "error": str(e)}


def get_cloud_pinned_registry() -> tuple:
    """
    Возвращает (message_id, list_of_hwids).
    Если закрепленного сообщения нет, ищет или создает его.
    """
    res = _telegram_api_call("getChat", {"chat_id": AUDIT_CHANNEL_ID})
    if not res.get("ok"):
        return None, []

    chat = res.get("result", {})
    pinned = chat.get("pinned_message")
    if pinned:
        mid = pinned.get("message_id")
        text = pinned.get("text", "")
        hwids = []
        try:
            # Извлекаем JSON из текста
            if "[" in text and "]" in text:
                parts = text.split("\n")
                for p in parts:
                    p = p.strip()
                    if p.startswith("[") and p.endswith("]") and not p.startswith("[HWID_REGISTRY"):
                        hwids = json.loads(p)
                        break
        except Exception:
            pass
        return mid, hwids

    # Если нет закрепленного сообщения - создаем и закрепляем
    new_text = f"📊 ВСЕГО УСТРОЙСТВ С ТРИАЛОМ: 0 шт.\n{REGISTRY_HEADER}\n[HWID_REGISTRY:ACTIVE]\n[]"
    res_msg = _telegram_api_call("sendMessage", {"chat_id": AUDIT_CHANNEL_ID, "text": new_text})
    if res_msg.get("ok"):
        mid = res_msg["result"]["message_id"]
        _telegram_api_call("pinChatMessage", {"chat_id": AUDIT_CHANNEL_ID, "message_id": mid})
        sync_cloud_header_counter(0, [], mid)
        return mid, []

    return None, []


def sync_cloud_header_counter(total_devices: int = None, hwids: list = None, mid: int = None) -> bool:
    """
    Синхронизирует счетчик устройств в шапке группы:
    1. Название группы (setChatTitle): "AvitoHunter лицензии (Триалы: N)"
    2. Описание группы (setChatDescription): "📊 Устройств с триалом: N шт."
    3. Закрепленное сообщение (editMessageText): первая строка "📊 ВСЕГО УСТРОЙСТВ С ТРИАЛОМ: N шт."
    """
    try:
        if total_devices is None or hwids is None or mid is None:
            cur_mid, cur_hwids = get_cloud_pinned_registry()
            if mid is None:
                mid = cur_mid
            if hwids is None:
                hwids = cur_hwids
            if total_devices is None:
                total_devices = len(hwids or [])

        # 1. Название группы (фиксированное "AvitoHunter лицензии", чтобы Telegram не приписывал "(Триалы: N)" над каждым постом)
        title_text = "AvitoHunter лицензии"
        _telegram_api_call("setChatTitle", {
            "chat_id": AUDIT_CHANNEL_ID,
            "title": title_text
        })

        # 2. Описание группы (в шапке профиля группы)
        desc_text = (
            f"📊 Устройств с триалом: {total_devices} шт.\n"
            "🔒 Облачный реестр лицензий и триалов AvitoHunter"
        )
        _telegram_api_call("setChatDescription", {
            "chat_id": AUDIT_CHANNEL_ID,
            "description": desc_text
        })

        # 3. Закрепленное сообщение (первая строка видна в баннере закрепа в шапке чата)
        pinned_text = (
            f"📊 ВСЕГО УСТРОЙСТВ С ТРИАЛОМ: {total_devices} шт.\n"
            f"{REGISTRY_HEADER}\n"
            f"[HWID_REGISTRY:ACTIVE]\n"
            f"{json.dumps(hwids or [], ensure_ascii=False)}"
        )
        if mid:
            _telegram_api_call("editMessageText", {
                "chat_id": AUDIT_CHANNEL_ID,
                "message_id": mid,
                "text": pinned_text
            })
        else:
            res_msg = _telegram_api_call("sendMessage", {
                "chat_id": AUDIT_CHANNEL_ID,
                "text": pinned_text
            })
            if res_msg.get("ok"):
                new_mid = res_msg["result"]["message_id"]
                _telegram_api_call("pinChatMessage", {
                    "chat_id": AUDIT_CHANNEL_ID,
                    "message_id": new_mid
                })

        logger.info(f"[CLOUD_LICENSE] Шапка группы синхронизирована (устройств с триалом: {total_devices})")
        return True
    except Exception as e:
        logger.warning(f"[CLOUD_LICENSE] Ошибка обновления счетчика в шапке: {e}")
        return False


def is_hwid_used_in_cloud(hwid: str) -> bool:
    """
    Проверяет в облачном Telegram-канале, был ли уже использован триал на данном HWID.
    """
    if not hwid:
        return False
    norm_hwid = str(hwid).strip().upper()
    try:
        mid, hwids = get_cloud_pinned_registry()
        if not hwids:
            return False
        return norm_hwid in [h.upper() for h in hwids]
    except Exception as e:
        logger.warning(f"Error checking HWID in cloud: {e}")
        return False


def register_hwid_in_cloud(hwid: str, trial_key: str, expires_at: str, username: str = "", ip: str = "") -> bool:
    """
    Записывает HWID в закрепленный реестр канала, сразу обновляет счетчик во всех элементах шапки группы
    и отправляет пост-уведомление ТОЛЬКО в группу (-1003716161270)
    и ТОЛЬКО при самой первой активации.
    """
    if not hwid or not trial_key or trial_key == "ALREADY_ACTIVATED":
        return False
    norm_hwid = str(hwid).strip().upper()
    try:
        mid, hwids = get_cloud_pinned_registry()
        hwids_upper = [h.upper() for h in hwids]

        # Если этот HWID уже зарегистрирован в облаке — это повторная активация!
        if norm_hwid in hwids_upper:
            logger.info(f"[CLOUD_LICENSE] HWID {norm_hwid} уже в облачном реестре. Повторное уведомление не отправляется.")
            sync_cloud_header_counter(len(hwids_upper), hwids, mid)
            return True

        hwids_set = set(hwids_upper)
        hwids_set.add(norm_hwid)
        updated_hwids = list(hwids_set)
        total_trial_devices = len(updated_hwids)

        # 1. Сразу обновляем счетчик во всех элементах шапки группы (название, описание, закреп)
        sync_cloud_header_counter(total_trial_devices, updated_hwids, mid)

        # 2. Отправляем пост аудита ТОЛЬКО В ГРУППУ и ТОЛЬКО ДЛЯ САМОЙ ПЕРВОЙ АКТИВАЦИИ
        now_str = datetime.now().strftime("%d.%m.%Y %H:%M:%S")
        post_text = (
            "🎁 <b>НОВАЯ АКТИВАЦИЯ ТРИАЛА (3 ДНЯ)</b>\n\n"
            f"🖥️ <b>HWID устройства:</b> <code>{norm_hwid}</code>\n"
            f"🔑 <b>Ключ:</b> <code>{trial_key}</code>\n"
            f"⏳ <b>Действует до:</b> <b>{expires_at}</b>\n"
            f"👤 <b>Пользователь:</b> {username or 'Новый клиент'}\n"
            f"🌐 <b>IP адрес:</b> <code>{ip or '127.0.0.1'}</code>\n"
            f"⏱️ <b>Время активации:</b> {now_str}\n\n"
            "<i>Устройство успешно внесено в облачный реестр защиты. Повторная выдача триала заблокирована навсегда.</i>"
        )
        resp = _telegram_api_call("sendMessage", {
            "chat_id": AUDIT_CHANNEL_ID,
            "text": post_text,
            "parse_mode": "HTML"
        })
        print(f"[CLOUD_LICENSE] Отправка первого отчета в группу {AUDIT_CHANNEL_ID} (всего устройств: {total_trial_devices}): ok={resp.get('ok')}", flush=True)
        return True
    except Exception as e:
        print(f"[CLOUD_LICENSE] Ошибка регистрации в облаке: {e}", flush=True)
        logger.warning(f"Error registering HWID in cloud: {e}")
        return False


def notify_cloud_trial_rejected(hwid: str, ip: str = ""):
    """
    О повторных попытках триала уведомления никуда не шлем.
    """
    logger.info(f"[CLOUD_LICENSE] Попытка повторного триала {hwid} отклонена без отправки уведомлений.")
    return
