"""
Главный исполняемый модуль Telegram-бота мониторинга Avito с мультисессионной архитектурой.
1. Вы являетесь главным Администратором: только у вас есть доступ к управлению клиентами (/users, /pending, /approve, /block).
2. Мультисессия: у каждого одобренного клиента СВОИ персональные ссылки поиска (/add, /del, /list, /check).
   Клиент А не видит и не получает поиски Клиента Б!
"""
import sys
try:
    if sys.stdout and hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.stderr and hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

import os
import sys

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
if BOT_DIR not in sys.path:
    sys.path.insert(0, BOT_DIR)
SITE_DIR = os.path.dirname(BOT_DIR)
if SITE_DIR not in sys.path:
    sys.path.insert(0, SITE_DIR)
LIB_DIR = os.path.join(SITE_DIR, "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

import json
import sqlite3
import aiosqlite
import atexit
import asyncio
import logging
import random
import re
from urllib.parse import urlparse, parse_qs, unquote, quote
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict, Any
import hashlib
import html

BOT_DIR = os.path.dirname(os.path.abspath(__file__))
PID_FILE = os.path.join(BOT_DIR, "bot.pid")
primary_admin_id: Optional[int] = 5680198246

def get_configured_search_depth() -> int:
    """Возвращает настроенную глубину поиска страниц (0 = без ограничений)."""
    for base in [os.path.join(BOT_DIR, "..", "data"), os.path.join(BOT_DIR, "data")]:
        cfg_file = os.path.join(base, "sniper_config.json")
        if os.path.exists(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    if "search_depth" in c and c["search_depth"] is not None:
                        return int(c["search_depth"])
            except Exception:
                pass
    return 0

def get_all_pid_files():
    candidates = [PID_FILE]
    for extra in [
        r"C:\Program Files (x86)\SkyBotParser\avito_bot\bot.pid",
        r"D:\ins\skybase\Avito-Parser3\skybase\avito_bot\bot.pid",
        r"D:\ins\skybase\skybotparser\app\avito_bot\bot.pid",
        r"E:\TEMP\База-бот\SITE\avito_bot\bot.pid",
        r"C:\ins\EXP\Arduino\Проект\База-бот\SITE\avito_bot\bot.pid"
    ]:
        if os.path.exists(os.path.dirname(extra)):
            candidates.append(extra)
    seen = set()
    result = []
    for c in candidates:
        norm = os.path.normpath(c).lower()
        if norm not in seen:
            seen.add(norm)
            result.append(os.path.normpath(c))
    return result

_bot_instance_mutex = None

def acquire_single_instance_mutex():
    """
    Гарантирует, что в операционной системе Windows работает ровно один экземпляр bot.py.
    Предотвращает TelegramConflictError (terminated by other getUpdates), возникающий
    при случайном повторном запуске бота.
    """
    global _bot_instance_mutex
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            mutex_name = "Global\\SkyBase_AvitoBot_SingleInstance"
            _bot_instance_mutex = kernel32.CreateMutexW(None, False, mutex_name)
            last_error = kernel32.GetLastError()
            ERROR_ALREADY_EXISTS = 183
            if last_error == ERROR_ALREADY_EXISTS:
                print("[BOT] Другой экземпляр bot.py уже запущен в системе. Выход.", flush=True)
                sys.exit(0)
        except Exception:
            pass

def write_pid_file():
    pid_str = str(os.getpid())
    for p in get_all_pid_files():
        try:
            parent = os.path.dirname(p)
            if os.path.exists(parent):
                with open(p, "w", encoding="utf-8") as f:
                    f.write(pid_str)
        except Exception as e:
            print(f"Warning: could not write {p}: {e}", file=sys.stderr)

def remove_pid_file():
    for p in get_all_pid_files():
        try:
            if os.path.exists(p):
                os.remove(p)
        except Exception:
            pass

atexit.register(remove_pid_file)

def is_license_active() -> bool:
    """Проверяет статус лицензии программы: возвращает True только если лицензия активна."""
    try:
        if SITE_DIR not in sys.path:
            sys.path.insert(0, SITE_DIR)
        import avito_api_helper
        lic = avito_api_helper.get_license_status_info("")
        if not lic or lic.get("is_expired") is True:
            return False
        return True
    except Exception:
        return False

def is_master_monitor_enabled() -> bool:
    """Проверяет общий статус мониторинга в monitor_state.json с учётом лицензии."""
    if not is_license_active():
        return False
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor_state.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return bool(data.get("enabled", True))
    except Exception:
        pass
    return True

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    CallbackQuery,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    KeyboardButton,
    BufferedInputFile,
    FSInputFile,
    BotCommand
)
from curl_cffi.requests import AsyncSession

from config import (
    BOT_TOKEN,
    ADMIN_CHAT_ID,
    ADMIN_USERNAME,
    CHECK_INTERVAL_SECONDS,
    CHECK_INTERVAL_JITTER,
    PAUSE_BETWEEN_REQUESTS,
    TELEGRAM_PROXY,
    AVITO_PROXY,
    DATABASE_PATH
)
from database import (
    init_db,
    is_seen,
    add_seen,
    update_seen_details_if_missing,
    get_seen_price,
    update_seen_price,
    get_user_tracked_urls,
    get_all_active_tasks,
    set_url_initialized,
    set_url_polled,
    add_user_tracked_url,
    delete_user_tracked_url,
    seed_default_urls_for_user,
    get_stats,
    get_user_status,
    register_or_update_user,
    set_user_status,
    get_users_by_status,
    delete_user_and_clean_data,
    add_favorite,
    remove_favorite,
    get_user_favorites,
    add_to_blacklist,
    is_blacklisted,
    get_user_blacklist,
    remove_from_blacklist,
    is_silent_mode,
    toggle_silent_mode,
    is_notified_tg,
    set_notified_tg,
    get_total_seen_count,
    delete_seen_item,
    is_item_deleted,
    get_user_proxies,
    clear_deleted_items_by_search,
    remove_deleted_item,
    is_tg_notified,
    record_tg_notified
)
from parser import AvitoParser, AvitoAd
from filters import STOP_WORDS, extract_keywords_from_url_or_name, is_relevant_ad, is_ad_in_price_range, attach_price_suffix_to_name

# Настройка логирования
log_handlers = [logging.FileHandler(os.path.join(os.path.dirname(__file__), "bot.log"), encoding="utf-8")]
if sys.stdout is not None:
    log_handlers.append(logging.StreamHandler(sys.stdout))
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=log_handlers
)
logger = logging.getLogger("AvitoBot")

def get_persisted_state():
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor_state.json")
        data = {}
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        val = data.get("target_interval")
        mode = data.get("mode", "normal")
        is_direct = bool(data.get("direct_mode", False) or mode == "direct")
        is_hybrid = bool(data.get("hybrid_mode", False) or mode == "hybrid")

        # Fallback to users.json if target_interval is not specified in monitor_state.json
        if val is None:
            users_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "users.json")
            if os.path.exists(users_path):
                try:
                    with open(users_path, "r", encoding="utf-8") as uf:
                        users_data = json.load(uf)
                        for u in users_data:
                            if u.get("role") == "admin" or (u.get("username") or "").lower() == "skynet83":
                                val = u.get("active_interval") or u.get("target_interval")
                                if u.get("mode"):
                                    mode = u.get("mode")
                                    is_direct = bool(u.get("direct_mode", False) or mode == "direct")
                                    is_hybrid = bool(u.get("hybrid_mode", False) or mode == "hybrid")
                                break
                except Exception:
                    pass

        if val is None:
            val = CHECK_INTERVAL_SECONDS

        try:
            int_val = max(1, int(val))
        except Exception:
            int_val = 1 if str(val).isdigit() else 30
        return int_val, is_hybrid, is_direct
    except Exception:
        pass
    return 1, False, False

def get_persisted_target_interval():
    val, _, _ = get_persisted_state()
    return val

def set_persisted_target_interval(sec, user_id=None, mode="normal"):
    try:
        cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor_state.json")
        data = {"enabled": True, "target_interval": 1, "mode": "normal"}
        if os.path.exists(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        try:
            save_val = max(1, int(sec))
        except Exception:
            save_val = 1

        data["target_interval"] = save_val
        data["mode"] = mode
        data["hybrid_mode"] = (mode == "hybrid")
        data["direct_mode"] = (mode == "direct")

        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Синхронизируем с users.json для мгновенного отображения на сайте
        users_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "users.json")
        if os.path.exists(users_path):
            try:
                with open(users_path, "r", encoding="utf-8") as uf:
                    users_data = json.load(uf)
                if isinstance(users_data, list):
                    updated = False
                    for u in users_data:
                        tg_chat_id = u.get("telegram_chat_id")
                        is_match_user = bool(user_id and tg_chat_id and str(tg_chat_id) == str(user_id))
                        is_admin_user = (u.get("role") == "admin" or (u.get("username") or "").lower() == "skynet83")
                        if is_admin_user or is_match_user:
                            u["target_interval"] = str(save_val)
                            u["active_interval"] = str(save_val)
                            u["mode"] = mode
                            u["hybrid_mode"] = (mode == "hybrid")
                            u["direct_mode"] = (mode == "direct")
                            updated = True
                    if updated:
                        with open(users_path, "w", encoding="utf-8") as uf:
                            json.dump(users_data, uf, ensure_ascii=False, indent=2)
            except Exception as ue:
                logger.error(f"Failed to sync target_interval to users.json: {ue}")
    except Exception as e:
        logger.error(f"Error in set_persisted_target_interval: {e}")

# Глобальное состояние
is_monitoring_active = True
_init_int, _init_hybrid, _init_direct = get_persisted_state()
target_check_interval = _init_int
current_check_interval = _init_int
proxy_harvester_running = False                 # Флаг работы фонового сборщика прокси
proxy_wake_event = asyncio.Event()              # Событие мгновенного пробуждения сборщика прокси
admin_waiting_proxy = set()                     # User ID администраторов, ожидающих ввод прокси
start_time = datetime.now()
last_check_time: Optional[datetime] = None
checks_performed_count = 0
primary_admin_id: Optional[int] = ADMIN_CHAT_ID
hybrid_mode_enabled = _init_hybrid              # Гибридный режим: прямой+прокси (прямой при 0 прокси 60-90 сек)
direct_mode_enabled = _init_direct              # Режим прямого подключения: 60 сек, без прокси

def get_safe_interval_for_proxies(target_sec, proxy_count: int) -> int:
    """
    Рассчитывает безопасный интервал:
    Чтобы ни один IP не опрашивал Avito чаще 1 раза в 30 секунд:
    безопасный_интервал = max(target_sec, ceil(30 / max(1, proxy_count)))
    """
    if str(target_sec).startswith("rand") or target_sec == "random_30_60":
        return 30
    try:
        t_int = int(target_sec)
    except Exception:
        t_int = 30
    if proxy_count == 0:
        return max(t_int, 30)
    import math
    min_safe = math.ceil(30 / proxy_count)
    return max(t_int, min_safe)

parser = AvitoParser(proxy=AVITO_PROXY)
dp = Dispatcher()

# Словари состояний ввода
user_waiting_feedback = {}
user_waiting_auth_login = {}  # user_id -> True
user_waiting_auth_pass = {}   # user_id -> username
user_waiting_add_search = {}  # user_id -> True (ожидание ввода ссылки Авито)
admin_waiting_reply_to = {}   # admin_id -> {"chat_id": int, "name": str}
admin_waiting_manual_block = set()  # admin_ids waiting for manual block username/id input
user_waiting_activation = {}  # user_id -> True (ожидание ввода 20-значного кода активации)
admin_waiting_keygen = {}      # admin_id -> "STD" or "VIP" (ожидание Request ID для генерации ключа)

def get_users_json_paths():
    """Возвращает пути к файлам users.json в директории проекта."""
    p_local = os.path.normpath(os.path.join(os.path.dirname(BOT_DIR), "data", "users.json"))
    return [p_local]

def load_site_users() -> list:
    """Загружает список пользователей сайта из users.json с защитой от одновременной записи."""
    import time
    for p in get_users_json_paths():
        if os.path.exists(p):
            for attempt in range(4):
                try:
                    if os.path.getsize(p) == 0:
                        time.sleep(0.06)
                        continue
                    with open(p, "r", encoding="utf-8-sig") as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            return data
                        elif isinstance(data, dict):
                            return [data]
                except Exception as e:
                    if attempt == 3:
                        logger.error(f"Ошибка чтения {p}: {e}")
                    else:
                        time.sleep(0.06)
    return []

def save_site_users(users_list: list) -> bool:
    """Синхронно сохраняет список пользователей сайта в обе директории (E: и C:)."""
    saved_any = False
    for p in get_users_json_paths():
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8-sig") as f:
                json.dump(users_list, f, ensure_ascii=False, indent=2)
            saved_any = True
        except Exception as e:
            logger.error(f"Ошибка сохранения users.json в {p}: {e}")
    return saved_any

def get_site_url() -> str:
    """Определяет локальный IP-адрес сервера или возвращает localhost."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        if ip and not ip.startswith("127."):
            return f"http://{ip}:8080"
    except Exception:
        pass
    return "http://localhost:8080"

def get_guest_auth_markup(user_id: int, username: Optional[str] = None):
    """Генерирует инлайн и реплай кнопки для привязки к программе."""
    site_url = get_site_url()
    inline_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Проверить привязку", callback_data="check_tg_bind"),
            InlineKeyboardButton(text="🌐 Открыть SkyBase", url=f"{site_url}/")
        ],
        [
            InlineKeyboardButton(text="❓ Как привязать программу?", callback_data="auth_help_howto")
        ]
    ])
    reply_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔄 Проверить привязку")],
            [KeyboardButton(text="❓ Как привязать к сайту")]
        ],
        resize_keyboard=True
    )
    return inline_kb, reply_kb

def get_site_user_by_tg_id(tg_id: int, tg_username: Optional[str] = None) -> Optional[dict]:
    """Находит пользователя сайта по его подтвержденному telegram_chat_id или telegram_username."""
    if not tg_id and not tg_username:
        return None
    users = load_site_users()
    # 1. Поиск по подтвержденному telegram_chat_id
    if tg_id:
        for u in users:
            t_id = u.get("telegram_chat_id")
            if t_id is not None and str(t_id).strip() == str(tg_id).strip():
                return u

    # 2. Поиск по подтвержденному telegram_username
    if tg_username:
        clean_user = tg_username.strip().lstrip("@").lower()
        if clean_user:
            for u in users:
                saved_tg_u = (u.get("telegram_username") or "").strip().lstrip("@").lower()
                if saved_tg_u and saved_tg_u == clean_user and u.get("telegram_chat_id"):
                    return u

    return None

def get_site_user_by_username(username: str) -> Optional[dict]:
    """Находит пользователя сайта по логину (без учета регистра)."""
    if not username:
        return None
    target = username.strip().lower()
    for u in load_site_users():
        if (u.get("username") or "").strip().lower() == target:
            return u
    return None

def verify_site_password(plain_password: str, stored_hash: str) -> bool:
    """Проверяет пароль пользователя сайта (sha256 с солью ElectroBase_2026_Salt! или прямой текст)."""
    if not plain_password or not stored_hash:
        return False
    if plain_password.strip() == stored_hash.strip():
        return True
    salt = "ElectroBase_2026_Salt!"
    calc = hashlib.sha256((plain_password.strip() + salt).encode("utf-8")).hexdigest().lower()
    return calc == stored_hash.strip().lower()

def get_chat_json_paths():
    """Возвращает пути к файлам chat_messages.json с приоритетом текущей рабочей директории."""
    p_local = os.path.normpath(os.path.join(os.path.dirname(BOT_DIR), "data", "chat_messages.json"))
    paths = [p_local]
    sync_candidates = [
        r"C:\Program Files (x86)\SkyBotParser\data\chat_messages.json",
        r"C:\Program Files\SkyBotParser\data\chat_messages.json",
        r"D:\ins\skybase\Avito-Parser3\skybase\data\chat_messages.json",
        r"D:\ins\skybase\skybotparser\app\data\chat_messages.json",
        r"e:\TEMP\База-бот\SITE\data\chat_messages.json",
        r"C:\ins\EXP\Arduino\Проект\База-бот\SITE\data\chat_messages.json"
    ]
    for p in sync_candidates:
        if os.path.exists(os.path.dirname(p)) and p not in paths:
            paths.append(p)
    return paths

def load_chat_messages() -> list:
    """Загружает сообщения чата из chat_messages.json."""
    for p in get_chat_json_paths():
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    elif isinstance(data, dict):
                        return [data]
            except Exception as e:
                logger.error(f"Ошибка чтения {p}: {e}")
    return []

def save_chat_messages(messages_list: list) -> bool:
    """Синхронно сохраняет сообщения чата в обе директории (E: и C:)."""
    saved_any = False
    for p in get_chat_json_paths():
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8-sig") as f:
                json.dump(messages_list, f, ensure_ascii=False, indent=4)
            saved_any = True
        except Exception as e:
            logger.error(f"Ошибка записи {p}: {e}")
    return saved_any

def append_chat_message(sender: str, sender_name: str, recipient: str, text: str, extra: Optional[dict] = None) -> dict:
    """Сохраняет сообщение в чат на сайте и синхронизирует."""
    messages = load_chat_messages()
    import time
    msg_id = f"msg_{int(time.time()*1000)}_{random.randint(1000, 9999)}"
    new_msg = {
        "id": msg_id,
        "sender": sender,
        "sender_name": sender_name,
        "recipient": recipient,
        "text": text.strip(),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_read": False
    }
    if extra and isinstance(extra, dict):
        new_msg.update(extra)
    messages.append(new_msg)
    if len(messages) > 500:
        messages = messages[-500:]
    save_chat_messages(messages)
    return new_msg

def get_recent_chat_messages(limit=10):
    """Возвращает последние сообщения из чата сайта."""
    msgs = load_chat_messages()
    return msgs[-limit:] if msgs else []

def save_admin_reply_state(state_dict: dict):
    for p in get_chat_json_paths():
        sp = os.path.join(os.path.dirname(p), "admin_reply_state.json")
        try:
            os.makedirs(os.path.dirname(sp), exist_ok=True)
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(state_dict, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

def load_admin_reply_state() -> dict:
    for p in get_chat_json_paths():
        sp = os.path.join(os.path.dirname(p), "admin_reply_state.json")
        if os.path.exists(sp):
            try:
                with open(sp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return {int(k) if str(k).isdigit() else k: v for k, v in data.items()}
            except Exception:
                pass
    return {}

def extract_device_id_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    m = re.search(r'\b((?:EBID|EBMOB)-[A-Z0-9\-]+)\b', text, re.IGNORECASE)
    if m:
        return m.group(1).upper()
    return None

def find_last_active_client_hwid() -> Optional[str]:
    msgs = load_chat_messages()
    for m in reversed(msgs):
        if str(m.get("id")) == "1":
            continue
        s = str(m.get("sender") or "").strip()
        sid = str(m.get("sender_id") or "").strip()
        hw = str(m.get("hw_id") or "").strip()
        r = str(m.get("recipient") or "").strip()
        rid = str(m.get("recipient_id") or "").strip()
        for cand in [hw, sid, s, rid, r]:
            if cand.upper().startswith(("EBID-", "EBMOB-")):
                return cand.upper()
    return None



def get_authorized_site_user(user_id: int, username: Optional[str] = None) -> Tuple[Optional[dict], Optional[str]]:
    """
    Возвращает (site_user, error_reason).
    Пользователь (включая администратора) считается авторизованным ТОЛЬКО если его Telegram-аккаунт
    был подтвержден и привязан к профилю на сайте.
    Автоматическая привязка запрещена — каждый пользователь должен подтвердить привязку сам в боте.
    """
    site_u = get_site_user_by_tg_id(user_id, username)
    if site_u:
        if site_u.get("is_blocked"):
            return site_u, "blocked"
        return site_u, None

    # Проверяем, ожидает ли данный аккаунт подтверждения привязки
    clean_tg_uname = (username or "").strip().lstrip("@").lower()
    for u in load_site_users():
        pend = u.get("telegram_pending")
        if pend and isinstance(pend, dict) and pend.get("status") == "pending":
            p_h = str(pend.get("handle") or "").strip().lstrip("@").lower()
            p_cid = pend.get("chat_id")
            if (p_cid and int(p_cid) == user_id) or (clean_tg_uname and clean_tg_uname == p_h) or str(user_id) == p_h:
                return None, "pending"

    return None, "not_linked"

async def prompt_unauthorized_user(event, user_id: int, username: Optional[str] = None, full_name: Optional[str] = None, reason: str = "not_linked"):
    """
    Выводит четкое сообщение о необходимости регистрации на сайте и привязки Telegram-аккаунта.
    Скрывает обычное меню кнопок у неавторизованного пользователя.
    """
    site_url = get_site_url()
    tg_hint = f"@{username.lstrip('@')}" if username else f"ID: {user_id}"

    if reason == "blocked":
        text = (
            "⛔️ <b>Доступ заблокирован</b>\n\n"
            "Ваш аккаунт заблокирован администратором сервиса <b>SkyBase</b>.\n"
            "Пожалуйста, свяжитесь с поддержкой на сайте для уточнения причин."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Открыть сайт SkyBase", url=f"{site_url}/")]
        ])
    elif reason == "tg_disabled":
        text = (
            "⚠️ <b>Telegram-бот отключен в настройках вашего тарифа</b>\n\n"
            "В вашем личном кабинете на сайте SkyBase выключен доступ к Telegram-боту.\n"
            "Вы можете включить его на сайте возле кнопки «📱 Бот» или обратиться к администратору."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🌐 Перейти на сайт", url=f"{site_url}/")]
        ])
    else:
        text = (
            "ℹ️ <b>Привязка Telegram к SkyBase</b>\n\n"
            "SkyBase — это ваша персональная программа мониторинга объявлений на ПК. "
            "Для получения уведомлений и связи привяжите этот Telegram-аккаунт в вашей программе:\n\n"
            f"1️⃣ Откройте программу SkyBase на вашем ПК: <a href=\"{site_url}/\"><b>{site_url}</b></a>\n"
            f"2️⃣ Вверху возле кнопки <b>«📱 Бот»</b> укажите ваш Telegram: <code>{tg_hint}</code> и нажмите <b>«Привязать»</b>.\n\n"
            f"3️⃣ После этого нажмите кнопку <b>«🔄 Проверить привязку»</b> ниже или отправьте команду /start."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="🔄 Проверить привязку", callback_data="check_tg_bind"),
                InlineKeyboardButton(text="🌐 Открыть программу", url=f"{site_url}/")
            ],
            [
                InlineKeyboardButton(text="❓ Как привязать аккаунт?", callback_data="auth_help_howto")
            ]
        ])

    if isinstance(event, CallbackQuery):
        await event.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await event.answer()
    else:
        # Убираем клавиатуру управления ботом
        await event.answer(text, reply_markup=ReplyKeyboardRemove(), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await event.answer("👇 Нажмите для проверки привязки:", reply_markup=kb)


async def is_admin(user_id: int, username: Optional[str] = None) -> bool:
    """Проверка, является ли пользователь главным администратором (@skynet19081983)."""
    global primary_admin_id
    if not user_id:
        return False
    if primary_admin_id and int(user_id) == int(primary_admin_id):
        return True
    if ADMIN_CHAT_ID and int(user_id) == int(ADMIN_CHAT_ID):
        primary_admin_id = user_id
        return True
    if str(user_id) in ("5680198246", str(ADMIN_CHAT_ID)):
        primary_admin_id = user_id
        return True
    clean_u = (username or "").strip().lstrip("@").lower()
    if clean_u in ("skynet19081983", "skynet83", ADMIN_USERNAME.lower()):
        primary_admin_id = user_id
        return True
    site_u = get_site_user_by_tg_id(user_id, username)
    if site_u:
        site_tg = (site_u.get("telegram_username") or "").strip().lstrip("@").lower()
        site_cid = site_u.get("telegram_chat_id")
        if site_tg in ("skynet19081983", "skynet83", ADMIN_USERNAME.lower()):
            primary_admin_id = user_id
            return True
        if site_cid and (str(site_cid).strip() in (str(ADMIN_CHAT_ID), "5680198246")):
            primary_admin_id = user_id
            return True
        if (site_u.get("username") or "").lower() in ("skynet83", "skynet19081983") or site_u.get("role") == "admin":
            primary_admin_id = user_id
            return True
    # Проверяем в users.json
    try:
        for u in load_site_users():
            if (u.get("role") == "admin" or (u.get("username") or "").lower() in ("skynet83", "skynet19081983")):
                if u.get("telegram_chat_id") and str(u["telegram_chat_id"]).strip() == str(user_id).strip():
                    primary_admin_id = user_id
                    return True
    except Exception:
        pass
    return False


async def is_authorized(user_id: int, username: Optional[str] = None) -> bool:
    """Проверка, имеет ли пользователь доступ к боту."""
    site_u, reason = get_authorized_site_user(user_id, username)
    return site_u is not None and reason != "blocked"


async def check_auth_or_prompt(message: types.Message) -> Optional[dict]:
    """
    Проверяет авторизацию пользователя.
    Если пользователь заблокирован — выводит уведомление.
    В остальных случаях возвращает словарь site_u.
    """
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    site_u, reason = get_authorized_site_user(user_id, username)
    if site_u and reason != "blocked":
        return site_u

    if reason == "blocked":
        await prompt_unauthorized_user(message, user_id, username, full_name, "blocked")
        return None

    return site_u


def get_license_keys_path() -> str:
    """Возвращает путь к базе ключей license_keys.json."""
    p = os.path.normpath(os.path.join(os.path.dirname(BOT_DIR), "data", "license_keys.json"))
    return p


def get_activation_lock_path() -> str:
    """Возвращает путь к файлу с попытками ввода ключей activation_lock.json."""
    return os.path.normpath(os.path.join(os.path.dirname(BOT_DIR), "data", "activation_lock.json"))


def load_activation_lock() -> dict:
    """Загружает данные блокировок попыток активации."""
    p = get_activation_lock_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_activation_lock(data: dict):
    """Сохраняет данные блокировок попыток активации."""
    p = get_activation_lock_path()
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Ошибка сохранения activation_lock.json: {e}")


def check_activation_attempts(identity: str) -> tuple:
    """
    Проверяет, заблокирован ли ввод ключей для identity (user_id или username).
    Возвращает (is_blocked: bool, remaining_seconds: int, attempts_made: int).
    """
    locks = load_activation_lock()
    rec = locks.get(str(identity))
    if not rec:
        return False, 0, 0

    attempts = int(rec.get("attempts", 0))
    blocked_until_str = rec.get("blocked_until")
    if blocked_until_str:
        try:
            blocked_dt = datetime.strptime(blocked_until_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            if now < blocked_dt:
                rem_sec = int((blocked_dt - now).total_seconds())
                return True, rem_sec, attempts
            else:
                # 24 часа прошло — сбрасываем блокировку
                locks.pop(str(identity), None)
                save_activation_lock(locks)
                return False, 0, 0
        except Exception:
            pass
    return False, 0, attempts


def record_failed_activation_attempt(identity: str) -> tuple:
    """
    Записывает неудачную попытку ввода ключа.
    При 3 неудаче блокирует на 24 часа.
    Возвращает (is_now_blocked: bool, attempts_made: int, blocked_until: str).
    """
    from datetime import timedelta
    locks = load_activation_lock()
    ident_str = str(identity)
    rec = locks.get(ident_str, {"attempts": 0, "blocked_until": None})
    attempts = int(rec.get("attempts", 0)) + 1
    rec["attempts"] = attempts

    is_blocked = False
    blocked_until = None
    if attempts >= 3:
        is_blocked = True
        blocked_dt = datetime.now() + timedelta(hours=24)
        blocked_until = blocked_dt.strftime("%Y-%m-%d %H:%M:%S")
        rec["blocked_until"] = blocked_until

    locks[ident_str] = rec
    save_activation_lock(locks)
    return is_blocked, attempts, blocked_until


def reset_activation_attempts(identity: str):
    """Сбрасывает неудачные попытки при успешной активации."""
    locks = load_activation_lock()
    ident_str = str(identity)
    if ident_str in locks:
        locks.pop(ident_str, None)
        save_activation_lock(locks)


def activate_key_for_user(raw_key: str, identity: str, username: Optional[str] = None) -> tuple:
    """
    Активирует ключ:
    - Проверяет блокировку попыток (3 ошибки -> блок 24ч).
    - Проверяет SHA-256 хэш в license_keys.json.
    - Помечает использованным.
    - Продлевает тариф пользователя в users.json на +30 дней.
    Возвращает (success: bool, message: str).
    """
    is_blocked, rem_sec, _ = check_activation_attempts(identity)
    if is_blocked:
        hours = rem_sec // 3600
        mins = (rem_sec % 3600) // 60
        return False, f"⛔️ <b>Ввод кодов временно заблокирован!</b>\n\nПревышено число неверных попыток (3 из 3).\nПовторная попытка будет доступна через <b>{hours} ч. {mins} мин.</b>"

    clean_key = re.sub(r"[^A-Za-z0-9]", "", raw_key).strip().upper()
    if len(clean_key) != 20:
        is_now_blocked, attempts, _ = record_failed_activation_attempt(identity)
        rem = max(0, 3 - attempts)
        if is_now_blocked:
            return False, "⛔️ <b>Ввод кодов заблокирован на 24 часа!</b>\nВы 3 раза ввели неверный код активации. Кнопка и приём ключей деактивированы."
        return False, f"❌ <b>Неверный формат ключа!</b> Код должен состоять ровно из 20 символов (например, <code>XXXX-XXXX-XXXX-XXXX-XXXX</code>).\nОсталось попыток: <b>{rem}</b> из 3."

    # Вычисляем SHA-256
    h = hashlib.sha256(clean_key.encode("utf-8")).hexdigest()
    keys_path = get_license_keys_path()
    if not os.path.exists(keys_path):
        return False, "❌ База лицензионных ключей не найдена на сервере."

    try:
        with open(keys_path, "r", encoding="utf-8") as f:
            keys_db = json.load(f)
    except Exception as e:
        return False, f"❌ Ошибка чтения базы лицензий: {e}"

    if h not in keys_db:
        is_now_blocked, attempts, _ = record_failed_activation_attempt(identity)
        rem = max(0, 3 - attempts)
        if is_now_blocked:
            return False, "⛔️ <b>Ввод кодов заблокирован на 24 часа!</b>\nВы 3 раза ввели неверный код активации. Кнопка активации и приём ключей деактивированы."
        return False, f"❌ <b>Указанный ключ активации не существует!</b>\nПожалуйста, проверьте правильность ввода.\nОсталось попыток: <b>{rem}</b> из 3."

    key_record = keys_db[h]
    if key_record.get("used"):
        used_at = key_record.get("used_at") or "ранее"
        is_now_blocked, attempts, _ = record_failed_activation_attempt(identity)
        rem = max(0, 3 - attempts)
        if is_now_blocked:
            return False, "⛔️ <b>Ввод кодов заблокирован на 24 часа!</b>\nВы 3 раза ввели неверный код активации."
        return False, f"⚠️ <b>Этот ключ уже был использован ({used_at})!</b>\nКаждый ключ является одноразовым.\nОсталось попыток: <b>{rem}</b> из 3."

    # Ключ верный! Помечаем как использованный
    key_record["used"] = True
    key_record["used_by"] = username or str(identity)
    key_record["used_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(keys_path, "w", encoding="utf-8") as f:
        json.dump(keys_db, f, ensure_ascii=False, indent=2)

    reset_activation_attempts(identity)

    # Продлеваем тариф пользователя на 30 дней
    from datetime import timedelta
    users = load_site_users()
    target_u = None
    for u in users:
        t_id = u.get("telegram_chat_id")
        if t_id and str(t_id).strip() == str(identity).strip():
            target_u = u
            break
        if username and (u.get("username") or "").strip().lower() == username.strip().lower():
            target_u = u
            break
    if not target_u:
        return False, "⚠️ <b>Пользователь не найден!</b>\nНевозможно применить ключ активации."

    is_unlimited_key = bool(key_record.get("is_unlimited") or str(key_record.get("duration_days")) == "unlimited")

    if target_u:
        perms = target_u.setdefault("permissions", {})
        perms["avito"] = True
        perms["avito_bot"] = True
        perms["monitoring"] = True
        perms["tg_bot"] = True
        perms["is_expired"] = False
        if is_unlimited_key:
            perms["avito_duration"] = "unlimited"
            perms["avito_expires_at"] = None
            save_site_users(users)
            return True, "👑 <b>VIP-код успешно активирован!</b>\n\n♾ <b>Вам предоставлен БЕССРОЧНЫЙ доступ (Безлимит навсегда)!</b>\nНикаких ограничений по времени действия."
        else:
            curr_exp_str = perms.get("avito_expires_at")
            now = datetime.now()
            base_dt = now
            if curr_exp_str:
                try:
                    curr_dt = datetime.strptime(curr_exp_str, "%Y-%m-%d %H:%M:%S")
                    if curr_dt > now:
                        base_dt = curr_dt
                except Exception:
                    base_dt = now

            new_exp_dt = base_dt + timedelta(days=30)
            new_exp_str = new_exp_dt.strftime("%Y-%m-%d %H:%M:%S")
            perms["avito_duration"] = "30_days"
            perms["avito_expires_at"] = new_exp_str
            save_site_users(users)
            return True, f"🎉 <b>Код успешно активирован!</b>\n\n📦 <b>Тариф продлен на 30 дней!</b>\n⏳ Новый срок действия: <b>до {new_exp_str}</b>."

    if is_unlimited_key:
        return True, "👑 <b>VIP-код успешно активирован на бессрочный доступ!</b>"
    return True, "🎉 <b>Ключ успешно активирован на 30 дней!</b>"


def format_remaining_tariff_time(total_seconds: int, exp_dt: Optional[datetime] = None) -> str:
    """Форматирует оставшееся время тарифа: дни, часы, минуты, секунды."""
    if total_seconds <= 0:
        return "Истек"
    def plural_ru(n, one, few, many):
        mod10 = n % 10
        mod100 = n % 100
        if 11 <= mod100 <= 19:
            return many
        if mod10 == 1:
            return one
        if 2 <= mod10 <= 4:
            return few
        return many
    now = datetime.now()
    if exp_dt:
        cal_days = (exp_dt.date() - now.date()).days
    else:
        cal_days = total_seconds // 86400

    if cal_days >= 1:
        return f"{cal_days} {plural_ru(cal_days, 'день', 'дня', 'дней')}"
    elif total_seconds >= 3600:
        hours = total_seconds // 3600
        return f"{hours} {plural_ru(hours, 'час', 'часа', 'часов')}"
    elif total_seconds >= 60:
        mins = total_seconds // 60
        return f"{mins} {plural_ru(mins, 'минута', 'минуты', 'минут')}"
    else:
        secs = max(0, total_seconds)
        return f"{secs} {plural_ru(secs, 'секунда', 'секунды', 'секунд')}"


def format_user_privileges_card(site_u: dict, user_urls_count: int, is_silent: bool) -> str:
    """Формирует наглядную карточку привилегий, тарифа и лимитов пользователя."""
    perms = site_u.get("permissions") or {}
    role = site_u.get("role", "user")
    is_adm = (role == "admin" or (site_u.get("username") or "").lower() in ("skynet83", "skynet19081983") or (site_u.get("telegram_username") or "").lower() in ("skynet83", "skynet19081983"))

    role_title = "👑 Главный Администратор (@skynet19081983)" if is_adm else "👤 Клиент сервиса"
    login = site_u.get("username", "")
    name = site_u.get("name") or login

    # Срок действия тарифа
    is_exp = perms.get("is_expired") is True
    active_k = perms.get("active_key")
    exp_str = perms.get("avito_expires_at")
    duration = perms.get("avito_duration")
    if is_adm:
        tariff_status = "♾ Безлимит (Админ)"
    elif duration == "unlimited" or not is_exp:
        tariff_status = "🟢 Уведомления активны (Безлимит)"
    elif exp_str:
        try:
            exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
            now = datetime.now()
            total_sec = int((exp_dt - now).total_seconds())
            if total_sec <= 0:
                tariff_status = "🟢 Уведомления активны"
            else:
                rem_text = format_remaining_tariff_time(total_sec, exp_dt)
                tariff_status = f"⏳ {rem_text} (до {exp_str})"
        except Exception:
            tariff_status = f"✅ До {exp_str}"
    else:
        tariff_status = "🟢 Уведомления активны"

    # Лимит поисков (максимум 10)
    max_s = min(10, 10 if is_adm else int(perms.get("max_searches") or 10))
    limit_str = f"<b>{user_urls_count}</b> из <b>{max_s}</b>"

    sound_status = "🔕 ВЫКЛ (тихий)" if is_silent else "🔔 ВКЛ (со звуком)"

    user_label = "Администратор" if is_adm else f"<b>{html.escape(name)}</b>" + (f" (логин: <code>{html.escape(login)}</code>)" if name != login else "")
    lines = [
        f"👤 <b>Пользователь:</b> {user_label}",
        f"🏷 <b>Роль:</b> {role_title}",
        f"📦 <b>Тариф:</b> {tariff_status}",
        f"🔍 <b>Лимит ссылок:</b> {limit_str}",
        f"🔔 <b>Звук уведомлений:</b> {sound_status}"
    ]
    return "\n".join(lines)


async def show_welcome_panel(target_message: types.Message, site_u: dict, user_id: int, username: Optional[str], full_name: Optional[str]):
    """Отображает лаконичное меню бота без громоздких списков команд."""
    is_user_admin = await is_admin(user_id, username)
    silent = await is_silent_mode(user_id)
    urls = await get_user_tracked_urls(user_id)

    privileges_card = format_user_privileges_card(site_u, len(urls), silent)

    if is_user_admin:
        primary_admin_id = user_id
        text = (
            f"👑 <b>Панель Администратора</b>\n\n"
            f"💡 <i>Выберите действие в меню внизу экрана.</i>"
        )
        await target_message.answer(text, reply_markup=get_main_keyboard(is_user_admin=True, is_silent=silent), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    else:
        is_active = is_system_or_user_monitoring_active(user_id, username)
        panel_text = format_control_panel_text(is_active)
        panel_kb = get_control_panel_keyboard(is_active)
        text = (
            f"👋 <b>Здравствуйте, {html.escape(site_u.get('name') or full_name or '')}!</b>\n\n"
            f"{privileges_card}\n\n"
            f"💡 <i>Отправьте ссылку на Avito для мгновенного добавления в мониторинг.</i>"
        )
        await target_message.answer(text, reply_markup=get_main_keyboard(is_user_admin=False, is_silent=silent, is_active=is_active, user_id=user_id, username=username), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await target_message.answer(panel_text, reply_markup=panel_kb, parse_mode=ParseMode.HTML)


def add_search_to_site_users(user_id: int, username_or_tg: Optional[str], search_item: dict) -> bool:
    """Добавляет поисковую ссылку в avito_searches пользователя в users.json для мгновенной синхронизации."""
    users = load_site_users()
    target_u = None
    for u in users:
        t_id = u.get("telegram_chat_id")
        if t_id is not None and str(t_id).strip() == str(user_id).strip():
            target_u = u
            break
        if username_or_tg:
            clean_u = username_or_tg.strip().lstrip("@").lower()
            saved_u = (u.get("telegram_username") or "").strip().lstrip("@").lower()
            if saved_u and saved_u == clean_u:
                target_u = u
                break
            if (u.get("username") or "").strip().lower() == clean_u:
                target_u = u
                break
    if not target_u:
        return False

    searches = target_u.setdefault("avito_searches", [])
    clean_url = search_item.get("url", "").strip().rstrip('/')
    found = False
    for s in searches:
        if isinstance(s, dict) and s.get("url", "").strip().rstrip('/') == clean_url:
            s.update(search_item)
            found = True
            break
    if not found:
        searches.append(search_item)

    save_site_users(users)
    return True


def delete_search_from_site_users(user_id: int, search_id: int, username: Optional[str] = None, url: Optional[str] = None) -> bool:
    """Удаляет поисковую ссылку из avito_searches пользователя в users.json по id и/или url."""
    users = load_site_users()
    changed = False
    clean_uname = (username or "").strip().lower()
    clean_url = (url or "").strip().rstrip("/").lower()
    for u in users:
        t_id = u.get("telegram_chat_id")
        u_name = (u.get("username") or "").strip().lower()
        is_match = False
        if t_id is not None and str(t_id).strip() == str(user_id).strip():
            is_match = True
        elif clean_uname and u_name == clean_uname:
            is_match = True
        elif user_id == ADMIN_CHAT_ID and (u.get("role") == "admin" or u_name == "skynet83"):
            is_match = True

        if is_match:
            searches = u.get("avito_searches") or []
            new_searches = []
            for s in searches:
                if not isinstance(s, dict):
                    continue
                s_id = str(s.get("id", "")).strip()
                s_url = (s.get("url") or "").strip().rstrip("/").lower()
                if search_id and (s_id == str(search_id).strip() or str(s.get("id")) == str(search_id)):
                    continue
                if clean_url and s_url == clean_url:
                    continue
                new_searches.append(s)
            if len(new_searches) != len(searches):
                u["avito_searches"] = new_searches
                changed = True
            break
    if changed:
        save_site_users(users)
    return changed




def get_avito_checkout_url(item_id: str, item_url: Optional[str] = None) -> str:
    """
    Генерирует прямую ссылку на оформление заказа через Авито Доставку:
    https://www.avito.ru/order/delivery/checkout/{item_id}?source=item[&context={context}]
    Параметр context извлекается из ссылки на объявление (item_url), если он там присутствует.
    """
    clean_id = str(item_id or "").strip()
    if not clean_id:
        return ""
    base = f"https://www.avito.ru/order/delivery/checkout/{clean_id}?source=item"
    if item_url:
        try:
            parsed = urlparse(item_url)
            params = parse_qs(parsed.query)
            ctx_list = params.get("context")
            if ctx_list and ctx_list[0]:
                base += f"&context={quote(ctx_list[0])}"
        except Exception:
            pass
    return base


def is_system_or_user_monitoring_active(user_id: Optional[int] = None, username: Optional[str] = None) -> bool:
    """Определяет текущий статус мониторинга (глобальный или персональный)."""
    global is_monitoring_active
    try:
        if SITE_DIR not in sys.path:
            sys.path.insert(0, SITE_DIR)
        import avito_api_helper
        paused = avito_api_helper.get_bot_paused()
        if paused:
            return False
    except Exception:
        pass

    if user_id is not None:
        try:
            u_list = load_site_users()
            uname = (username or "").strip().lower()
            for u in u_list:
                tg_id = u.get("telegram_chat_id")
                u_site = (u.get("username") or "").strip().lower()
                if (tg_id and str(tg_id).strip() == str(user_id).strip()) or (uname and u_site == uname) or (uname in ("skynet19081983", "skynet83") and (u_site in ("skynet83", "admin") or u.get("role") == "admin")):
                    perms = u.get("permissions") or {}
                    if perms.get("tg_bot") is False:
                        return False
                    return True
        except Exception:
            pass

    return bool(is_monitoring_active)


def get_control_panel_keyboard(is_active: bool) -> InlineKeyboardMarkup:
    """
    Панель управления ровно с двумя кнопками:
    - Активен: '⚪ Включить' (серая/затемненная, некликабельная) и '⏹️ Выключить' (доступная/активная).
    - Остановлен: '▶️ Включить' (доступная/активная) и '⚪ Выключить' (серая/затемненная, некликабельная).
    """
    if is_active:
        kb = [
            [
                InlineKeyboardButton(text="⚪ Включить", callback_data="cp_noop_active"),
                InlineKeyboardButton(text="⏹️ Выключить", callback_data="cp_stop")
            ]
        ]
    else:
        kb = [
            [
                InlineKeyboardButton(text="▶️ Включить", callback_data="cp_start"),
                InlineKeyboardButton(text="⚪ Выключить", callback_data="cp_noop_stopped")
            ]
        ]
    return InlineKeyboardMarkup(inline_keyboard=kb)


def format_control_panel_text(is_active: bool) -> str:
    """Текст для панели управления ТГ-уведомлениями."""
    if is_active:
        return (
            "🎛 <b>Панель управления</b>\n\n"
            "Статус: 🟢 <b>ТГ-уведомления: ВКЛ</b>\n\n"
            "• Кнопка «Включить» затемнена (некликабельна)\n"
            "• Доступна кнопка «Выключить»"
        )
    else:
        return (
            "🎛 <b>Панель управления</b>\n\n"
            "Статус: 🔴 <b>ТГ-уведомления: ВЫКЛ</b>\n\n"
            "• Кнопка «Выключить» затемнена (некликабельна)\n"
            "• Доступна кнопка «Включить»"
        )


def create_ad_keyboard(ad_url: str, item_id: str, seller: Optional[str] = None, has_delivery: bool = False) -> Optional[InlineKeyboardMarkup]:
    """
    Клавиатура под карточкой объявления.
    Все кнопки удалены по требованию: кнопок нет.
    """
    return None


def format_ad_caption(ad: AvitoAd, search_name: str, old_price: Optional[str] = None) -> str:
    """Форматирует карточку объявления: чистый текст с деталями и прямой ссылкой на товар возле названия."""
    lines = []
    raw_url = ad.url if ad.url else f"https://www.avito.ru/{ad.id}"
    clean_url = raw_url.split("?")[0] if raw_url else f"https://www.avito.ru/{ad.id}"
    target_url = html.escape(clean_url, quote=True)
    safe_title = html.escape(ad.title or "Товар на Авито")

    if old_price:
        lines.append("🔥 <b>Снижение цены!</b>\n")
        price_line = f"💰 <b>Цена:</b> <s>{html.escape(str(old_price))}</s> ➔ <b>{html.escape(str(ad.price))}</b>"
    else:
        price_line = f"💰 <b>Цена:</b> {html.escape(str(ad.price))}"

    city_line = f"🏘️ <b>Город:</b> {html.escape(str(ad.address))}" if ad.address else "🏘️ <b>Город:</b> Не указан"
    
    # Тип продавца (без дублирования иконки в скобках)
    seller_type = getattr(ad, "seller_type", None) or ("Компания" if getattr(ad, "is_company", False) else "Частное лицо")
    if ad.seller:
        seller_line = f"👤 <b>Продавец:</b> {html.escape(str(ad.seller))} ({html.escape(str(seller_type))})"
    else:
        seller_line = f"👤 <b>Продавец:</b> {html.escape(str(seller_type))}"

    # Доставка
    delivery_line = "🚚 <b>Доставка:</b> Доступна (Авито Доставка)" if getattr(ad, "has_delivery", False) else "🚚 <b>Доставка:</b> Самовывоз"

    search_line = f"🔎 <b>Поиск:</b> <i>{html.escape(str(search_name))}</i>"

    # Название товара со стрелкой-ссылкой прямо возле названия (как на сайте)
    lines.append(f"🏷 <b>{safe_title}</b> <a href=\"{target_url}\"><b>↗️</b></a>\n")
    lines.append(price_line)
    lines.append(city_line)
    lines.append(seller_line)
    lines.append(delivery_line)
    lines.append(search_line)
    lines.append("\n━━━━━━━━━━━━━━━━━━━━")

    return "\n".join(lines)


def get_main_keyboard(is_user_admin: bool = False, is_silent: bool = False, is_active: Optional[bool] = None, user_id: Optional[int] = None, username: Optional[str] = None) -> ReplyKeyboardMarkup:
    """Создаёт постоянное удобное меню кнопок внизу экрана."""
    silent_text = "🔕 Звук: ВЫКЛ" if is_silent else "🔔 Звук: ВКЛ"
    
    start_btn = KeyboardButton(text="▶️ Включить")
    stop_btn = KeyboardButton(text="⏹️ Выключить")

    if is_user_admin:
        keyboard = [
            [KeyboardButton(text="👥 Пользователи"), KeyboardButton(text="💬 Чат с пользователями")],
            [start_btn, stop_btn]
        ]
    else:
        keyboard = [
            [start_btn, stop_btn]
        ]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


# Словарь для кэширования seller по item_id (для колбэка добавления в ЧС)
ad_sellers_cache = {}


async def send_notification_to_user(bot: Bot, user_id: int, ad: AvitoAd, search_name: str, old_price: Optional[str] = None):
    """
    Отправляет объявление с реальной фотографией товара:
    - Фото кликабельно: можно нажать, открыть на весь экран, зумить и детально рассмотреть.
    - Никаких розовых ссылочных блоков превью нет.
    - Учитывает настройку тихих уведомлений (без звука).
    """
    # Если уведомления или лицензия неактивны — прерываем отправку
    if not is_license_active():
        logger.warning(f"Лицензия не активна/истекла: отправка уведомления для user_id={user_id} заблокирована.")
        return

    if not is_user_tg_enabled(user_id):
        return

    # Сохраняем имя продавца в кэш для кнопки "В ЧС"
    if ad.seller:
        ad_sellers_cache[ad.id] = ad.seller

    text = format_ad_caption(ad, search_name, old_price=old_price)
    kb = create_ad_keyboard(ad.url, ad.id, seller=ad.seller, has_delivery=getattr(ad, "has_delivery", False))
    silent = await is_silent_mode(user_id)

    # Извлекаем URL фото из ad.photo или ad.photos
    target_photo_url = None
    if getattr(ad, "photo", None) and str(ad.photo).strip().startswith("http"):
        target_photo_url = str(ad.photo).strip()
    elif getattr(ad, "photos", None):
        pts = ad.photos
        if isinstance(pts, str) and pts.strip().startswith("["):
            try:
                import json as _json
                pts = _json.loads(pts)
            except Exception:
                pts = []
        if isinstance(pts, list) and len(pts) > 0:
            for p_item in pts:
                if isinstance(p_item, str) and p_item.strip().startswith("http"):
                    target_photo_url = p_item.strip()
                    break
                elif isinstance(p_item, dict):
                    cand = p_item.get("1280x960") or p_item.get("1024x768") or p_item.get("864x648") or p_item.get("678x678") or p_item.get("url") or p_item.get("src")
                    if cand and str(cand).strip().startswith("http"):
                        target_photo_url = str(cand).strip()
                        break

    if target_photo_url:
        img_proxy = None
        if hasattr(parser, "proxy_pool") and parser.proxy_pool and parser.proxy_pool.proxies:
            img_proxy = parser.proxy_pool.get_next_proxy()
        if not img_proxy:
            try:
                user_prx = await get_user_proxies(user_id)
                if user_prx:
                    img_proxy = user_prx[0]
            except Exception:
                pass

        photo_bytes = None
        # 1. Сначала пробуем скачать через прокси
        if img_proxy:
            try:
                px = ("socks5h://" + img_proxy[9:]) if img_proxy.startswith("socks5://") else img_proxy
                async with AsyncSession(impersonate="safari15_5", proxy=px) as img_session:
                    resp = await img_session.get(target_photo_url, timeout=5)
                    if resp.status_code == 200 and resp.content:
                        photo_bytes = resp.content
            except Exception as e:
                err_s = str(e).lower()
                if "chat not found" in err_s or "blocked" in err_s:
                    logger.warning(f"Пользователь {user_id} не активировал бота или заблокировал его ({e}). Пропуск.")
                    return

        # 2. Если через прокси не вышло — скачиваем напрямую с CDN Авито (CDN отдает статику без блокировок)
        if not photo_bytes:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Referer": "https://www.avito.ru/",
                    "Accept": "image/webp,image/apng,image/*,*/*;q=0.8"
                }
                async with AsyncSession(impersonate="safari15_5") as img_session:
                    resp = await img_session.get(target_photo_url, headers=headers, timeout=5)
                    if resp.status_code == 200 and resp.content:
                        photo_bytes = resp.content
            except Exception:
                pass

        if photo_bytes:
            try:
                photo_file = BufferedInputFile(photo_bytes, filename=f"item_{ad.id}.jpg")
                await bot.send_photo(
                    chat_id=user_id,
                    photo=photo_file,
                    caption=text,
                    reply_markup=kb,
                    parse_mode=ParseMode.HTML,
                    disable_notification=silent
                )
                return
            except Exception as e:
                err_s = str(e).lower()
                if "chat not found" in err_s or "blocked" in err_s:
                    logger.warning(f"Пользователь {user_id} не активировал бота или заблокировал его ({e}). Пропуск.")
                    return

        # 3. Передаем URL фото в Telegram напрямую если байты не скачались
        try:
            await bot.send_photo(
                chat_id=user_id,
                photo=target_photo_url,
                caption=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
                disable_notification=silent
            )
            return
        except Exception as e:
            err_s = str(e).lower()
            if "chat not found" in err_s or "blocked" in err_s:
                logger.warning(f"Пользователь {user_id} не активировал бота или заблокировал его ({e}). Пропуск.")
                return

    # Если у объявления нет фото или загрузка не удалась - отправляем заглушку "НЕТ ФОТО"
    no_photo_path = os.path.join(os.path.dirname(__file__), "no_photo.jpg")
    if os.path.exists(no_photo_path):
        try:
            photo_file = FSInputFile(no_photo_path)
            await bot.send_photo(
                chat_id=user_id,
                photo=photo_file,
                caption=text,
                reply_markup=kb,
                parse_mode=ParseMode.HTML,
                disable_notification=silent
            )
            return
        except Exception as e:
            err_s = str(e).lower()
            if "chat not found" in err_s or "blocked" in err_s:
                logger.warning(f"Пользователь {user_id} не активировал бота или заблокировал его ({e}). Пропуск.")
                return
            logger.warning(f"Не удалось отправить заглушку 'НЕТ ФОТО': {e}")

    # Крайний fallback - текстовое сообщение
    try:
        await bot.send_message(
            chat_id=user_id,
            text=text,
            reply_markup=kb,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
            disable_notification=silent
        )
    except Exception as e:
        logger.error(f"Не удалось доставить сообщение пользователю {user_id}: {e}")

def is_user_tg_enabled(user_id: int) -> bool:
    """Проверяет, включены ли уведомления Telegram для пользователя (активен, не заблокирован)."""
    users = load_site_users()
    for u in users:
        tg_id = u.get("telegram_chat_id")
        is_match = False
        if tg_id and str(tg_id).strip() == str(user_id).strip():
            is_match = True
        elif user_id == ADMIN_CHAT_ID and (u.get("role") == "admin" or (u.get("username") or "").lower() == "skynet83"):
            is_match = True

        if is_match:
            if u.get("is_blocked"):
                return False
            perms = u.get("permissions") or {}
            if perms.get("tg_bot") is False:
                return False
            return True
    return True


# Глобальный замок для отправки уведомлений в Telegram (защита от Flood limits 429 при параллельных запросах)
tg_notification_lock = asyncio.Lock()


async def _poll_single_search_task(bot: Bot, task: dict, task_proxy: Optional[str], initial_seed_user: Optional[int] = None) -> int:
    """Опрашивает одну конкретную поисковую ссылку через переданный прокси."""
    if not is_license_active():
        return 0

    task_id = task["id"]
    user_id = task["user_id"]
    name = task["name"]
    url = task["url"]
    is_initialized = bool(task.get("is_initialized", 0))
    total_seen = await get_total_seen_count(user_id)
    items_found = 0

    if not task_proxy or task_proxy == "direct":
        logger.warning(f"🛡️ Пропуск #{task_id} ('{name}', user_id={user_id}): нет доступных прокси (прямой опрос запрещён для защиты IP).")
        return 0

    # Если поиск ещё не был инициализирован или не имеет времени опроса — первый сбор (базовый срез):
    # сохраняем текущие объявления БЕЗ отправки сообщений в Telegram, чтобы не было спама.
    is_first_run = (not is_initialized) or (task.get("last_polled_at") is None) or bool(initial_seed_user)
    try:
        conf_depth = get_configured_search_depth()
        pages_to_fetch = conf_depth if is_first_run else 1
        ads = await parser.fetch_ads(url, proxy=task_proxy, max_pages=pages_to_fetch)
        for ad in ads:
            # Фильтр удаленных объявлений: всегда учитываем удаленные карточки (включая первый сбор)
            if await is_item_deleted(str(ad.id), user_id=user_id):
                continue

            # Фильтр зарезервированных/забронированных товаров
            ad_title_str = str(getattr(ad, "title", "") or "").lower()
            is_ad_res = getattr(ad, "is_reserved", False) or any(w in ad_title_str for w in [
                "зарезервирован", "забронирован", "в резерве", "товар забронирован", "товар в резерве",
                "бронь", "(бронь)", "[бронь]", "резерв", "(рез)", "[рез]"
            ])
            if is_ad_res:
                await delete_seen_item(str(ad.id))
                try:
                    async with aiosqlite.connect(DATABASE_PATH) as db:
                        await db.execute("DELETE FROM deleted_items WHERE item_id = ?", (str(ad.id),))
                        await db.commit()
                except Exception:
                    pass
                logger.info(f"Объявление #{ad.id} удалено из базы: товар зарезервирован на Авито.")
                continue

            # Фильтр цены и релевантности (отсекаем цены вне диапазона, мусор, чужие модели и запчасти)
            ad_price_val = getattr(ad, "price", None)
            if not is_ad_in_price_range(ad_price_val, url, name) or not is_relevant_ad(ad.title, url, name, ad_price_val):
                continue

            # Фильтр доставки: если включен поиск только с доставкой (в настройках или в URL d=1/cd=1)
            task_only_deliv = bool(task.get("only_delivery", 0)) or ("d=1" in url) or ("cd=1" in url)
            if task_only_deliv and not getattr(ad, "has_delivery", False):
                continue

            # Фильтр Черного Списка (Blacklist)
            if ad.seller and await is_blacklisted(user_id, ad.seller, getattr(ad, "url", None), getattr(ad, "address", None)):
                logger.info(f"Объявление пропущено (продавец '{ad.seller}' в ЧС у user_id={user_id}): {ad.title}")
                continue

            already_in_tg = await is_tg_notified(user_id, ad.id)
            seen = await is_seen(user_id, ad.id)
            user_tg_on = is_user_tg_enabled(user_id)

            if not seen:
                # Если первый запуск ИЛИ товар уже отправлялся ранее в TG ИЛИ TG выключен — глушим
                target_notified = 1 if (is_first_run or already_in_tg or not user_tg_on) else 0
                await add_seen(user_id, ad.id, ad.title, ad.price, ad.url, photo=ad.photo, photos=getattr(ad, "photos", None), seller=ad.seller, address=ad.address, search_name=name, has_delivery=int(ad.has_delivery), seller_type=getattr(ad, "seller_type", "Частное лицо"), item_date=getattr(ad, "item_date", None), notified_tg=target_notified, seller_rating=getattr(ad, "seller_rating", None), description=getattr(ad, "description", None))

                # При первом запуске фиксируем все базовые объявления в истории TG, чтобы никогда не спамить ими
                if is_first_run:
                    await record_tg_notified(user_id, ad.id)

                # ── АВТО-СНАЙПЕР: Авто-сообщение и Авто-выкуп при обнаружении нового лота ──
                if not is_first_run and not already_in_tg:
                    try:
                        parent_dir = os.path.dirname(BOT_DIR)
                        if parent_dir not in sys.path:
                            sys.path.insert(0, parent_dir)
                        from avito_sniper import trigger_sniper_on_new_ad
                        trigger_sniper_on_new_ad(
                            item_id=str(ad.id),
                            item_title=str(ad.title or ""),
                            item_price=ad.price,
                            item_url=str(ad.url or ""),
                            has_delivery=bool(ad.has_delivery),
                            seller_rating=getattr(ad, "seller_rating", None),
                            search_name=name,
                            search_url=url
                        )
                    except Exception as _sne:
                        logger.error(f"[SNIPER TRIGGER ERROR]: {_sne}")

                # Отправляем уведомление ТОЛЬКО если это не первый обход, объявление не отправлялось ранее и ТГ включен
                if not is_first_run and not already_in_tg and user_tg_on:
                    items_found += 1
                    async with tg_notification_lock:
                        await send_notification_to_user(bot, user_id, ad, name)
                        await record_tg_notified(user_id, ad.id)
                        await set_notified_tg(user_id, ad.id)
                        await asyncio.sleep(0.35)
            else:
                # Обогащаем существующее объявление фото/продавцом/адресом/доставкой/датой/рейтингом, если они отсутствовали
                await update_seen_details_if_missing(user_id, ad.id, photo=ad.photo, seller=ad.seller, address=ad.address, search_name=name, has_delivery=int(ad.has_delivery), seller_type=getattr(ad, "seller_type", "Частное лицо"), item_date=getattr(ad, "item_date", None), seller_rating=getattr(ad, "seller_rating", None))

                # Если объявление уже есть в базе, но ТГ выключен — глушим его
                if not user_tg_on:
                    await set_notified_tg(user_id, ad.id)

                # Если объявление уже видели, проверяем, не снизилась ли цена
                if not is_first_run and ad.price and ad.price != "Цена не указана":
                    old_price = await get_seen_price(user_id, ad.id)
                    if old_price and old_price != ad.price and old_price != "Цена не указана":
                        # Проверяем, действительно ли цена стала ниже
                        old_val = re.sub(r"[^\d]", "", old_price)
                        new_val = re.sub(r"[^\d]", "", ad.price)
                        if old_val.isdigit() and new_val.isdigit() and int(new_val) < int(old_val):
                            logger.info(f"Снижение цены по {ad.id}: было {old_price} -> стало {ad.price}")
                            await update_seen_price(user_id, ad.id, ad.price)
                            async with tg_notification_lock:
                                await send_notification_to_user(bot, user_id, ad, name, old_price=old_price)
                                await asyncio.sleep(0.35)

        # Фиксируем время последнего опроса ссылки
        await set_url_polled(task_id)
        try:
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            sys.path.insert(0, os.path.dirname(BOT_DIR))
            import avito_api_helper
            avito_api_helper.update_search_polled_in_users_json(url, now_str, user_id)
        except Exception:
            pass

        # Очищаем deleted_items для объявлений, которых больше нет в выдаче Авито
        if ads and name:
            try:
                avito_ids_in_result = set(str(ad.id) for ad in ads)
                async with aiosqlite.connect(DATABASE_PATH) as db:
                    async with db.execute(
                        "SELECT item_id FROM deleted_items WHERE LOWER(search_name) = LOWER(?)",
                        (name.strip(),)
                    ) as cursor:
                        deleted_in_db = [r[0] for r in await cursor.fetchall()]
                    stale_ids = [iid for iid in deleted_in_db if iid not in avito_ids_in_result]
                    if stale_ids:
                        placeholders = ",".join("?" * len(stale_ids))
                        await db.execute(f"DELETE FROM deleted_items WHERE item_id IN ({placeholders})", stale_ids)
                        await db.commit()
            except Exception:
                pass

        if not is_initialized:
            await set_url_initialized(task_id)
            logger.info(f"Поиск #{task_id} ('{name}') успешно инициализирован (текущие объявления сохранены без спама).")

    except Exception as e:
        logger.error(f"Ошибка при проверке поиска #{task_id} ({name}): {e}")

    return items_found


async def check_all_active_searches(bot: Bot, initial_seed_user: Optional[int] = None) -> int:
    """
    Опрашивает все активные персональные поиски пользователей:
    - При достатке прокси (прокси >= ссылок * 2) запускает параллельный опрос без ожидания в очереди!
    - При малом количестве прокси или в прямом режиме — автоматически переключается на безопасный последовательный режим.
    """
    global last_check_time, checks_performed_count

    if not is_license_active():
        logger.info("Мониторинг Avito пропущен: лицензия не активна или истекла.")
        return 0

    tasks = await get_all_active_tasks()
    if not tasks:
        return 0

    shared_proxy_count = parser.proxy_pool.get_proxy_count() if hasattr(parser, "proxy_pool") else 0

    last_check_time = datetime.now()
    checks_performed_count += 1
    new_items_found = 0

    # Если опрос запущен для первичного заполнения базы конкретного пользователя
    if initial_seed_user:
        tasks = [t for t in tasks if t["user_id"] == initial_seed_user]

    if not tasks:
        return 0

    # Приоритет: неинициализированные ссылки (первый сбор) опрашиваются первыми
    tasks.sort(key=lambda t: (bool(t.get("is_initialized", 0)), t.get("id", 0)))
    task_count = len(tasks)

    # ── Проверка условий для параллельного опроса ──
    # Для параллельного опроса требуется 1 прокси на каждую ссылку (для 3 ссылок = 3 прокси).
    base_required_proxies = max(2, task_count)
    was_parallel = getattr(check_all_active_searches, "_last_was_parallel", False)
    # Защитный гистерезис: откат в последовательный режим только если пул просел ниже количества ссылок
    min_threshold = max(2, base_required_proxies) if was_parallel else base_required_proxies

    can_parallel = (
        task_count > 1 and
        not direct_mode_enabled and
        not (hybrid_mode_enabled and shared_proxy_count == 0) and
        shared_proxy_count >= min_threshold
    )
    check_all_active_searches._last_was_parallel = can_parallel

    if can_parallel:
        logger.info(f"⚡️ [Параллельный опрос] Порог безопасности выполнен ({shared_proxy_count}/{base_required_proxies} прокси). Одновременный опрос {task_count} ссылок...")
        # Для каждой задачи подбираем уникальный изолированный прокси
        used_batch_proxies = set()
        task_proxy_pairs = []

        for task in tasks:
            user_proxies = await get_user_proxies(task["user_id"])
            prx = None
            if user_proxies:
                avail_user = [p for p in user_proxies if p not in used_batch_proxies]
                candidates = avail_user if avail_user else user_proxies
                # Приоритет прокси с наименьшим пингом
                pool = getattr(parser, "proxy_pool", None)
                if pool and hasattr(pool, "get_proxy_ping"):
                    prx = min(candidates, key=lambda p: pool.get_proxy_ping(p))
                else:
                    prx = candidates[0]
            elif hasattr(parser, "proxy_pool"):
                prx = parser.proxy_pool.get_next_proxy(exclude=used_batch_proxies)
            if prx:
                used_batch_proxies.add(prx)
            task_proxy_pairs.append((task, prx))

        concurrency = min(task_count, 12)
        sem = asyncio.Semaphore(concurrency)

        async def _worker(t_item, t_prx):
            async with sem:
                return await _poll_single_search_task(bot, t_item, t_prx, initial_seed_user=initial_seed_user)

        results = await asyncio.gather(*(_worker(t, p) for t, p in task_proxy_pairs), return_exceptions=True)
        for r in results:
            if isinstance(r, int):
                new_items_found += r
            elif isinstance(r, Exception):
                logger.error(f"Ошибка в параллельной задаче опроса: {r}")

    else:
        # Последовательный режим (1 ссылка, прямой режим или мало прокси для параллельности)
        if task_count > 1 and not direct_mode_enabled:
            logger.info(
                f"⏳ [Последовательный опрос] В пуле {shared_proxy_count}/{base_required_proxies} прокси для {task_count} ссылок. "
                f"Опрос ведется по очереди до набора {base_required_proxies} адресов."
            )
        for task in tasks:
            user_proxies = await get_user_proxies(task["user_id"])
            task_proxy = None
            if user_proxies:
                pool = getattr(parser, "proxy_pool", None)
                if pool and hasattr(pool, "get_proxy_ping"):
                    task_proxy = min(user_proxies, key=lambda p: pool.get_proxy_ping(p))
                else:
                    task_proxy = user_proxies[0]
            elif shared_proxy_count > 0 and hasattr(parser, "proxy_pool"):
                task_proxy = parser.proxy_pool.get_next_proxy()

            if not task_proxy or task_proxy == "direct":
                logger.warning(
                    f"🛡️ Защита IP: Пропуск задачи #{task['id']} ('{task.get('name')}'): нет доступных прокси. "
                    f"Все опросы Авито ведутся исключительно через прокси."
                )
                continue

            res = await _poll_single_search_task(bot, task, task_proxy, initial_seed_user=initial_seed_user)
            new_items_found += res
            await asyncio.sleep(PAUSE_BETWEEN_REQUESTS)

    return new_items_found


async def background_proxy_harvester(bot: Bot):
    """
    Фоновый сборщик и валидатор прокси:
    - Регулярно удаляет мертвые прокси из proxies.txt
    - Если желаемый интервал (target_check_interval) меньше текущего, в фоне добирает недостающие прокси
    - По мере набора живых прокси автоматически разгоняет скорость опроса!
    """
    global current_check_interval, target_check_interval, proxy_harvester_running
    if proxy_harvester_running:
        return
    proxy_harvester_running = True
    logger.info("Запущен умный фоновый сборщик и валидатор прокси.")

    try:
        cleanup_counter = 0
        first_run = True
        while True:
            try:
                # 1. Если мониторинг выключен и тг уведомления выключены то не искать прокси
                is_master_mon = is_master_monitor_enabled()
                ext_bot_paused = False
                try:
                    sys.path.insert(0, os.path.dirname(BOT_DIR))
                    import avito_api_helper
                    ext_bot_paused = avito_api_helper.get_bot_paused()
                except Exception:
                    pass

                is_tg_active = not ext_bot_paused
                is_mon_active = is_monitoring_active and is_master_mon

                if not is_mon_active and not is_tg_active:
                    if hasattr(parser, "proxy_pool") and parser.proxy_pool and getattr(parser.proxy_pool, "is_fetching", False):
                        parser.proxy_pool.stop_fetching()
                    try:
                        await asyncio.wait_for(proxy_wake_event.wait(), timeout=10.0)
                        proxy_wake_event.clear()
                    except asyncio.TimeoutError:
                        pass
                    continue

                # Синхронизируем пул с proxies.txt (если прокси добавлены пользователем или фоновым воркером)
                parser.proxy_pool.reload()
                proxy_count = parser.proxy_pool.get_proxy_count()

                # Отсеиваем мертвые прокси:
                # - сразу при первом запуске (чтобы не ждать 20 циклов после рестарта)
                # - когда пул выглядит непустым, но добор не помогает (файл содержит мёртвые записи)
                # - раз в 20 циклов в штатном режиме
                cleanup_counter += 1
                if (first_run or cleanup_counter >= 20) and proxy_count > 0:
                    first_run = False
                    cleanup_counter = 0
                    await parser.proxy_pool.filter_and_clean_dead_proxies()
                    proxy_count = parser.proxy_pool.get_proxy_count()

                safe_int = get_safe_interval_for_proxies(target_check_interval, proxy_count)

                # Если скорость изменилась в лучшую сторону
                if safe_int != current_check_interval:
                    prev = current_check_interval
                    current_check_interval = safe_int
                    logger.info(f"Саморегуляция скорости: было {prev}с -> стало {current_check_interval}с (прокси: {proxy_count} шт.)")

                # 2. Если цель быстрее текущей скорости или в пуле мало прокси - добираем живые прокси
                import math
                if is_mon_active or is_tg_active:
                    # Требование: если мониторинг или ТГ включены — цель до 999
                    needed_proxies = 999
                elif str(target_check_interval).startswith("rand") or target_check_interval == "random_30_60":
                    needed_proxies = 15
                else:
                    try:
                        t_sec = int(target_check_interval)
                    except Exception:
                        t_sec = 30
                    # Масштабирование пула под скорость вплоть до 999 прокси
                    needed_proxies = max(15, math.ceil(30 / t_sec) * 10) if t_sec < 30 else 15
                needed_proxies = min(999, needed_proxies)

                if needed_proxies > 0 and proxy_count < needed_proxies:
                    logger.info(f"Добор прокси: есть {proxy_count} из {needed_proxies} нужных (мониторинг={is_mon_active}, ТГ={is_tg_active})...")
                    try:
                        # В фоне ищем порциями с двухэтапным быстрым TCP-отсевом
                        await asyncio.wait_for(
                            parser.proxy_pool.fetch_free_proxies_and_verify(target_alive=needed_proxies, max_candidates=5000),
                            timeout=75.0
                        )
                    except asyncio.TimeoutError:
                        logger.info("Таймаут одного раунда фонового добора прокси. Продолжаем мониторинг.")
                    new_count = parser.proxy_pool.get_proxy_count()
                    new_safe = get_safe_interval_for_proxies(target_check_interval, new_count)
                    if new_safe != current_check_interval:
                        current_check_interval = new_safe
                        logger.info(f"Авто-разгон! Интервал ускорен до {current_check_interval} сек! (Прокси: {new_count} шт.)")

            except Exception as e:
                logger.debug(f"Ошибка в фоновом сборщике прокси: {e}")

            # Если всё ещё не хватает прокси для целевого интервала — повторяем добор быстрее
            # Если прокси хватает — спим 2 минуты или ждем смены таймера
            if is_mon_active or is_tg_active:
                rem_needed = 999
            elif str(target_check_interval).startswith("rand") or target_check_interval == "random_30_60":
                rem_needed = 15
            else:
                try:
                    t_sec = int(target_check_interval)
                except Exception:
                    t_sec = 30
                rem_needed = max(15, math.ceil(30 / t_sec) * 10) if t_sec < 30 else 15
            rem_needed = min(999, rem_needed)
            has_enough = parser.proxy_pool.get_proxy_count() >= rem_needed
            sleep_sec = 120 if has_enough else 5

            try:
                await asyncio.wait_for(proxy_wake_event.wait(), timeout=sleep_sec)
                proxy_wake_event.clear()
            except asyncio.TimeoutError:
                pass
    finally:
        proxy_harvester_running = False


async def background_monitoring_loop(bot: Bot):
    """Фоновый цикл мониторинга каждые 30 секунд."""
    global is_monitoring_active, target_check_interval, hybrid_mode_enabled, direct_mode_enabled
    logger.info("Запуск фонового мультисессионного цикла мониторинга...")
    await asyncio.sleep(3)

    while True:
        try:
            # Проверка лицензии: если лицензия истекла или не активирована, фоновый опрос не выполняется
            if not is_license_active():
                await asyncio.sleep(10)
                continue

            # Синхронизация целевого интервала с monitor_state.json
            cfg_target = get_persisted_target_interval()
            if cfg_target != target_check_interval:
                target_check_interval = cfg_target
                proxy_wake_event.set()

            ext_bot_paused = False
            try:
                sys.path.insert(0, os.path.dirname(BOT_DIR))
                import avito_api_helper
                ext_bot_paused = avito_api_helper.get_bot_paused()
            except Exception:
                pass

            proxy_count = parser.proxy_pool.get_proxy_count() if hasattr(parser, "proxy_pool") else 0
            if is_monitoring_active and is_master_monitor_enabled() and not ext_bot_paused:
                if direct_mode_enabled:
                    # Режим прямого подключения: всегда работаем напрямую
                    found = await check_all_active_searches(bot)
                    if found > 0:
                        logger.info(f"[Прямое подключение] Найдено новых объявлений в цикле: {found}.")
                elif hybrid_mode_enabled:
                    # Гибридный режим: прокси если есть, иначе прямое подключение
                    if proxy_count > 0:
                        found = await check_all_active_searches(bot)
                    else:
                        logger.info("🔀 Гибридный режим: 0 прокси, использую прямое подключение...")
                        found = await check_all_active_searches(bot)
                    if found > 0:
                        logger.info(f"[Гибридный режим] Найдено новых объявлений в цикле: {found}.")
                elif proxy_count == 0:
                    logger.warning("🛡️ Опрос ссылок приостановлен: в пуле 0 доступных прокси. Ожидание появления прокси...")
                else:
                    found = await check_all_active_searches(bot)
                    if found > 0:
                        logger.info(f"Найдено новых объявлений в цикле: {found}.")


            # Определение времени ожидания до следующего опроса
            if direct_mode_enabled:
                # Прямой режим: случайный интервал 60-90 сек (защита от бана)
                sleep_sec = random.randint(60, 90)
                logger.info(f"🟢 Прямой режим: следующий цикл через {sleep_sec} сек. (60–90 сек рандом, защита от бана)")
            elif hybrid_mode_enabled and proxy_count == 0:
                # Гибридный режим без прокси: случайный интервал 60-90 сек
                sleep_sec = random.randint(60, 90)
                logger.info(f"🔀 Гибридный режим (прямой): следующий цикл через {sleep_sec} сек. (60–90 сек рандом, защита от бана)")
            else:
                is_rand = str(target_check_interval).startswith("rand") or target_check_interval == "random_30_60"
                is_cur_rand = str(current_check_interval).startswith("rand") or current_check_interval == "random_30_60"
                if is_rand or is_cur_rand:
                    sleep_sec = random.randint(30, 60)
                    logger.info(f"🎲 Следующий цикл опроса через {sleep_sec} сек. (рандом 30–60 сек, защита от бана)")
                else:
                    try:
                        _ci = int(current_check_interval)
                    except (ValueError, TypeError):
                        _ci = 30
                    if _ci <= 5:
                        sleep_sec = max(1, _ci)
                    else:
                        jitter = random.randint(-CHECK_INTERVAL_JITTER, CHECK_INTERVAL_JITTER)
                        sleep_sec = max(1, _ci + jitter)
            await asyncio.sleep(sleep_sec)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Ошибка в цикле мониторинга: {e}", exc_info=True)
            await asyncio.sleep(20)


# ===================== КОМАНДЫ ДЛЯ ВСЕХ ПОЛЬЗОВАТЕЛЕЙ =====================

@dp.message(CommandStart())
@dp.message(Command("admin"))
@dp.message(Command("help"))
@dp.message(Command("menu"))
async def cmd_start(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    user_waiting_feedback.pop(user_id, None)

    # Проверяем, есть ли запрос на подтверждение привязки с сайта SkyBase
    all_site_users = load_site_users()
    pending_u = None
    clean_tg_uname = username.strip().lstrip("@").lower() if username else ""
    start_arg = ""
    if message.text and len(message.text.split()) > 1:
        start_arg = message.text.split(None, 1)[1].strip().lower()

    if start_arg and start_arg.startswith("trial_"):
        raw_hw = start_arg.replace("trial_", "").strip().upper()
        m_hw = re.search(r'\b((?:EBID|EBMOB)-[A-Z0-9\-]+)\b', raw_hw, re.I)
        target_hw = m_hw.group(1).upper() if m_hw else raw_hw

        try:
            if SITE_DIR not in sys.path:
                sys.path.insert(0, SITE_DIR)
            import hwid_security
            import devices_db

            parsed = hwid_security.parse_request_id(target_hw)
            if not parsed.get("valid"):
                await message.answer(
                    f"⚠️ <b>Недействительный ID код устройства:</b> <code>{html.escape(target_hw)}</code>\n\n"
                    "Убедитесь, что передан верный ID в формате <code>EBID-XXXX-...</code> из программы на ПК.",
                    parse_mode=ParseMode.HTML
                )
                return

            if devices_db.has_device_used_trial(target_hw):
                await message.answer(
                    f"⚠️ <b>Ключ уже был ранее активирован на данном устройстве!</b>\n\n"
                    f"🖥️ <b>Устройство:</b> <code>{html.escape(target_hw)}</code>\n\n"
                    "Бесплатный ознакомительный период (3 дня) на этом компьютере уже был активирован ранее.\n"
                    "Повторная выдача триал-ключа на данном оборудовании невозможна (в том числе после удаления файлов или переустановки программы).\n\n"
                    "Для продления доступа и покупки лицензии обратитесь к администратору: @skynet19081983",
                    parse_mode=ParseMode.HTML
                )
                return

            exp_dt = datetime.now() + timedelta(days=3)
            exp_dt_str = exp_dt.strftime("%Y-%m-%d %H:%M:%S")
            trial_key = hwid_security.generate_response_key(target_hw, tier="3_days", expires_date=exp_dt)
            devices_db.record_device_trial_activation(target_hw, trial_key, exp_dt_str, client_ip=str(user_id), username=username or str(user_id))

            try:
                import avito_api_helper
                avito_api_helper.activate_license_key(trial_key, username or f"tg_{user_id}", "127.0.0.1", target_hw)
            except Exception as e_act:
                logger.warning(f"Error auto-activating trial key on site: {e_act}")

            await message.answer(
                f"🎁 <b>Ваш бесплатный пробный доступ на 3 дня активирован!</b>\n\n"
                f"🖥️ <b>Устройство:</b> <code>{html.escape(target_hw)}</code>\n"
                f"⏳ <b>Действует до:</b> <b>{exp_dt.strftime('%d.%m.%Y в %H:%M')}</b>\n\n"
                f"🔑 <b>Ваш персональный ключ активации:</b>\n"
                f"<code>{html.escape(trial_key)}</code>\n\n"
                f"<i>Лицензия успешно применена к вашей программе на ПК! Кнопка активации триала заблокирована.</i>",
                parse_mode=ParseMode.HTML
            )
            return
        except Exception as e:
            await message.answer(f"❌ Ошибка генерации триал-ключа: {e}")
            return

    for su in all_site_users:
        pend = su.get("telegram_pending")
        if pend and isinstance(pend, dict) and pend.get("status") == "pending":
            p_handle = str(pend.get("handle") or "").strip().lstrip("@").lower()
            p_cid = pend.get("chat_id")
            su_name = (su.get("username") or "").strip().lower()
            is_adm_cand = (clean_tg_uname in ("skynet19081983", "skynet83") or user_id == 5680198246)
            is_adm_pend = p_handle in ("skynet19081983", "skynet83", "5680198246") or (p_cid and int(p_cid) == 5680198246)
            if (p_cid and int(p_cid) == user_id) or (clean_tg_uname and clean_tg_uname == p_handle) or str(user_id) == p_handle or (is_adm_cand and is_adm_pend) or (start_arg and (start_arg == f"bind_{su_name}" or start_arg == su_name or start_arg == f"bind_{p_handle}")):
                pending_u = su
                break
    if pending_u:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"bind_confirm:{pending_u['username']}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"bind_reject:{pending_u['username']}")
        ]])
        p_name = pending_u.get("name") or pending_u["username"]
        is_admin_req = (pending_u.get("role") == "admin" or (pending_u.get("username") or "").lower() in ("skynet83", "admin") or (p_name or "").lower() in ("skynet83", "admin"))
        who = "Администратор" if is_admin_req else f"Пользователь <b>{pending_u['username']}</b>"
        await message.answer(
            f"🔔 <b>Подтверждение привязки к AvitoHunter</b>\n\n"
            f"{who} запросил привязку этого Telegram-аккаунта к программе AvitoHunter.\n\n"
            f"Подтвердить привязку?",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    site_u = await check_auth_or_prompt(message)
    if not site_u:
        return

    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO users (user_id, username, full_name, status) VALUES (?, ?, ?, 'approved')",
                (user_id, username or f"tg_{user_id}", full_name or username or str(user_id))
            )
            await db.commit()
    except Exception as dbe:
        logger.warning(f"Error saving user to database: {dbe}")

    await show_welcome_panel(message, site_u, user_id, username, full_name)


@dp.message(Command("trial"))
async def cmd_user_trial(message: types.Message):
    """Позволяет пользователю получить бесплатный 3-дневный триал-ключ по Request ID."""
    user_id = message.from_user.id
    username = message.from_user.username
    raw_text = (message.text or "").strip()
    parts = raw_text.split(None, 1)
    target_hw = None
    if len(parts) > 1:
        m_hw = re.search(r'\b((?:EBID|EBMOB)-[A-Z0-9\-]+)\b', parts[1], re.I)
        target_hw = m_hw.group(1).upper() if m_hw else parts[1].strip().upper()

    if not target_hw:
        site_u = get_site_user_by_tg_id(user_id, username)
        if site_u:
            perms = site_u.get("permissions") or {}
            target_hw = perms.get("hwid_request_id") or site_u.get("request_id")

    if not target_hw:
        await message.answer(
            "🎁 <b>Получение бесплатного ознакомительного периода (3 дня)</b>\n\n"
            "Отправьте команду вместе с вашим <b>Request ID</b> из программы на ПК:\n"
            "<code>/trial EBID-XXXX-XXXX-XXXX-XXXX-XXXX</code>\n\n"
            "<i>Request ID отображается в окне программы при запуске.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    try:
        if SITE_DIR not in sys.path:
            sys.path.insert(0, SITE_DIR)
        import hwid_security
        import devices_db

        parsed = hwid_security.parse_request_id(target_hw)
        if not parsed.get("valid"):
            await message.answer(
                f"⚠️ <b>Недействительный ID код устройства:</b> <code>{html.escape(target_hw)}</code>\n\n"
                f"Убедитесь, что ID скопирован правильно из программы (например, <code>EBID-XXXX-...</code>).",
                parse_mode=ParseMode.HTML
            )
            return

        if devices_db.has_device_used_trial(target_hw):
            await message.answer(
                f"⚠️ <b>Ключ уже был ранее активирован на данном устройстве!</b>\n\n"
                f"🖥️ <b>Устройство:</b> <code>{html.escape(target_hw)}</code>\n\n"
                "Бесплатный ознакомительный период (3 дня) на этом компьютере уже был активирован ранее.\n"
                "Повторная выдача триал-ключа на данном оборудовании невозможна (в том числе после удаления файлов или переустановки программы).\n\n"
                "Для продления доступа и покупки лицензии обратитесь к администратору: @skynet19081983",
                parse_mode=ParseMode.HTML
            )
            return

        exp_dt = datetime.now() + timedelta(days=3)
        exp_dt_str = exp_dt.strftime("%Y-%m-%d %H:%M:%S")
        trial_key = hwid_security.generate_response_key(target_hw, tier="3_days", expires_date=exp_dt)
        devices_db.record_device_trial_activation(target_hw, trial_key, exp_dt_str, client_ip=str(user_id), username=username or str(user_id))

        try:
            import avito_api_helper
            avito_api_helper.activate_license_key(trial_key, username or f"tg_{user_id}", "127.0.0.1", target_hw)
        except Exception as e_act:
            logger.warning(f"Error auto-activating trial key on site: {e_act}")

        await message.answer(
            f"🎁 <b>Ваш бесплатный пробный доступ на 3 дня активирован!</b>\n\n"
            f"🖥️ <b>Устройство:</b> <code>{html.escape(target_hw)}</code>\n"
            f"⏳ <b>Действует до:</b> <b>{exp_dt.strftime('%d.%m.%Y в %H:%M')}</b>\n\n"
            f"🔑 <b>Ваш персональный ключ активации:</b>\n"
            f"<code>{html.escape(trial_key)}</code>\n\n"
            f"<i>Лицензия успешно применена к вашей программе на ПК! Кнопка активации триала заблокирована.</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")


@dp.callback_query(F.data.startswith("bind_confirm:") | F.data.startswith("bind_reject:"))
async def cb_handle_tg_bind_response(call: CallbackQuery, bot: Bot):
    action, target_user = call.data.split(":", 1)
    user_id = call.from_user.id
    username = call.from_user.username
    full_name = call.from_user.full_name or username or str(user_id)

    users = load_site_users()
    matched_u = None
    for u in users:
        if (u.get("username") or "").strip().lower() == target_user.strip().lower():
            matched_u = u
            break

    if not matched_u:
        await call.message.edit_text("⚠️ Пользователь программы не найден или запрос устарел.", reply_markup=None)
        await call.answer()
        return

    # Проверка, что подтверждает именно владелец указанного Telegram-аккаунта
    pending = matched_u.get("telegram_pending")
    if pending and isinstance(pending, dict):
        p_handle = str(pending.get("handle") or "").strip().lstrip("@").lower()
        p_cid = pending.get("chat_id")
        my_uname = (username or "").strip().lstrip("@").lower()

        matches = False
        if p_cid and int(p_cid) == user_id:
            matches = True
        elif my_uname and my_uname == p_handle:
            matches = True
        elif str(user_id) == p_handle:
            matches = True
        elif (my_uname in ("skynet19081983", "skynet83") or user_id == 5680198246) and p_handle in ("skynet19081983", "skynet83", "5680198246"):
            matches = True

        if not matches:
            await call.answer("❌ Этот запрос предназначен для другого аккаунта Telegram!", show_alert=True)
            return

    if action == "bind_confirm":
        # Пользователь подтвердил привязку в Telegram
        matched_u["telegram_chat_id"] = user_id
        if username:
            matched_u["telegram_username"] = username.lstrip("@")
        elif not matched_u.get("telegram_username"):
            pending = matched_u.get("telegram_pending") or {}
            matched_u["telegram_username"] = str(pending.get("handle", "")).lstrip("@")
        matched_u["telegram_pending"] = None
        perms = matched_u.setdefault("permissions", {})
        perms["tg_bot"] = True
        perms["monitoring"] = True

        clean_uname = (username or "").strip().lstrip("@").lower()
        if target_user.lower() in ("skynet83", "admin") or clean_uname in ("skynet19081983", "skynet83") or matched_u.get("role") == "admin":
            matched_u["role"] = "admin"
        else:
            matched_u["role"] = matched_u.get("role", "user")

        save_site_users(users)
        try:
            import urllib.request
            bind_payload = json.dumps({"username": target_user, "chat_id": user_id, "handle": username or ""}).encode("utf-8")
            n_req = urllib.request.Request("http://127.0.0.1:8081/api/avito/notify_bind_success", data=bind_payload, headers={"Content-Type": "application/json"})
            urllib.request.urlopen(n_req, timeout=1.5)
        except Exception:
            pass
        try:
            import avito_api_helper
            avito_api_helper.sync_users_searches_to_db()
        except Exception:
            pass

        try:
            async with aiosqlite.connect(DATABASE_PATH) as db:
                await db.execute(
                    "INSERT OR REPLACE INTO users (user_id, username, full_name, status) VALUES (?, ?, ?, 'approved')",
                    (user_id, username or target_user, full_name)
                )
                await db.commit()
        except Exception as dbe:
            logger.warning(f"Error saving approved user to database: {dbe}")

        is_adm = (matched_u.get("role") == "admin" or target_user.lower() in ("skynet83", "admin"))
        profile_label = "Администратор" if is_adm else f"<b>{target_user}</b>"

        site_ip = "127.0.0.1"
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect(('8.8.8.8', 80))
            cand = s.getsockname()[0]
            s.close()
            if cand and not cand.startswith('127.'):
                site_ip = cand
        except Exception:
            pass
        clean_tg_uname = (username or str(user_id)).lstrip("@")
        confirm_text = (
            f"🎉 <b>Telegram-аккаунт успешно подтвержден и привязан к AvitoHunter!</b>\n\n"
            f"• Профиль: <b>{profile_label}</b>\n"
            f"• Telegram: <b>@{clean_tg_uname}</b> (ID: <code>{user_id}</code>)\n"
            f"• Статус: <b>Подтвержден</b> ✅\n"
            f"• Telegram-уведомления: <b>ВКЛ</b> 🟢\n"
            f"• Веб-интерфейс AvitoHunter: <a href=\"{site_url}\">{site_ip}</a>\n\n"
            f"Теперь все уведомления мониторинга будут приходить прямо сюда!"
        )

        await call.message.edit_text(
            confirm_text,
            parse_mode="HTML",
            reply_markup=None
        )
        await call.answer("✅ Telegram-аккаунт успешно привязан!")

    else:
        # Пользователь отклонил привязку
        matched_u["telegram_pending"] = None
        matched_u["telegram_chat_id"] = None
        matched_u["telegram_username"] = None
        save_site_users(users)
        await call.message.edit_text(
            f"❌ <b>Привязка отклонена.</b>\n"
            f"Запрос на привязку к профилю <b>{target_user}</b> в AvitoHunter отменен.",
            parse_mode="HTML",
            reply_markup=None
        )
        await call.answer("❌ Привязка отклонена.")


@dp.callback_query(F.data.startswith("admin_bind_confirm:") | F.data.startswith("admin_bind_reject:"))
async def cb_admin_bind_response(call: CallbackQuery, bot: Bot):
    await call.answer("Каждый пользователь должен подтвердить свой Telegram самостоятельно в боте!", show_alert=True)
    try:
        await call.message.edit_text("ℹ️ Привязка Telegram-аккаунтов должна подтверждаться каждым пользователем (включая администратора) индивидуально из своего Telegram-аккаунта.", reply_markup=None)
    except Exception:
        pass
    return


@dp.callback_query(F.data == "check_tg_bind")
async def cb_check_tg_bind(call: CallbackQuery, bot: Bot):
    """Инлайн-кнопка повторной проверки привязки Telegram-аккаунта к сайту."""
    user_id = call.from_user.id
    username = call.from_user.username
    full_name = call.from_user.full_name

    site_u, reason = get_authorized_site_user(user_id, username)
    if site_u and reason is None:
        await call.answer("✅ Telegram успешно привязан!", show_alert=False)
        await show_welcome_panel(call.message, site_u, user_id, username, full_name)
        return
    elif reason == "blocked":
        await call.answer("⛔️ Аккаунт заблокирован администратором.", show_alert=True)
        return
    elif reason == "tg_disabled":
        await call.answer("⚠️ Telegram-уведомления отключены в настройках профиля.", show_alert=True)
        return

    # Проверяем, ожидает ли данный аккаунт подтверждения привязки
    clean_tg_uname = (username or "").strip().lstrip("@").lower()
    pending_u = None
    for su in load_site_users():
        pend = su.get("telegram_pending")
        if pend and isinstance(pend, dict) and pend.get("status") == "pending":
            p_handle = str(pend.get("handle") or "").strip().lstrip("@").lower()
            p_cid = pend.get("chat_id")
            is_adm_cand = (clean_tg_uname in ("skynet19081983", "skynet83") or user_id == 5680198246)
            is_adm_pend = p_handle in ("skynet19081983", "skynet83", "5680198246") or (p_cid and int(p_cid) == 5680198246)
            if (p_cid and int(p_cid) == user_id) or (clean_tg_uname and clean_tg_uname == p_handle) or str(user_id) == p_handle or (is_adm_cand and is_adm_pend):
                pending_u = su
                break

    if pending_u:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"bind_confirm:{pending_u['username']}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"bind_reject:{pending_u['username']}")
        ]])
        p_name = pending_u.get("name") or pending_u["username"]
        is_admin_req = (pending_u.get("role") == "admin" or (pending_u.get("username") or "").lower() in ("skynet83", "admin") or (p_name or "").lower() in ("skynet83", "admin"))
        who = "Администратор" if is_admin_req else f"Пользователь <b>{pending_u['username']}</b>"
        await call.message.answer(
            f"🔔 <b>Подтверждение привязки к AvitoHunter</b>\n\n"
            f"{who} запросил привязку этого Telegram-аккаунта к программе AvitoHunter.\n\n"
            f"Подтвердить привязку?",
            parse_mode="HTML",
            reply_markup=kb
        )
        await call.answer()
        return

    site_url = get_site_url()
    tg_hint = f"@{username.lstrip('@')}" if username else f"ID: {user_id}"
    await call.answer(
        f"❌ Привязка пока не найдена!\n\n"
        f"Укажите {tg_hint} на сайте {site_url} возле кнопки «📱 Бот» и нажмите «Привязать».",
        show_alert=True
    )


@dp.message(F.text == "🔄 Проверить привязку")
async def btn_check_tg_bind_text(message: types.Message, bot: Bot):
    """Реплай-кнопка проверки привязки."""
    user_id = message.from_user.id
    username = message.from_user.username
    full_name = message.from_user.full_name

    site_u, reason = get_authorized_site_user(user_id, username)
    if site_u and reason is None:
        await message.answer("✅ <b>Привязка подтверждена!</b>", parse_mode=ParseMode.HTML)
        await show_welcome_panel(message, site_u, user_id, username, full_name)
        return

    # Проверяем, ожидает ли данный аккаунт подтверждения привязки
    clean_tg_uname = (username or "").strip().lstrip("@").lower()
    pending_u = None
    for su in load_site_users():
        pend = su.get("telegram_pending")
        if pend and isinstance(pend, dict) and pend.get("status") == "pending":
            p_handle = str(pend.get("handle") or "").strip().lstrip("@").lower()
            p_cid = pend.get("chat_id")
            is_adm_cand = (clean_tg_uname in ("skynet19081983", "skynet83") or user_id == 5680198246)
            is_adm_pend = p_handle in ("skynet19081983", "skynet83", "5680198246") or (p_cid and int(p_cid) == 5680198246)
            if (p_cid and int(p_cid) == user_id) or (clean_tg_uname and clean_tg_uname == p_handle) or str(user_id) == p_handle or (is_adm_cand and is_adm_pend):
                pending_u = su
                break

    if pending_u:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"bind_confirm:{pending_u['username']}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"bind_reject:{pending_u['username']}")
        ]])
        p_name = pending_u.get("name") or pending_u["username"]
        is_admin_req = (pending_u.get("role") == "admin" or (pending_u.get("username") or "").lower() in ("skynet83", "admin") or (p_name or "").lower() in ("skynet83", "admin"))
        who = "Администратор" if is_admin_req else f"Пользователь <b>{pending_u['username']}</b>"
        await message.answer(
            f"🔔 <b>Подтверждение привязки к AvitoHunter</b>\n\n"
            f"{who} запросил привязку этого Telegram-аккаунта к программе AvitoHunter.\n\n"
            f"Подтвердить привязку?",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    await prompt_unauthorized_user(message, user_id, username, full_name, reason or "not_linked")


@dp.message(Command("login"))
async def cmd_login(message: types.Message):
    """Ручной запуск входа или переавторизации по логину и паролю от сайта."""
    user_id = message.from_user.id
    user_waiting_auth_login[user_id] = True
    user_waiting_auth_pass.pop(user_id, None)
    await message.answer(
        "🔐 <b>Вход в систему SkyBase</b>\n\n"
        "Введите ваш <b>логин</b> от сайта:\n"
        "<i>(Отправьте /cancel для отмены)</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(Command("logout"))
async def cmd_logout(message: types.Message):
    """Выход из учетной записи сайта и отвязка Telegram."""
    user_id = message.from_user.id
    site_u = get_site_user_by_tg_id(user_id)
    if not site_u:
        await message.answer("Вы не авторизованы. Для входа введите /login.")
        return

    users = load_site_users()
    for u in users:
        t_id = u.get("telegram_chat_id")
        if t_id is not None and str(t_id).strip() == str(user_id).strip():
            u["telegram_chat_id"] = None
            u["telegram_username"] = None
    save_site_users(users)

    await register_or_update_user(user_id, message.from_user.username, site_u.get("name") or "", status="pending")
    global primary_admin_id
    if primary_admin_id == user_id:
        primary_admin_id = None

    await message.answer(
        "🚪 <b>Вы успешно вышли из учетной записи.</b>\n"
        "Ваш Telegram отвязан от сайта SkyBase.\n\n"
        "Чтобы войти снова, отправьте /login или /start.",
        reply_markup=ReplyKeyboardRemove(),
        parse_mode=ParseMode.HTML
    )


# ===================== ПЕРСОНАЛЬНЫЕ КОМАНДЫ КЛИЕНТА (И АДМИНА) =====================

def build_user_searches_keyboard(urls: list) -> InlineKeyboardMarkup:
    """Формирует инлайн-клавиатуру для списка поисков с кнопками перехода, удаления и добавления."""
    buttons = []
    for u in urls:
        search_id = u.get("id")
        search_name = (u.get("name") or "Поиск")[:24]
        search_url = u.get("url") or "https://www.avito.ru"
        # Ряд: [🔗 Название] и [➖ Удалить]
        buttons.append([
            InlineKeyboardButton(text=f"🔗 {search_name}", url=search_url),
            InlineKeyboardButton(text=f"➖ Удалить #{search_id}", callback_data=f"list_del_{search_id}")
        ])
    # Нижний ряд: кнопка добавления нового поиска
    buttons.append([
        InlineKeyboardButton(text="➕ Добавить поиск", callback_data="list_add_search")
    ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(Command("list"))
async def cmd_list(message: types.Message):
    user_id = message.from_user.id
    if not await check_auth_or_prompt(message):
        return

    # Синхронизируем ссылки из users.json перед показом
    try:
        sys.path.insert(0, os.path.dirname(BOT_DIR))
        import avito_api_helper
        avito_api_helper.sync_users_searches_to_db()
    except Exception:
        pass

    urls = await get_user_tracked_urls(user_id)
    if not urls:
        empty_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить поиск", callback_data="list_add_search")]
        ])
        await message.answer(
            "ℹ️ <b>У вас пока нет отслеживаемых ссылок.</b>\n\n"
            "Нажмите <b>«➕ Добавить поиск»</b> ниже или отправьте ссылку на Avito прямо в чат!",
            reply_markup=empty_kb,
            parse_mode=ParseMode.HTML
        )
        return

    active_cnt = sum(1 for u in urls if u.get("is_active"))
    lines = [f"🔍 <b>Ваши персональные поисковые ссылки ({active_cnt} из {len(urls)} активны):</b>\n"]
    for u in urls:
        is_act = bool(u.get("is_active", 1))
        tag = "✅ <b>[Активна]</b>" if is_act else "⛔️ <i>[Не активна: лимит]</i>"
        lines.append(
            f"{tag} <b>[{u['id']}]</b> {u['name']}\n"
            f"🔗 <a href='{u['url']}'>Открыть на Avito</a>"
        )
    lines.append("\n<i>Нажмите <b>[➖ Удалить]</b> возле поиска или <b>[➕ Добавить поиск]</b> для создания нового:</i>")

    kb = build_user_searches_keyboard(urls)
    await message.answer("\n".join(lines), reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@dp.callback_query(F.data == "list_add_search")
async def cb_list_add_search(call: CallbackQuery):
    """Инлайн-кнопка [+] Добавить поиск: запрашивает у пользователя ссылку на Avito."""
    user_id = call.from_user.id
    username = call.from_user.username
    site_u, reason = get_authorized_site_user(user_id, username)
    if not site_u or reason is not None:
        await call.answer("⚠️ Требуется авторизация!", show_alert=True)
        return

    is_adm = await is_admin(user_id, username)
    perms = site_u.get("permissions") or {}

    # Проверка лимитов по тарифу (максимум 10)
    max_s = min(10, 10 if is_adm else int(perms.get("max_searches") or 10))
    current_urls = await get_user_tracked_urls(user_id)
    if len(current_urls) >= max_s:
        await call.answer(f"⚠️ Достигнут лимит: максимум {max_s} поисковых ссылок (10 шт.)!", show_alert=True)
        return

    user_waiting_add_search[user_id] = True
    await call.answer()
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_search")]
    ])
    await call.message.answer(
        "➕ <b>Добавление нового поиска Avito:</b>\n\n"
        "Отправьте в чат <b>ссылку на поиск Avito</b> (из браузера или приложения).\n"
        "<i>Бот автоматически определит название и параметры поиска, либо отправьте <code>/cancel</code> для отмены.</i>",
        reply_markup=cancel_kb,
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "cancel_add_search")
async def cb_cancel_add_search(call: CallbackQuery):
    """Отмена режима добавления поиска."""
    user_id = call.from_user.id
    user_waiting_add_search.pop(user_id, None)
    await call.answer("Отменено")
    await call.message.edit_text("❌ Добавление поиска отменено.", reply_markup=None)


@dp.callback_query(F.data.startswith("list_del_"))
async def cb_list_del_search(call: CallbackQuery):
    """Инлайн-кнопка [-] Удалить: удаляет выбранный поиск из SQLite и users.json."""
    user_id = call.from_user.id
    username = call.from_user.username
    site_u, reason = get_authorized_site_user(user_id, username)
    if not site_u or reason is not None:
        await call.answer("⚠️ Требуется авторизация!", show_alert=True)
        return

    try:
        url_id = int(call.data.replace("list_del_", ""))
    except Exception:
        await call.answer("Ошибка формата ID поиска", show_alert=True)
        return

    target_url = None
    urls = await get_user_tracked_urls(user_id)
    for u in urls:
        if u.get("id") == url_id:
            target_url = u.get("url")
            break

    success = await delete_user_tracked_url(user_id, url_id)
    if not success and await is_admin(user_id):
        success = await delete_user_tracked_url(ADMIN_CHAT_ID, url_id)

    try:
        sys.path.insert(0, os.path.dirname(BOT_DIR))
        import avito_api_helper
        avito_api_helper.delete_search(search_id=url_id, url=target_url)
    except Exception:
        pass

    delete_search_from_site_users(user_id, url_id, username=site_u.get("username"), url=target_url)

    await call.answer(f"🗑 Поиск #{url_id} удален!", show_alert=False)

    # Обновляем сообщение со списком
    remaining_urls = await get_user_tracked_urls(user_id)
    if not remaining_urls:
        empty_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить поиск", callback_data="list_add_search")]
        ])
        await call.message.edit_text(
            "ℹ️ <b>У вас пока нет отслеживаемых ссылок.</b>\n\n"
            "Нажмите <b>«➕ Добавить поиск»</b> ниже или отправьте ссылку на Avito прямо в чат!",
            reply_markup=empty_kb,
            parse_mode=ParseMode.HTML
        )
    else:
        active_cnt = sum(1 for u in remaining_urls if u.get("is_active"))
        lines = [f"🔍 <b>Ваши персональные поисковые ссылки ({active_cnt} из {len(remaining_urls)} активны):</b>\n"]
        for u in remaining_urls:
            is_act = bool(u.get("is_active", 1))
            tag = "✅ <b>[Активна]</b>" if is_act else "⛔️ <i>[Не активна: лимит]</i>"
            lines.append(
                f"{tag} <b>[{u['id']}]</b> {u['name']}\n"
                f"🔗 <a href='{u['url']}'>Открыть на Avito</a>"
            )
        lines.append("\n<i>Нажмите <b>[➖ Удалить]</b> возле поиска или <b>[➕ Добавить поиск]</b> для создания нового:</i>")
        kb = build_user_searches_keyboard(remaining_urls)
        await call.message.edit_text("\n".join(lines), reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@dp.message(Command("add"))
async def cmd_add(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username
    site_u = await check_auth_or_prompt(message)
    if not site_u:
        return

    is_adm = await is_admin(user_id, username)
    perms = site_u.get("permissions") or {}

    # Проверяем лимит поисков по тарифу (максимум 10)
    max_s = min(10, 10 if is_adm else int(perms.get("max_searches") or 10))
    current_urls = await get_user_tracked_urls(user_id)
    if len(current_urls) >= max_s:
        await message.answer(
            f"⚠️ <b>Достигнут лимит поисковых ссылок!</b>\n\n"
            f"По вашему тарифу доступно максимум <b>{max_s}</b> ссылок (сейчас добавлено <b>{len(current_urls)}</b>, системный предел: 10).\n\n"
            f"Чтобы добавить новый поиск:\n"
            f"• Удалите ненужную ссылку: <code>/del &lt;номер&gt;</code>\n"
            f"• Или управляйте ссылками на сайте: <a href=\"{get_site_url()}/\">SkyBase</a>",
            parse_mode=ParseMode.HTML
        )
        return

    args = message.text.split(maxsplit=2)
    if len(args) < 2:
        await message.answer(
            "⚠️ <b>Формат команды:</b>\n<code>/add &lt;ссылка на Avito&gt; [название]</code>\n\n"
            "Пример:\n<code>/add https://www.avito.ru/... Видеокарта RTX 3060</code>",
            parse_mode=ParseMode.HTML
        )
        return

    url = args[1].strip()
    name = args[2].strip() if len(args) > 2 else "Мой поиск"

    if "avito.ru" not in url:
        await message.answer("❌ Ссылка должна вести на сайт avito.ru!")
        return

    try:
        new_id = await add_user_tracked_url(user_id, url, name)
        # Синхронизируем добавление в users.json для сайта
        add_search_to_site_users(user_id, username, {
            "id": new_id,
            "name": name,
            "url": url,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_active": 1,
            "is_initialized": 0,
            "last_polled_at": None
        })
        rem_count = max_s - (len(current_urls) + 1)
        rem_info = f"\n📊 Осталось слотов: <b>{rem_count}</b> из <b>{max_s}</b>" if not is_adm else ""
        await message.answer(
            f"✅ <b>Поиск успешно добавлен в вашу персональную сессию и на сайт!</b>\n\n"
            f"🆔 <b>Номер:</b> {new_id}\n"
            f"📌 <b>Название:</b> {name}{rem_info}\n\n"
            f"<i>Бот сохранит текущие товары и будет присылать только новые поступления каждые 30 секунд.</i>",
            parse_mode=ParseMode.HTML
        )
        # Сохраняем уже существующие объявления, чтобы не спамить
        asyncio.create_task(check_all_active_searches(bot, initial_seed_user=user_id))
    except Exception as e:
        await message.answer(f"❌ Ошибка добавления: {e}")


@dp.message(Command("del"))
async def cmd_del(message: types.Message):
    user_id = message.from_user.id
    site_u = await check_auth_or_prompt(message)
    if not site_u:
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Укажите номер поиска из команды /list:\nПример: <code>/del 1</code>", parse_mode=ParseMode.HTML)
        return

    url_id = int(args[1])
    username = site_u.get("username")

    # Получаем URL перед удалением, чтобы удалить по id и по url
    target_url = None
    urls = await get_user_tracked_urls(user_id)
    for u in urls:
        if u.get("id") == url_id:
            target_url = u.get("url")
            break

    success = await delete_user_tracked_url(user_id, url_id)
    # Если не нашло по user_id, но пользователь админ — проверяем по ADMIN_CHAT_ID
    if not success and await is_admin(user_id):
        success = await delete_user_tracked_url(ADMIN_CHAT_ID, url_id)

    # Синхронизируем удаление через helper и users.json
    try:
        sys.path.insert(0, os.path.dirname(BOT_DIR))
        import avito_api_helper
        avito_api_helper.delete_search(search_id=url_id, url=target_url)
    except Exception:
        pass

    delete_search_from_site_users(user_id, url_id, username=username, url=target_url)

    if success or target_url:
        await message.answer(f"🗑 Поиск с номером <b>{url_id}</b> успешно удален из вашей сессии и с сайта.", parse_mode=ParseMode.HTML)
    else:
        await message.answer(f"❌ Поиск с номером <b>{url_id}</b> не найден в вашем списке.", parse_mode=ParseMode.HTML)


@dp.message(Command("check"))
async def cmd_check(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    site_u = await check_auth_or_prompt(message)
    if not site_u:
        return

    is_adm = await is_admin(user_id, message.from_user.username)
    perms = site_u.get("permissions") or {}

    # Проверка глобальной лицензии программы
    if not is_license_active():
        await message.answer(
            "⏳ <b>Срок действия лицензии истёк или программа не активирована!</b>\n\n"
            "Сканирование объявлений Avito приостановлено до активации ключа.",
            parse_mode=ParseMode.HTML
        )
        return

    # Проверяем срок действия тарифа
    if not is_adm:
        exp_str = perms.get("avito_expires_at")
        if exp_str:
            try:
                exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > exp_dt:
                    await message.answer(
                        f"⏳ <b>Срок действия вашего тарифа истек ({exp_str})!</b>\n\n"
                        f"Продлите тариф на сайте SkyBase для запуска сканирования: <a href=\"{get_site_url()}/\">SkyBase</a>.",
                        parse_mode=ParseMode.HTML
                    )
                    return
            except Exception:
                pass

    urls = await get_user_tracked_urls(user_id)
    if not urls:
        await message.answer("ℹ️ У вас нет добавленных поисков. Добавьте командой /add.")
        return

    status_msg = await message.answer(f"🔎 Сканирую ваши поиски ({len(urls)} шт.)...")
    
    user_proxies = await get_user_proxies(user_id)
    task_proxy = None
    if user_proxies:
        pool = getattr(parser, "proxy_pool", None)
        if pool and hasattr(pool, "get_proxy_ping"):
            task_proxy = min(user_proxies, key=lambda p: pool.get_proxy_ping(p))
        else:
            task_proxy = user_proxies[0]
    elif hasattr(parser, "proxy_pool") and parser.proxy_pool and parser.proxy_pool.proxies:
        task_proxy = parser.proxy_pool.get_next_proxy()

    if not task_proxy or task_proxy == "direct":
        await message.answer("🛡️ Проверка отменена: нет доступных рабочих прокси. Прямое обращение к Авито заблокировано для защиты IP сервера.")
        return

    if task_proxy.startswith("socks5://"):
        task_proxy = "socks5h://" + task_proxy[9:]

    new_count = 0
    for task in urls:
        task_id = task["id"]
        is_init = bool(task.get("is_initialized", 0))
        conf_depth = get_configured_search_depth()
        pages_to_fetch = 1 if is_init else conf_depth
        ads = await parser.fetch_ads(task["url"], proxy=task_proxy, max_pages=pages_to_fetch)
        for ad in ads:
            ad_title_str = str(getattr(ad, "title", "") or "").lower()
            is_ad_res = getattr(ad, "is_reserved", False) or any(w in ad_title_str for w in [
                "зарезервирован", "забронирован", "в резерве", "товар забронирован", "товар в резерве",
                "бронь", "(бронь)", "[бронь]", "резерв", "(рез)", "[рез]"
            ])
            if is_ad_res:
                await delete_seen_item(str(ad.id))
                continue

            ad_price_val = getattr(ad, "price", None)
            if not is_ad_in_price_range(ad_price_val, task["url"], task["name"]) or not is_relevant_ad(ad.title, task["url"], task["name"], ad_price_val):
                continue

            # Фильтр доставки: если включен поиск только с доставкой (в настройках или в URL d=1/cd=1)
            task_only_deliv = bool(task.get("only_delivery", 0)) or ("d=1" in task["url"]) or ("cd=1" in task["url"])
            if task_only_deliv and not getattr(ad, "has_delivery", False):
                continue

            # Фильтр удаленных карточек
            if await is_item_deleted(str(ad.id)):
                continue

            seen = await is_seen(user_id, ad.id)
            if not seen:
                await add_seen(user_id, ad.id, ad.title, ad.price, ad.url, photo=ad.photo, photos=getattr(ad, "photos", None), seller=ad.seller, address=ad.address, search_name=task["name"], has_delivery=int(ad.has_delivery), seller_type=getattr(ad, "seller_type", "Частное лицо"), item_date=getattr(ad, "item_date", None), seller_rating=getattr(ad, "seller_rating", None), description=getattr(ad, "description", None))
                if is_init:
                    new_count += 1
                    await send_notification_to_user(bot, user_id, ad, task["name"])
                    await asyncio.sleep(0.5)
            else:
                await update_seen_details_if_missing(user_id, ad.id, photo=ad.photo, seller=ad.seller, address=ad.address, search_name=task["name"], has_delivery=int(ad.has_delivery), seller_type=getattr(ad, "seller_type", "Частное лицо"), item_date=getattr(ad, "item_date", None), seller_rating=getattr(ad, "seller_rating", None))

        if not is_init:
            await set_url_initialized(task_id)

        await asyncio.sleep(PAUSE_BETWEEN_REQUESTS)

    await status_msg.edit_text(
        f"✅ Проверка ваших ссылок завершена!\nНайдено новых объявлений: <b>{new_count}</b>.",
        parse_mode=ParseMode.HTML
    )


# ===================== КОМАНДА СТАТУСА =====================

@dp.message(Command("status"))
@dp.message(F.text == "📊 Статус")
async def cmd_status(message: types.Message):
    user_id = message.from_user.id
    site_u = await check_auth_or_prompt(message)
    if not site_u:
        return

    is_user_admin = await is_admin(user_id, message.from_user.username)
    if not is_user_admin:
        silent = await is_silent_mode(user_id)
        urls = await get_user_tracked_urls(user_id)
        active_cnt = sum(1 for u in urls if u.get("is_active"))
        card = format_user_privileges_card(site_u, len(urls), silent)
        text = (
            f"📊 <b>Ваш статус и тариф в сервисе SkyBase:</b>\n\n"
            f"{card}\n\n"
            f"🔍 <b>Активных поисков:</b> {active_cnt} из {len(urls)}\n"
            f"<i>Для управления ссылками отправьте команду /list</i>"
        )
        await message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        return

    stats = await get_stats()
    uptime = str(datetime.now() - start_time).split(".")[0]
    status_str = "🟢 <b>Активен</b>" if is_monitoring_active else "⏸ <b>На паузе</b>"
    last_str = last_check_time.strftime("%H:%M:%S") if last_check_time else "Еще не проводилась"

    parser.proxy_pool.reload()
    proxy_count = parser.proxy_pool.get_proxy_count()
    import math
    is_rand = str(target_check_interval).startswith("rand") or target_check_interval == "random_30_60"
    if is_rand:
        needed_proxies = 0
        target_display = "🎲 Рандом 30–60 сек"
    else:
        try:
            t_sec = int(target_check_interval)
        except Exception:
            t_sec = 30
        needed_proxies = max(1, math.ceil(30 / t_sec)) if t_sec < 30 else 0
        target_display = f"{t_sec} сек."

    speed_info = (
        f"⚡️ <b>Текущая скорость:</b> каждые <b>{current_check_interval} сек.</b>\n"
        f"🎯 <b>Целевой интервал:</b> {target_display}\n"
        f"🌐 <b>Живых прокси в работе:</b> <b>{proxy_count} шт.</b> (для цели нужно: {needed_proxies})\n"
    )

    text = (
        f"📊 <b>Панель администратора:</b> {status_str}\n\n"
        f"{speed_info}\n"
        f"⏱ <b>Время работы:</b> {uptime}\n"
        f"🔄 <b>Проверок выполнено:</b> {checks_performed_count}\n"
        f"🕒 <b>Последняя проверка:</b> {last_str}\n"
        f"🔗 <b>Всего активных поисков:</b> {stats['urls_count']}\n"
        f"💾 <b>Объявлений в базе:</b> {stats['seen_count']}"
    )
    admin = await is_admin(message.from_user.id, message.from_user.username)
    silent = await is_silent_mode(message.from_user.id)
    await message.answer(text, reply_markup=get_main_keyboard(is_user_admin=admin, is_silent=silent), parse_mode=ParseMode.HTML)


@dp.message(Command("stop"))
async def cmd_stop(message: types.Message):
    """Приостановка фонового мониторинга."""
    global is_monitoring_active
    user_id = message.from_user.id
    username = message.from_user.username
    if not await is_admin(user_id, username):
        return

    silent = await is_silent_mode(user_id)
    if not is_monitoring_active:
        await message.answer(
            "⏸ <b>Мониторинг Avito уже выключен (на паузе).</b>\n\n"
            "Нажмите «▶️ Включить», чтобы запустить сбор новых объявлений.",
            reply_markup=get_main_keyboard(is_user_admin=True, is_silent=silent, is_active=False, user_id=user_id, username=username),
            parse_mode=ParseMode.HTML
        )
        return

    is_monitoring_active = False
    try:
        sys.path.insert(0, os.path.dirname(BOT_DIR))
        import avito_api_helper
        avito_api_helper.set_bot_paused("pause")
    except Exception:
        pass

    logger.info(f"Администратор {user_id} поставил мониторинг на паузу.")
    await message.answer(
        "⏸ <b>Мониторинг Avito приостановлен!</b>\n\n"
        "Бот перестал сканировать новые объявления.\n"
        "Для запуска нажмите «▶️ Включить».",
        reply_markup=get_main_keyboard(is_user_admin=True, is_silent=silent, is_active=False, user_id=user_id, username=username),
        parse_mode=ParseMode.HTML
    )


@dp.message(Command("resume"))
async def cmd_resume(message: types.Message):
    """Возобновление фонового мониторинга."""
    global is_monitoring_active
    user_id = message.from_user.id
    username = message.from_user.username
    if not await is_admin(user_id, username):
        return

    silent = await is_silent_mode(user_id)
    if is_monitoring_active:
        await message.answer(
            "🟢 <b>Мониторинг Avito уже включен и работает!</b>\n\n"
            "Все поиски активно проверяются в фоновом режиме.",
            reply_markup=get_main_keyboard(is_user_admin=True, is_silent=silent, is_active=True, user_id=user_id, username=username),
            parse_mode=ParseMode.HTML
        )
        return

    # Проверка лицензии
    try:
        if SITE_DIR not in sys.path:
            sys.path.insert(0, SITE_DIR)
        import avito_api_helper
        lic = avito_api_helper.get_license_status_info("")
        if not lic or lic.get("is_expired") is True:
            await message.answer(
                "⛔️ <b>Срок действия лицензии истёк или требуется активация!</b>\n\n"
                "Мониторинг Avito не может быть запущен без активной лицензии.\n"
                "Для активации перейдите на сайт или введите команду /activate.",
                parse_mode=ParseMode.HTML
            )
            return
    except Exception:
        pass

    is_monitoring_active = True
    try:
        sys.path.insert(0, os.path.dirname(BOT_DIR))
        import avito_api_helper
        avito_api_helper.set_bot_paused("resume")
    except Exception:
        pass

    logger.info(f"Администратор {user_id} возобновил мониторинг.")
    await message.answer(
        "🟢 <b>Мониторинг Avito возобновлен!</b>\n\n"
        "Проверка новых объявлений снова активна.",
        reply_markup=get_main_keyboard(is_user_admin=True, is_silent=silent, is_active=True, user_id=user_id, username=username),
        parse_mode=ParseMode.HTML
    )

@dp.message(Command("timer"))
async def cmd_timer(message: types.Message, bot: Optional[Bot] = None):
    """Настройка интервала опроса (только для администратора)."""
    global current_check_interval, target_check_interval
    if not await is_admin(message.from_user.id, message.from_user.username):
        return

    text = (message.text or "").strip()
    args = text.split()
    if len(args) > 1 and args[0].lower().startswith(("/timer", "/t")):
        arg_val = args[1].lower()
        if arg_val in ("random", "rand", "random_30_60"):
            target_check_interval = "random_30_60"
            current_check_interval = 30
            set_persisted_target_interval("random_30_60", user_id=message.from_user.id if message.from_user else None)
            await message.answer(
                "🎲 <b>Установлен режим защиты от бана!</b>\n\n"
                "⏱ Интервал проверки: случайный <b>от 30 до 60 секунд</b>.\n"
                "🛡 Avito не заблокирует бота, так как запросы идут с нерегулярными интервалами.",
                parse_mode=ParseMode.HTML
            )
            return

        if arg_val.isdigit():
            sec = int(arg_val)
            if sec < 1:
                await message.answer("⚠️ Минимальный интервал — 1 секунда.")
                return

            target_check_interval = sec
            set_persisted_target_interval(sec, user_id=message.from_user.id if message.from_user else None)
            parser.proxy_pool.reload()
            proxy_count = parser.proxy_pool.get_proxy_count()
            import math
            needed_proxies = max(1, math.ceil(30 / sec)) if sec < 30 else 0
            safe_int = get_safe_interval_for_proxies(target_check_interval, proxy_count)
            current_check_interval = safe_int

            if proxy_count < needed_proxies:
                await message.answer(
                    f"🎯 <b>Цель: {target_check_interval} сек</b> (нужно {needed_proxies} прокси).\n\n"
                    f"📊 В наличии: <b>{proxy_count} прокси</b>.\n"
                    f"🛡 Для защиты от бана бот сейчас работает на безопасной скорости: <b>{current_check_interval} сек</b>.\n\n"
                    f"🤖 <b>Включен умный авто-разгон:</b> бот в фоне уже ищет и проверяет бесплатные прокси. "
                    f"Как только наберется нужное число — бот сам разгонится до <b>{target_check_interval} сек</b>!",
                    parse_mode=ParseMode.HTML
                )
                # Будим фоновый сборщик прокси для немедленного поиска
                proxy_wake_event.set()
            else:
                await message.answer(
                    f"✅ <b>Проверка безопасности пройдена!</b>\n\n"
                    f"⏱ Интервал проверки установлен: <b>{current_check_interval} сек.</b>\n"
                    f"🌐 Активных прокси: <b>{proxy_count} шт.</b> (требовалось: {needed_proxies})\n"
                    f"Авито не заблокирует: каждый IP будет опрашиваться не чаще 1 раза в 30 сек.",
                    parse_mode=ParseMode.HTML
                )
            return
        else:
            await message.answer("⚠️ Неверный формат интервала. Укажите число секунд (например, <code>/timer 5</code>) или <code>/timer random</code>.")
            return

    # Инлайн-кнопки быстрого выбора
    is_rand = str(target_check_interval).startswith("rand") or target_check_interval == "random_30_60"
    mode_display = ""
    if direct_mode_enabled:
        mode_display = "\n🟢 <b>Активен: Прямой режим (60–90 сек)</b>"
    elif hybrid_mode_enabled:
        mode_display = "\n🟢 <b>Активен: Гибридный режим (direct/proxy)</b>"
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚡️ 1 сек (30 прокси)", callback_data="set_timer_1"),
            InlineKeyboardButton(text="⚡️ 3 сек (10 прокси)", callback_data="set_timer_3")
        ],
        [
            InlineKeyboardButton(text="⚡️ 5 сек (6 прокси)", callback_data="set_timer_5"),
            InlineKeyboardButton(text="⏱ 10 сек (3 прокси)", callback_data="set_timer_10")
        ],
        [
            InlineKeyboardButton(text="⏱ 15 сек (2 прокси)", callback_data="set_timer_15"),
            InlineKeyboardButton(text="⏱ 30 сек (1 прокси)", callback_data="set_timer_30")
        ],
        [
            InlineKeyboardButton(text=f"{'🟢' if direct_mode_enabled else '⚪'} 60-90 сек — Прямое подключение", callback_data="set_timer_60_direct")
        ],
        [
            InlineKeyboardButton(text=f"{'🟢' if hybrid_mode_enabled else '⚪'} Гибридный режим direct(60-90)/Proxy", callback_data="set_timer_hybrid")
        ]
    ])
    
    parser.proxy_pool.reload()
    current_proxies = parser.proxy_pool.get_proxy_count()
    if direct_mode_enabled:
        target_display = "🟢 Прямое подключение (60–90 сек)"
        current_display = "60–90 сек рандом (прямой)"
    elif hybrid_mode_enabled:
        target_display = "🟢 Гибридный режим (direct/proxy)"
        current_display = f"60–90 сек рандом (прямой)" if current_proxies == 0 else f"{current_check_interval} сек (прокси)"
    else:
        target_display = "🎲 Рандом 30–60 сек" if (str(target_check_interval).startswith("rand") or target_check_interval == "random_30_60") else f"{target_check_interval} сек."
        current_display = "30–60 сек (рандом)" if (str(target_check_interval).startswith("rand") or target_check_interval == "random_30_60") else f"{current_check_interval} сек."
    await message.answer(
        f"⏱ <b>Управление таймером опроса Avito (Саморегуляция)</b>\n\n"
        f"🎯 Желаемая цель: <b>{target_display}</b>{mode_display}\n"
        f"⚡️ Текущая безопасная скорость: <b>{current_display}</b>\n"
        f"🌐 Доступно прокси в пуле: <b>{current_proxies} шт.</b>\n\n"
        f"💡 <i>30 сек — нужно 1 прокси. 60-90 сек — прямое подключение в рандоме без прокси (защита от бана). Гибридный режим: прокси + прямой 60–90 сек при 0 прокси.</i>\n\n"
        f"Выберите интервал кнопкой или задайте командой:\n"
        f"<code>/timer &lt;секунды&gt;</code> или <code>/timer random</code>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("set_timer_"))
async def cb_set_timer(call: CallbackQuery, bot: Bot):
    global current_check_interval, target_check_interval, hybrid_mode_enabled, direct_mode_enabled
    if not await is_admin(call.from_user.id):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return

    sec_str = call.data.replace("set_timer_", "")

    # Режим прямого подключения 60-90 сек
    if sec_str == "60_direct":
        direct_mode_enabled = True
        hybrid_mode_enabled = False
        target_check_interval = 60
        current_check_interval = 60
        set_persisted_target_interval(60, user_id=call.from_user.id if call.from_user else None, mode="direct")
        # Останавливаем поиск прокси
        try:
            parser.proxy_pool.stop_fetching()
        except Exception:
            pass
        try:
            await call.message.edit_text(
                "🟢 <b>Прямое подключение активировано!</b>\n\n"
                "⏱ Интервал проверки: случайный <b>от 60 до 90 секунд</b> (без прокси).\n"
                "🛡 Защита от бана: нерегулярные паузы между запросами.\n"
                "🔍 Поиск прокси остановлен.",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
        await call.answer("🟢 Прямое подключение: 60-90 сек")
        return

    # Гибридный режим: прямой + прокси
    if sec_str == "hybrid":
        if hybrid_mode_enabled:
            # Выключаем гибридный режим
            hybrid_mode_enabled = False
            direct_mode_enabled = False
            set_persisted_target_interval(target_check_interval or 60, user_id=call.from_user.id if call.from_user else None, mode="normal")
            try:
                await call.message.edit_text(
                    "ℹ️ <b>Гибридный режим выключен.</b>\n\n"
                    "Возврат в стандартный режим (ожидание прокси).",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
            await call.answer("Гибридный режим выключен")
        else:
            # Включаем гибридный режим
            hybrid_mode_enabled = True
            direct_mode_enabled = False
            set_persisted_target_interval(target_check_interval or 60, user_id=call.from_user.id if call.from_user else None, mode="hybrid")
            parser.proxy_pool.reload()
            proxy_count = parser.proxy_pool.get_proxy_count()
            try:
                await call.message.edit_text(
                    "🟢 <b>Гибридный режим активирован!</b>\n\n"
                    "🔀 При наличии прокси — работает через прокси.\n"
                    "🌐 При 0 прокси — прямое подключение с <b>случайным интервалом 60–90 сек</b> (защита от бана).\n\n"
                    f"📊 Прокси в пуле сейчас: <b>{proxy_count} шт.</b>\n"
                    f"{'✅ Сейчас используются прокси.' if proxy_count > 0 else '🔀 Сейчас используется прямое подключение (60–90 сек).'}",
                    parse_mode=ParseMode.HTML
                )
            except Exception:
                pass
            await call.answer("🟢 Гибридный режим включен")
        return

    if sec_str.isdigit():
        direct_mode_enabled = False
        hybrid_mode_enabled = False
        sec = int(sec_str)
        target_check_interval = sec
        set_persisted_target_interval(sec, user_id=call.from_user.id if call.from_user else None, mode="normal")
        parser.proxy_pool.reload()
        proxy_count = parser.proxy_pool.get_proxy_count()
        import math
        needed_proxies = max(1, math.ceil(30 / sec)) if sec < 30 else 0
        safe_int = get_safe_interval_for_proxies(target_check_interval, proxy_count)
        current_check_interval = safe_int

        try:
            if proxy_count < needed_proxies:
                await call.message.edit_text(
                    f"🎯 <b>Целевой интервал установлен: {target_check_interval} сек!</b>\n\n"
                    f"📊 Сейчас живых прокси: <b>{proxy_count} шт.</b> (для целевой скорости нужно {needed_proxies})\n"
                    f"🛡 Бот прямо сейчас безопасно сканирует со скоростью: <b>{current_check_interval} сек</b>.\n\n"
                    f"🤖 <b>Включен умный авто-разгон:</b> бот прямо сейчас в фоне ищет и проверяет новые бесплатные прокси. "
                    f"По мере набора бот сам пришлет уведомление и автоматически разгонится до <b>{target_check_interval} сек</b>!",
                    parse_mode=ParseMode.HTML
                )
                proxy_wake_event.set()
            else:
                await call.message.edit_text(
                    f"✅ <b>Проверка безопасности пройдена!</b>\n\n"
                    f"⏱ Интервал мониторинга установлен на <b>{current_check_interval} сек!</b>\n"
                    f"🌐 Активных прокси в пуле: <b>{proxy_count} шт.</b> (требовалось: {needed_proxies})\n\n"
                    f"Бот на максимальной скорости сканирует новые объявления.",
                    parse_mode=ParseMode.HTML
                )
        except Exception:
            pass
        if str(sec_str) in ("10", "15"):
            await call.answer()
        else:
            await call.answer(f"Интервал: {sec_str} сек")
        return


def get_proxy_menu_keyboard(is_fetching: bool = False) -> InlineKeyboardMarkup:
    """Создаёт инлайн-клавиатуру меню прокси с кнопками проверки, очистки, тумблером сбора."""
    if is_fetching:
        fetch_btn = InlineKeyboardButton(text="🟢 Идет поиск прокси... (Нажмите для остановки)", callback_data="proxy_fetch_free")
    else:
        fetch_btn = InlineKeyboardButton(text="📥 Найти бесплатные прокси", callback_data="proxy_fetch_free")

    return InlineKeyboardMarkup(inline_keyboard=[
        [fetch_btn],
        [
            InlineKeyboardButton(text="🔍 Проверить", callback_data="proxy_check_all"),
            InlineKeyboardButton(text="🗑 Очистить все", callback_data="proxy_clear_all")
        ],
        [InlineKeyboardButton(text="➕ Добавить свой прокси", callback_data="proxy_add_custom")],
        [InlineKeyboardButton(text="📋 Показать текущие прокси", callback_data="proxy_list_view")]
    ])


@dp.message(Command("proxy"))
@dp.message(Command("proxies"))
@dp.message(F.text == "🌐 Прокси")
async def cmd_proxy(message: types.Message):
    """Управление прокси: поиск, проверка, очистка, добавление своего, просмотр."""
    if not await is_admin(message.from_user.id, message.from_user.username):
        return

    parser.proxy_pool.reload()
    count = parser.proxy_pool.get_proxy_count()
    is_active = getattr(parser.proxy_pool, "is_fetching", False)
    kb = get_proxy_menu_keyboard(is_fetching=is_active)

    await message.answer(
        f"🌐 <b>Управление прокси-серверами</b>\n\n"
        f"📊 Актуальных живых прокси в пуле: <b>{count} шт.</b>\n"
        f"📁 Файл списка: <code>proxies.txt</code>\n\n"
        f"<i>💡 Бот автоматически в фоне ищет новые прокси, проверяет их на живучесть и удаляет мертвые при необходимости.</i>",
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "proxy_check_all")
async def cb_proxy_check_all(call: CallbackQuery):
    """Проверка всех имеющихся прокси на доступ к Avito и удаление мертвых."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступно только администратору!", show_alert=True)
        return

    parser.proxy_pool.reload()
    total = parser.proxy_pool.get_proxy_count()
    if total == 0:
        await call.answer("Пул прокси пуст. Нечего проверять.", show_alert=True)
        return

    await call.answer("⏳ Запущена проверка прокси...", show_alert=False)
    status_msg = await call.message.answer(
        f"⏳ <b>Начата проверка {total} прокси на доступ к Avito...</b>\n"
        f"<i>Неработающие прокси будут автоматически удалены из пула. Пожалуйста, подождите.</i>",
        parse_mode=ParseMode.HTML
    )

    alive_count = await parser.proxy_pool.filter_and_clean_dead_proxies()
    proxy_wake_event.set()

    # Актуализируем proxy_status.json
    try:
        cfg_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy_status.json")
        st = {"is_fetching": False, "found": alive_count, "message": f"Проверено: {alive_count} живых"}
        if os.path.exists(cfg_p):
            with open(cfg_p, "r", encoding="utf-8") as f:
                st = json.load(f)
        st["found"] = alive_count
        with open(cfg_p, "w", encoding="utf-8") as f:
            json.dump(st, f, ensure_ascii=False)
    except Exception:
        pass

    removed_count = total - alive_count
    await status_msg.edit_text(
        f"✅ <b>Проверка прокси завершена!</b>\n\n"
        f"• Всего проверено: <b>{total} шт.</b>\n"
        f"• Живых и готовых к работе: <b>{alive_count} шт.</b>\n"
        f"• Удалено неработающих: <b>{removed_count} шт.</b>",
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "proxy_clear_all")
async def cb_proxy_clear_all_prompt(call: CallbackQuery):
    """Запрос подтверждения на полную очистку пула прокси."""
    if not await is_admin(call.from_user.id):
        await call.answer("Доступно только администратору!", show_alert=True)
        return

    confirm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="⚠️ Да, очистить все!", callback_data="proxy_clear_confirm"),
            InlineKeyboardButton(text="❌ Отмена", callback_data="proxy_clear_cancel")
        ]
    ])
    await call.message.answer(
        "⚠️ <b>Вы действительно хотите удалить все прокси?</b>\n\n"
        "Пул прокси будет полностью очищен (0 шт.).",
        reply_markup=confirm_kb,
        parse_mode=ParseMode.HTML
    )
    await call.answer()


@dp.callback_query(F.data == "proxy_clear_cancel")
async def cb_proxy_clear_cancel(call: CallbackQuery):
    """Отмена очистки прокси."""
    try:
        await call.message.delete()
    except Exception:
        pass
    await call.answer("Очистка отменена.")


@dp.callback_query(F.data == "proxy_clear_confirm")
async def cb_proxy_clear_confirm(call: CallbackQuery):
    """Полная очистка всех прокси из пула и файла."""
    if not await is_admin(call.from_user.id):
        await call.answer("Доступно только администратору!", show_alert=True)
        return

    prev_count = parser.proxy_pool.get_proxy_count()
    parser.proxy_pool.proxies = []
    parser.proxy_pool.save_to_file()

    # Очищаем файл proxies.txt
    p_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxies.txt")
    if os.path.exists(p_file):
        try:
            with open(p_file, "w", encoding="utf-8") as f:
                f.write("# Список рабочих прокси (очищен)\n")
        except Exception:
            pass

    # Очищаем proxy_status.json
    try:
        cfg_p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy_status.json")
        if os.path.exists(cfg_p):
            with open(cfg_p, "w", encoding="utf-8") as f:
                json.dump({"is_fetching": False, "found": 0, "message": "Пул очищен"}, f, ensure_ascii=False)
    except Exception:
        pass

    try:
        await call.message.edit_text(
            f"🗑 <b>Все прокси успешно удалены!</b>\n\n"
            f"Удалено: <b>{prev_count} шт.</b>\n"
            f"Текущее количество прокси в пуле: <b>0 шт.</b>",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        await call.message.answer(
            f"🗑 <b>Все прокси успешно удалены!</b> (удалено {prev_count} шт.)",
            parse_mode=ParseMode.HTML
        )
    await call.answer("Пул прокси полностью очищен!", show_alert=True)


@dp.callback_query(F.data == "proxy_fetch_free")
async def cb_proxy_fetch_free(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return

    # Если поиск УЖЕ идёт — повторный клик останавливает его и возвращает кнопку
    if getattr(parser.proxy_pool, "is_fetching", False):
        parser.proxy_pool.stop_fetching()
        idle_kb = get_proxy_menu_keyboard(is_fetching=False)
        try:
            await call.message.edit_reply_markup(reply_markup=idle_kb)
        except Exception:
            pass

        await call.answer()
        return

    # Иначе — запускаем поиск и переключаем кнопку в зелёный режим
    active_kb = get_proxy_menu_keyboard(is_fetching=True)
    try:
        await call.message.edit_reply_markup(reply_markup=active_kb)
    except Exception:
        pass

    await call.answer()


    async def _runner():
        await parser.proxy_pool.fetch_free_proxies_and_verify(target_alive=100)

        # После завершения возвращаем кнопку в исходное состояние — без сообщений в чат
        idle_kb = get_proxy_menu_keyboard(is_fetching=False)
        try:
            await call.message.edit_reply_markup(reply_markup=idle_kb)
        except Exception:
            pass

    asyncio.create_task(_runner())


@dp.callback_query(F.data == "proxy_add_custom")
async def cb_proxy_add_custom(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return

    admin_waiting_proxy.add(call.from_user.id)
    await call.message.answer(
        "➕ <b>Добавление своего прокси</b>\n\n"
        "Отправьте прокси в чат одним сообщением (можно сразу несколько строк, каждый с новой строки).\n\n"
        "<b>Поддерживаемые форматы:</b>\n"
        "• <code>ip:port</code>\n"
        "• <code>http://ip:port</code>\n"
        "• <code>http://login:pass@ip:port</code>\n"
        "• <code>socks5://login:pass@ip:port</code>\n\n"
        "<i>Бот сразу проверит их на доступ к Avito и добавит живые в список! Для отмены отправьте /cancel.</i>",
        parse_mode=ParseMode.HTML
    )
    await call.answer()


@dp.callback_query(F.data == "proxy_list_view")
async def cb_proxy_list_view(call: CallbackQuery):
    if not await is_admin(call.from_user.id):
        return

    parser.proxy_pool.reload()
    proxies = parser.proxy_pool.proxies
    if not proxies:
        await call.answer("Пул прокси пуст. Добавьте свои или подождите авто-поиска.", show_alert=True)
        return

    text = "📋 <b>Список рабочих прокси:</b>\n\n" + "\n".join(f"• <code>{p}</code>" for p in proxies[:25])
    if len(proxies) > 25:
        text += f"\n\n<i>... и еще {len(proxies) - 25} прокси в файле proxies.txt</i>"
    await call.message.answer(text, parse_mode=ParseMode.HTML)
    await call.answer()


@dp.message(Command("restart"))
async def cmd_restart(message: types.Message):
    """Мягкий перезапуск сервиса бота прямо из Telegram."""
    if not await is_admin(message.from_user.id):
        return

    await message.answer(
        "🔄 <b>Перезапуск сервиса...</b>\n\n"
        "Бот перезагружает конфигурацию и базу данных. Через пару секунд мониторинг снова будет активен!",
        parse_mode=ParseMode.HTML
    )
    logger.warning(f"Администратор {message.from_user.id} инициировал команду /restart.")

    await asyncio.sleep(1)
    # Запускаем новый процесс бота и завершаем старый
    import subprocess
    subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=os.path.dirname(os.path.abspath(__file__)))
    os._exit(0)


@dp.message(Command("shutdown"))
async def cmd_shutdown(message: types.Message):
    """Полное выключение процесса бота."""
    if not await is_admin(message.from_user.id):
        return

    await message.answer(
        "🔌 <b>Сервис полностью выключается...</b>\n\n"
        "Процесс бота завершает работу. Для повторного запуска используйте <code>run.bat</code> или команду запуска.",
        parse_mode=ParseMode.HTML
    )
    logger.warning(f"Администратор {message.from_user.id} инициировал команду /shutdown.")

    # Даем сообщению отправиться в Telegram перед остановкой процесса
    await asyncio.sleep(1)
    os._exit(0)


@dp.message(Command("pending"))
async def cmd_pending(message: types.Message):
    if not await is_admin(message.from_user.id):
        return

    pending_users = await get_users_by_status("pending")
    if not pending_users:
        await message.answer("✨ Нет ожидающих заявок. Все клиенты обработаны!")
        return

    lines = [f"📋 <b>Ожидают подтверждения ({len(pending_users)}):</b>\n"]
    for u in pending_users:
        uname = f"@{u['username']}" if u['username'] else "нет username"
        lines.append(
            f"• <b>{u['full_name']}</b> ({uname})\n"
            f"  ID: <code>{u['user_id']}</code>\n"
            f"  Действия: /approve {u['user_id']} | /block {u['user_id']}\n"
        )
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


# ===================== ПАНЕЛЬ УПРАВЛЕНИЯ ПОЛЬЗОВАТЕЛЯМИ (ADMIN) =====================

def get_blacklist_json_paths():
    """Возвращает пути к файлам blacklist.json в директории проекта."""
    p_local = os.path.normpath(os.path.join(os.path.dirname(BOT_DIR), "data", "blacklist.json"))
    paths = [p_local]
    for extra in [r"e:\TEMP\База-бот\SITE\data\blacklist.json", r"C:\ins\EXP\Arduino\Проект\База-бот\SITE\data\blacklist.json"]:
        if os.path.exists(os.path.dirname(extra)) and extra not in paths:
            paths.append(extra)
    return paths


def load_site_blacklist() -> list:
    """Загружает записи чёрного списка."""
    for p in get_blacklist_json_paths():
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8-sig") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception:
                pass
    return []


def save_site_blacklist(entries: list) -> bool:
    """Сохраняет записи чёрного списка."""
    saved = False
    for p in get_blacklist_json_paths():
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8-sig") as f:
                json.dump(entries, f, ensure_ascii=False, indent=2)
            saved = True
        except Exception:
            pass
    return saved


def add_user_to_site_blacklist(username: str, ip: Optional[str] = None, mac: Optional[str] = None, reason: str = "Заблокирован через Telegram"):
    """Добавляет пользователя в blacklist.json."""
    if not username or username.strip().lower() in ("skynet83", "skynet19081983"):
        return
    clean_u = username.strip().lower()
    entries = load_site_blacklist()
    exists = any((e.get("username") or "").strip().lower() == clean_u for e in entries)
    if not exists:
        entries.append({
            "username": username.strip(),
            "ip": ip or "",
            "mac": mac or "",
            "reason": reason,
            "blocked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
        save_site_blacklist(entries)


def remove_user_from_site_blacklist(username: str):
    """Удаляет пользователя из blacklist.json."""
    if not username:
        return
    clean_u = username.strip().lower()
    entries = load_site_blacklist()
    new_entries = [e for e in entries if (e.get("username") or "").strip().lower() != clean_u]
    if len(new_entries) != len(entries):
        save_site_blacklist(new_entries)


async def get_all_system_users() -> list:
    """Возвращает объединенный актуальный список пользователей сайта и Telegram-бота."""
    site_users = load_site_users()
    db_users = await get_users_by_status()

    users_map = {}
    for u in site_users:
        uname = (u.get("username") or "").strip()
        if uname:
            users_map[uname.lower()] = u

    for dbu in db_users:
        db_id = dbu.get("user_id")
        db_uname = (dbu.get("username") or "").strip()
        matched = False
        for u in site_users:
            if str(u.get("telegram_chat_id", "")).strip() == str(db_id):
                matched = True
                break
        if not matched:
            pseudo_name = f"tg_{db_id}"
            if pseudo_name.lower() not in users_map:
                stub_u = {
                    "username": pseudo_name,
                    "name": dbu.get("full_name") or pseudo_name,
                    "role": "admin" if dbu.get("status") == "admin" else "user",
                    "telegram_chat_id": db_id,
                    "telegram_username": db_uname,
                    "is_blocked": dbu.get("status") in ("blocked", "rejected"),
                    "chat_blocked": False,
                    "permissions": {
                        "is_expired": True,
                        "avito_duration": "expired"
                    },
                    "avito_searches": []
                }
                users_map[pseudo_name.lower()] = stub_u

    return list(users_map.values())


async def show_users_control_panel(event):
    """Главная панель управления пользователями (ЧС, блокировка чата, сообщения, тарифы)."""
    users = await get_all_system_users()
    total_count = len(users)
    blocked_count = sum(1 for u in users if u.get("is_blocked"))
    chat_blocked_count = sum(1 for u in users if u.get("chat_blocked"))
    active_count = sum(1 for u in users if not u.get("is_blocked"))

    text = (
        "👑 <b>Панель управления пользователями SkyBase</b>\n\n"
        f"📊 <b>Статистика сервиса:</b>\n"
        f"• Всего пользователей: <b>{total_count}</b>\n"
        f"• 🟢 Активных: <b>{active_count}</b>\n"
        f"• 🚫 В чёрном списке: <b>{blocked_count}</b>\n"
        f"• 🔇 Чат заблокирован: <b>{chat_blocked_count}</b>\n\n"
        "<i>Нажмите на пользователя ниже для перехода в карточку (блокировка, чат, личные сообщения, тариф, поиски):</i>"
    )

    inline_keyboard = []
    for u in users:
        uname = u.get("username") or "user"
        name = u.get("name") or uname
        is_adm = (u.get("role") == "admin" or uname.lower() in ("skynet83", "skynet19081983"))
        is_bl = bool(u.get("is_blocked"))
        is_chat_bl = bool(u.get("chat_blocked"))

        if is_adm:
            badge = "👑"
            role_hint = "Админ"
        elif is_bl:
            badge = "🚫"
            role_hint = "В ЧС"
        elif is_chat_bl:
            badge = "🔇"
            role_hint = "Чат заблокирован"
        else:
            perms = u.get("permissions") or {}
            is_exp = perms.get("is_expired") is True
            badge = "⏳" if is_exp else "🟢"
            role_hint = "Истек" if is_exp else "Активен"

        label = f"{badge} {name[:14]} ({role_hint})"
        inline_keyboard.append([
            InlineKeyboardButton(text=label, callback_data=f"adm_usr_{uname}")
        ])

    inline_keyboard.append([
        InlineKeyboardButton(text="➕ В черный список", callback_data="adm_bl_add"),
        InlineKeyboardButton(text="💬 Чат с пользователями", callback_data="adm_chat")
    ])
    inline_keyboard.append([
        InlineKeyboardButton(text="🔄 Обновить список", callback_data="adm_refresh")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=inline_keyboard)
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


async def show_user_detail_card(event, username: str):
    """Детальная карточка выбранного пользователя с кнопками взаимодействия."""
    users = await get_all_system_users()
    target_u = None
    for u in users:
        if (u.get("username") or "").strip().lower() == username.strip().lower():
            target_u = u
            break

    if not target_u:
        msg_text = f"❌ Пользователь <b>{html.escape(username)}</b> не найден."
        if isinstance(event, CallbackQuery):
            await event.answer("Пользователь не найден!", show_alert=True)
            await show_users_control_panel(event)
        else:
            await event.answer(msg_text, parse_mode=ParseMode.HTML)
        return

    uname = target_u.get("username")
    name = target_u.get("name") or uname
    role = target_u.get("role", "user")
    is_adm = (role == "admin" or uname.lower() in ("skynet83", "skynet19081983"))
    is_bl = bool(target_u.get("is_blocked"))
    is_chat_bl = bool(target_u.get("chat_blocked"))
    tg_id = target_u.get("telegram_chat_id")
    tg_uname = target_u.get("telegram_username")
    tg_info = f"@{tg_uname.lstrip('@')}" if tg_uname else (f"ID: <code>{tg_id}</code>" if tg_id else "<i>Не привязан</i>")

    perms = target_u.get("permissions") or {}
    duration = perms.get("avito_duration", "expired")
    exp_str = perms.get("avito_expires_at")
    is_exp = perms.get("is_expired") is True
    if is_adm:
        tariff_text = "👑 Полный доступ (Администратор)"
    elif duration == "unlimited":
        tariff_text = "♾ VIP Бессрочно"
    elif not is_exp and exp_str:
        tariff_text = f"⏳ До {exp_str}"
    else:
        tariff_text = "⛔️ Истек / Не активирован"

    searches = target_u.get("avito_searches") or []
    srch_count = len(searches)

    bl_status = "🚫 <b>В ЧЁРНОМ СПИСКЕ (Заблокирован)</b>" if is_bl else "🟢 <b>Активен (Доступ разрешен)</b>"
    chat_status = "🔇 <b>ЗАБЛОКИРОВАН (не может писать)</b>" if is_chat_bl else "🔊 <b>Разрешён (может писать)</b>"

    lines = [
        f"👤 <b>Карточка пользователя: {html.escape(name)}</b>\n",
        f"🖥️ <b>Логин на сайте:</b> <code>{html.escape(uname)}</code>",
        f"🏷 <b>Роль:</b> {'👑 Главный Администратор' if is_adm else '👤 Клиент'}",
        f"📱 <b>Telegram:</b> {tg_info}",
        f"🛡 <b>Статус доступа:</b> {bl_status}",
        f"💬 <b>Доступ к чату:</b> {chat_status}",
        f"📦 <b>Тариф:</b> {tariff_text}",
        f"🔍 <b>Активных поисков:</b> <b>{srch_count}</b> шт."
    ]
    text = "\n".join(lines)

    kb_rows = []
    if not is_adm:
        # 1. Чёрный список (Toggle)
        if is_bl:
            kb_rows.append([InlineKeyboardButton(text="✅ Убрать из Чёрного Списка", callback_data=f"adm_ublk_{uname}")])
        else:
            kb_rows.append([InlineKeyboardButton(text="🚫 Добавить в Чёрный Список", callback_data=f"adm_blk_{uname}")])

        # 2. Блокировка чата (Toggle)
        if is_chat_bl:
            kb_rows.append([InlineKeyboardButton(text="🔊 Разблокировать чат", callback_data=f"adm_cublk_{uname}")])
        else:
            kb_rows.append([InlineKeyboardButton(text="🔇 Заблокировать чат", callback_data=f"adm_cblk_{uname}")])

        # 3. Написать пользователю и поиски
        kb_rows.append([
            InlineKeyboardButton(text="💬 Написать пользователю", callback_data=f"adm_msg_{uname}"),
            InlineKeyboardButton(text=f"🔎 Поиски ({srch_count})", callback_data=f"adm_src_{uname}")
        ])

        # 4. Управление тарифом
        kb_rows.append([InlineKeyboardButton(text="🔑 Управление тарифом", callback_data=f"adm_trf_{uname}")])

        # 5. Удалить аккаунт
        kb_rows.append([InlineKeyboardButton(text="🗑 Удалить пользователя", callback_data=f"adm_del_{uname}")])
    else:
        kb_rows.append([InlineKeyboardButton(text=f"🔎 Поиски ({srch_count})", callback_data=f"adm_src_{uname}")])

    kb_rows.append([InlineKeyboardButton(text="⬅️ Назад к списку", callback_data="adm_list")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            await event.message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@dp.message(Command("users"))
@dp.message(Command("admin_users"))
@dp.message(Command("admin"))
async def cmd_users(message: types.Message):
    """Отображает панель управления пользователями."""
    if not await is_admin(message.from_user.id, message.from_user.username):
        return
    await show_users_control_panel(message)


@dp.callback_query(F.data.in_(["adm_refresh", "adm_list"]))
async def cb_users_panel_refresh(call: CallbackQuery):
    """Обновление или возврат к списку пользователей."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    await show_users_control_panel(call)


@dp.callback_query(F.data == "adm_chat")
async def cb_users_open_chat(call: CallbackQuery):
    """Быстрый переход в чат с пользователями из панели управления."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    await call.answer()
    await show_admin_chat(call.message)


@dp.callback_query(F.data.startswith("adm_usr_"))
async def cb_admin_user_card(call: CallbackQuery):
    """Открытие карточки выбранного пользователя."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    username = call.data.replace("adm_usr_", "", 1).strip()
    await show_user_detail_card(call, username)


@dp.callback_query(F.data.startswith("adm_blk_"))
async def cb_admin_act_block(call: CallbackQuery):
    """Добавление пользователя в чёрный список."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    username = call.data.replace("adm_blk_", "", 1).strip()
    if username.lower() in ("skynet83", "skynet19081983"):
        await call.answer("Нельзя заблокировать главного администратора!", show_alert=True)
        return

    users = load_site_users()
    target_u = None
    for u in users:
        if (u.get("username") or "").strip().lower() == username.lower():
            u["is_blocked"] = True
            u["session_token"] = ""
            target_u = u
            break
    if target_u:
        save_site_users(users)
        add_user_to_site_blacklist(username, ip=target_u.get("last_ip"), mac=target_u.get("last_mac"))
        if target_u.get("telegram_chat_id"):
            await set_user_status(target_u["telegram_chat_id"], "blocked")
    else:
        try:
            if username.startswith("tg_"):
                tg_id = int(username.replace("tg_", ""))
                await set_user_status(tg_id, "blocked")
                add_user_to_site_blacklist(username)
        except Exception:
            pass

    await call.answer("⛔️ Пользователь добавлен в Чёрный список!", show_alert=True)
    await show_user_detail_card(call, username)


@dp.callback_query(F.data.startswith("adm_ublk_"))
async def cb_admin_act_unblock(call: CallbackQuery):
    """Удаление пользователя из чёрного списка."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    username = call.data.replace("adm_ublk_", "", 1).strip()
    users = load_site_users()
    target_u = None
    for u in users:
        if (u.get("username") or "").strip().lower() == username.lower():
            u["is_blocked"] = False
            target_u = u
            break
    if target_u:
        save_site_users(users)
        remove_user_from_site_blacklist(username)
        if target_u.get("telegram_chat_id"):
            await set_user_status(target_u["telegram_chat_id"], "approved")
    else:
        try:
            if username.startswith("tg_"):
                tg_id = int(username.replace("tg_", ""))
                await set_user_status(tg_id, "approved")
                remove_user_from_site_blacklist(username)
        except Exception:
            pass

    await call.answer("✅ Пользователь убран из Чёрного списка!", show_alert=True)
    await show_user_detail_card(call, username)


@dp.callback_query(F.data.startswith("adm_cblk_"))
async def cb_admin_act_blockchat(call: CallbackQuery):
    """Блокировка отправки сообщений в чат для конкретного пользователя."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    username = call.data.replace("adm_cblk_", "", 1).strip()
    if username.lower() in ("skynet83", "skynet19081983"):
        await call.answer("Нельзя заблокировать чат администратора!", show_alert=True)
        return

    users = load_site_users()
    for u in users:
        if (u.get("username") or "").strip().lower() == username.lower():
            u["chat_blocked"] = True
            break
    save_site_users(users)

    await call.answer("🔇 Чат для пользователя заблокирован!", show_alert=True)
    await show_user_detail_card(call, username)


@dp.callback_query(F.data.startswith("adm_cublk_"))
async def cb_admin_act_unchat(call: CallbackQuery):
    """Разблокировка отправки сообщений в чат для пользователя."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    username = call.data.replace("adm_cublk_", "", 1).strip()
    users = load_site_users()
    for u in users:
        if (u.get("username") or "").strip().lower() == username.lower():
            u["chat_blocked"] = False
            break
    save_site_users(users)

    await call.answer("🔊 Чат для пользователя разблокирован!", show_alert=True)
    await show_user_detail_card(call, username)


@dp.callback_query(F.data.startswith("adm_msg_"))
async def cb_admin_act_write(call: CallbackQuery):
    """Инициализация написания сообщения конкретному пользователю."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    await call.answer()
    username = call.data.replace("adm_msg_", "", 1).strip()
    users = load_site_users()
    target_u = None
    for u in users:
        if (u.get("username") or "").strip().lower() == username.lower():
            target_u = u
            break

    tg_id = target_u.get("telegram_chat_id") if target_u else None
    if not tg_id and username.startswith("tg_"):
        try:
            tg_id = int(username.replace("tg_", ""))
        except Exception:
            pass

    tg_u = target_u.get("telegram_username") if target_u else None
    tg_handle = f"@{tg_u.lstrip('@')}" if tg_u else (f"ID: {tg_id}" if tg_id else "не привязан")

    admin_waiting_reply_to[call.from_user.id] = {
        "username": username,
        "chat_id": tg_id,
        "name": target_u.get("name") if target_u else username,
        "tg_handle": tg_handle
    }

    await call.message.answer(
        f"✉️ <b>Диалог с пользователем: <code>{html.escape(username)}</code></b>\n\n"
        f"📱 Привязанный TG: <code>{html.escape(tg_handle)}</code>\n\n"
        f"<i>Напишите ваше сообщение (например, ключ активации, уведомление или ответ на вопрос).\n"
        f"Оно отобразится в чате на сайте и будет отправлено пользователю в Telegram.\n"
        f"Для отмены отправьте /cancel.</i>",
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("adm_trf_"))
async def cb_admin_act_tariff(call: CallbackQuery):
    """Меню управления тарифом пользователя."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    username = call.data.replace("adm_trf_", "", 1).strip()
    users = load_site_users()
    target_u = None
    for u in users:
        if (u.get("username") or "").strip().lower() == username.lower():
            target_u = u
            break

    if not target_u:
        await call.answer("Пользователь не найден в users.json.", show_alert=True)
        return

    perms = target_u.get("permissions") or {}
    exp_str = perms.get("avito_expires_at") or "не задан"
    dur = perms.get("avito_duration", "expired")

    text = (
        f"🔑 <b>Управление тарифом: <code>{html.escape(username)}</code></b>\n\n"
        f"📦 Текущий тариф: <b>{dur}</b>\n"
        f"⏳ Срок действия: <b>{exp_str}</b>\n\n"
        f"<i>Выберите действие для изменения тарифного плана пользователя:</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Продлить на 30 дней", callback_data=f"adm_tset_30d_{username}")],
        [InlineKeyboardButton(text="👑 Выдать VIP Безлимит", callback_data=f"adm_tset_vip_{username}")],
        [InlineKeyboardButton(text="🎁 Выдать Триал (3 дня)", callback_data=f"adm_tset_trial3_{username}")],
        [InlineKeyboardButton(text="⛔️ Сбросить / Завершить тариф", callback_data=f"adm_tset_expire_{username}")],
        [InlineKeyboardButton(text="⬅️ Назад к карточке", callback_data=f"adm_usr_{username}")]
    ])

    await call.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    await call.answer()


@dp.callback_query(F.data.startswith("adm_tset_"))
async def cb_admin_set_tariff(call: CallbackQuery):
    """Применение выбранного тарифа к пользователю."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return

    parts = call.data.split("_", 3)
    tier = parts[2]
    username = parts[3]

    users = load_site_users()
    target_u = None
    for u in users:
        if (u.get("username") or "").strip().lower() == username.lower():
            target_u = u
            break

    if not target_u:
        await call.answer("Пользователь не найден.", show_alert=True)
        return

    perms = target_u.setdefault("permissions", {})
    now = datetime.now()

    if tier == "30d":
        curr_exp = perms.get("avito_expires_at")
        base_dt = now
        if curr_exp:
            try:
                c_dt = datetime.strptime(curr_exp, "%Y-%m-%d %H:%M:%S")
                if c_dt > now:
                    base_dt = c_dt
            except Exception:
                base_dt = now
        new_exp = (base_dt + timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")
        perms["avito"] = True
        perms["avito_bot"] = True
        perms["monitoring"] = True
        perms["is_expired"] = False
        perms["avito_duration"] = "30_days"
        perms["avito_expires_at"] = new_exp
        perms["active_key"] = "ADMIN_PROLONG_30D"
        alert_text = f"✅ Тариф {username} продлен на 30 дней (до {new_exp})!"
    elif tier == "vip":
        perms["avito"] = True
        perms["avito_bot"] = True
        perms["monitoring"] = True
        perms["is_expired"] = False
        perms["avito_duration"] = "unlimited"
        perms["avito_expires_at"] = None
        perms["active_key"] = "ADMIN_VIP_UNLIMITED"
        alert_text = f"👑 Пользователю {username} выдан VIP Безлимит навсегда!"
    elif tier == "trial3":
        new_exp = (now + timedelta(days=3)).strftime("%Y-%m-%d %H:%M:%S")
        perms["avito"] = True
        perms["avito_bot"] = True
        perms["monitoring"] = True
        perms["is_expired"] = False
        perms["avito_duration"] = "trial_3_days"
        perms["avito_expires_at"] = new_exp
        perms["active_key"] = "ADMIN_TRIAL_3D"
        alert_text = f"🎁 Пользователю {username} выдан триал на 3 дня (до {new_exp})!"
    elif tier == "expire":
        perms["is_expired"] = True
        perms["avito_duration"] = "expired"
        perms["monitoring"] = False
        perms["active_key"] = None
        alert_text = f"⛔️ Тариф пользователя {username} сброшен (истек)!"
    else:
        alert_text = "Неизвестный тариф."

    save_site_users(users)
    await call.answer(alert_text, show_alert=True)
    await show_user_detail_card(call, username)


@dp.callback_query(F.data.startswith("adm_src_"))
async def cb_admin_act_srch(call: CallbackQuery):
    """Просмотр поисковых ссылок выбранного пользователя."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    username = call.data.replace("adm_src_", "", 1).strip()
    users = load_site_users()
    target_u = None
    for u in users:
        if (u.get("username") or "").strip().lower() == username.lower():
            target_u = u
            break

    urls = target_u.get("avito_searches") or [] if target_u else []
    if not urls and target_u and target_u.get("telegram_chat_id"):
        urls = await get_user_tracked_urls(target_u["telegram_chat_id"])
    elif not urls and username.startswith("tg_"):
        try:
            tg_id = int(username.replace("tg_", ""))
            urls = await get_user_tracked_urls(tg_id)
        except Exception:
            pass

    if not urls:
        await call.answer("У этого пользователя нет добавленных поисковых ссылок.", show_alert=True)
        return

    lines = [f"🔎 <b>Поисковые ссылки пользователя <code>{html.escape(username)}</code> ({len(urls)} шт.):</b>\n"]
    for idx, u in enumerate(urls, 1):
        s_id = u.get("id") or idx
        s_name = u.get("name") or "Поиск"
        s_url = u.get("url") or ""
        s_act = "🟢 Активен" if u.get("is_active", 1) else "⏸ Пауза"
        lines.append(
            f"<b>[{s_id}]</b> {html.escape(s_name)} ({s_act})\n"
            f"🔗 <a href='{s_url}'>Открыть на Avito</a>\n"
        )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Назад к карточке", callback_data=f"adm_usr_{username}")]
    ])

    await call.message.edit_text("\n".join(lines), reply_markup=kb, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    await call.answer()


@dp.callback_query(F.data.startswith("adm_del_"))
async def cb_admin_act_del(call: CallbackQuery):
    """Полное удаление пользователя из системы."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    username = call.data.replace("adm_del_", "", 1).strip()
    if username.lower() in ("skynet83", "skynet19081983"):
        await call.answer("Нельзя удалить главного администратора!", show_alert=True)
        return

    users = load_site_users()
    new_users = []
    tg_id_to_clean = None
    for u in users:
        if (u.get("username") or "").strip().lower() == username.lower():
            tg_id_to_clean = u.get("telegram_chat_id")
        else:
            new_users.append(u)

    save_site_users(new_users)
    remove_user_from_site_blacklist(username)

    if not tg_id_to_clean and username.startswith("tg_"):
        try:
            tg_id_to_clean = int(username.replace("tg_", ""))
        except Exception:
            pass

    if tg_id_to_clean:
        try:
            await delete_user_and_clean_data(tg_id_to_clean)
        except Exception:
            pass

    await call.answer(f"🗑 Пользователь {username} успешно удален!", show_alert=True)
    await show_users_control_panel(call)


@dp.callback_query(F.data == "adm_bl_add")
async def cb_admin_manual_block_prompt(call: CallbackQuery):
    """Запрос ввода пользователя для добавления в чёрный список вручную."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    await call.answer()
    admin_waiting_manual_block.add(call.from_user.id)
    await call.message.answer(
        "🚫 <b>Добавление в чёрный список вручную</b>\n\n"
        "Отправьте <b>логин пользователя на сайте</b>, <b>Telegram @username</b> или <b>числовой Telegram ID</b>.\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        parse_mode=ParseMode.HTML
    )


@dp.message(lambda msg: msg.from_user and msg.from_user.id in admin_waiting_manual_block and not (msg.text and msg.text.startswith("/")))
async def handle_admin_manual_block_input(message: types.Message):
    """Принимает логин / tg_id для добавления в чёрный список вручную."""
    admin_id = message.from_user.id
    if admin_id in admin_waiting_manual_block:
        admin_waiting_manual_block.remove(admin_id)

    raw_input = (message.text or "").strip()
    if not raw_input:
        await message.answer("⚠️ Значение не может быть пустым.")
        return

    clean_target = raw_input.lstrip("@").strip()
    if clean_target.lower() in ("skynet83", "skynet19081983"):
        await message.answer("❌ Нельзя добавить в чёрный список главного администратора!")
        return

    users = load_site_users()
    matched_u = None
    for u in users:
        u_name = (u.get("username") or "").strip().lower()
        t_name = (u.get("telegram_username") or "").strip().lstrip("@").lower()
        t_id = str(u.get("telegram_chat_id") or "").strip()
        if clean_target.lower() in (u_name, t_name) or clean_target == t_id:
            u["is_blocked"] = True
            u["session_token"] = ""
            matched_u = u
            break

    if matched_u:
        save_site_users(users)
        uname = matched_u.get("username")
        add_user_to_site_blacklist(uname, ip=matched_u.get("last_ip"), mac=matched_u.get("last_mac"))
        if matched_u.get("telegram_chat_id"):
            await set_user_status(matched_u["telegram_chat_id"], "blocked")
        await message.answer(
            f"✅ Пользователь <b>{html.escape(uname)}</b> успешно добавлен в чёрный список!",
            parse_mode=ParseMode.HTML
        )
    else:
        add_user_to_site_blacklist(clean_target)
        if clean_target.isdigit():
            await set_user_status(int(clean_target), "blocked")
        await message.answer(
            f"✅ Идентификатор <b>{html.escape(clean_target)}</b> добавлен в чёрный список!",
            parse_mode=ParseMode.HTML
        )


@dp.callback_query(F.data.startswith("adm_usr_srch_"))
async def cb_admin_user_searches(call: CallbackQuery):
    """Обработчик нажатия на инлайн-кнопку клиента: моментально показывает его поиски без ввода команд."""
    if not await is_admin(call.from_user.id):
        await call.answer("Доступно только администратору!", show_alert=True)
        return

    target_id = int(call.data.replace("adm_usr_srch_", "", 1))
    urls = await get_user_tracked_urls(target_id)
    if not urls:
        await call.answer("У этого пользователя пока нет добавленных ссылок.", show_alert=True)
        return

    lines = [f"🔎 <b>Поисковые ссылки клиента <code>{target_id}</code> ({len(urls)} шт.):</b>\n"]
    for u in urls:
        lines.append(
            f"<b>[{u['id']}]</b> {u['name']}\n"
            f"🔗 <a href='{u['url']}'>Открыть на Avito</a>\n"
        )

    await call.message.answer("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)
    await call.answer()


@dp.message(Command("user_searches"))
async def cmd_user_searches(message: types.Message):
    """Просмотр администратором поисковых ссылок конкретного пользователя по команде."""
    if not await is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Укажите ID пользователя. Пример:\n<code>/user_searches 123456789</code>", parse_mode=ParseMode.HTML)
        return

    target_id = int(args[1])
    urls = await get_user_tracked_urls(target_id)
    if not urls:
        await message.answer(f"ℹ️ У пользователя <code>{target_id}</code> нет активных поисковых ссылок.", parse_mode=ParseMode.HTML)
        return

    lines = [f"🔍 <b>Поисковые ссылки пользователя <code>{target_id}</code> ({len(urls)} шт.):</b>\n"]
    for u in urls:
        lines.append(
            f"<b>[{u['id']}]</b> {u['name']}\n"
            f"🔗 <a href='{u['url']}'>Перейти на Avito</a>\n"
        )
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@dp.message(Command("approve"))
async def cmd_approve(message: types.Message, bot: Bot):
    if not await is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Укажите ID пользователя. Пример:\n<code>/approve 123456789</code>", parse_mode=ParseMode.HTML)
        return

    target_id = int(args[1])
    await set_user_status(target_id, "approved")
    await message.answer(f"✅ Доступ для пользователя <code>{target_id}</code> успешно <b>разрешен</b>!", parse_mode=ParseMode.HTML)

    try:
        await bot.send_message(
            chat_id=target_id,
            text=(
                "🎉 <b>Администратор одобрил вашу заявку!</b>\n\n"
                "Для вас открыта персональная сессия. Чтобы добавить поиск, используйте:\n"
                "<code>/add &lt;ссылка на Avito&gt; [название]</code>\n"
                "Посмотреть свои поиски: /list"
            ),
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass


@dp.message(Command("block"))
async def cmd_block(message: types.Message, bot: Bot):
    """Блокировка доступа клиенту (без удаления его настроек)."""
    if not await is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Укажите ID пользователя. Пример:\n<code>/block 123456789</code>", parse_mode=ParseMode.HTML)
        return

    target_id = int(args[1])
    await set_user_status(target_id, "rejected")
    await message.answer(f"⛔️ Доступ для пользователя <code>{target_id}</code> <b>заблокирован</b>.", parse_mode=ParseMode.HTML)

    try:
        await bot.send_message(
            chat_id=target_id,
            text="⛔️ <b>Ваш доступ к сервису мониторинга был приостановлен администратором.</b>",
            parse_mode=ParseMode.HTML
        )
    except Exception:
        pass


@dp.message(Command("delete_user"))
@dp.message(Command("del_user"))
async def cmd_delete_client(message: types.Message, bot: Bot):
    """Полное удаление клиента с очисткой всех его поисков, истории объявлений и сжатием базы SQLite."""
    if not await is_admin(message.from_user.id):
        return

    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer(
            "⚠️ Укажите ID пользователя для полного удаления.\n"
            "Пример: <code>/del_user 123456789</code>",
            parse_mode=ParseMode.HTML
        )
        return

    target_id = int(args[1])
    if await is_admin(target_id):
        await message.answer("❌ Нельзя удалить главного администратора!", parse_mode=ParseMode.HTML)
        return

    res = await delete_user_and_clean_data(target_id)
    if res["deleted_users"] > 0 or res["deleted_seen"] > 0 or res["deleted_urls"] > 0:
        await message.answer(
            f"🗑 <b>Клиент <code>{target_id}</code> полностью удален!</b>\n\n"
            f"🧹 Очищено ссылок поиска: <b>{res['deleted_urls']}</b>\n"
            f"📦 Удалено записей объявлений: <b>{res['deleted_seen']}</b>\n"
            f"💾 Выполнена оптимизация SQLite (VACUUM): свободное место на диске возвращено!",
            parse_mode=ParseMode.HTML
        )
        try:
            await bot.send_message(
                chat_id=target_id,
                text="ℹ️ <b>Ваш аккаунт и все сохраненные данные поиска были удалены администратором.</b>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    else:
        await message.answer(f"❌ Пользователь с ID <code>{target_id}</code> не найден в базе данных.", parse_mode=ParseMode.HTML)


@dp.callback_query(F.data.startswith("user_app_") | F.data.startswith("user_rej_"))
async def cb_user_action(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        await call.answer("Только администратор может подтверждать заявки!", show_alert=True)
        return

    action, uid_str = call.data.split("_")[1], call.data.split("_")[2]
    target_id = int(uid_str)

    if action == "app":
        await set_user_status(target_id, "approved")
        await call.message.edit_text(
            f"{call.message.text}\n\n✅ <b>Доступ РАЗРЕШЕН</b>",
            parse_mode=ParseMode.HTML
        )
        try:
            await bot.send_message(
                chat_id=target_id,
                text=(
                    "🎉 <b>Ваша заявка одобрена!</b>\n"
                    "Для вас открыта личная сессия поиска.\n"
                    "Добавьте свои поиски командой: <code>/add &lt;ссылка&gt; [название]</code>"
                ),
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass
    else:
        await set_user_status(target_id, "rejected")
        await call.message.edit_text(
            f"{call.message.text}\n\n❌ <b>Доступ ЗАПРЕЩЕН</b>",
            parse_mode=ParseMode.HTML
        )
        try:
            await bot.send_message(
                chat_id=target_id,
                text="⛔️ <b>Заявка отклонена администратором.</b>",
                parse_mode=ParseMode.HTML
            )
        except Exception:
            pass

    await call.answer()


# ===================== ИЗБРАННОЕ И КНОПКИ МЕНЮ =====================

@dp.callback_query(F.data.startswith("fav_add_"))
async def cb_fav_add(call: CallbackQuery):
    """Добавление объявления в избранное по инлайн-кнопке."""
    item_id = call.data.replace("fav_add_", "", 1)
    user_id = call.from_user.id

    title = "Объявление с Avito"
    price = "Цена"
    url = f"https://www.avito.ru/{item_id}"

    # Пытаемся извлечь название и цену из текста сообщения
    if call.message and call.message.caption:
        lines = call.message.caption.split("\n")
        for line in lines:
            if line.startswith("🏷 "):
                title = line.replace("🏷 ", "").strip()
            elif line.startswith("💰 "):
                price = line.replace("💰 ", "").strip()

    ok = await add_favorite(user_id, item_id, title, price, url)
    if ok:
        await call.answer("⭐ Товар добавлен в ваше 'Избранное'!", show_alert=False)
    else:
        await call.answer("Уже в избранном или ошибка.", show_alert=False)


@dp.message(Command("fav"))
@dp.message(F.text == "⭐ Избранное")
async def cmd_favorites(message: types.Message):
    """Просмотр списка избранных товаров."""
    user_id = message.from_user.id
    if not await check_auth_or_prompt(message):
        return

    admin = is_admin(user_id)
    if admin and message.text == "⭐ Избранное":
        silent = await is_silent_mode(user_id)
        await message.answer(
            "ℹ️ Кнопка «Избранное» убрана из меню администратора.",
            reply_markup=get_main_keyboard(is_user_admin=True, is_silent=silent),
            parse_mode=ParseMode.HTML
        )
        return

    text = (message.text or "").strip()
    args = text.split(maxsplit=1)
    if len(args) > 1 and args[0].lower().startswith("/fav"):
        raw_val = args[1].strip()
        m_id = re.search(r'(\d{8,15})', raw_val)
        if m_id:
            item_id = m_id.group(1)
            target_url = raw_val if raw_val.startswith("http") else f"https://www.avito.ru/{item_id}"
            ok = await add_favorite(user_id, item_id, f"Товар {item_id}", "Цена не указана", target_url)
            if ok:
                await message.answer(f"⭐ <b>Товар {item_id} добавлен в ваше избранное!</b>", parse_mode=ParseMode.HTML)
                return
            else:
                await message.answer(f"ℹ️ Товар {item_id} уже сохранен в вашем избранном.", parse_mode=ParseMode.HTML)
                return

    favs = await get_user_favorites(user_id)
    if not favs:
        await message.answer(
            "⭐ <b>Ваш список избранного пуст.</b>\n\n"
            "Чтобы добавить объявление в избранное, отправьте команду:\n"
            "<code>/fav &lt;ID товара или ссылка на Avito&gt;</code>",
            parse_mode=ParseMode.HTML
        )
        return

    lines = [f"⭐ <b>Ваши избранные объявления ({len(favs)}):</b>\n"]
    for idx, f_item in enumerate(favs, 1):
        lines.append(
            f"<b>{idx}.</b> <a href='{f_item['url']}'>{f_item['title']}</a>\n"
            f"💰 {f_item['price']} (ID: <code>{f_item['item_id']}</code>)\n"
        )
    lines.append("<i>Чтобы удалить из избранного:</i> <code>/del_fav &lt;ID&gt;</code>")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@dp.message(Command("del_fav"))
async def cmd_del_favorite(message: types.Message):
    """Удаление товара из избранного."""
    user_id = message.from_user.id
    if not await check_auth_or_prompt(message):
        return

    args = message.text.split()
    if len(args) < 2:
        await message.answer("⚠️ Укажите ID товара. Пример:\n<code>/del_fav 123456789</code>", parse_mode=ParseMode.HTML)
        return

    item_id = args[1].strip()
    removed = await remove_favorite(user_id, item_id)
    if removed:
        await message.answer(f"🗑 Товар <code>{item_id}</code> удален из избранного.", parse_mode=ParseMode.HTML)
    else:
        await message.answer(f"❌ Товар с ID <code>{item_id}</code> не найден в вашем избранном.", parse_mode=ParseMode.HTML)


# ===================== ЧЕРНЫЙ СПИСОК (BLACKLIST) =====================

@dp.callback_query(F.data.startswith("bl_add_"))
async def cb_blacklist_add(call: CallbackQuery):
    """Добавление продавца в черный список по инлайн-кнопке."""
    item_id = call.data.replace("bl_add_", "", 1)
    user_id = call.from_user.id

    seller_name = ad_sellers_cache.get(item_id)
    if not seller_name:
        # Пробуем вытащить из текста сообщения
        if call.message and (call.message.caption or call.message.text):
            content = call.message.caption or call.message.text
            for line in content.split("\n"):
                if "👤 <b>Продавец:</b>" in line:
                    clean = re.sub(r"<[^>]+>", "", line).replace("👤 Продавец:", "").strip()
                    # Убираем суффикс типа "(Частное лицо)"
                    clean = re.sub(r"\(.*?\)", "", clean).strip()
                    if clean:
                        seller_name = clean
                    break

    if not seller_name:
        await call.answer("Не удалось определить имя продавца.", show_alert=True)
        return

    ok = await add_to_blacklist(user_id, seller_name)
    if ok:
        await call.answer(f"🚫 Продавец '{seller_name}' добавлен в ЧС! Вы больше не увидите его объявлений.", show_alert=True)
    else:
        await call.answer(f"Продавец '{seller_name}' уже находится в вашем ЧС.", show_alert=True)


@dp.message(Command("blacklist"))
@dp.message(Command("bl"))
async def cmd_blacklist(message: types.Message):
    """Просмотр черного списка продавцов."""
    user_id = message.from_user.id
    if not await check_auth_or_prompt(message):
        return

    bl = await get_user_blacklist(user_id)
    if not bl:
        await message.answer(
            "📋 <b>Ваш черный список продавцов пуст.</b>\n\n"
            "Чтобы заблокировать продавца, нажмите кнопку <i>'🚫 Отправить в ЧС'</i> под его объявлением.",
            parse_mode=ParseMode.HTML
        )
        return

    lines = [f"🚫 <b>Черный список продавцов ({len(bl)}):</b>\n"]
    for idx, s_name in enumerate(bl, 1):
        lines.append(f"<b>{idx}.</b> {s_name}")
    lines.append("\n<i>Чтобы разблокировать:</i> <code>/unblock &lt;имя продавца&gt;</code>")
    await message.answer("\n".join(lines), parse_mode=ParseMode.HTML)


@dp.message(Command("unblock"))
async def cmd_unblock(message: types.Message):
    """Удаление продавца из черного списка."""
    user_id = message.from_user.id
    if not await check_auth_or_prompt(message):
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.answer("⚠️ Укажите имя продавца. Пример:\n<code>/unblock Иван</code>", parse_mode=ParseMode.HTML)
        return

    name = args[1].strip()
    removed = await remove_from_blacklist(user_id, name)
    if removed:
        await message.answer(f"✅ Продавец <b>{name}</b> удален из черного списка.", parse_mode=ParseMode.HTML)
    else:
        await message.answer(f"❌ Продавец <b>{name}</b> не найден в вашем черном списке.", parse_mode=ParseMode.HTML)


# ===================== ТИХИЙ РЕЖИМ (ЗВУК / MUTE) =====================

@dp.message(Command("mute"))
@dp.message(F.text.startswith("🔔 Звук:"))
@dp.message(F.text.startswith("🔕 Звук:"))
@dp.message(F.text.in_(["🔔 Звук", "🔕 Звук"]))
async def btn_toggle_sound(message: types.Message):
    """Переключение тихого режима уведомлений (со звуком / без звука)."""
    user_id = message.from_user.id
    username = message.from_user.username
    if not await is_authorized(user_id, username):
        return

    is_silent = await toggle_silent_mode(user_id)
    admin_flag = await is_admin(user_id, username)
    new_kb = get_main_keyboard(is_user_admin=admin_flag, is_silent=is_silent, user_id=user_id, username=username)

    if is_silent:
        await message.answer(
            "🔕 <b>Тихий режим включен!</b>\n\n"
            "Все новые уведомления теперь приходят без звука и вибрации.",
            reply_markup=new_kb,
            parse_mode=ParseMode.HTML
        )
    else:
        await message.answer(
            "🔔 <b>Звуковой режим включен!</b>\n\n"
            "Новые уведомления будут приходить со стандартным звуком.",
            reply_markup=new_kb,
            parse_mode=ParseMode.HTML
        )


# ===================== ДОБАВЛЕНИЕ СВОИХ ПРОКСИ =====================

@dp.message(F.text == "/cancel")
@dp.message(Command("cancel"))
async def cmd_cancel_proxy_wait(message: types.Message):
    user_id = message.from_user.id
    cancelled = False
    if user_id in admin_waiting_proxy:
        admin_waiting_proxy.remove(user_id)
        cancelled = True
    if user_waiting_feedback.get(user_id):
        user_waiting_feedback.pop(user_id, None)
        cancelled = True
    if user_waiting_auth_login.get(user_id):
        user_waiting_auth_login.pop(user_id, None)
        cancelled = True
    if user_waiting_auth_pass.get(user_id):
        user_waiting_auth_pass.pop(user_id, None)
        cancelled = True
    if user_waiting_add_search.get(user_id):
        user_waiting_add_search.pop(user_id, None)
        cancelled = True
    if user_waiting_activation.get(user_id):
        user_waiting_activation.pop(user_id, None)
        cancelled = True
    if user_id in admin_waiting_keygen:
        admin_waiting_keygen.pop(user_id, None)
        cancelled = True
    if user_id in admin_waiting_reply_to:
        admin_waiting_reply_to.pop(user_id, None)
        cancelled = True
    if user_id in admin_waiting_manual_block:
        admin_waiting_manual_block.remove(user_id)
        cancelled = True

    site_u = get_site_user_by_tg_id(user_id, message.from_user.username)
    is_adm = await is_admin(user_id, message.from_user.username)
    kb = get_main_keyboard(is_user_admin=is_adm) if (site_u or is_adm) else ReplyKeyboardRemove()

    if cancelled:
        await message.answer("❌ Действие отменено.", reply_markup=kb)
    else:
        await message.answer("Нет активных действий для отмены.", reply_markup=kb)


@dp.message(lambda msg: msg.from_user and user_waiting_auth_login.get(msg.from_user.id) and not (msg.text and msg.text.startswith("/")))
async def handle_auth_login_input(message: types.Message):
    """Принимает логин от сайта при авторизации."""
    user_id = message.from_user.id
    raw_login = (message.text or "").strip()
    if not raw_login:
        await message.answer("⚠️ Логин не может быть пустым. Пожалуйста, введите логин:")
        return

    target_user = get_site_user_by_username(raw_login)
    if not target_user:
        await message.answer(
            f"❌ Пользователь с логином <code>{html.escape(raw_login)}</code> не найден на сайте <b>SkyBase</b>.\n\n"
            f"Пожалуйста, проверьте логин и попробуйте снова, или отправьте /cancel для отмены.",
            parse_mode=ParseMode.HTML
        )
        return

    user_waiting_auth_login.pop(user_id, None)
    user_waiting_auth_pass[user_id] = target_user.get("username")
    user_display = target_user.get("name") or target_user.get("username")
    await message.answer(
        f"👤 Пользователь <b>{html.escape(user_display)}</b> найден!\n\n"
        f"🔑 Теперь введите ваш <b>пароль</b> от учетной записи на сайте:\n"
        f"<i>(Сообщение с паролем будет сразу удалено ботом для безопасности)</i>",
        parse_mode=ParseMode.HTML
    )


@dp.message(lambda msg: msg.from_user and user_waiting_auth_pass.get(msg.from_user.id) and not (msg.text and msg.text.startswith("/")))
async def handle_auth_password_input(message: types.Message, bot: Bot):
    """Принимает пароль от сайта, проверяет хэш и привязывает аккаунт к сайту."""
    user_id = message.from_user.id
    target_username = user_waiting_auth_pass.get(user_id)
    plain_password = message.text or ""

    # Немедленно удаляем сообщение с паролем из чата для безопасности
    try:
        await message.delete()
    except Exception:
        pass

    target_user = get_site_user_by_username(target_username)
    if not target_user:
        user_waiting_auth_pass.pop(user_id, None)
        await message.answer("⚠️ Ошибка: пользователь не найден. Введите /login для повторного входа.")
        return

    stored_hash = target_user.get("password") or ""
    if not verify_site_password(plain_password, stored_hash):
        await message.answer(
            "❌ <b>Неверный пароль!</b>\n\n"
            "Пожалуйста, попробуйте ввести пароль еще раз, или отправьте /cancel для отмены.",
            parse_mode=ParseMode.HTML
        )
        return

    # Авторизация успешна!
    user_waiting_auth_pass.pop(user_id, None)
    is_adm = (target_user.get("role") == "admin" or target_username.lower() in ("skynet83", "admin"))
    users = load_site_users()
    for u in users:
        # Если данный telegram_chat_id был привязан к кому-то другому (и это не другое устройство админа), сбрасываем
        if not is_adm and u.get("role") != "admin":
            if u.get("telegram_chat_id") is not None and str(u.get("telegram_chat_id")).strip() == str(user_id).strip():
                u["telegram_chat_id"] = None
                u["telegram_username"] = None
        if (u.get("username") or "").strip().lower() == target_username.lower():
            u["telegram_chat_id"] = user_id
            u["telegram_username"] = message.from_user.username or ""
            target_user = u
    save_site_users(users)

    is_adm = (target_user.get("role") == "admin" or target_username.lower() == "skynet83")
    target_status = "admin" if is_adm else "approved"
    if is_adm:
        global primary_admin_id
        primary_admin_id = user_id

    await register_or_update_user(
        user_id,
        message.from_user.username,
        target_user.get("name") or target_username,
        status=target_status
    )

    # Немедленно синхронизируем персональные поиски пользователя в базу SQLite
    try:
        sys.path.insert(0, os.path.dirname(BOT_DIR))
        import avito_api_helper
        avito_api_helper.sync_users_searches_to_db()
    except Exception as e:
        logger.error(f"Ошибка синхронизации ссылок после авторизации: {e}")

    # Запускаем первичное сохранение объявлений без лишнего шума
    asyncio.create_task(check_all_active_searches(bot, initial_seed_user=user_id))

    user_display = target_user.get("name") or target_username
    await message.answer(
        f"✅ <b>Авторизация успешна!</b>\n\n"
        f"Добро пожаловать, <b>{html.escape(user_display)}</b>!\n"
        f"Ваш профиль Telegram успешно связан с аккаунтом на сайте <b>SkyBase</b>.",
        parse_mode=ParseMode.HTML
    )
    await show_welcome_panel(message, target_user, user_id, message.from_user.username, message.from_user.full_name)

@dp.message(lambda msg: msg.from_user and user_waiting_feedback.get(msg.from_user.id) and not (msg.text and msg.text.startswith("/")))
async def handle_user_feedback_input(message: types.Message, bot: Bot):
    """Принимает сообщение для администратора, сохраняет в чат на сайте и отправляет в TG администратору."""
    user_id = message.from_user.id
    user_waiting_feedback.pop(user_id, None)
    text = (message.text or "").strip()
    if not text:
        await message.answer("⚠️ Сообщение не может быть пустым.")
        return

    site_u = get_site_user_by_tg_id(user_id, message.from_user.username)
    if site_u and (site_u.get("chat_blocked") or site_u.get("is_blocked")):
        await message.answer("⛔️ <b>Ваш доступ к чату заблокирован администратором (Чёрный список).</b>", parse_mode=ParseMode.HTML)
        return

    login = site_u.get("username") if site_u else f"tg_{user_id}"
    sender_name = site_u.get("name") or login
    tg_nick = f"@{message.from_user.username.lstrip('@')}" if message.from_user.username else f"ID: {user_id}"

    new_msg = append_chat_message(
        sender=login,
        sender_name=sender_name,
        recipient="admin",
        text=text,
        extra={
            "sender_tg_id": user_id,
            "sender_tg_username": message.from_user.username,
            "tg_user_msg_id": message.message_id
        }
    )

    admin_id = primary_admin_id or ADMIN_CHAT_ID
    if admin_id and admin_id != user_id:
        try:
            adm_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✉️ Ответить", callback_data=f"admin_reply_user_{login}"),
                    InlineKeyboardButton(text="✅ Прочитано", callback_data=f"chat_read_{new_msg['id']}")
                ]
            ])
            adm_m = await bot.send_message(
                chat_id=admin_id,
                text=(
                    f"💬 <b>Новое сообщение от пользователя!</b>\n\n"
                    f"👤 <b>Логин:</b> <code>{html.escape(login)}</code>\n"
                    f"📱 <b>Telegram:</b> <code>{html.escape(tg_nick)}</code>\n"
                    f"🕒 <b>Время:</b> {new_msg['created_at']}\n\n"
                    f"📝 <i>{html.escape(text)}</i>"
                ),
                reply_markup=adm_kb,
                parse_mode=ParseMode.HTML
            )
            all_msgs = load_chat_messages()
            for m in all_msgs:
                if str(m.get("id")) == str(new_msg["id"]):
                    m["admin_tg_notified"] = True
                    m["admin_tg_msg_id"] = adm_m.message_id
                    m["admin_tg_chat_id"] = admin_id
                    break
            save_chat_messages(all_msgs)
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление админу в TG ({admin_id}): {e}")

    await message.answer(
        "✅ <b>Ваше сообщение успешно отправлено!</b>\n"
        "<i>Оно появилось в чате на сайте и передано администратору в Telegram.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(is_user_admin=False)
    )


# ===================== КНОПКИ АВТОРИЗАЦИИ И ССЫЛОК ДЛЯ ГОСТЕЙ =====================

@dp.callback_query(F.data == "auth_login_start")
async def cb_auth_login_start(call: types.CallbackQuery):
    """Инлайн-кнопка для начала авторизации по логину и паролю."""
    await call.answer()
    user_id = call.from_user.id
    user_waiting_auth_login[user_id] = True
    user_waiting_auth_pass.pop(user_id, None)
    await call.message.answer(
        "🔐 <b>Вход в систему SkyBase</b>\n\n"
        "Введите ваш <b>логин</b> от сайта:\n"
        "<i>(Отправьте /cancel для отмены)</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


@dp.message(F.text == "🔐 Войти по логину")
async def btn_auth_login_text(message: types.Message):
    """Реплай-кнопка для быстрого входа."""
    user_id = message.from_user.id
    user_waiting_auth_login[user_id] = True
    user_waiting_auth_pass.pop(user_id, None)
    await message.answer(
        "🔐 <b>Вход в систему SkyBase</b>\n\n"
        "Введите ваш <b>логин</b> от сайта:\n"
        "<i>(Отправьте /cancel для отмены)</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ReplyKeyboardRemove()
    )


@dp.callback_query(F.data == "auth_help_howto")
async def cb_auth_help_howto(call: types.CallbackQuery):
    """Инлайн-кнопка с инструкцией как привязать TG без ввода пароля."""
    await call.answer()
    site_url = get_site_url()
    username_hint = f"@{call.from_user.username}" if call.from_user.username else f"ID: <code>{call.from_user.id}</code>"
    text = (
        "💡 <b>Как привязать Telegram к сайту без ввода пароля:</b>\n\n"
        f"1. Откройте сайт SkyBase в браузере: <a href=\"{site_url}/\">{site_url}</a>\n"
        "2. Войдите в свой аккаунт на сайте под своим логином.\n"
        "3. Вверху в строке переключателей рядом с кнопкой <b>«📱 Бот»</b> найдите поле <b>«✈️ Ваш @username или ID»</b>.\n"
        f"4. Введите туда: <b>{username_hint}</b> и нажмите кнопку <b>«Привязать»</b>.\n\n"
        "🎉 <b>Готово!</b> Бот сразу распознает вас, обновит команды и начнет присылать уведомления!"
    )
    await call.message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@dp.message(F.text == "❓ Как привязать к сайту")
async def btn_auth_help_text(message: types.Message):
    """Реплай-кнопка с инструкцией."""
    site_url = get_site_url()
    username_hint = f"@{message.from_user.username}" if message.from_user.username else f"ID: <code>{message.from_user.id}</code>"
    text = (
        "💡 <b>Как привязать Telegram к SkyBase:</b>\n\n"
        f"1. Откройте программу SkyBase в браузере на вашем ПК: <a href=\"{site_url}/\">{site_url}</a>\n"
        "2. Вверху в строке переключателей рядом с кнопкой <b>«📱 Бот»</b> найдите поле <b>«✈️ Ваш @username или ID»</b>.\n"
        f"3. Введите туда: <b>{username_hint}</b> и нажмите кнопку <b>«Привязать»</b>.\n\n"
        "🎉 <b>Готово!</b> Бот свяжется с вашей локальной программой по уникальному ID и начнет присылать персональные уведомления!"
    )
    await message.answer(text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@dp.message(Command("site"))
@dp.message(Command("link"))
async def cmd_site(message: types.Message):
    """Команда для получения ссылки на сайт."""
    site_url = get_site_url()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🌐 Открыть SkyBase", url=f"{site_url}/")]
    ])
    await message.answer(
        f"🌐 <b>Программа SkyBase:</b> <a href=\"{site_url}/\">{site_url}</a>\n\n"
        "Перейдите по ссылке для работы с базой товаров и мониторингом в браузере.",
        reply_markup=kb,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True
    )


@dp.message(lambda msg: msg.from_user and msg.from_user.id in admin_waiting_proxy and not (msg.text and msg.text.startswith("/")))
async def handle_custom_proxy_input(message: types.Message):
    """Принимает прокси от администратора, тестирует их и сохраняет живые."""
    user_id = message.from_user.id
    if user_id in admin_waiting_proxy:
        admin_waiting_proxy.remove(user_id)

    raw_text = message.text.strip()
    lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
    
    candidates = []
    for line in lines:
        if ":" in line:
            if not line.startswith("http://") and not line.startswith("https://") and not line.startswith("socks5://"):
                line = f"http://{line}"
            candidates.append(line)

    if not candidates:
        await message.answer("⚠️ Не удалось распознать формат прокси. Пример: <code>185.220.101.5:8080</code>", parse_mode=ParseMode.HTML)
        return

    wait_msg = await message.answer(f"⏳ Проверяю {len(candidates)} прокси на доступ к Avito...")

    tasks = [parser.proxy_pool.check_proxy_alive(p, timeout=5) for p in candidates]
    results = await asyncio.gather(*tasks)

    added = 0
    failed = 0
    parser.proxy_pool.reload()
    for p, ok in zip(candidates, results):
        if ok:
            if p not in parser.proxy_pool.proxies:
                parser.proxy_pool.proxies.append(p)
                added += 1
        else:
            failed += 1

    if added > 0:
        parser.proxy_pool.save_to_file()
        proxy_wake_event.set()

    total = parser.proxy_pool.get_proxy_count()
    await wait_msg.edit_text(
        f"✅ <b>Результаты добавления прокси:</b>\n\n"
        f"• Добавлено рабочих: <b>{added} шт.</b>\n"
        f"• Отклонено (не работают с Avito): <b>{failed} шт.</b>\n"
        f"🌐 Всего живых прокси в пуле: <b>{total} шт.</b>",
        parse_mode=ParseMode.HTML
    )


@dp.message(lambda msg: msg.from_user and user_waiting_add_search.get(msg.from_user.id) and not (msg.text and msg.text.startswith("/")))
async def handle_user_waiting_add_search(message: types.Message, bot: Bot):
    """Принимает ссылку на поиск Avito, когда пользователь нажал [+] Добавить поиск."""
    user_id = message.from_user.id
    username = message.from_user.username
    raw_text = (message.text or "").strip()

    match = re.search(r"https?://(?:m\.|www\.)?avito\.ru/\S+", raw_text)
    if not match:
        cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_add_search")]
        ])
        await message.answer(
            "⚠️ <b>Ссылка не распознана!</b>\n\n"
            "Пожалуйста, отправьте корректную ссылку на Avito (например, <code>https://www.avito.ru/...</code>)\n"
            "или нажмите «❌ Отмена».",
            reply_markup=cancel_kb,
            parse_mode=ParseMode.HTML
        )
        return

    user_waiting_add_search.pop(user_id, None)
    await handle_direct_avito_link(message, bot)


# ===================== АКТИВАЦИЯ ТАРИФА / КЛЮЧИ =====================

@dp.message(Command("activate"))
@dp.message(F.text == "🔑 Активация")
async def cmd_activate(message: types.Message):
    """Открывает ввод кода активации или админ-панель генерации ключей."""
    user_id = message.from_user.id
    username = message.from_user.username
    site_u = await check_auth_or_prompt(message)
    if not site_u:
        return

    # Для администратора открываем расширенную панель управления лицензиями и генерацией ключей!
    if await is_admin(user_id, username):
        admin_kb = InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="⚡️ Сгенерировать ключ (30 дней)", callback_data="adm_keygen_prompt_30d")
            ],
            [
                InlineKeyboardButton(text="👑 Сгенерировать VIP ключ (бессрочный)", callback_data="adm_keygen_prompt_vip")
            ],
            [
                InlineKeyboardButton(text="👥 Продлить тариф пользователю", callback_data="adm_refresh")
            ],
            [
                InlineKeyboardButton(text="🔑 Ввести ключ на этом аккаунте", callback_data="adm_enter_key_self")
            ]
        ])
        await message.answer(
            "🔑 <b>Панель управления лицензиями и активацией</b>\n\n"
            "Как администратор, вы можете мгновенно создавать лицензионные ключи или напрямую продлевать тарифы клиентам в базе.\n\n"
            "<i>Выберите необходимое действие:</i>",
            reply_markup=admin_kb,
            parse_mode=ParseMode.HTML
        )
        return

    # Проверяем блокировку на 24 часа для обычного пользователя
    is_blocked, rem_sec, attempts = check_activation_attempts(str(user_id))
    if is_blocked:
        hours = rem_sec // 3600
        mins = (rem_sec % 3600) // 60
        await message.answer(
            f"⛔️ <b>Ввод кодов активации заблокирован на 24 часа!</b>\n\n"
            f"Превышено допустимое число неверных попыток (3 из 3).\n"
            f"Повторная возможность ввода станет доступна через: <b>{hours} ч. {mins} мин.</b>\n\n"
            f"<i>Защита от подбора ключей включена.</i>",
            parse_mode=ParseMode.HTML
        )
        return

    user_waiting_activation[user_id] = True
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_activation")]
    ])
    rem_attempts = max(0, 3 - attempts)
    await message.answer(
        f"🔑 <b>Активация и продление тарифа</b>\n\n"
        f"Отправьте ваш <b>20-значный код активации</b> (формат: <code>XXXX-XXXX-XXXX-XXXX-XXXX</code>).\n\n"
        f"• Каждый ключ продлевает доступ на <b>+30 дней</b> от текущего тарифа.\n"
        f"• Время идёт непрерывно независимо от работы сервиса.\n"
        f"• ⚠️ <i>Внимание: после 3 неверных попыток ввод блокируется на <b>24 часа</b>! "
        f"Осталось попыток: <b>{rem_attempts}</b> из 3.</i>\n\n"
        f"Для отмены отправьте <code>/cancel</code> или нажмите кнопку ниже:",
        reply_markup=cancel_kb,
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data == "adm_enter_key_self")
async def cb_adm_enter_key_self(call: CallbackQuery):
    user_id = call.from_user.id
    user_waiting_activation[user_id] = True
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_activation")]
    ])
    await call.message.answer(
        "🔑 <b>Ввод ключа активации</b>\n\n"
        "Отправьте 20-значный код активации (формат: <code>XXXX-XXXX-XXXX-XXXX-XXXX</code>):\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        reply_markup=cancel_kb,
        parse_mode=ParseMode.HTML
    )
    await call.answer()


@dp.callback_query(F.data == "adm_keygen_prompt_30d")
async def cb_adm_keygen_prompt_30d(call: CallbackQuery):
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    admin_waiting_keygen[call.from_user.id] = "STD"
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_keygen")]
    ])
    await call.message.answer(
        "⚡️ <b>Генерация ключа на 30 дней (EB30)</b>\n\n"
        "Отправьте <b>Request ID</b> устройства пользователя (например, <code>EBID-...</code> или <code>EBMOB-...</code>) ответным сообщением:\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        reply_markup=cancel_kb,
        parse_mode=ParseMode.HTML
    )
    await call.answer()


@dp.callback_query(F.data == "adm_keygen_prompt_vip")
async def cb_adm_keygen_prompt_vip(call: CallbackQuery):
    if not await is_admin(call.from_user.id, call.from_user.username):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return
    admin_waiting_keygen[call.from_user.id] = "VIP"
    cancel_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_keygen")]
    ])
    await call.message.answer(
        "👑 <b>Генерация VIP ключа (бессрочный)</b>\n\n"
        "Отправьте <b>Request ID</b> устройства пользователя (например, <code>EBID-...</code> или <code>EBMOB-...</code>) ответным сообщением:\n\n"
        "<i>Для отмены отправьте /cancel</i>",
        reply_markup=cancel_kb,
        parse_mode=ParseMode.HTML
    )
    await call.answer()


@dp.callback_query(F.data == "cancel_keygen")
async def cb_cancel_keygen(call: CallbackQuery):
    admin_waiting_keygen.pop(call.from_user.id, None)
    await call.answer("Отменено")
    try:
        await call.message.edit_text("❌ Генерация ключа отменена.", reply_markup=None)
    except Exception:
        pass


@dp.message(lambda msg: msg.from_user and msg.from_user.id in admin_waiting_keygen and not (msg.text and msg.text.startswith("/")))
async def handle_admin_keygen_input(message: types.Message):
    admin_id = message.from_user.id
    if not await is_admin(admin_id, message.from_user.username):
        return
    tier = admin_waiting_keygen.pop(admin_id, "STD")
    raw_text = (message.text or "").strip()

    match_id = re.search(r'\b((?:EBID|EBMOB)-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})\b', raw_text, re.IGNORECASE)
    target_id = match_id.group(1).upper() if match_id else raw_text.upper()

    try:
        if SITE_DIR not in sys.path:
            sys.path.insert(0, SITE_DIR)
        import hwid_security
        key = hwid_security.generate_response_key(target_id, tier)
        tier_title = "👑 VIP (бессрочно)" if tier == "VIP" else "⚡️ 30 дней (EB30)"
        await message.answer(
            f"✅ <b>Ключ успешно создан!</b>\n\n"
            f"📦 <b>Тариф:</b> {tier_title}\n"
            f"💻 <b>Request ID:</b> <code>{html.escape(target_id)}</code>\n\n"
            f"🔑 <b>Ключ активации:</b>\n"
            f"<code>{html.escape(key)}</code>\n\n"
            f"<i>Нажмите на ключ выше, чтобы скопировать его и отправить пользователю!</i>",
            parse_mode=ParseMode.HTML
        )
    except Exception as e:
        await message.answer(
            f"❌ <b>Ошибка генерации ключа:</b> {html.escape(str(e))}\n\n"
            f"Убедитесь, что передан верный ID в формате <code>EBID-XXXX-...</code> или <code>EBMOB-XXXX-...</code>",
            parse_mode=ParseMode.HTML
        )


@dp.callback_query(F.data == "cancel_activation")
async def cb_cancel_activation(call: CallbackQuery):
    user_id = call.from_user.id
    user_waiting_activation.pop(user_id, None)
    await call.answer("Отменено")
    try:
        await call.message.edit_text("❌ Ввод кода активации отменен.", reply_markup=None)
    except Exception:
        pass


@dp.message(lambda msg: msg.from_user and user_waiting_activation.get(msg.from_user.id) and not (msg.text and msg.text.startswith("/")))
async def handle_user_activation_input(message: types.Message):
    """Обрабатывает введенный пользователем 20-значный ключ активации."""
    user_id = message.from_user.id
    username = message.from_user.username
    raw_key = (message.text or "").strip()

    site_u = get_site_user_by_tg_id(user_id, username)
    u_login = site_u.get("username") if site_u else (username or str(user_id))

    success, msg = activate_key_for_user(raw_key, str(user_id), username=u_login)
    if success:
        user_waiting_activation.pop(user_id, None)
        is_adm = (site_u.get("role") == "admin" or (site_u.get("username") or "").lower() == "skynet83") if site_u else False
        await message.answer(msg, reply_markup=get_main_keyboard(is_user_admin=is_adm), parse_mode=ParseMode.HTML)
    else:
        # Проверяем, наступила ли блокировка на 24 часа
        is_blocked, rem_sec, attempts = check_activation_attempts(str(user_id))
        if is_blocked:
            user_waiting_activation.pop(user_id, None)
        await message.answer(msg, parse_mode=ParseMode.HTML)


# ===================== БЫСТРОЕ ДОБАВЛЕНИЕ ПО ССЫЛКЕ =====================

@dp.message(F.text.regexp(r"https?://(?:m\.|www\.)?avito\.ru/\S+"))
async def handle_direct_avito_link(message: types.Message, bot: Bot):
    """
    Если пользователь просто отправляет боту ссылку с Avito (из браузера или приложения):
    Бот автоматически проверяет тариф и лимиты, извлекает параметры, создает красивое имя поиска и ставит на мониторинг!
    """
    user_id = message.from_user.id
    username = message.from_user.username
    site_u = await check_auth_or_prompt(message)
    if not site_u:
        return

    is_adm = await is_admin(user_id, username)
    perms = site_u.get("permissions") or {}

    # 1. Проверяем срок действия подписки
    if not is_adm:
        exp_str = perms.get("avito_expires_at")
        if exp_str:
            try:
                exp_dt = datetime.strptime(exp_str, "%Y-%m-%d %H:%M:%S")
                if datetime.now() > exp_dt:
                    await message.answer(
                        f"⏳ <b>Срок действия вашего тарифа истек ({exp_str})!</b>\n\n"
                        f"Добавление новых поисков приостановлено. Продлите тариф на сайте: <a href=\"{get_site_url()}/\">SkyBase</a>.",
                        parse_mode=ParseMode.HTML
                    )
                    return
            except Exception:
                pass

    # 2. Проверяем лимит поисков по тарифу (максимум 10)
    max_s = min(10, 10 if is_adm else int(perms.get("max_searches") or 10))
    current_urls = await get_user_tracked_urls(user_id)
    if len(current_urls) >= max_s:
        await message.answer(
            f"⚠️ <b>Достигнут лимит поисковых ссылок!</b>\n\n"
            f"По вашему тарифу доступно максимум <b>{max_s}</b> ссылок (сейчас добавлено <b>{len(current_urls)}</b>, системный предел: 10).\n\n"
            f"Чтобы добавить новый поиск:\n"
            f"• Удалите ненужную ссылку: <code>/del &lt;номер&gt;</code>\n"
            f"• Или управляйте ссылками на сайте: <a href=\"{get_site_url()}/\">SkyBase</a>",
            parse_mode=ParseMode.HTML
        )
        return

    raw_text = message.text.strip()
    match = re.search(r"https?://(?:m\.|www\.)?avito\.ru/\S+", raw_text)
    if not match:
        return
    url = match.group(0)

    # Автоматическое определение названия поиска
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    search_q = params.get("q", [None])[0]

    if search_q:
        auto_name = f"Поиск: {unquote(search_q)}"
    else:
        path_parts = [p for p in parsed.path.split("/") if p and p != "all"]
        auto_name = unquote(path_parts[-1]).replace("_", " ").title() if path_parts else "Новый поиск Avito"

    try:
        new_id = await add_user_tracked_url(user_id, url, auto_name)
        # Синхронизируем добавление ссылки в users.json для сайта
        add_search_to_site_users(user_id, username, {
            "id": new_id,
            "name": auto_name,
            "url": url,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_active": 1,
            "is_initialized": 0,
            "last_polled_at": None
        })
        rem_count = max_s - (len(current_urls) + 1)
        rem_info = f"\n📊 Осталось слотов: <b>{rem_count}</b> из <b>{max_s}</b>" if not is_adm else ""
        await message.answer(
            f"🎯 <b>Ссылка распознана и поставлена на отслеживание!</b>\n\n"
            f"🆔 <b>Номер задачи:</b> <code>{new_id}</code>\n"
            f"📌 <b>Название:</b> <i>{auto_name}</i>{rem_info}\n"
            f"🔗 <a href='{url}'>Открыть ссылку</a>\n\n"
            f"<i>Текущие объявления сохранены без лишнего шума. Новые предложения будут приходить каждые 30 секунд.</i>",
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
        # Инициализируем поиск в фоне
        asyncio.create_task(check_all_active_searches(bot, initial_seed_user=user_id))
    except Exception as e:
        await message.answer(f"❌ Ошибка добавления поиска: {e}")


# Обработчики постоянных кнопок меню (Reply Keyboard)
@dp.message(F.text == "📋 Мои поиски")
async def btn_my_searches(message: types.Message):
    await cmd_list(message)


@dp.message(F.text == "🔍 Проверить сейчас")
async def btn_check_now(message: types.Message, bot: Bot):
    await cmd_check(message, bot)


@dp.message(F.text == "📊 Статус")
async def btn_status(message: types.Message):
    await cmd_status(message)


@dp.message(F.text.in_(["👥 Пользователи", "👥 Клиенты", "/users", "/admin_users", "/admin"]))
async def btn_users_panel(message: types.Message):
    if await is_admin(message.from_user.id, message.from_user.username):
        await show_users_control_panel(message)


@dp.message(F.text.in_(["▶️ Включить", "Включить", "⚪ Включить", "▶️ Запустить", "Запустить", "⚪ Запустить", "/resume", "/start_mon"]))
async def btn_start_monitoring_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    if not await check_auth_or_prompt(message):
        return

    admin = await is_admin(user_id, username)
    u_list = load_site_users()
    uname = (username or "").strip().lower()
    for u in u_list:
        tg_id = u.get("telegram_chat_id")
        u_site = (u.get("username") or "").strip().lower()
        if (tg_id and str(tg_id).strip() == str(user_id).strip()) or (uname and u_site == uname) or (admin and (u_site in ("skynet83", "admin") or u.get("role") == "admin")):
            if not u.get("permissions"):
                u["permissions"] = {}
            u["permissions"]["tg_bot"] = True
            break
    save_site_users(u_list)

    silent = await is_silent_mode(user_id)
    await message.answer(
        "🟢 <b>ТГ-уведомления включены!</b>\n\n"
        "Все найденные объявления будут поступать в этот диалог.",
        reply_markup=get_main_keyboard(is_user_admin=admin, is_silent=silent, is_active=True, user_id=user_id, username=username),
        parse_mode=ParseMode.HTML
    )


@dp.message(F.text.in_(["⏹️ Выключить", "Выключить", "⚪ Выключить", "⏹️ Остановить", "Остановить", "⚪ Остановить", "/pause", "/stop", "/stop_mon"]))
async def btn_stop_monitoring_handler(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username
    if not await check_auth_or_prompt(message):
        return

    admin = await is_admin(user_id, username)
    u_list = load_site_users()
    uname = (username or "").strip().lower()
    for u in u_list:
        tg_id = u.get("telegram_chat_id")
        u_site = (u.get("username") or "").strip().lower()
        if (tg_id and str(tg_id).strip() == str(user_id).strip()) or (uname and u_site == uname) or (admin and (u_site in ("skynet83", "admin") or u.get("role") == "admin")):
            if not u.get("permissions"):
                u["permissions"] = {}
            u["permissions"]["tg_bot"] = False
            break
    save_site_users(u_list)

    silent = await is_silent_mode(user_id)
    await message.answer(
        "🔴 <b>ТГ-уведомления выключены!</b>\n\n"
        "Уведомления в Telegram приостановлены. Нажмите «▶️ Включить» для возобновления.",
        reply_markup=get_main_keyboard(is_user_admin=admin, is_silent=silent, is_active=False, user_id=user_id, username=username),
        parse_mode=ParseMode.HTML
    )


@dp.message(F.text == "⏸ Пауза / Старт")
async def btn_toggle_pause(message: types.Message):
    global is_monitoring_active
    user_id = message.from_user.id
    if not await check_auth_or_prompt(message):
        return

    if await is_admin(user_id):
        is_paused = False
        try:
            sys.path.insert(0, os.path.dirname(BOT_DIR))
            import avito_api_helper
            is_paused = avito_api_helper.get_bot_paused()
        except Exception:
            is_paused = not is_monitoring_active

        if is_paused:
            await cmd_resume(message)
        else:
            await cmd_stop(message)
    else:
        # Персональная пауза Telegram для обычного пользователя в users.json
        new_state = False
        u_list = load_site_users()
        uname = (message.from_user.username or "").lower()
        for u in u_list:
            tg_id = u.get("telegram_chat_id")
            if (tg_id and str(tg_id).strip() == str(user_id).strip()) or (u.get("username", "").lower() == uname):
                if not u.get("permissions"):
                    u["permissions"] = {}
                cur_tg = u["permissions"].get("tg_bot", True)
                new_state = not cur_tg
                u["permissions"]["tg_bot"] = new_state
                break
        save_site_users(u_list)

        if new_state:
            await message.answer("🟢 <b>Ваши персональные уведомления в Telegram возобновлены!</b>", reply_markup=get_main_keyboard(is_user_admin=False), parse_mode=ParseMode.HTML)
        else:
            await message.answer("⏸ <b>Ваши персональные уведомления в Telegram приостановлены!</b>\n<i>Новые объявления не будут присылаться. Нажмите «▶️ Запустить» для включения.</i>", reply_markup=get_main_keyboard(is_user_admin=False), parse_mode=ParseMode.HTML)

@dp.message(F.text.in_(["✉️ Написать админу", "💬 Чат с админом"]))
async def btn_write_to_admin(message: types.Message):
    user_id = message.from_user.id
    if not await check_auth_or_prompt(message):
        return

    # Если нажал сам админ — открываем админ-панель чата со всеми пользователями
    if await is_admin(user_id, message.from_user.username):
        await show_admin_chat(message)
        return

    site_u = get_site_user_by_tg_id(user_id, message.from_user.username)
    if site_u and (site_u.get("chat_blocked") or site_u.get("is_blocked")):
        await message.answer("⛔️ <b>Ваш доступ к чату заблокирован администратором (Чёрный список).</b>", parse_mode=ParseMode.HTML)
        return

    user_waiting_feedback[user_id] = True
    adm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Открыть диалог с @skynet19081983", url="https://t.me/skynet19081983")]
    ])
    await message.answer(
        "💬 <b>Напишите ваше сообщение для администратора:</b>\n\n"
        "<i>Оно сразу появится на сайте и будет отправлено админу @skynet19081983 в Telegram.</i>\n\n"
        "Отправьте текст ответным сообщением или нажмите кнопку ниже для прямого перехода в Telegram:\n"
        "<i>(Для отмены отправьте /cancel)</i>",
        reply_markup=adm_kb,
        parse_mode=ParseMode.HTML
    )

@dp.message(F.text.in_(["💬 Чат с пользователями", "⏳ Заявки клиентов", "Заявки клиентов"]))
@dp.message(Command("chat"))
async def btn_chat_with_users(message: types.Message):
    if not await is_admin(message.from_user.id, message.from_user.username):
        await btn_write_to_admin(message)
        return
    await show_admin_chat(message)


async def show_admin_chat(message: types.Message):
    """Показывает последние сообщения чата с логинами пользователей и привязанными TG, а также кнопки выбора получателя."""
    msgs = get_recent_chat_messages(limit=10)
    users = load_site_users()
    users_by_name = { (u.get("username") or "").strip().lower(): u for u in users }
    users_by_tg = {}
    for u in users:
        if u.get("telegram_chat_id"):
            users_by_tg[str(u["telegram_chat_id"]).strip()] = u

    lines = ["💬 <b>Последние сообщения из чата:</b>\n"]
    if msgs:
        for m in msgs:
            sender = (m.get("sender") or "").strip()
            recipient = (m.get("recipient") or "").strip()
            text_snippet = (m.get("text", "") or "")[:150]
            time_str = m.get("created_at", "")
            is_read = m.get("is_read", False)
            read_status = "✅ Прочитано" if is_read else "🆕 Новое"

            is_admin_msg = sender.lower() in ["skynet83", "admin"]
            target_user_key = recipient if is_admin_msg else sender
            
            site_u = users_by_name.get(target_user_key.lower())
            if not site_u and target_user_key.startswith("tg_"):
                site_u = users_by_tg.get(target_user_key.replace("tg_", "").strip())
            
            login = site_u.get("username") if site_u else target_user_key
            tg_nick = f"@{site_u['telegram_username'].lstrip('@')}" if (site_u and site_u.get("telegram_username")) else (f"ID: {site_u['telegram_chat_id']}" if (site_u and site_u.get("telegram_chat_id")) else "TG не привязан")

            if is_admin_msg:
                lines.append(
                    f"📤 <b>Вы ➔ {html.escape(login)}</b> (TG: <code>{html.escape(tg_nick)}</code>) [{read_status}]\n"
                    f"🕒 <i>{time_str}</i>\n"
                    f"<i>{html.escape(text_snippet)}</i>\n"
                )
            else:
                lines.append(
                    f"👤 <b>Логин:</b> <code>{html.escape(login)}</code> | 📱 <b>TG:</b> <code>{html.escape(tg_nick)}</code> [{read_status}]\n"
                    f"🕒 <i>{time_str}</i>\n"
                    f"<i>{html.escape(text_snippet)}</i>\n"
                )
    else:
        lines.append("<i>Пока нет сообщений в чате.</i>\n")

    inline_rows = []
    # Кнопки для написания каждому пользователю с его логином и привязанным TG
    for u in users:
        u_login = u.get("username") or "user"
        if u_login.lower() in ["skynet83", "admin"] and str(u.get("telegram_chat_id", "")) == str(message.from_user.id):
            continue
        tg_id = u.get("telegram_chat_id")
        tg_u = u.get("telegram_username")
        tg_label = f"@{tg_u.lstrip('@')}" if tg_u else (f"ID:{tg_id}" if tg_id else "нет TG")
        btn_text = f"✉️ {u_login} | {tg_label}"
        inline_rows.append([
            InlineKeyboardButton(
                text=btn_text,
                callback_data=f"admin_reply_user_{u_login}"
            )
        ])

    inline_rows.append([
        InlineKeyboardButton(text="🔄 Обновить сообщения", callback_data="admin_chat_refresh")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=inline_rows)

    await message.answer(
        "\n".join(lines),
        reply_markup=kb,
        parse_mode=ParseMode.HTML
    )


@dp.callback_query(F.data.startswith("admin_reply_"))
async def cb_admin_reply_select(call: types.CallbackQuery):
    """Администратор выбрал получателя — ждём текст сообщения."""
    if not await is_admin(call.from_user.id, call.from_user.username):
        try:
            await call.answer("Нет доступа.", show_alert=True)
        except Exception:
            pass
        return
    try:
        await call.answer()
    except Exception:
        pass

    raw = call.data.replace("admin_reply_user_", "").replace("admin_reply_", "").strip()
    users = load_site_users()
    target_u = None
    for u in users:
        if (u.get("username") or "").lower() == raw.lower():
            target_u = u
            break
        if str(u.get("telegram_chat_id", "")).strip() == raw:
            target_u = u
            break
        if str(u.get("permissions", {}).get("hwid_request_id", "")).strip().lower() == raw.lower():
            target_u = u
            break
    if not target_u:
        try:
            target_u = get_site_user_by_tg_id(int(raw))
        except Exception:
            pass

    username = target_u.get("username") if target_u else raw
    tg_id = target_u.get("telegram_chat_id") if target_u else None
    tg_u = target_u.get("telegram_username") if target_u else None
    tg_handle = f"@{tg_u.lstrip('@')}" if tg_u else (f"ID: {tg_id}" if tg_id else "не привязан")

    hw_id = raw if raw.startswith(("EBID-", "EBMOB-")) else (
        (target_u.get("permissions", {}).get("hwid_request_id") or target_u.get("request_id")) if target_u else None
    )

    admin_waiting_reply_to[call.from_user.id] = {
        "raw": raw,
        "hw_id": hw_id,
        "username": username,
        "chat_id": tg_id,
        "name": target_u.get("name") if target_u else username,
        "tg_handle": tg_handle
    }
    save_admin_reply_state(admin_waiting_reply_to)

    disp_name = hw_id or username
    if disp_name.startswith("EBID-"):
        lbl = "ID пользователя (ПК)"
    elif disp_name.startswith("EBMOB-"):
        lbl = "ID пользователя (Телефон)"
    else:
        lbl = "Логин на сайте"

    from aiogram.types import ForceReply
    await call.message.reply(
        f"✉️ <b>Диалог с получателем:</b>\n\n"
        f"🖥️ <b>{lbl}:</b> <code>{html.escape(disp_name)}</code>\n"
        + (f"📱 <b>Привязанный Telegram:</b> <code>{html.escape(tg_handle)}</code>\n\n" if tg_id else "\n")
        + f"<i>Отправьте ответное сообщение (например, ключ активации).\n"
        f"Оно сразу появится в окне активации у этого пользователя.\n"
        f"Для отмены отправьте /cancel.</i>",
        parse_mode=ParseMode.HTML,
        reply_markup=ForceReply(selective=False, input_field_placeholder="Введите ключ активации или текст...")
    )


async def deliver_admin_reply(admin_id: int, text: str, target: dict, bot: Bot, message: types.Message):
    """Единая функция надежной доставки ответа администратора в окно активации и в Telegram."""
    target_username = target.get("username")
    target_hw_id = target.get("hw_id")
    target_chat_id = target.get("chat_id")

    # Если hw_id не был явно определен, ищем его по имени пользователя или истории чата
    if not target_hw_id and target_username:
        if target_username.upper().startswith(("EBID-", "EBMOB-")):
            target_hw_id = target_username.upper()
        else:
            for u in load_site_users():
                if (u.get("username") or "").lower() == target_username.lower():
                    cand = (u.get("permissions", {}).get("hwid_request_id") or u.get("request_id"))
                    if cand and cand.upper().startswith(("EBID-", "EBMOB-")):
                        target_hw_id = cand.upper()
                        break

    if not target_hw_id and target_username:
        msgs = load_chat_messages()
        for m in reversed(msgs):
            if (m.get("sender") or "").lower() == target_username.lower() or (m.get("recipient") or "").lower() == target_username.lower():
                cand = m.get("hw_id") or m.get("recipient_id") or m.get("sender_id")
                if cand and cand.upper().startswith(("EBID-", "EBMOB-")):
                    target_hw_id = cand.upper()
                    break

    # Если всё еще нет hw_id, но есть активный клиент на сайте — подставляем его
    if not target_hw_id:
        target_hw_id = find_last_active_client_hwid()

    primary_recipient = target_hw_id if target_hw_id else (target_username or "all")
    extra_fields = {
        "admin_tg_sent": True,
        "recipient_username": target_username or primary_recipient,
        "recipient_id": target_hw_id or primary_recipient,
        "hw_id": target_hw_id or primary_recipient,
    }

    # 1. Сохраняем в chat_messages.json на сайте
    new_msg = append_chat_message(
        sender="skynet83",
        sender_name="Администратор (skynet83)",
        recipient=primary_recipient,
        text=text,
        extra=extra_fields
    )

    # 2. Если у пользователя привязан Telegram (и это не сам администратор) — отправляем в Telegram
    delivered_tg = False
    if target_chat_id and target_chat_id != admin_id:
        try:
            user_kb = InlineKeyboardMarkup(inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Прочитано", callback_data=f"chat_read_{new_msg['id']}"),
                    InlineKeyboardButton(text="✉️ Ответить", callback_data="btn_write_to_admin")
                ]
            ])
            user_m = await bot.send_message(
                chat_id=target_chat_id,
                text=(
                    f"📩 <b>Сообщение от администратора AvitoHunter:</b>\n\n"
                    f"{html.escape(text)}\n\n"
                    f"🕒 <i>{new_msg['created_at']}</i>"
                ),
                reply_markup=user_kb,
                parse_mode=ParseMode.HTML
            )
            delivered_tg = True
            all_msgs = load_chat_messages()
            for m in all_msgs:
                if str(m.get("id")) == str(new_msg["id"]):
                    m["tg_delivered"] = True
                    m["tg_user_msg_id"] = user_m.message_id
                    m["tg_user_chat_id"] = target_chat_id
                    break
            save_chat_messages(all_msgs)
        except Exception as e:
            logger.warning(f"Не удалось доставить в TG пользователю {target_chat_id}: {e}")

    disp_target = target_hw_id or target_username or primary_recipient
    if disp_target.startswith(("EBID-", "EBMOB-")):
        confirm_text = f"✅ <b>Ответ для <code>{html.escape(disp_target)}</code> успешно доставлен в окно активации на сайте!</b>"
    elif delivered_tg:
        confirm_text = f"✅ <b>Сообщение для <code>{html.escape(disp_target)}</code> успешно отправлено на сайт и в Telegram!</b>"
    else:
        confirm_text = f"✅ <b>Сообщение для <code>{html.escape(disp_target)}</code> успешно сохранено на сайте!</b>"

    await message.answer(
        confirm_text,
        parse_mode=ParseMode.HTML,
        reply_markup=get_main_keyboard(is_user_admin=True)
    )


@dp.message(Command("reply"))
@dp.message(Command("key"))
async def handle_cmd_admin_direct_reply(message: types.Message, bot: Bot):
    if not await is_admin(message.from_user.id, message.from_user.username):
        return
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "ℹ️ <b>Формат команды:</b>\n"
            "<code>/reply EBID-XXXX-XXXX Текст ответа</code>\n"
            "или\n"
            "<code>/key EBID-XXXX-XXXX EB30-XXXX-XXXX-XXXX-XXXX</code>",
            parse_mode=ParseMode.HTML
        )
        return
    target_raw = parts[1].strip()
    reply_text = parts[2].strip()
    target = {
        "raw": target_raw,
        "hw_id": target_raw if target_raw.upper().startswith(("EBID-", "EBMOB-")) else None,
        "username": target_raw,
        "chat_id": None
    }
    await deliver_admin_reply(message.from_user.id, reply_text, target, bot, message)


@dp.message(lambda msg: msg.from_user and (
    msg.from_user.id in admin_waiting_reply_to
    or (msg.reply_to_message is not None)
    or bool(re.search(r'\b(?:EB30|VIPX)-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b', msg.text or '', re.IGNORECASE))
    or (str(msg.from_user.id) in load_admin_reply_state() or msg.from_user.id in load_admin_reply_state())
) and not (msg.text and msg.text.startswith("/")))
async def handle_admin_reply_input(message: types.Message, bot: Bot):
    """
    Принимает текст от админа и отправляет его пользователю на сайт и в TG:
    - если админ нажал «Ответить» (ForceReply / admin_waiting_reply_to / сохраненное состояние)
    - если админ сделал свайп/Reply на сообщение в Telegram (message.reply_to_message)
    - если админ просто прислал ключ активации (EB30-... / VIPX-...)
    """
    admin_id = message.from_user.id
    is_adm = await is_admin(admin_id, message.from_user.username)
    if not is_adm:
        return
    text = (message.text or "").strip()

    # Сначала проверяем активное состояние ожидания ответа
    target = admin_waiting_reply_to.pop(admin_id, None)
    if not target:
        persisted = load_admin_reply_state()
        if admin_id in persisted:
            target = persisted.pop(admin_id, None)
            save_admin_reply_state(persisted)
        elif str(admin_id) in persisted:
            target = persisted.pop(str(admin_id), None)
            save_admin_reply_state(persisted)

    # Если состояния нет, проверяем reply_to_message (ответ цитированием в Telegram)
    if not target and message.reply_to_message:
        replied_text = message.reply_to_message.text or message.reply_to_message.caption or ""
        dev_id = extract_device_id_from_text(replied_text)
        if dev_id:
            target = {
                "raw": dev_id,
                "hw_id": dev_id,
                "username": dev_id,
                "chat_id": None
            }

    # Если всё еще нет, но админ прислал ключ активации — связываем с последним клиентом в чате
    key_pattern = r'\b(?:EB30|VIPX)-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}\b'
    if not target and re.search(key_pattern, text, re.IGNORECASE):
        last_hwid = find_last_active_client_hwid()
        if last_hwid:
            target = {
                "raw": last_hwid,
                "hw_id": last_hwid,
                "username": last_hwid,
                "chat_id": None
            }

    if target:
        if not text:
            await message.answer("⚠️ Сообщение не может быть пустым.")
            return
        await deliver_admin_reply(admin_id, text, target, bot, message)
        return


@dp.callback_query(F.data == "admin_chat_refresh")
async def cb_admin_chat_refresh(call: types.CallbackQuery):
    """Обновляет экран чата с пользователями для администратора."""
    if not await is_admin(call.from_user.id):
        await call.answer("Нет доступа.", show_alert=True)
        return
    await call.answer("Обновлено!")
    try:
        await call.message.delete()
    except Exception:
        pass
    await show_admin_chat(call.message)


@dp.callback_query(F.data.startswith("chat_read_"))
async def cb_chat_mark_read(call: types.CallbackQuery, bot: Bot):
    """Помечает сообщение как прочитанное в Telegram и на сайте."""
    msg_id = call.data.replace("chat_read_", "").strip()
    messages = load_chat_messages()
    found = None
    for m in messages:
        if str(m.get("id")) == str(msg_id):
            m["is_read"] = True
            m["read_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            found = m
            break
    if found:
        save_chat_messages(messages)
        try:
            current_kb = call.message.reply_markup.inline_keyboard if call.message.reply_markup else []
            new_rows = []
            for row in current_kb:
                new_row = []
                for btn in row:
                    if btn.callback_data == call.data:
                        new_row.append(InlineKeyboardButton(text="✅ Прочитано", callback_data="noop_read"))
                    else:
                        new_row.append(btn)
                new_rows.append(new_row)
            await call.message.edit_reply_markup(reply_markup=InlineKeyboardMarkup(inline_keyboard=new_rows))
        except Exception:
            pass
        await call.answer("✅ Отмечено как прочитанное на сайте и в Telegram!")
    else:
        await call.answer("Сообщение уже прочитано.")


@dp.callback_query(F.data == "noop_read")
async def cb_noop_read(call: types.CallbackQuery):
    await call.answer("Сообщение уже прочитано.", show_alert=False)


@dp.callback_query(F.data == "btn_write_to_admin")
async def cb_btn_write_to_admin(call: types.CallbackQuery):
    """Инлайн-кнопка быстрого ответа администратору."""
    user_id = call.from_user.id
    site_u = get_site_user_by_tg_id(user_id, call.from_user.username)
    if site_u and (site_u.get("chat_blocked") or site_u.get("is_blocked")):
        await call.answer("Доступ к чату заблокирован администратором.", show_alert=True)
        return
    await call.answer()
    user_waiting_feedback[user_id] = True
    await call.message.answer(
        "💬 <b>Напишите ваше сообщение для администратора:</b>\n\n"
        "<i>Оно сразу появится на сайте и будет доставлено администратору в Telegram.\n"
        "Для отмены отправьте /cancel.</i>",
        parse_mode=ParseMode.HTML
    )


async def background_chat_sync_loop(bot: Bot):
    """Фоновый цикл двусторонней синхронизации сообщений и статусов прочтения между сайтом и Telegram."""
    global primary_admin_id
    logger.info("Запущен фоновый цикл синхронизации чата Сайт <-> Telegram")
    while True:
        try:
            await asyncio.sleep(2)
            messages = load_chat_messages()
            if not messages:
                continue

            save_needed = False
            users = load_site_users()
            users_by_name = { (u.get("username") or "").strip().lower(): u for u in users }

            for m in messages:
                sender = (m.get("sender") or "").strip().lower()
                recipient = (m.get("recipient") or "").strip().lower()
                is_read = bool(m.get("is_read", False))

                # 1. Доставка новых сообщений с сайта
                # А) От админа пользователю (создано на сайте)
                if sender in ["skynet83", "admin"] and recipient not in ["all", "admin"]:
                    if not m.get("tg_delivered") and not m.get("admin_tg_sent"):
                        target_u = users_by_name.get(recipient)
                        target_chat_id = target_u.get("telegram_chat_id") if target_u else None
                        if target_chat_id:
                            try:
                                user_kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [
                                        InlineKeyboardButton(text="✅ Прочитано", callback_data=f"chat_read_{m['id']}"),
                                        InlineKeyboardButton(text="✉️ Ответить", callback_data="btn_write_to_admin")
                                    ]
                                ])
                                user_m = await bot.send_message(
                                    chat_id=target_chat_id,
                                    text=(
                                        f"📩 <b>Сообщение от администратора AvitoHunter:</b>\n\n"
                                        f"{html.escape(m.get('text', ''))}\n\n"
                                        f"🕒 <i>{m.get('created_at', '')}</i>"
                                    ),
                                    reply_markup=user_kb,
                                    parse_mode=ParseMode.HTML
                                )
                                m["tg_delivered"] = True
                                m["tg_user_msg_id"] = user_m.message_id
                                m["tg_user_chat_id"] = target_chat_id
                                save_needed = True
                            except Exception as e:
                                logger.warning(f"Ошибка доставки сообщения из чата пользователю {target_chat_id}: {e}")
                                m["tg_delivered"] = "error"
                                save_needed = True
                        else:
                            m["tg_delivered"] = "no_tg"
                            save_needed = True

                # Б) От пользователя администратору (создано на сайте, в т.ч. из окна активации)
                elif recipient == "admin" and not m.get("sender_tg_id") and not m.get("admin_tg_sent"):
                    notified_state = m.get("admin_tg_notified")
                    retry_count = int(m.get("admin_tg_retry_count", 0))
                    if not notified_state or (notified_state == "error" and retry_count < 15):
                        curr_admin_id = ADMIN_CHAT_ID or primary_admin_id
                        if not curr_admin_id or (curr_admin_id and len(str(curr_admin_id)) < 8):
                            curr_admin_id = ADMIN_CHAT_ID or 5680198246
                        if not curr_admin_id:
                            for u in users:
                                if (u.get("role") == "admin" or (u.get("username") or "").lower() in ["skynet83", "skynet19081983"]) and u.get("telegram_chat_id"):
                                    curr_admin_id = int(u.get("telegram_chat_id"))
                                    primary_admin_id = curr_admin_id
                                    break
                        if curr_admin_id:
                            # Извлекаем уникальный аппаратный ID компьютера пользователя
                            user_id_code = m.get("sender_id") or m.get("hwid_request_id") or ""
                            if not user_id_code and sender and (sender.startswith("EBID-") or sender.startswith("EBMOB-")):
                                user_id_code = sender
                            if not user_id_code:
                                import re
                                match_ebid = re.search(r'\b((?:EBID|EBMOB)-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4})\b', m.get("text", ""), re.IGNORECASE)
                                if match_ebid:
                                    user_id_code = match_ebid.group(1).upper()
                            if not user_id_code:
                                target_u = users_by_name.get(sender)
                                if target_u and isinstance(target_u, dict):
                                    perms = target_u.get("permissions") or {}
                                    user_id_code = perms.get("hwid_request_id") or ""
                            if not user_id_code:
                                user_id_code = sender

                            reply_target = user_id_code
                            try:
                                adm_kb = InlineKeyboardMarkup(inline_keyboard=[
                                    [
                                        InlineKeyboardButton(text="✉️ Ответить", callback_data=f"admin_reply_user_{reply_target}"),
                                        InlineKeyboardButton(text="✅ Прочитано", callback_data=f"chat_read_{m['id']}")
                                    ]
                                ])
                                is_mob_id = str(user_id_code).upper().startswith("EBMOB")
                                dev_icon = "📱" if is_mob_id else "🖥️"
                                dev_label = "ID пользователя (Телефон)" if is_mob_id else "ID пользователя (ПК)"
                                adm_m = await bot.send_message(
                                    chat_id=curr_admin_id,
                                    text=(
                                        f"💬 <b>Новое сообщение из окна активации!</b>\n\n"
                                        f"{dev_icon} <b>{dev_label}:</b> <code>{html.escape(str(user_id_code))}</code>\n"
                                        f"🕒 <b>Время:</b> {m.get('created_at', '')}\n\n"
                                        f"📝 <i>{html.escape(str(m.get('text', '')))}</i>"
                                    ),
                                    reply_markup=adm_kb,
                                    parse_mode=ParseMode.HTML
                                )
                                m["admin_tg_notified"] = True
                                m["admin_tg_msg_id"] = adm_m.message_id
                                m["admin_tg_chat_id"] = curr_admin_id
                                m["sender_id"] = user_id_code
                                save_needed = True
                            except Exception as e:
                                logger.warning(f"Ошибка уведомления админа о сообщении с сайта: {e}")
                                m["admin_tg_notified"] = "error"
                                m["admin_tg_retry_count"] = retry_count + 1
                                save_needed = True

                # 2. Синхронизация статуса «Прочитано» с сайта в Telegram
                if is_read:
                    # Для админа
                    if m.get("admin_tg_msg_id") and not m.get("admin_tg_read_synced"):
                        try:
                            sender_login = m.get("sender") or "user"
                            await bot.edit_message_reply_markup(
                                chat_id=m["admin_tg_chat_id"],
                                message_id=m["admin_tg_msg_id"],
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                    [
                                        InlineKeyboardButton(text="✉️ Ответить", callback_data=f"admin_reply_user_{sender_login}"),
                                        InlineKeyboardButton(text="✅ Прочитано на сайте", callback_data="noop_read")
                                    ]
                                ])
                            )
                        except Exception:
                            pass
                        m["admin_tg_read_synced"] = True
                        save_needed = True

                    # Для пользователя
                    if m.get("tg_user_msg_id") and not m.get("user_tg_read_synced"):
                        try:
                            await bot.edit_message_reply_markup(
                                chat_id=m["tg_user_chat_id"],
                                message_id=m["tg_user_msg_id"],
                                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                    [
                                        InlineKeyboardButton(text="✅ Прочитано на сайте", callback_data="noop_read"),
                                        InlineKeyboardButton(text="✉️ Ответить", callback_data="btn_write_to_admin")
                                    ]
                                ])
                            )
                        except Exception:
                            pass
                        m["user_tg_read_synced"] = True
                        save_needed = True

            if save_needed:
                save_chat_messages(messages)

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"Ошибка в цикле синхронизации чата: {e}")
            await asyncio.sleep(5)

@dp.message(F.text.in_(["⏱ Таймер", "/timer"]))
async def btn_timer(message: types.Message):
    if await is_admin(message.from_user.id, message.from_user.username):
        await cmd_timer(message)
    else:
        await message.answer("⚠️ Настройка таймера доступна только администратору.")


@dp.message(F.text.in_(["🌐 Прокси", "/proxies", "/proxy"]))
async def btn_proxy(message: types.Message):
    if await is_admin(message.from_user.id, message.from_user.username):
        await cmd_proxy(message)
    else:
        await message.answer("⚠️ Управление прокси доступно только администратору.")


@dp.message(F.text.in_(["🎛 Панель управления", "Панель управления", "💻 Команды управления", "Панель", "Админ панель", "админ панель"]))
@dp.message(Command("panel"))
@dp.message(Command("control"))
@dp.message(Command("commands"))
async def btn_commands_panel(message: types.Message, bot: Bot):
    user_id = message.from_user.id
    username = message.from_user.username
    if not await check_auth_or_prompt(message):
        return

    admin = await is_admin(user_id, username)
    silent = await is_silent_mode(user_id)
    new_kb = get_main_keyboard(is_user_admin=admin, is_silent=silent)

    if admin:
        await message.answer(
            "👑 <b>Панель администратора</b>\n\n"
            "Кнопки управления (👥 Пользователи, 💬 Чат с пользователями, ▶️ Включить / ⏹️ Выключить) расположены на панели внизу экрана.",
            reply_markup=new_kb,
            parse_mode=ParseMode.HTML
        )
        return

    active = is_system_or_user_monitoring_active(user_id, username)
    text = format_control_panel_text(is_active=active)
    kb = get_control_panel_keyboard(is_active=active)
    await message.answer(text, reply_markup=kb, parse_mode=ParseMode.HTML)


@dp.callback_query(F.data == "cp_noop_active")
async def cb_control_noop_active(call: CallbackQuery):
    await call.answer("Мониторинг уже запущен (кнопка неактивна)", show_alert=False)


@dp.callback_query(F.data == "cp_noop_stopped")
async def cb_control_noop_stopped(call: CallbackQuery):
    await call.answer("Мониторинг уже остановлен (кнопка неактивна)", show_alert=False)


@dp.callback_query(F.data == "cp_start")
async def cb_control_start(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    username = call.from_user.username
    admin = await is_admin(user_id, username)

    global is_monitoring_active
    is_monitoring_active = True
    try:
        sys.path.insert(0, os.path.dirname(BOT_DIR))
        import avito_api_helper
        avito_api_helper.set_bot_paused("resume")
    except Exception:
        pass

    u_list = load_site_users()
    uname = (username or "").strip().lower()
    for u in u_list:
        tg_id = u.get("telegram_chat_id")
        u_site = (u.get("username") or "").strip().lower()
        if (tg_id and str(tg_id).strip() == str(user_id).strip()) or (uname and u_site == uname) or (admin and (u_site in ("skynet83", "admin") or u.get("role") == "admin")):
            if not u.get("permissions"):
                u["permissions"] = {}
            u["permissions"]["tg_bot"] = True
            break
    save_site_users(u_list)

    text = format_control_panel_text(is_active=True)
    kb = get_control_panel_keyboard(is_active=True)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await call.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass

    await call.answer("🟢 ТГ-уведомления включены!", show_alert=False)


@dp.callback_query(F.data == "cp_stop")
async def cb_control_stop(call: CallbackQuery, bot: Bot):
    user_id = call.from_user.id
    username = call.from_user.username
    admin = await is_admin(user_id, username)

    u_list = load_site_users()
    uname = (username or "").strip().lower()
    for u in u_list:
        tg_id = u.get("telegram_chat_id")
        u_site = (u.get("username") or "").strip().lower()
        if (tg_id and str(tg_id).strip() == str(user_id).strip()) or (uname and u_site == uname) or (admin and (u_site in ("skynet83", "admin") or u.get("role") == "admin")):
            if not u.get("permissions"):
                u["permissions"] = {}
            u["permissions"]["tg_bot"] = False
            break
    save_site_users(u_list)

    text = format_control_panel_text(is_active=False)
    kb = get_control_panel_keyboard(is_active=False)
    try:
        await call.message.edit_text(text, reply_markup=kb, parse_mode=ParseMode.HTML)
    except Exception:
        try:
            await call.message.edit_reply_markup(reply_markup=kb)
        except Exception:
            pass

    await call.answer("🔴 ТГ-уведомления выключены!", show_alert=False)


@dp.callback_query(F.data.startswith("act_"))
async def cb_admin_actions(call: CallbackQuery, bot: Bot):
    if not await is_admin(call.from_user.id):
        await call.answer("Доступ только для администратора!", show_alert=True)
        return

    act = call.data.replace("act_", "")
    await call.answer()

    # Важно: подменяем from_user в сообщении на пользователя, который нажал кнопку (админа),
    # чтобы обработчики команд не путали его с ботом
    call.message.from_user = call.from_user

    if act == "timer":
        await cmd_timer(call.message, bot=bot)
    elif act == "proxy":
        await cmd_proxy(call.message)
    elif act == "status":
        await cmd_status(call.message)
    elif act == "check":
        await cmd_check(call.message, bot)
    elif act == "list":
        await cmd_list(call.message)
    elif act == "fav":
        await cmd_favorites(call.message)
    elif act == "bl":
        await cmd_blacklist(call.message)
    elif act == "users":
        await cmd_users(call.message)
    elif act in ("chat", "pending"):
        await btn_chat_with_users(call.message)
    elif act == "toggle_pause":
        is_paused = False
        try:
            sys.path.insert(0, os.path.dirname(BOT_DIR))
            import avito_api_helper
            is_paused = avito_api_helper.get_bot_paused()
        except Exception:
            is_paused = not is_monitoring_active
        if is_paused:
            await cmd_resume(call.message)
        else:
            await cmd_stop(call.message)
    elif act == "restart":
        await cmd_restart(call.message)


@dp.message()
async def handle_unhandled_message(message: types.Message):
    """
    Глобальный перехват любых прочих сообщений:
    Если аккаунт не привязан к сайту — выводит строгое сообщение о необходимости регистрации и привязки.
    Если привязан — подсказывает доступные команды.
    """
    # 0. Проверяем, не отправлен ли ID код устройства (EBID / EBMOB) для запроса триала
    raw_m_text = (message.text or "").strip()
    m_direct_hw = re.search(r'\b((?:EBID|EBMOB)-[A-Z0-9\-]+)\b', raw_m_text, re.IGNORECASE)
    if m_direct_hw and (len(raw_m_text.split()) <= 2 or "триал" in raw_m_text.lower() or "пробн" in raw_m_text.lower() or "trial" in raw_m_text.lower()):
        message.text = f"/trial {m_direct_hw.group(1).upper()}"
        await cmd_user_trial(message)
        return

    # Проверяем, есть ли запрос на подтверждение привязки с сайта SkyBase
    all_site_users = load_site_users()
    pending_u = None
    clean_tg_uname = username.strip().lstrip("@").lower() if username else ""
    for su in all_site_users:
        pend = su.get("telegram_pending")
        if pend and isinstance(pend, dict) and pend.get("status") == "pending":
            p_handle = str(pend.get("handle") or "").strip().lstrip("@").lower()
            if (clean_tg_uname and clean_tg_uname == p_handle) or str(user_id) == p_handle:
                pending_u = su
                break
    if pending_u:
        from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"bind_confirm:{pending_u['username']}"),
            InlineKeyboardButton(text="❌ Отказать", callback_data=f"bind_reject:{pending_u['username']}")
        ]])
        p_name = pending_u.get("name") or pending_u["username"]
        is_admin_req = (pending_u.get("role") == "admin" or (pending_u.get("username") or "").lower() in ("skynet83", "admin") or (p_name or "").lower() in ("skynet83", "admin"))
        who = "Администратор" if is_admin_req else f"Пользователь <b>{pending_u['username']}</b>"
        await message.answer(
            f"🔔 <b>Подтверждение привязки к AvitoHunter</b>\n\n"
            f"{who} запросил привязку этого Telegram-аккаунта к программе AvitoHunter.\n\n"
            f"Подтвердить привязку?",
            parse_mode="HTML",
            reply_markup=kb
        )
        return

    site_u, reason = get_authorized_site_user(user_id, username)
    if not site_u or reason is not None:
        await prompt_unauthorized_user(message, user_id, username, full_name, reason or "not_linked")
        return

    is_adm = await is_admin(user_id, username)
    silent = await is_silent_mode(user_id)
    await message.answer(
        "ℹ️ Команда не распознана.\n\n"
        "• Отправьте ссылку на Avito для добавления в персональный мониторинг\n"
        "• Или выберите действие на клавиатуре внизу экрана\n"
        "• Полный список команд: /help",
        reply_markup=get_main_keyboard(is_user_admin=is_adm, is_silent=silent)
    )


# ===================== ТОЧКА ВХОДА =====================

async def get_hybrid_telegram_proxies() -> List[str]:
    """
    Возвращает список прокси для Telegram в гибридном режиме:
    1. Персональные прокси пользователей и админа (наивысший приоритет)
    2. Общий проверенный пул прокси из proxies.txt
    """
    candidates = []
    seen = set()

    # 1. Личные прокси из базы данных SQLite (наивысший приоритет)
    try:
        async with aiosqlite.connect(DATABASE_PATH) as db:
            async with db.execute("SELECT proxy FROM user_proxies WHERE is_alive = 1 ORDER BY id DESC") as cursor:
                for row in await cursor.fetchall():
                    px = (row[0] or "").strip()
                    if px and px not in seen:
                        candidates.append(px)
                        seen.add(px)
    except Exception:
        pass

    # 2. Общий пул прокси
    shared = []
    if hasattr(parser, "proxy_pool") and parser.proxy_pool and parser.proxy_pool.proxies:
        shared = parser.proxy_pool.proxies
    elif os.path.exists(PROXIES_FILE):
        try:
            with open(PROXIES_FILE, "r", encoding="utf-8-sig") as f:
                for l in f:
                    l = l.strip().lstrip("\ufeff")
                    if l and not l.startswith("#"):
                        shared.append(l)
        except Exception:
            pass

    for px in shared:
        if px and px not in seen:
            candidates.append(px)
            seen.add(px)

    return candidates


async def main():
    write_pid_file()
    logger.info(f"Инициализация мультисессионной базы данных (PID {os.getpid()})...")
    await init_db()

    global primary_admin_id
    if ADMIN_CHAT_ID and int(ADMIN_CHAT_ID) > 0:
        primary_admin_id = int(ADMIN_CHAT_ID)
        logger.info(f"Установлен администратор из конфигурации (Telegram ID): {primary_admin_id}")
    else:
        for u in load_site_users():
            if (u.get("role") == "admin" or (u.get("username") or "").lower() in ["skynet83", "skynet19081983"]) and u.get("telegram_chat_id"):
                primary_admin_id = int(u.get("telegram_chat_id"))
                logger.info(f"Загружен администратор из users.json: {primary_admin_id}")
                break
        if not primary_admin_id:
            admin_users = await get_users_by_status("admin")
            for au in admin_users:
                uname = str(au.get("username", "")).lower()
                if not uname.startswith("ebid-") and not uname.startswith("ebmob-") and len(str(au["user_id"])) >= 8:
                    primary_admin_id = au["user_id"]
                    logger.info(f"Загружен администратор из БД: {primary_admin_id}")
                    break

    session = None
    direct_tg_ok = False
    if TELEGRAM_PROXY:
        import urllib.parse
        import socket
        try:
            parsed = urllib.parse.urlparse(TELEGRAM_PROXY)
            host = parsed.hostname or "127.0.0.1"
            port = parsed.port or 80
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            res = sock.connect_ex((host, port))
            sock.close()
            if res == 0:
                logger.info(f"Используется прокси для Telegram: {TELEGRAM_PROXY}")
                session = AiohttpSession(proxy=TELEGRAM_PROXY)
            else:
                logger.warning(f"Прокси Telegram {TELEGRAM_PROXY} недоступен. Пробуем гибридный режим...")
        except Exception as pe:
            logger.warning(f"Ошибка проверки прокси Telegram ({pe})...")
    
    if not session:
        # Проверяем прямое соединение с Telegram
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1.5)
            c_res = sock.connect_ex(("api.telegram.org", 443))
            sock.close()
            if c_res == 0:
                direct_tg_ok = True
        except Exception:
            direct_tg_ok = False

        if not direct_tg_ok:
            logger.warning("🛡️ Прямое соединение с api.telegram.org недоступно. Поиск гибридного прокси (личный в приоритете)...")
            hybrid_pxs = await get_hybrid_telegram_proxies()
            for h_px in hybrid_pxs:
                try:
                    session = AiohttpSession(proxy=h_px)
                    logger.info(f"🟢 Подключение к Telegram через гибридный прокси (личный в приоритете): {h_px}")
                    break
                except Exception:
                    continue

    bot = Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )

    logger.info("Бот запущен в мультисессионном режиме.")

    try:
        commands = [
            BotCommand(command="start", description="Главное меню / Старт"),
            BotCommand(command="login", description="Войти по логину сайта"),
            BotCommand(command="site", description="Открыть сайт SkyBase"),
            BotCommand(command="list", description="Мои поиски Avito"),
            BotCommand(command="check", description="Проверить объявления"),
            BotCommand(command="fav", description="Избранное"),
            BotCommand(command="help", description="Помощь и команды")
        ]
        await bot.set_my_commands(commands)
    except Exception as ce:
        logger.warning(f"Не удалось зарегистрировать команды бота: {ce}")

    monitor_task = asyncio.create_task(background_monitoring_loop(bot))
    harvester_task = asyncio.create_task(background_proxy_harvester(bot))
    chat_sync_task = asyncio.create_task(background_chat_sync_loop(bot))

    # Счётчик неудач — после 3 сбоев пробуем прокси из пула Авито для Telegram
    _tg_fail_count = 0
    _tg_proxy_idx = 0

    try:
        while True:
            try:
                await bot.delete_webhook(drop_pending_updates=False)
                await dp.start_polling(bot, handle_signals=False)
                break
            except Exception as e:
                err_text = str(e).lower()
                if "conflict" in err_text or "terminated by other getupdates" in err_text:
                    logger.warning(f"⚠️ Временный конфликт Telegram API ({e}). Ожидание 15 сек и повтор...")
                    await asyncio.sleep(15)
                    continue
                logger.warning(f"Временный сбой соединения с Telegram API ({e}). Повторная попытка через 5 сек...")
                _tg_fail_count += 1

                if TELEGRAM_PROXY:
                    # Явно задан прокси — используем его
                    try:
                        if hasattr(bot, "session") and bot.session and getattr(bot.session, "closed", False):
                            bot = Bot(
                                token=BOT_TOKEN,
                                session=AiohttpSession(proxy=TELEGRAM_PROXY),
                                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
                            )
                    except Exception:
                        pass
                else:
                    # При сбое — пробуем гибридный прокси (личные в приоритете + общий пул)
                    hybrid_pxs = await get_hybrid_telegram_proxies()
                    if hybrid_pxs and (_tg_fail_count >= 2 or not direct_tg_ok):
                        _tg_proxy_idx = (_tg_proxy_idx + 1) % len(hybrid_pxs)
                        tg_fallback_proxy = hybrid_pxs[_tg_proxy_idx]
                        logger.info(f"🔄 Ротация Telegram на гибридный прокси (личные в приоритете): {tg_fallback_proxy}")
                        try:
                            await bot.session.close()
                        except Exception:
                            pass
                        try:
                            bot = Bot(
                                token=BOT_TOKEN,
                                session=AiohttpSession(proxy=tg_fallback_proxy),
                                default=DefaultBotProperties(parse_mode=ParseMode.HTML)
                            )
                        except Exception as pe:
                            logger.warning(f"Не удалось создать сессию с прокси {tg_fallback_proxy}: {pe}")
                    elif session is not None:
                        logger.info("Пробуем переключиться на прямое соединение без прокси...")
                        try:
                            await bot.session.close()
                        except Exception:
                            pass
                        session = None
                        bot = Bot(
                            token=BOT_TOKEN,
                            session=None,
                            default=DefaultBotProperties(parse_mode=ParseMode.HTML)
                        )
                await asyncio.sleep(5)

    finally:
        monitor_task.cancel()
        harvester_task.cancel()
        chat_sync_task.cancel()
        await bot.session.close()
        remove_pid_file()


if __name__ == "__main__":
    acquire_single_instance_mutex()
    write_pid_file()
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен пользователем.")
    except Exception as e:
        logger.exception(f"Критическая ошибка запуска бота: {e}")
    finally:
        remove_pid_file()
