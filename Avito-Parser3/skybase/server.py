#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyBase Server v2.0 (High-Performance Pure-Python Backend)
-----------------------------------------------------------
Полноценный асинхронный/многопоточный HTTP-сервер для SkyBase:
1. Полная замена устаревшего PowerShell-скрипта server.ps1.
2. 100% совместимость со всеми 73 маршрутами REST API и фронтендом js/app.js.
3. Прямая работа в памяти с avito_api_helper, avito_sniper, hwid_security и ngrok_service.
4. Потокобезопасная работа с файлами data/*.json в кодировке UTF-8 (полный отказ от BOM).
5. Высокоскоростная раздача статических файлов с GZip-сжатием и HTTP-кэшированием.
"""

import os
import sys
from typing import Any, Dict, List, Optional
import time
import json
import gzip
import uuid
import socket
import select
import signal
import struct
import ctypes
import hashlib
import mimetypes
import threading
import subprocess
import shutil
import re
import random
import base64
import traceback
from datetime import datetime, timedelta
from urllib.parse import urlparse, parse_qs, unquote
from http.server import HTTPServer, BaseHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer
except ImportError:
    ThreadingHTTPServer = HTTPServer

# ── Базовые пути и окружение ────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

LIB_DIR = os.path.join(BASE_DIR, "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

TOOLS_DIR = os.path.join(BASE_DIR, "tools")
if os.path.exists(TOOLS_DIR) and TOOLS_DIR not in sys.path:
    sys.path.insert(0, TOOLS_DIR)

DATA_DIR = os.path.join(BASE_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

IMG_DIR = os.path.join(BASE_DIR, "img")
SCHEMATICS_DIR = os.path.join(IMG_DIR, "schematics")
os.makedirs(SCHEMATICS_DIR, exist_ok=True)

USERS_FILE = os.path.join(DATA_DIR, "users.json")
CHAT_FILE = os.path.join(DATA_DIR, "chat_messages.json")
BLACKLIST_FILE = os.path.join(DATA_DIR, "blacklist.json")
ENGINEERING_NOTES_FILE = os.path.join(DATA_DIR, "engineering_notes.json")
WAN_CONFIG_FILE = os.path.join(DATA_DIR, "wan_config.json")
PID_FILE = os.path.join(BASE_DIR, "server.pid")
ACTIVE_TABS_FILE = os.path.join(DATA_DIR, "active_tabs.json")
SERVER_BOOT_TIMESTAMP = int(time.time())

def record_client_tab_ping(tab_id: str = ""):
    try:
        data = {
            "last_ping": time.time(),
            "boot_time": SERVER_BOOT_TIMESTAMP,
            "tab_id": tab_id
        }
        with open(ACTIVE_TABS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# ── Подключение модулей бизнес-логики ─────────────────────────────────────────
try:
    import avito_api_helper
except Exception as _e:
    avito_api_helper = None
    print(f"[!] Предупреждение: avito_api_helper не загружен: {_e}", file=sys.stderr)

try:
    import hwid_security
except Exception:
    hwid_security = None

try:
    import avito_sniper
except Exception:
    avito_sniper = None

try:
    import ngrok_service
except Exception:
    ngrok_service = None

# ── Глобальное состояние сервера ─────────────────────────────────────────────
server_power_state = "running"  # "running" или "off"
server_port = 8081
server_instance = None
recent_visitors = {}  # ip -> dict info
ip_to_mac_cache = {}
cached_raw_stats = None
last_stats_time = 0
last_sniper_status = None
last_sniper_time = 0
machine_request_id = None

# Блокировки для потокобезопасной записи JSON
users_lock = threading.Lock()
chat_lock = threading.Lock()
blacklist_lock = threading.Lock()
notes_lock = threading.Lock()
stats_cache_lock = threading.Lock()
avito_check_lock = threading.Lock()

# Инициализация MIME-типов
mimetypes.init()
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/jpeg", ".jpeg")
mimetypes.add_type("image/x-icon", ".ico")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("audio/mpeg", ".mp3")
mimetypes.add_type("audio/wav", ".wav")
mimetypes.add_type("audio/ogg", ".ogg")
mimetypes.add_type("audio/mp4", ".m4a")


# ── Вспомогательные функции ──────────────────────────────────────────────────
def get_password_hash(plain: str) -> str:
    """Генерирует SHA256-хэш пароля с солью SkyBase (100% совместимо с V1)."""
    if not plain:
        return ""
    salted = plain + "SkyBase_2026_Salt!"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest().lower()


def new_session_token() -> str:
    return uuid.uuid4().hex


def read_json_file(file_path: str, default=None):
    """Безопасное чтение JSON-файла без чувствительности к BOM."""
    if default is None:
        default = []
    if not os.path.exists(file_path):
        return default
    try:
        with open(file_path, "r", encoding="utf-8-sig") as f:
            content = f.read().strip()
            if not content:
                return default
            return json.loads(content)
    except Exception:
        return default


def write_json_file(file_path: str, data, lock: threading.Lock = None):
    """Атомарная запись JSON-файла в чистом UTF-8 (без BOM)."""
    def _do_write():
        tmp_path = file_path + f".tmp_{os.getpid()}_{threading.get_ident()}"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        # Атомарная замена файла
        if sys.platform == "win32":
            # На Windows replace может упасть при гонке, делаем попытки
            for _ in range(5):
                try:
                    os.replace(tmp_path, file_path)
                    break
                except Exception:
                    time.sleep(0.05)
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        else:
            os.replace(tmp_path, file_path)

    if lock:
        with lock:
            _do_write()
    else:
        _do_write()


def get_local_ip() -> str:
    """Определение локального IP-адреса хоста в сети."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"
    finally:
        s.close()


def get_client_mac(ip: str) -> str:
    """Определяет MAC-адрес клиента по IP с помощью Windows API SendARP / arp -a."""
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return ""
    if ip in ip_to_mac_cache:
        return ip_to_mac_cache[ip]

    if sys.platform == "win32":
        try:
            ip_bytes = socket.inet_aton(ip)
            ip_int = struct.unpack("!I", ip_bytes)[0]
            dest_ip = ctypes.c_ulong(socket.ntohl(ip_int))
            mac_bytes = (ctypes.c_byte * 6)()
            mac_len = ctypes.c_ulong(6)
            res = ctypes.windll.iphlpapi.SendARP(dest_ip, 0, ctypes.byref(mac_bytes), ctypes.byref(mac_len))
            if res == 0:
                mac = ":".join(f"{b & 0xff:02X}" for b in mac_bytes)
                ip_to_mac_cache[ip] = mac
                return mac
        except Exception:
            pass

        try:
            out = subprocess.check_output(["arp", "-a", ip], text=True, timeout=1, creationflags=CREATE_NO_WINDOW)
            for line in out.splitlines():
                if ip in line:
                    m = re.search(r"([0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2}[:-][0-9a-fA-F]{2})", line)
                    if m:
                        mac = m.group(1).upper().replace("-", ":")
                        ip_to_mac_cache[ip] = mac
                        return mac
        except Exception:
            pass

    return ""


def get_machine_request_id() -> str:
    """Возвращает уникальный идентификатор оборудования EBID-..."""
    global machine_request_id
    if machine_request_id:
        return machine_request_id
    try:
        if hwid_security:
            fp = hwid_security.get_local_hwid_fingerprint()
            if fp and fp.get("request_id"):
                machine_request_id = fp["request_id"]
                return machine_request_id
    except Exception:
        pass
    machine_request_id = "EBID-" + hashlib.md5(socket.gethostname().encode("utf-8")).hexdigest()[:12].upper()
    return machine_request_id


def is_blacklisted(mac: str, ip: str, username: str) -> bool:
    """Проверяет, заблокирован ли клиент в ЧС."""
    if username and username.lower() == "skynet83":
        return False
    entries = read_json_file(BLACKLIST_FILE, default=[])
    if not entries:
        return False
    norm_mac = mac.upper().replace("-", ":").strip() if mac else ""
    norm_ip = ip.strip() if ip else ""
    norm_user = username.lower().strip() if username else ""
    is_loopback = norm_ip in ("127.0.0.1", "::1", "localhost")

    for b in entries:
        b_u = (b.get("username") or "").lower().strip()
        b_m = (b.get("mac") or "").upper().replace("-", ":").strip()
        b_i = (b.get("ip") or "").strip()
        if norm_user and b_u and norm_user == b_u:
            return True
        if norm_mac and b_m and norm_mac == b_m:
            return True
        if not is_loopback and norm_ip and b_i and norm_ip == b_i:
            return True
    return False


# Ошибки штатного разрыва соединения клиентом
_DISCONNECT_ERRORS = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)


def is_client_disconnect(exc) -> bool:
    if not exc:
        return False
    if isinstance(exc, _DISCONNECT_ERRORS):
        return True
    if isinstance(exc, OSError):
        if getattr(exc, "winerror", None) in (10053, 10054, 10038, 10058):
            return True
        if getattr(exc, "errno", None) in (10053, 10054, 32):
            return True
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause and cause is not exc:
        return is_client_disconnect(cause)
    return False


# ── HTTP Request Handler ─────────────────────────────────────────────────────
class SkyBaseHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # Отключаем встроенный спам логов веб-сервера
        pass

    def handle(self):
        try:
            super().handle()
        except Exception as e:
            if not is_client_disconnect(e):
                traceback.print_exc()

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Session-Token")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_json(self, status_code: int, data: Any):
        import inspect
        if inspect.iscoroutine(data):
            try:
                import asyncio
                data = asyncio.run(data)
            except Exception as e:
                data = {"success": False, "error": str(e)}
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status_code)
            self.send_cors_headers()
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            if not is_client_disconnect(e):
                pass

    def send_html(self, status_code: int, html_str: str):
        body = html_str.encode("utf-8")
        try:
            self.send_response(status_code)
            self.send_cors_headers()
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            if not is_client_disconnect(e):
                pass

    def read_post_body(self) -> dict:
        content_len = int(self.headers.get("Content-Length", 0))
        if content_len <= 0:
            return {}
        try:
            raw = self.rfile.read(content_len).decode("utf-8", errors="ignore")
            if not raw.strip():
                return {}
            return json.loads(raw)
        except Exception:
            return {}

    def get_query_param(self, name: str, default: str = "") -> str:
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        vals = qs.get(name, [])
        return vals[0].strip() if vals else default

    def get_remote_ip(self) -> str:
        for h in ["X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP"]:
            val = self.headers.get(h)
            if val:
                return val.split(",")[0].strip()
        if self.client_address:
            return self.client_address[0]
        return "127.0.0.1"

    def record_visitor(self, remote_ip: str, client_mac: str, path: str):
        ua = self.headers.get("User-Agent", "")
        is_mob = bool(re.search(r"Mobile|Android|iPhone|iPad|iPod|webOS|BlackBerry", ua, re.I))
        device_label = "Телефон / Планшет" if is_mob else "Компьютер (ПК)"
        recent_visitors[remote_ip] = {
            "ip": remote_ip,
            "mac": client_mac or "—",
            "device": device_label,
            "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "last_path": path
        }

    def resolve_user_profile(self, username_or_id: str = "", req_id: str = "") -> tuple[dict, list]:
        """
        Определяет изолированный профиль пользователя по Request ID (ID оборудования).
        ID компьютера или телефона выступает в роли уникального логина:
        у каждого ID свои ссылки, интервал, настройки и чаты.
        """
        users = read_json_file(USERS_FILE, default=[])
        target_id = ""
        clean_in = (username_or_id or "").strip()
        clean_req = (req_id or "").strip()
        remote_ip = self.get_remote_ip()

        # 1. Если явно передан Request ID (EBID-... или EBMOB-...)
        if clean_req and clean_req.upper().startswith("EB"):
            target_id = clean_req.upper()
        elif clean_in and clean_in.upper().startswith("EB"):
            target_id = clean_in.upper()

        # 2. Если запрос локальный (с самого ПК-сервера) и ID не передан явно
        if not target_id and remote_ip in ("127.0.0.1", "::1", "localhost", ""):
            target_id = get_machine_request_id()

        # 3. Если запрос из локальной сети по IP
        if not target_id and remote_ip:
            client_mac = get_client_mac(remote_ip)
            if client_mac:
                import devices_db
                try:
                    for d in devices_db.get_all_devices():
                        if (d.get("mac") or "").upper() == client_mac.upper():
                            target_id = d.get("request_id", "")
                            break
                except Exception:
                    pass
                if not target_id:
                    mac_clean = client_mac.upper().replace(":", "").replace("-", "")
                    target_id = f"EBID-{mac_clean[-4:]}-LAN-{mac_clean[:4]}".upper()

        # 4. Fallback если ничего не определилось
        if not target_id:
            if clean_in and clean_in.lower() not in ("skynet83", "admin", "null", "undefined"):
                target_id = clean_in
            else:
                target_id = get_machine_request_id()

        matched_u = None
        for u in users:
            u_req = (u.get("request_id") or "").strip().upper()
            u_name = (u.get("username") or "").strip().upper()
            if target_id.upper() in (u_req, u_name):
                matched_u = u
                break

        # Если не найден — создаем новый изолированный профиль для данного ID
        if not matched_u:
            dev_label = "Телефон" if target_id.startswith("EBMOB") else "ПК"
            short_id = target_id[:14] if len(target_id) > 14 else target_id
            matched_u = {
                "username": target_id,
                "request_id": target_id,
                "name": f"{dev_label}-{short_id}",
                "role": "user",
                "last_ip": remote_ip or "127.0.0.1",
                "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "target_interval": "1",
                "active_interval": "1",
                "permissions": {
                    "avito": False,
                    "avito_bot": False,
                    "avito_duration": "none",
                    "avito_expires_at": None,
                    "target_interval": "1",
                    "unlimited": False,
                    "is_expired": True,
                    "hwid_mac": get_client_mac(remote_ip) if remote_ip else "",
                    "hwid_request_id": target_id,
                    "active_key": None,
                    "tg_bot": False,
                    "monitoring": False,
                    "max_searches": 10
                },
                "avito_searches": [],
                "telegram_chat_id": None,
                "telegram_username": None,
                "telegram_pending": None,
                "proxies": []
            }
            users.append(matched_u)
            write_json_file(USERS_FILE, users, users_lock)

        # Роль admin назначается администратору, но Telegram-аккаунт НИКОГДА не привязывается автоматически!
        # И обычный пользователь, и администратор ОБЯЗАНЫ подтвердить привязку своего аккаунта в боте самостоятельно.
        site_tg = (matched_u.get("telegram_username") or "").strip().lstrip("@").lower()
        site_cid = matched_u.get("telegram_chat_id")
        if (site_tg in ("skynet19081983", "skynet83") or (site_cid and str(site_cid).strip() == "5680198246") or (matched_u.get("username", "").lower() in ("skynet83", "admin"))):
            matched_u["role"] = "admin"
        else:
            matched_u["role"] = matched_u.get("role", "user")

        return matched_u, users

    # ── Основной роутер GET ──────────────────────────────────────────────────
    def do_GET(self):
        parsed = urlparse(self.path)
        url_path = parsed.path
        remote_ip = self.get_remote_ip()
        client_mac = get_client_mac(remote_ip)
        self.record_visitor(remote_ip, client_mac, url_path)

        # 0. Проверка ЧС
        q_user = self.get_query_param("username")
        if is_blacklisted(client_mac, remote_ip, q_user):
            self.render_blacklisted_page(remote_ip, client_mac)
            return

        # 1. API Сервера
        if url_path == "/api/server/live-check":
            q_tab = self.get_query_param("tab_id") or ""
            record_client_tab_ping(q_tab)
            self.send_json(200, {
                "success": True,
                "boot_time": SERVER_BOOT_TIMESTAMP,
                "server_time": time.time()
            })
            return

        if url_path == "/api/server/power-state":
            self.send_json(200, {
                "success": True,
                "state": server_power_state,
                "backend_port": server_port,
                "gateway_port": 80
            })
            return

        if url_path in ("/api/server/network-info", "/api/server/info", "/api/server/visitors"):
            loc_ip = get_local_ip()
            vis_list = list(recent_visitors.values())
            self.send_json(200, {
                "success": True,
                "port": 80,
                "local_ip": loc_ip,
                "network_url": f"http://{loc_ip}",
                "network_access": True,
                "visitors": vis_list
            })
            return

        if url_path in ("/api/server/ngrok", "/api/server/ngrok/status"):
            if ngrok_service:
                self.send_json(200, ngrok_service.check_status())
            else:
                self.send_json(200, {"running": False, "url": None, "message": "Ngrok service unavailable"})
            return

        if url_path == "/api/server/wan/config":
            if ngrok_service:
                self.send_json(200, ngrok_service.get_masked_config())
            else:
                self.send_json(200, {})
            return

        # 2. Если сервер выключен (режим ожидания) — блокируем тяжелые API
        if server_power_state == "off" and url_path.startswith("/api/"):
            if url_path not in ("/api/me", "/api/login", "/api/logout"):
                self.send_json(503, {
                    "success": False,
                    "error": "server_off",
                    "message": "Основной сервер выключен",
                    "state": "off"
                })
                return

        # 3. Аутентификация и пользователи
        if url_path == "/api/me":
            self.handle_api_me(remote_ip, client_mac)
            return

        if url_path == "/api/users":
            self.handle_api_users(remote_ip, client_mac)
            return

        if url_path == "/api/users/avito-searches":
            self.handle_api_users_avito_searches()
            return

        # 4. Чат
        if url_path == "/api/chat/messages":
            self.handle_api_chat_messages(remote_ip)
            return

        # 5. Лицензия и HWID
        if url_path == "/api/license/status":
            self.handle_api_license_status(remote_ip)
            return

        if url_path == "/api/license/client_id":
            self.handle_api_license_client_id()
            return

        # 6. Avito Мониторинг
        if url_path == "/api/avito/stats":
            self.handle_api_avito_stats()
            return

        if url_path == "/api/avito/searches":
            self.handle_api_avito_searches()
            return

        if url_path == "/api/avito/fetch-all":
            self.handle_api_avito_fetch_all()
            return

        if url_path == "/api/avito/interval":
            self.handle_api_avito_interval()
            return

        if url_path == "/api/avito/proxies":
            self.handle_api_avito_proxies()
            return

        if url_path == "/api/avito/item/reviews":
            self.handle_api_avito_item_reviews()
            return

        if url_path == "/api/avito/item/details":
            self.handle_api_avito_item_details()
            return

        if url_path == "/api/avito/proxy-image":
            self.handle_api_avito_proxy_image()
            return

        if url_path == "/api/avito/users":
            res = avito_api_helper.get_users() if avito_api_helper else {"success": True, "users": []}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/blacklist":
            res = avito_api_helper.get_blacklist() if avito_api_helper else {"success": True, "blacklist": []}
            self.send_json(200, res)
            return

        # 7. Sniper
        if url_path == "/api/avito/sniper/status":
            self.handle_api_sniper_status()
            return

        if url_path == "/api/avito/sniper/config":
            cfg = avito_sniper.get_config() if avito_sniper else {}
            self.send_json(200, {"success": True, "config": cfg})
            return

        if url_path in ("/api/avito/sniper/open-review", "/api/avito/sniper/review"):
            item_id = self.get_query_param("item_id")
            item_url = self.get_query_param("url") or self.get_query_param("item_url")
            self.handle_sniper_open_review({"item_id": item_id, "item_url": item_url})
            return

        # 8. Звуки оповещения
        if url_path == "/api/sound/list":
            self.handle_api_sound_list()
            return

        # 9. Статические файлы
        self.serve_static_file(url_path)

    # ── Основной роутер POST ─────────────────────────────────────────────────
    def do_POST(self):
        parsed = urlparse(self.path)
        url_path = parsed.path
        remote_ip = self.get_remote_ip()
        client_mac = get_client_mac(remote_ip)
        body = self.read_post_body()

        # 0. Проверка ЧС
        user_name = body.get("username") or self.get_query_param("username")
        if is_blacklisted(client_mac, remote_ip, user_name):
            self.send_json(403, {"success": False, "error": "blacklisted", "message": "Доступ заблокирован администратором"})
            return

        # 1. API управления сервером
        if url_path == "/api/server/start":
            self.handle_server_start()
            return

        if url_path in ("/api/server/shutdown", "/api/shutdown"):
            self.handle_server_shutdown()
            return

        if url_path in ("/api/server/restart", "/api/restart"):
            self.handle_server_restart()
            return

        if url_path == "/api/server/ngrok/toggle":
            self.handle_ngrok_toggle(body)
            return

        if url_path == "/api/server/wan/config":
            self.handle_wan_config_save(body)
            return

        # 2. Если сервер выключен — блокируем запросы
        if server_power_state == "off" and url_path not in ("/api/login", "/api/logout"):
            self.send_json(503, {
                "success": False,
                "error": "server_off",
                "message": "Основной сервер выключен",
                "state": "off"
            })
            return

        # 3. Аутентификация
        if url_path == "/api/login":
            self.handle_api_login(body, remote_ip, client_mac)
            return

        if url_path == "/api/register":
            self.handle_api_register(body, remote_ip, client_mac)
            return

        if url_path == "/api/logout":
            self.send_json(200, {"success": True})
            return

        if url_path == "/api/users/delete":
            self.handle_api_users_delete(body)
            return

        if url_path in ("/api/users/blacklist/add", "/api/blacklist/add"):
            self.handle_api_blacklist_add(body)
            return

        if url_path in ("/api/users/blacklist/remove", "/api/blacklist/remove"):
            self.handle_api_blacklist_remove(body)
            return

        if url_path == "/api/users/permission":
            self.handle_api_users_permission(body)
            return

        if url_path == "/api/user/telegram":
            self.handle_api_user_telegram(body)
            return

        if url_path == "/api/user/telegram/cancel":
            self.handle_api_user_telegram_cancel(body)
            return

        if url_path == "/api/avito/notify-bind-success":
            self.handle_api_avito_notify_bind_success(body)
            return

        # 4. Чат
        if url_path == "/api/chat/send":
            self.handle_api_chat_send(body)
            return

        if url_path == "/api/chat/read":
            self.handle_api_chat_read(body)
            return

        if url_path == "/api/chat/edit-welcome":
            self.handle_api_chat_edit_welcome(body)
            return

        if url_path == "/api/chat/edit":
            self.handle_api_chat_edit(body)
            return

        if url_path == "/api/chat/delete":
            self.handle_api_chat_delete(body)
            return

        if url_path == "/api/chat/clear":
            self.handle_api_chat_clear()
            return

        # 5. Лицензия
        if url_path == "/api/license/activate":
            self.handle_api_license_activate(body, remote_ip)
            return

        if url_path == "/api/license/request-trial":
            self.handle_api_license_request_trial(body, remote_ip)
            return

        # 6. Схемы
        if url_path == "/api/upload-circuit":
            self.handle_api_upload_circuit(body)
            return

        # 7. Avito Мониторинг
        global last_stats_time, cached_raw_stats
        last_stats_time = 0  # Сбрасываем кэш статов при любых изменениях

        if url_path == "/api/avito/add-search":
            self.handle_api_avito_add_search(body)
            return

        if url_path == "/api/avito/delete-search":
            self.handle_api_avito_delete_search(body)
            return

        if url_path == "/api/avito/toggle-search":
            self.handle_api_avito_toggle_search(body)
            return

        if url_path == "/api/avito/edit-search":
            self.handle_api_avito_edit_search(body)
            return

        if url_path == "/api/avito/update-search-settings":
            self.handle_api_avito_update_search_settings(body)
            return

        if url_path == "/api/avito/activate-pending-searches":
            self.handle_api_avito_activate_pending_searches(body)
            return

        if url_path == "/api/avito/check":
            self.handle_api_avito_check()
            return

        if url_path == "/api/avito/fetch-all":
            self.handle_api_avito_fetch_all(body)
            return

        if url_path == "/api/avito/bot-toggle":
            action = body.get("action", "start")
            res = avito_api_helper.bot_toggle(action) if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/monitor-toggle":
            action = body.get("action", "toggle")
            res = avito_api_helper.set_monitor_state(action) if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/interval":
            self.handle_api_avito_interval(body)
            return

        if url_path in ("/api/avito/proxies/fetch", "/api/avito/proxies/stop"):
            action = "stop" if url_path.endswith("/stop") else body.get("action", "start")
            source = body.get("source", "manual")
            uname = body.get("username") or self.get_query_param("username")
            res = avito_api_helper.fetch_proxies(action, source, username=uname) if avito_api_helper else {"success": True}
            with stats_cache_lock:
                cached_raw_stats = None
                last_stats_time = 0
            self.send_json(200, res)
            return

        if url_path == "/api/avito/apply-rules":
            mon = bool(body.get("monitoring", False))
            tg = bool(body.get("tg_bot", False))
            uname = body.get("username") or self.get_query_param("username")
            res = avito_api_helper.apply_automation_rules(mon, tg, username=uname) if avito_api_helper else {"success": True}
            with stats_cache_lock:
                cached_raw_stats = None
                last_stats_time = 0
            self.send_json(200, res)
            return

        if url_path == "/api/avito/proxies/add":
            txt = body.get("proxies", "")
            uname = body.get("username") or self.get_query_param("username")
            res = avito_api_helper.add_proxies(txt, uname) if avito_api_helper else {"success": True}
            with stats_cache_lock:
                cached_raw_stats = None
                last_stats_time = 0
            self.send_json(200, res)
            return

        if url_path == "/api/avito/proxies/delete":
            px = body.get("proxy", "")
            uname = body.get("username") or self.get_query_param("username")
            res = avito_api_helper.del_proxy(px, uname) if avito_api_helper else {"success": True}
            with stats_cache_lock:
                cached_raw_stats = None
                last_stats_time = 0
            self.send_json(200, res)
            return

        if url_path == "/api/avito/proxies/clear":
            uname = body.get("username") or self.get_query_param("username")
            res = avito_api_helper.clear_proxies(uname) if avito_api_helper else {"success": True}
            with stats_cache_lock:
                cached_raw_stats = None
                last_stats_time = 0
            self.send_json(200, res)
            return

        if url_path == "/api/avito/proxies/check":
            uname = body.get("username") or self.get_query_param("username")
            res = avito_api_helper.check_proxies(uname) if avito_api_helper else {"success": True}
            with stats_cache_lock:
                cached_raw_stats = None
                last_stats_time = 0
            self.send_json(200, res)
            return

        if url_path == "/api/avito/users/status":
            uid = int(body.get("user_id", 0))
            st = body.get("status", "approved")
            res = avito_api_helper.set_user_status(uid, st) if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/items/sync-batch":
            if avito_api_helper:
                import asyncio
                ids_list = body.get("item_ids") if isinstance(body, dict) else (body if isinstance(body, list) else None)
                lim = int(body.get("limit", 2)) if isinstance(body, dict) else 2
                lim = min(lim, 2)
                try:
                    res = asyncio.run(asyncio.wait_for(avito_api_helper.verify_and_sync_items(ids_list, limit=lim), timeout=12.0))
                except Exception:
                    res = {"success": True, "updated": [], "removed": [], "has_more": False}
            else:
                res = {"success": True, "updated": [], "removed": [], "has_more": False}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/items/cleanup":
            res = avito_api_helper.cleanup_legacy_ads() if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/items/clear":
            s_name = body.get("search_name") or self.get_query_param("search_name")
            keep = body.get("keep_ids", [])
            keep_str = ",".join(str(x) for x in keep) if isinstance(keep, list) else str(keep)
            res = avito_api_helper.clear_all_items(s_name, keep_str) if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/favorites/toggle":
            iid = body.get("item_id", "")
            res = avito_api_helper.toggle_favorite(str(iid)) if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/items/delete":
            iid = body.get("item_id", "")
            res = avito_api_helper.delete_single_item(str(iid)) if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/blacklist/add":
            seller = body.get("seller", "")
            item_id = body.get("item_id", "")
            city = body.get("city", "")
            res = avito_api_helper.add_blacklist(seller_name=seller, item_id=str(item_id) if item_id else None, city=city) if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        if url_path in ("/api/avito/blacklist/delete", "/api/avito/blacklist/remove"):
            seller = body.get("seller", "")
            item_id = body.get("item_id", "")
            city = body.get("city", "")
            res = avito_api_helper.del_blacklist(seller_name=seller, item_id=str(item_id) if item_id else None, city=city) if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        if url_path == "/api/avito/blacklist/clear":
            res = avito_api_helper.clear_blacklist() if avito_api_helper else {"success": True}
            self.send_json(200, res)
            return

        # 8. Sniper Actions
        if url_path == "/api/avito/sniper/login":
            reauth = self.get_query_param("reauth") == "1"
            if avito_sniper:
                try:
                    import asyncio
                    asyncio.run(avito_sniper.open_login_window(reauth=reauth))
                except Exception:
                    pass
                res = {"success": True, "message": "Вкладка открыта в существующем браузере"}
            else:
                res = {"success": True, "message": "Авторизация в браузере"}
            self.send_json(200, res)
            return

        if url_path in ("/api/avito/sniper/open-review", "/api/avito/sniper/review"):
            self.handle_sniper_open_review(body)
            return

        if url_path == "/api/avito/sniper/config":
            if avito_sniper:
                avito_sniper.save_config(body)
            cfg = avito_sniper.get_config() if avito_sniper else {}
            self.send_json(200, {"success": True, "config": cfg})
            return

        if url_path == "/api/avito/sniper/checkout":
            self.handle_sniper_checkout(body)
            return

        if url_path == "/api/avito/sniper/checkout-preview":
            self.handle_sniper_checkout_preview(body)
            return

        if url_path == "/api/avito/sniper/checkout-confirm":
            self.handle_sniper_checkout_confirm(body)
            return

        if url_path == "/api/avito/sniper/message":
            self.handle_sniper_message(body)
            return

        if url_path == "/api/avito/sniper/cancel-order":
            self.handle_sniper_cancel_order(body)
            return

        if url_path == "/api/avito/sniper/check-cart-orders":
            self.handle_sniper_check_cart_orders(body)
            return

        # 9. Управление звуками оповещения
        if url_path == "/api/sound/custom-upload":
            self.handle_api_sound_custom_upload(body)
            return

        if url_path == "/api/sound/load-by-path":
            self.handle_api_sound_load_by_path(body)
            return

        self.send_json(404, {"success": False, "error": "Not Found"})

    # ── Детальные обработчики API ─────────────────────────────────────────────
    def handle_server_start(self):
        global server_power_state
        server_power_state = "running"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [ВКЛЮЧЕНИЕ] Запуск служб и Telegram-бота...")
        try:
            if avito_api_helper:
                avito_api_helper.bot_toggle("start")
                avito_api_helper.fetch_proxies("start", "auto")
        except Exception as e:
            print(f"[!] Ошибка запуска фоновых процессов: {e}", file=sys.stderr)
        self.send_json(200, {"success": True, "state": "running", "message": "Сервер и Telegram-бот успешно запущены!"})

    def handle_server_shutdown(self):
        global server_power_state
        server_power_state = "off"
        print(f"[{datetime.now().strftime('%H:%M:%S')}] [ДЕЖУРНЫЙ РЕЖИМ] Остановка фоновых служб...")
        try:
            if avito_api_helper:
                avito_api_helper.bot_toggle("stop")
                avito_api_helper.fetch_proxies("stop")
        except Exception:
            pass
        self.send_json(200, {"success": True, "state": "off", "message": "Сервер переведен в спящий режим"})
        # Если запущены как бэкенд на порту 8081 под gateway.py — завершаем процесс
        if server_port == 8081:
            def _delayed_exit():
                time.sleep(0.5)
                os._exit(0)
            threading.Thread(target=_delayed_exit, daemon=True).start()

    def handle_server_restart(self):
        self.send_json(200, {"success": True, "message": "Сервер перезапускается..."})
        def _do_restart():
            time.sleep(0.4)
            try:
                if avito_api_helper:
                    avito_api_helper.bot_toggle("stop")
            except Exception:
                pass
            # Запускаем новый экземпляр
            if os.environ.get("GATEWAY_PORT"):
                # gateway.py сам перезапустит бэкенд
                os._exit(0)
            else:
                bat = os.path.join(BASE_DIR, "start_server.bat")
                if os.path.exists(bat):
                    subprocess.Popen(["cmd.exe", "/c", bat], cwd=BASE_DIR, creationflags=CREATE_NO_WINDOW)
                os._exit(0)
        threading.Thread(target=_do_restart, daemon=True).start()

    def handle_ngrok_toggle(self, body: dict):
        if not ngrok_service:
            self.send_json(200, {"success": False, "error": "ngrok_service not loaded"})
            return
        action = body.get("action", "toggle")
        if action == "start":
            res = ngrok_service.start_tunnel()
        elif action in ("stop", "abort"):
            res = ngrok_service.stop_tunnel()
        elif action in ("status", "info"):
            res = ngrok_service.check_status()
        else:
            cur = ngrok_service.check_status()
            res = ngrok_service.stop_tunnel() if cur.get("running") else ngrok_service.start_tunnel()
        self.send_json(200, res)

    def handle_wan_config_save(self, body: dict):
        if not ngrok_service:
            self.send_json(200, {"success": False})
            return
        cfg = ngrok_service.get_config()
        for k, v in body.items():
            cfg[k] = v
        ok = ngrok_service.save_config(cfg)
        self.send_json(200 if ok else 500, {"success": ok, "config": ngrok_service.get_masked_config()})

    # ── Аутентификация и сессии ──────────────────────────────────────────────
    def handle_api_me(self, remote_ip: str, client_mac: str):
        q_user = self.get_query_param("username")
        q_req_id = self.get_query_param("request_id")
        q_token = self.get_query_param("token") or self.headers.get("X-Session-Token", "")

        matched_u, users = self.resolve_user_profile(q_user, req_id=q_req_id)
        if not matched_u:
            self.send_json(200, {"success": False, "error": "Пользователь не найден"})
            return

        # Проверка сессии (1 ПК и 1 телефон)
        if q_token:
            sessions = matched_u.setdefault("sessions", {})
            d_token = sessions.get("desktop", {}).get("token")
            m_token = sessions.get("mobile", {}).get("token")
            leg_token = matched_u.get("session_token")

            ua = self.headers.get("User-Agent", "")
            is_mob = bool(re.search(r"Mobile|Android|iPhone|iPad|iPod|webOS|BlackBerry", ua, re.I))
            slot = "mobile" if is_mob else "desktop"
            is_local = remote_ip in ("127.0.0.1", "::1", "localhost") or remote_ip.startswith("127.")

            # Если сессий в базе еще нет — инициализируем сессию для клиента
            if not d_token and not m_token:
                tok_to_use = q_token or leg_token or new_session_token()
                sessions[slot] = {
                    "token": tok_to_use,
                    "last_ip": remote_ip,
                    "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "device_type": slot
                }
                matched_u["session_token"] = tok_to_use
                d_token = sessions.get("desktop", {}).get("token")
                m_token = sessions.get("mobile", {}).get("token")
                leg_token = tok_to_use
                write_json_file(USERS_FILE, users, users_lock)

            # На localhost (хост-машина) рабочий стол всегда легитимен и обновляет свой токен
            elif is_local and slot == "desktop" and q_token not in (d_token, m_token, leg_token):
                sessions["desktop"] = {
                    "token": q_token,
                    "last_ip": remote_ip,
                    "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "device_type": "desktop"
                }
                matched_u["session_token"] = q_token
                d_token = q_token
                leg_token = q_token
                write_json_file(USERS_FILE, users, users_lock)

            is_valid_tok = q_token in (d_token, m_token, leg_token)
            if not is_valid_tok:
                dev_txt = "другого телефона" if is_mob else "другого компьютера"
                self.send_json(401, {
                    "success": False,
                    "error": "session_expired",
                    "message": f"⚠️ Доступ прекращен: выполнен вход с {dev_txt} (разрешен 1 компьютер и 1 телефон)"
                })
                return

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            if q_token == d_token and "desktop" in sessions:
                sessions["desktop"]["last_seen"] = now_str
                sessions["desktop"]["last_ip"] = remote_ip
            elif q_token == m_token and "mobile" in sessions:
                sessions["mobile"]["last_seen"] = now_str
                sessions["mobile"]["last_ip"] = remote_ip

        if not matched_u.get("session_token"):
            matched_u["session_token"] = new_session_token()
        matched_u["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        matched_u["last_ip"] = remote_ip
        if client_mac:
            matched_u["last_mac"] = client_mac

        # Проверка истечения тарифа
        is_expired = False
        perms = matched_u.get("permissions", {})
        if avito_api_helper:
            try:
                lic_st = avito_api_helper.get_license_status_info(matched_u.get("username") or "", remote_ip)
                if lic_st:
                    if lic_st.get("is_expired") is True:
                        is_expired = True
                    elif lic_st.get("is_expired") is False:
                        is_expired = False
                        # Автоматически синхронизируем актуальную лицензию в профиль пользователя
                        perms["is_expired"] = False
                        if lic_st.get("active_key"):
                            perms["active_key"] = lic_st.get("active_key")
                        if lic_st.get("expires_at"):
                            perms["avito_expires_at"] = lic_st.get("expires_at")
                        if lic_st.get("duration") and lic_st.get("duration") != "none":
                            perms["avito_duration"] = lic_st.get("duration")
                        perms["avito"] = True
                        perms["avito_bot"] = True
            except Exception:
                pass
        if not is_expired and (not avito_api_helper or lic_st is None):
            if perms.get("is_expired") is True:
                is_expired = True
            elif not perms.get("active_key") and perms.get("avito_duration") != "unlimited":
                is_expired = True
            elif perms.get("avito_expires_at"):
                try:
                    exp_dt = datetime.strptime(perms["avito_expires_at"], "%Y-%m-%d %H:%M:%S")
                    if datetime.now() > exp_dt:
                        is_expired = True
                except Exception:
                    pass

        is_admin_user = (matched_u.get("role") == "admin") or (matched_u.get("username", "").lower() == "skynet83")
        has_bot = not is_expired and (is_admin_user or bool(perms.get("avito_bot") or perms.get("avito")))

        safe_perms = {
            "avito_bot": has_bot,
            "avito": has_bot,
            "tg_bot": False if is_expired else (bool(perms.get("tg_bot")) if "tg_bot" in perms else has_bot),
            "monitoring": False if is_expired else (bool(perms.get("monitoring")) if "monitoring" in perms else True),
            "avito_duration": perms.get("avito_duration", "none"),
            "avito_expires_at": perms.get("avito_expires_at"),
            "is_expired": is_expired,
            "max_searches": min(10, 10 if is_admin_user else int(perms.get("max_searches", 1)))
        }

        # Сохраняем обновленные last_seen
        write_json_file(USERS_FILE, users, users_lock)

        self.send_json(200, {
            "success": True,
            "user": {
                "username": matched_u.get("username"),
                "name": matched_u.get("name") or matched_u.get("username"),
                "role": matched_u.get("role", "admin"),
                "last_ip": matched_u.get("last_ip", remote_ip),
                "last_seen": matched_u.get("last_seen"),
                "session_token": matched_u.get("session_token"),
                "permissions": safe_perms,
                "telegram_chat_id": matched_u.get("telegram_chat_id"),
                "telegram_username": matched_u.get("telegram_username"),
                "telegram_pending": matched_u.get("telegram_pending"),
                "target_interval": matched_u.get("target_interval", "60"),
                "active_interval": matched_u.get("active_interval", matched_u.get("target_interval", "60")),
                "avito_searches": matched_u.get("avito_searches", []),
                "plain_password": matched_u.get("plain_password", "")
            }
        })

    def handle_api_login(self, body: dict, remote_ip: str, client_mac: str):
        target_user = (body.get("username") or "").strip()
        target_pass = (body.get("password") or "").strip()
        target_hash = get_password_hash(target_pass)

        users = read_json_file(USERS_FILE, default=[])
        matched_u = None

        for u in users:
            u_name = (u.get("username") or "").strip().lower()
            if u_name == target_user.lower():
                pwd = u.get("password", "")
                plain = u.get("plain_password", "")
                if pwd in (target_hash, target_pass) or plain == target_pass:
                    matched_u = u
                    break

        if not matched_u:
            self.send_json(401, {"success": False, "error": "Неверный логин или пароль"})
            return

        ua = self.headers.get("User-Agent", "")
        dev_type = (body.get("device_type") or "").lower()
        is_mob = (dev_type in ("mobile", "phone")) or bool(re.search(r"Mobile|Android|iPhone|iPad|iPod|webOS|BlackBerry", ua, re.I))
        slot = "mobile" if is_mob else "desktop"

        session_tok = new_session_token()
        sessions = matched_u.setdefault("sessions", {})
        sessions[slot] = {
            "token": session_tok,
            "last_ip": remote_ip,
            "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "device_type": slot,
            "user_agent": ua
        }
        matched_u["session_token"] = session_tok
        matched_u["last_ip"] = remote_ip
        if client_mac:
            matched_u["last_mac"] = client_mac
        matched_u["last_seen"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if target_pass:
            matched_u["plain_password"] = target_pass
            matched_u["password"] = target_hash

        # Проверка срока действия тарифа
        is_expired = False
        perms = matched_u.get("permissions", {})
        if matched_u.get("role") != "admin" and perms.get("avito_expires_at"):
            try:
                exp_dt = datetime.strptime(perms["avito_expires_at"], "%Y-%m-%d %H:%M:%S")
                if datetime.now() > exp_dt:
                    is_expired = True
            except Exception:
                pass

        is_admin_user = (matched_u.get("role") == "admin") or (matched_u.get("username", "").lower() == "skynet83")
        has_bot = is_admin_user or (not is_expired and bool(perms.get("avito_bot") or perms.get("avito")))

        user_perms = {
            "avito_bot": has_bot,
            "avito": has_bot,
            "tg_bot": False if is_expired else (bool(perms.get("tg_bot")) if "tg_bot" in perms else has_bot),
            "monitoring": False if is_expired else (bool(perms.get("monitoring")) if "monitoring" in perms else True),
            "avito_duration": perms.get("avito_duration", "none"),
            "avito_expires_at": perms.get("avito_expires_at"),
            "is_expired": is_expired,
            "max_searches": min(10, 10 if is_admin_user else int(perms.get("max_searches", 1)))
        }

        write_json_file(USERS_FILE, users, users_lock)

        self.send_json(200, {
            "success": True,
            "session_token": session_tok,
            "user": {
                "username": matched_u.get("username"),
                "name": matched_u.get("name"),
                "role": matched_u.get("role"),
                "last_ip": matched_u.get("last_ip"),
                "last_seen": matched_u.get("last_seen"),
                "session_token": session_tok,
                "permissions": user_perms,
                "telegram_chat_id": matched_u.get("telegram_chat_id"),
                "telegram_username": matched_u.get("telegram_username"),
                "telegram_pending": matched_u.get("telegram_pending"),
                "target_interval": matched_u.get("target_interval", "60"),
                "active_interval": matched_u.get("active_interval", matched_u.get("target_interval", "60")),
                "avito_searches": matched_u.get("avito_searches", []),
                "plain_password": matched_u.get("plain_password", target_pass)
            }
        })

    def handle_api_register(self, body: dict, remote_ip: str, client_mac: str):
        target_user = (body.get("username") or "").strip()
        plain_pass = (body.get("password") or "").strip()
        name = (body.get("name") or "").strip() or target_user

        if not target_user or not plain_pass:
            self.send_json(400, {"success": False, "error": "Логин и пароль обязательны"})
            return

        users = read_json_file(USERS_FILE, default=[])
        for u in users:
            if (u.get("username") or "").strip().lower() == target_user.lower():
                self.send_json(200, {"success": False, "error": "Пользователь с таким логином уже существует"})
                return

        ua = self.headers.get("User-Agent", "")
        dev_type = (body.get("device_type") or "").lower()
        is_mob = (dev_type in ("mobile", "phone")) or bool(re.search(r"Mobile|Android|iPhone|iPad|iPod|webOS|BlackBerry", ua, re.I))
        slot = "mobile" if is_mob else "desktop"

        session_tok = new_session_token()
        new_perms = {
            "avito": False,
            "avito_bot": False,
            "tg_bot": False,
            "monitoring": True,
            "avito_duration": "none",
            "avito_expires_at": None,
            "max_searches": 1
        }
        new_user = {
            "username": target_user,
            "password": get_password_hash(plain_pass),
            "plain_password": plain_pass,
            "name": name,
            "role": "user",
            "last_ip": remote_ip,
            "last_mac": client_mac or "",
            "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "session_token": session_tok,
            "sessions": {
                slot: {
                    "token": session_tok,
                    "last_ip": remote_ip,
                    "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "device_type": slot,
                    "user_agent": ua
                }
            },
            "target_interval": "60",
            "active_interval": "60",
            "permissions": new_perms,
            "avito_searches": [],
            "telegram_chat_id": None,
            "telegram_username": None,
            "telegram_pending": None
        }
        users.append(new_user)
        write_json_file(USERS_FILE, users, users_lock)

        self.send_json(200, {
            "success": True,
            "session_token": session_tok,
            "user": {
                "username": target_user,
                "name": name,
                "role": "user",
                "last_ip": remote_ip,
                "last_seen": new_user["last_seen"],
                "session_token": session_tok,
                "permissions": new_perms,
                "telegram_chat_id": None,
                "telegram_username": None,
                "telegram_pending": None,
                "target_interval": "1",
                "active_interval": "1",
                "avito_searches": [],
                "plain_password": plain_pass
            }
        })

    def handle_api_users(self, remote_ip: str, client_mac: str):
        users = read_json_file(USERS_FILE, default=[])
        safe_users = []
        for u in users:
            u_name = u.get("username", "")
            d_name = u.get("name", "")
            if re.search(r"deev|деев", u_name, re.I) or re.search(r"deev|деев", d_name, re.I):
                continue

            is_admin_user = (u.get("role") == "admin") or (u_name.lower() == "skynet83")
            perms = u.get("permissions", {})
            has_bot = is_admin_user or bool(perms.get("avito_bot") or perms.get("avito"))
            u_mac = u.get("last_mac", "")
            is_blocked = is_blacklisted(u_mac, u.get("last_ip", ""), u_name) or bool(u.get("is_blocked"))

            safe_users.append({
                "username": u_name,
                "name": d_name,
                "role": u.get("role", "user"),
                "last_ip": u.get("last_ip") or "—",
                "last_mac": u_mac or "—",
                "last_seen": u.get("last_seen") or "—",
                "is_blocked": is_blocked,
                "permissions": perms,
                "target_interval": u.get("target_interval", perms.get("target_interval", "1")),
                "active_interval": u.get("active_interval", u.get("target_interval", "1")),
                "avito_searches": u.get("avito_searches", []),
                "telegram_chat_id": u.get("telegram_chat_id"),
                "telegram_username": u.get("telegram_username"),
                "plain_password": u.get("plain_password", ""),
                "password": u.get("password", "")
            })

        vis_list = list(recent_visitors.values())
        bl_entries = read_json_file(BLACKLIST_FILE, default=[])
        self.send_json(200, {
            "success": True,
            "users": safe_users,
            "visitors": vis_list,
            "blacklist": bl_entries
        })

    def handle_api_users_delete(self, body: dict):
        del_user = (body.get("username") or "").strip()
        if del_user.lower() == "skynet83":
            self.send_json(200, {"success": False, "error": "Нельзя удалить главного администратора skynet83"})
            return
        users = read_json_file(USERS_FILE, default=[])
        users = [u for u in users if (u.get("username") or "").lower() != del_user.lower()]
        write_json_file(USERS_FILE, users, users_lock)
        self.send_json(200, {"success": True})

    def handle_api_blacklist_add(self, body: dict):
        target_u = (body.get("username") or "").strip()
        target_ip = (body.get("ip") or "").strip()
        target_mac = (body.get("mac") or "").strip()
        reason = (body.get("reason") or "").strip() or "Заблокирован администратором"

        if target_u.lower() == "skynet83":
            self.send_json(200, {"success": False, "error": "Нельзя заблокировать главного администратора skynet83"})
            return
        if not target_u and target_ip in ("127.0.0.1", "::1", "localhost", get_local_ip()):
            self.send_json(200, {"success": False, "error": "Нельзя заблокировать локальный IP-адрес сервера!"})
            return

        users = read_json_file(USERS_FILE, default=[])
        if target_u:
            for u in users:
                if (u.get("username") or "").lower() == target_u.lower():
                    if not target_ip and u.get("last_ip") and u.get("last_ip") != "—":
                        target_ip = u.get("last_ip")
                    if not target_mac and u.get("last_mac") and u.get("last_mac") != "—":
                        target_mac = u.get("last_mac")
                    u["is_blocked"] = True
                    u["session_token"] = ""
            write_json_file(USERS_FILE, users, users_lock)

        if target_ip in ("127.0.0.1", "::1", "localhost", get_local_ip()):
            target_ip = ""

        bl_entries = read_json_file(BLACKLIST_FILE, default=[])
        exists = any((target_u and (b.get("username") or "").lower() == target_u.lower()) or (target_ip and b.get("ip") == target_ip) for b in bl_entries)
        if not exists:
            bl_entries.append({
                "username": target_u,
                "ip": target_ip,
                "mac": target_mac,
                "reason": reason,
                "blocked_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })
            write_json_file(BLACKLIST_FILE, bl_entries, blacklist_lock)

        self.send_json(200, {
            "success": True,
            "message": "Добавлено в черный список",
            "is_blocked": True,
            "blacklist": bl_entries
        })

    def handle_api_blacklist_remove(self, body: dict):
        target_u = (body.get("username") or "").strip()
        target_ip = (body.get("ip") or "").strip()
        target_mac = (body.get("mac") or "").strip()

        users = read_json_file(USERS_FILE, default=[])
        if target_u:
            for u in users:
                if (u.get("username") or "").lower() == target_u.lower():
                    u["is_blocked"] = False
            write_json_file(USERS_FILE, users, users_lock)

        bl_entries = read_json_file(BLACKLIST_FILE, default=[])
        norm_mac = target_mac.upper().replace("-", ":") if target_mac else ""
        new_bl = []
        for b in bl_entries:
            b_u = (b.get("username") or "").lower()
            b_i = b.get("ip", "")
            b_m = (b.get("mac") or "").upper().replace("-", ":")
            match = (target_u and b_u == target_u.lower()) or (target_ip and target_ip != "—" and b_i == target_ip) or (norm_mac and norm_mac != "—" and b_m == norm_mac)
            if not match:
                new_bl.append(b)

        write_json_file(BLACKLIST_FILE, new_bl, blacklist_lock)
        self.send_json(200, {
            "success": True,
            "message": "Удалено из черного списка",
            "is_blocked": False,
            "blacklist": new_bl
        })

    def handle_api_users_permission(self, body: dict):
        target_u = (body.get("username") or "").strip()
        clean_target = re.sub(r"\s*\(.*?\)", "", target_u).strip().lower() if target_u else ""
        perm_key = (body.get("permission") or "").strip()
        has_explicit = "value" in body
        perm_val = bool(body.get("value")) if has_explicit else True
        client_token = (body.get("session_token") or self.headers.get("X-Session-Token", "")).strip()
        duration = (body.get("duration") or "").strip()

        users = read_json_file(USERS_FILE, default=[])
        found_u = None

        for u in users:
            u_name = (u.get("username") or "").strip().lower()
            u_disp = re.sub(r"\s*\(.*?\)", "", (u.get("name") or "")).strip().lower()
            u_tg = (u.get("telegram_username") or "").strip().lower().lstrip("@")
            u_tid = str(u.get("telegram_chat_id") or "").strip()

            match_name = clean_target and (
                u_name == clean_target or u_disp == clean_target or
                (clean_target in ("admin", "skynet") and (u.get("role") == "admin" or u_name == "skynet83")) or
                (u_tg and clean_target == u_tg) or (u_tid and clean_target == u_tid)
            )
            toks = [u.get("session_token")]
            sess = u.get("sessions", {})
            toks.append(sess.get("desktop", {}).get("token"))
            toks.append(sess.get("mobile", {}).get("token"))
            match_tok = not clean_target and client_token and (client_token in toks)

            if match_name or match_tok:
                found_u = u
                break

        if not found_u:
            # Fallback admin
            for u in users:
                if u.get("role") == "admin" or (u.get("username") or "").lower() == "skynet83":
                    found_u = u
                    break

        if not found_u:
            self.send_json(200, {"success": False, "error": "Пользователь не найден"})
            return

        perms = found_u.setdefault("permissions", {})

        # tg_bot
        if perm_key == "tg_bot" or "tg_bot" in body:
            v = bool(body.get("tg_bot", body.get("value", True)))
            perms["tg_bot"] = v

        # monitoring
        if perm_key == "monitoring" or "monitoring" in body:
            v = bool(body.get("monitoring", body.get("value", True)))
            perms["monitoring"] = v

        # max_searches (1..10)
        if perm_key == "max_searches" or "max_searches" in body:
            val = int(body.get("max_searches", body.get("value", 1)))
            val = max(1, min(10, val))
            perms["max_searches"] = val

        # target_interval
        if perm_key in ("target_interval", "interval") or "target_interval" in body or "interval" in body:
            iv = str(body.get("target_interval", body.get("interval", body.get("value", "1"))))
            if iv.lower().startswith("rand"):
                iv = "1"
            found_u["target_interval"] = iv
            perms["target_interval"] = iv
            found_u["active_interval"] = iv
            if (found_u.get("role") == "admin") or (found_u.get("username") or "").lower() == "skynet83":
                if avito_api_helper:
                    try:
                        avito_api_helper.set_target_interval(iv)
                    except Exception:
                        pass

        # Тариф (duration / months)
        expires_at = perms.get("avito_expires_at")
        if perm_key in ("avito_bot", "avito", "avito_duration", "duration") or duration or body.get("action") == "extend" or body.get("extend"):
            duration_val = "none"
            has_access = False
            is_extend = (body.get("action") == "extend" or body.get("extend") is True or perm_key == "extend")
            raw_months = 0
            if body.get("months") and body.get("months") != "unlimited":
                raw_months = int(body.get("months"))
            elif re.match(r"^(\d+)m$", duration):
                raw_months = int(re.match(r"^(\d+)m$", duration).group(1))

            if duration == "unlimited" or body.get("months") == "unlimited" or (has_explicit and body.get("value") == "unlimited"):
                has_access = True
                duration_val = "unlimited"
                expires_at = None
            elif duration == "none" or (has_explicit and not duration and perm_val is False):
                has_access = False
                duration_val = "none"
                expires_at = None
            elif raw_months > 0 or is_extend or duration or (has_explicit and perm_val is True):
                m_count = max(1, min(12, raw_months if raw_months > 0 else 1))
                days = m_count * 30
                has_access = True
                duration_val = f"{m_count}m"
                base_dt = datetime.now()
                if is_extend and perms.get("avito_expires_at"):
                    try:
                        parsed_exp = datetime.strptime(perms["avito_expires_at"], "%Y-%m-%d %H:%M:%S")
                        if parsed_exp > base_dt:
                            base_dt = parsed_exp
                    except Exception:
                        pass
                expires_at = (base_dt + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

            if (found_u.get("username") or "").lower() == "skynet83":
                has_access = True
                duration_val = "unlimited"
                expires_at = None

            perms["avito_bot"] = has_access
            perms["avito"] = has_access
            perms["tg_bot"] = True if has_access else False
            perms["monitoring"] = True if has_access else False
            perms["avito_duration"] = duration_val
            perms["avito_expires_at"] = expires_at

        write_json_file(USERS_FILE, users, users_lock)

        days_rem = 0
        if expires_at:
            try:
                diff = datetime.strptime(expires_at, "%Y-%m-%d %H:%M:%S") - datetime.now()
                days_rem = max(0, int(diff.total_seconds() // 86400) + 1)
            except Exception:
                pass

        self.send_json(200, {
            "success": True,
            "message": "Разрешение сохранено",
            "expires_at": expires_at,
            "days_remaining": days_rem,
            "permissions": perms,
            "target_interval": found_u.get("target_interval", "1"),
            "active_interval": found_u.get("active_interval", "1")
        })

    def handle_api_user_telegram(self, body: dict):
        q_user = (body.get("username") or "").strip()
        q_req = (body.get("request_id") or "").strip()
        raw_handle = (body.get("telegram_handle") or "").strip()

        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)
        if not target_u:
            self.send_json(404, {"success": False, "error": f"Пользователь не найден"})
            return

        if not raw_handle:
            # Отвязка
            target_u["telegram_chat_id"] = None
            target_u["telegram_username"] = None
            target_u["telegram_pending"] = None
            perms = target_u.get("permissions")
            if isinstance(perms, dict):
                perms["tg_bot"] = False
            write_json_file(USERS_FILE, users, users_lock)
            self.send_json(200, {
                "success": True,
                "status": "unbound",
                "telegram_chat_id": None,
                "telegram_username": None,
                "telegram_pending": None,
                "message": "Telegram адрес отвязан"
            })
            return

        clean_h = raw_handle.lstrip("@")
        is_chat_id = bool(re.match(r"^-?\d+$", clean_h))
        clean_cid = int(clean_h) if is_chat_id else None
        clean_uname = clean_h.lower() if not is_chat_id else None

        # Проверка на статус главного администратора (@skynet19081983)
        site_tg = (target_u.get("telegram_username") or "").strip().lstrip("@").lower()
        is_admin_handle = (clean_uname in ("skynet19081983", "skynet83")) or (clean_cid and clean_cid in (5680198246,))
        is_admin_target = is_admin_handle or site_tg in ("skynet19081983", "skynet83") or q_user.lower() in ("skynet83",)

        # Для аккаунтов администратора жесткая привязка отключена:
        # У одного администратора может быть несколько устройств (ПК, ноутбук, телефон) при одной запущенной программе.
        already_taken = False
        if not is_admin_target and not is_admin_handle:
            for other in users:
                ou = (other.get("username") or "").lower()
                if ou and ou != q_user.lower():
                    # Не блокируем если другой аккаунт также является профилем администратора
                    other_tg = (other.get("telegram_username") or "").strip().lstrip("@").lower()
                    if other.get("role") == "admin" or other_tg in ("skynet19081983", "skynet83"):
                        continue
                    if clean_cid and other.get("telegram_chat_id") == clean_cid:
                        already_taken = True
                        break
                    if clean_uname and (other.get("telegram_username") or "").lower() == clean_uname:
                        already_taken = True
                        break

        if already_taken:
            self.send_json(200, {"success": False, "error": "Telegram аккаунт уже занят"})
            return

        # Устанавливаем статус ожидания подтверждения (pending)
        pending_obj = {
            "handle": f"@{clean_uname}" if clean_uname else str(clean_cid),
            "chat_id": clean_cid,
            "username": clean_uname,
            "status": "pending",
            "requested_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        target_u["telegram_pending"] = pending_obj
        target_u["telegram_chat_id"] = None
        target_u["telegram_username"] = None
        write_json_file(USERS_FILE, users, users_lock)

        # Отправляем интерактивный запрос на подтверждение в Telegram
        if avito_api_helper:
            try:
                avito_api_helper.send_bind_confirmation(target_u.get("username", q_user), raw_handle)
            except Exception as e:
                print(f"[TG_BIND_CONFIRM_ERROR] {e}")

        self.send_json(200, {
            "success": True,
            "status": "pending",
            "telegram_chat_id": None,
            "telegram_username": None,
            "telegram_pending": pending_obj,
            "message": "Запрос на привязку отправлен в Telegram. Пожалуйста, подтвердите в боте."
        })

    def handle_api_user_telegram_cancel(self, body: dict):
        q_user = (body.get("username") or "").strip()
        q_req = (body.get("request_id") or "").strip()
        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)
        if target_u:
            if target_u.get("telegram_pending"):
                target_u["telegram_chat_id"] = None
                target_u["telegram_username"] = None
            target_u["telegram_pending"] = None
            write_json_file(USERS_FILE, users, users_lock)
        self.send_json(200, {"success": True, "message": "Запрос на привязку отменен"})

    def handle_api_avito_notify_bind_success(self, body: dict):
        q_user = (body.get("username") or "").strip()
        q_cid = body.get("chat_id")
        q_handle = (body.get("handle") or "").strip()
        target_u, users = self.resolve_user_profile(q_user)
        if not target_u and q_cid:
            for u in users:
                if str(u.get("telegram_chat_id")) == str(q_cid):
                    target_u = u
                    break
        if target_u:
            target_u["telegram_pending"] = None
            if q_cid and str(q_cid).lstrip("-").isdigit():
                target_u["telegram_chat_id"] = int(q_cid)
            if q_handle:
                target_u["telegram_username"] = q_handle.lstrip("@")
            perms = target_u.setdefault("permissions", {})
            perms["tg_bot"] = True
            perms["monitoring"] = True
            write_json_file(USERS_FILE, users, users_lock)

        effective_cid = q_cid or (target_u.get("telegram_chat_id") if target_u else None)
        effective_handle = q_handle or (target_u.get("telegram_username") if target_u else "")
        effective_name = q_user or (target_u.get("username", "") if target_u else "")

        if avito_api_helper and effective_cid:
            def _send_success():
                try:
                    avito_api_helper.send_bind_success_notification(
                        effective_name,
                        effective_cid,
                        effective_handle
                    )
                except Exception as ex:
                    print(f"[TG_NOTIFY_SUCCESS_ERROR] {ex}")
            threading.Thread(target=_send_success, daemon=True).start()

        self.send_json(200, {"success": True, "message": "Уведомление о привязке отправлено"})

    # ── Чат ──────────────────────────────────────────────────────────────────
    def handle_api_chat_messages(self, remote_ip: str):
        q_user = self.get_query_param("username", "guest").strip()
        q_req_id = self.get_query_param("request_id", "").strip()
        messages = read_json_file(CHAT_FILE, default=[])

        is_admin_user = q_user.lower() in ("skynet83", "admin")
        users = read_json_file(USERS_FILE, default=[])
        for u in users:
            if (u.get("username") or "").lower() == q_user.lower() and u.get("role") == "admin":
                is_admin_user = True
                break

        if not q_req_id:
            m_id = get_machine_request_id()
            if not is_admin_user and remote_ip in ("127.0.0.1", "::1", "localhost"):
                q_req_id = m_id

        filtered = []
        unread = 0
        q_req_norm = q_req_id.lower().strip()
        q_user_norm = q_user.lower().strip()

        for m in messages:
            s_norm = str(m.get("sender") or "").strip().lower()
            r_norm = str(m.get("recipient") or "").strip().lower()
            sid_norm = str(m.get("sender_id") or "").strip().lower()
            rid_norm = str(m.get("recipient_id") or m.get("hw_id") or "").strip().lower()
            runame_norm = str(m.get("recipient_username") or "").strip().lower()
            is_read = bool(m.get("is_read"))

            is_broadcast = (r_norm == "all")

            m_hw = str(m.get("hw_id") or "").strip().lower()
            match_req = False
            if q_req_norm:
                match_req = (
                    s_norm == q_req_norm or
                    r_norm == q_req_norm or
                    sid_norm == q_req_norm or
                    rid_norm == q_req_norm or
                    m_hw == q_req_norm
                )

            match_user = False
            if q_user_norm and q_user_norm != "guest":
                match_user = (
                    s_norm == q_user_norm or
                    r_norm == q_user_norm or
                    runame_norm == q_user_norm
                )

            if match_req or match_user or is_broadcast:
                filtered.append(m)
                if not is_read and (r_norm in (q_req_norm, q_user_norm, "all") or rid_norm == q_req_norm) and s_norm != q_req_norm and s_norm != q_user_norm:
                    unread += 1
            elif is_admin_user:
                filtered.append(m)
                if not is_read and s_norm not in ("skynet83", "admin", q_user_norm):
                    unread += 1
            else:
                if s_norm == q_user_norm or r_norm in (q_user_norm, "all"):
                    filtered.append(m)
                    if not is_read and r_norm in (q_user_norm, "all") and s_norm != q_user_norm:
                        unread += 1

        self.send_json(200, {
            "success": True,
            "messages": filtered,
            "unread_count": unread,
            "is_admin": is_admin_user
        })

    def send_telegram_admin_notification(self, msg_dict: dict):
        """
        Отправляет уведомление администратору в Telegram (@skynet19081983, ID: 5680198246)
        о запросе триал-ключа, отправке ID устройства или новом сообщении из окна активации/сайта.
        Выполняется в фоновом потоке, использует рабочий прокси при необходимости (для РФ) с fallback на прямое подключение.
        """
        def _worker():
            try:
                bot_token = os.getenv("BOT_TOKEN", "8501191397:AAHwEhKIn745c2XocTq-WX_lcXMEEqsSjeg").strip()
                admin_chat_id = int(os.getenv("ADMIN_CHAT_ID", "5680198246"))
                tg_proxy = os.getenv("TELEGRAM_PROXY", "http://85.8.47.207:7080").strip()

                text_content = str(msg_dict.get("text") or "").strip()
                sender = str(msg_dict.get("sender") or "").strip()
                sender_id = str(msg_dict.get("sender_id") or "").strip()
                msg_id = str(msg_dict.get("id") or "")
                created_at = str(msg_dict.get("created_at") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

                # Определяем аппаратный ID устройства
                hw_id = sender_id or sender
                if not hw_id or hw_id.lower() in ("guest", "user", "admin", "skynet83"):
                    m_ebid = re.search(r'\b((?:EBID|EBMOB)-[A-Z0-9\-]+)\b', text_content, re.IGNORECASE)
                    if m_ebid:
                        hw_id = m_ebid.group(1).upper()
                    else:
                        hw_id = get_machine_request_id()

                lower_text = text_content.lower()
                # Полностью отключаем отправку уведомлений об активации ключей в бот Telegram
                if "активац" in lower_text or "успешно активирован" in lower_text or "активирован на этом" in lower_text or "активировал" in lower_text:
                    return

                if "триал" in lower_text or "trial" in lower_text or "3 дня" in lower_text or "3-дн" in lower_text:
                    header = "🎁 <b>Запрос на пробный период (3 дня)!</b>"
                elif "мой id для активации" in lower_text or "ответный ключ" in lower_text or "отправить id" in lower_text:
                    header = "🔑 <b>Запрос ключа активации (ID устройства)!</b>"
                else:
                    header = "💬 <b>Новое сообщение из окна активации!</b>"

                is_mob = str(hw_id).upper().startswith("EBMOB") or "телефон" in lower_text
                dev_icon = "📱" if is_mob else "🖥️"
                dev_label = "ID пользователя (Телефон)" if is_mob else "ID пользователя (ПК)"

                import html
                target_u, _ = self.resolve_user_profile(hw_id, req_id=hw_id)
                tg_display = None
                if target_u:
                    u_tg = (target_u.get("telegram_username") or "").strip().lstrip("@")
                    u_cid = target_u.get("telegram_chat_id")
                    u_pend = target_u.get("telegram_pending")
                    if u_tg:
                        tg_display = f"@{u_tg}"
                    elif u_cid:
                        tg_display = f"ID: {u_cid}"
                    elif u_pend and isinstance(u_pend, dict) and u_pend.get("handle"):
                        tg_display = f"{u_pend.get('handle')} (ожидает подтверждения)"
                if not tg_display and msg_dict.get("telegram_handle"):
                    tg_display = str(msg_dict.get("telegram_handle")).strip()

                msg_lines = [
                    f"{header}\n",
                    f"{dev_icon} <b>{dev_label}:</b> <code>{html.escape(str(hw_id))}</code>",
                ]
                if tg_display:
                    msg_lines.append(f"📱 <b>Telegram аккаунт:</b> <code>{html.escape(tg_display)}</code>")
                msg_lines.extend([
                    f"🕒 <b>Время:</b> {html.escape(str(created_at))}\n",
                    f"📝 <i>{html.escape(str(text_content))}</i>"
                ])

                tg_text = "\n".join(msg_lines)

                payload = {
                    "chat_id": admin_chat_id,
                    "text": tg_text,
                    "parse_mode": "HTML",
                    "reply_markup": {
                        "inline_keyboard": [
                            [
                                {"text": "✉️ Ответить", "callback_data": f"admin_reply_user_{hw_id}"},
                                {"text": "✅ Прочитано", "callback_data": f"chat_read_{msg_id}"}
                            ]
                        ]
                    }
                }

                url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
                data_bytes = json.dumps(payload).encode("utf-8")

                # Пробуем отправку: сначала через прокси (для РФ), затем напрямую
                sent = False
                for use_proxy in (True, False):
                    try:
                        import urllib.request
                        req = urllib.request.Request(url, data=data_bytes, headers={"Content-Type": "application/json"})
                        if use_proxy and tg_proxy:
                            proxy_handler = urllib.request.ProxyHandler({"https": tg_proxy, "http": tg_proxy})
                            opener = urllib.request.build_opener(proxy_handler)
                            resp = opener.open(req, timeout=6)
                        else:
                            resp = urllib.request.urlopen(req, timeout=4)

                        resp_json = json.loads(resp.read().decode("utf-8"))
                        if resp_json.get("ok"):
                            sent = True
                            tg_msg_id = resp_json.get("result", {}).get("message_id")
                            try:
                                msgs = read_json_file(CHAT_FILE, default=[])
                                for m in msgs:
                                    if str(m.get("id")) == msg_id:
                                        m["admin_tg_notified"] = True
                                        m["admin_tg_msg_id"] = tg_msg_id
                                        m["admin_tg_chat_id"] = admin_chat_id
                                        break
                                write_json_file(CHAT_FILE, msgs, chat_lock)
                            except Exception:
                                pass
                            print(f"[+] [TG-Notify] Сообщение успешно доставлено админу @skynet19081983 (msg_id={tg_msg_id})")
                            break
                    except Exception:
                        pass

                if not sent:
                    print(f"[!] [TG-Notify] Не удалось доставить уведомление в Telegram админу")
            except Exception as e:
                print(f"[!] [TG-Notify] Ошибка в фоновом обработчике Telegram: {e}")

        threading.Thread(target=_worker, daemon=True, name="TgAdminNotifyWorker").start()

    def handle_api_chat_send(self, body: dict):
        sender = str(body.get("sender") or "guest")
        sender_id = str(body.get("sender_id") or sender)
        sender_name = str(body.get("sender_name") or sender)
        recipient = str(body.get("recipient") or "admin")
        text = str(body.get("text") or "").strip()

        if (not sender_id or sender_id == "guest") and recipient == "admin":
            m_id = get_machine_request_id()
            sender_id = m_id
            if sender == "guest":
                sender = m_id
            if sender_name in ("guest", ""):
                sender_name = f"ПК ({m_id})"

        users = read_json_file(USERS_FILE, default=[])
        matched_u = next((u for u in users if (u.get("username") or "").lower() == sender.lower() or str(u.get("permissions", {}).get("hwid_request_id", "")).lower() == sender_id.lower()), None)
        if matched_u and (matched_u.get("is_blocked") or matched_u.get("chat_blocked")):
            self.send_json(200, {"success": False, "error": "Доступ к чату заблокирован администратором (Чёрный список)."})
            return

        if not text:
            self.send_json(200, {"success": False, "error": "Текст сообщения не может быть пустым"})
            return

        messages = read_json_file(CHAT_FILE, default=[])
        now_ts = datetime.now()
        telegram_handle = str(body.get("telegram_handle") or "").strip()
        new_msg = {
            "id": f"msg_{now_ts.strftime('%Y%m%d%H%M%S%f')[:17]}_{random.randint(1000, 9999)}",
            "sender": sender,
            "sender_id": sender_id,
            "sender_name": sender_name,
            "recipient": recipient,
            "text": text,
            "created_at": now_ts.strftime("%Y-%m-%d %H:%M:%S"),
            "is_read": False,
            "telegram_handle": telegram_handle or None
        }
        messages.append(new_msg)
        if len(messages) > 500:
            messages = messages[-500:]

        write_json_file(CHAT_FILE, messages, chat_lock)

        # Немедленная прямая отправка уведомления администратору в Telegram (@skynet19081983)
        if recipient.lower() in ("admin", "all") or sender.lower() not in ("skynet83", "admin", "skynet19081983"):
            self.send_telegram_admin_notification(new_msg)

        self.send_json(200, {"success": True, "message": new_msg})

    def handle_api_chat_read(self, body: dict):
        username = str(body.get("username") or "guest")
        req_id = str(body.get("request_id") or "") or get_machine_request_id()
        target_user = body.get("target_user")

        messages = read_json_file(CHAT_FILE, default=[])
        changed = False
        req_norm = req_id.lower().strip()
        u_norm = username.lower().strip()

        for m in messages:
            s_norm = str(m.get("sender") or "").strip().lower()
            r_norm = str(m.get("recipient") or "").strip().lower()
            sid_norm = str(m.get("sender_id") or "").strip().lower()
            rid_norm = str(m.get("recipient_id") or m.get("hw_id") or "").strip().lower()
            runame_norm = str(m.get("recipient_username") or "").strip().lower()
            is_read = bool(m.get("is_read"))

            if req_norm and (r_norm in (req_norm, "all") or rid_norm == req_norm) and s_norm != req_norm and sid_norm != req_norm:
                if not is_read:
                    m["is_read"] = True
                    changed = True
            elif u_norm in ("skynet83", "admin"):
                if not is_read and s_norm not in ("skynet83", "admin"):
                    if not target_user or target_user.lower() == "all" or s_norm == target_user.lower():
                        m["is_read"] = True
                        changed = True
            else:
                if not is_read and (r_norm in (u_norm, "all") or runame_norm == u_norm) and s_norm != u_norm:
                    m["is_read"] = True
                    changed = True

        if changed:
            write_json_file(CHAT_FILE, messages, chat_lock)
        self.send_json(200, {"success": True})

    def handle_api_chat_edit_welcome(self, body: dict):
        username = str(body.get("username") or "")
        new_text = str(body.get("text") or "").strip()

        is_admin = username.lower() == "skynet83"
        users = read_json_file(USERS_FILE, default=[])
        for u in users:
            if (u.get("username") or "").lower() == username.lower() and u.get("role") == "admin":
                is_admin = True
                break

        if not is_admin:
            self.send_json(403, {"success": False, "error": "Доступ запрещен. Только администратор может редактировать приветствие."})
            return
        if not new_text:
            self.send_json(400, {"success": False, "error": "Текст сообщения не может быть пустым."})
            return

        messages = read_json_file(CHAT_FILE, default=[])
        welcome_msg = next((m for m in messages if str(m.get("id")) == "1"), None)
        if welcome_msg:
            welcome_msg["text"] = new_text
        else:
            messages.insert(0, {
                "id": "1",
                "sender": "skynet83",
                "sender_name": "Администратор (skynet83)",
                "recipient": "all",
                "text": new_text,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "is_read": True
            })
        write_json_file(CHAT_FILE, messages, chat_lock)
        self.send_json(200, {"success": True, "text": new_text})

    def handle_api_chat_edit(self, body: dict):
        msg_id = str(body.get("id") or body.get("messageId") or "")
        username = str(body.get("username") or "guest")
        new_text = str(body.get("text") or "").strip()

        if not msg_id or not new_text:
            self.send_json(400, {"success": False, "error": "Не передан ID сообщения или текст пуст."})
            return

        is_admin = username.lower() == "skynet83"
        users = read_json_file(USERS_FILE, default=[])
        for u in users:
            if (u.get("username") or "").lower() == username.lower() and u.get("role") == "admin":
                is_admin = True
                break

        messages = read_json_file(CHAT_FILE, default=[])
        target_msg = next((m for m in messages if str(m.get("id")) == msg_id), None)
        if not target_msg:
            self.send_json(404, {"success": False, "error": "Сообщение не найдено."})
            return

        sender = str(target_msg.get("sender") or "").lower()
        is_sender = (sender == username.lower()) or (sender in ("guest", "гость") and username.lower() in ("guest", "гость"))
        if not is_admin and not is_sender:
            self.send_json(403, {"success": False, "error": "Вы можете редактировать только свои сообщения."})
            return

        target_msg["text"] = new_text
        target_msg["edited"] = True
        write_json_file(CHAT_FILE, messages, chat_lock)
        self.send_json(200, {"success": True, "message": target_msg})

    def handle_api_chat_delete(self, body: dict):
        msg_id = str(body.get("id") or body.get("messageId") or "")
        username = str(body.get("username") or "guest")

        if not msg_id:
            self.send_json(400, {"success": False, "error": "Не передан ID сообщения."})
            return

        if msg_id == "1":
            self.send_json(400, {"success": False, "error": "Приветственное сообщение нельзя удалить."})
            return

        is_admin = username.lower() == "skynet83"
        users = read_json_file(USERS_FILE, default=[])
        for u in users:
            if (u.get("username") or "").lower() == username.lower() and u.get("role") == "admin":
                is_admin = True
                break

        messages = read_json_file(CHAT_FILE, default=[])
        target_msg = next((m for m in messages if str(m.get("id")) == msg_id), None)
        if not target_msg:
            self.send_json(404, {"success": False, "error": "Сообщение не найдено."})
            return

        sender = str(target_msg.get("sender") or "").lower()
        is_sender = (sender == username.lower()) or (sender in ("guest", "гость") and username.lower() in ("guest", "гость"))
        if not is_admin and not is_sender:
            self.send_json(403, {"success": False, "error": "Вы можете удалять только свои сообщения."})
            return

        messages = [m for m in messages if str(m.get("id")) != msg_id]
        write_json_file(CHAT_FILE, messages, chat_lock)
        self.send_json(200, {"success": True, "deletedId": msg_id})

    def handle_api_chat_clear(self):
        clean_msg = [{
            "id": "1",
            "sender": "skynet83",
            "sender_name": "Администратор (@skynet19081983)",
            "recipient": "all",
            "text": "Здравствуйте! Здесь вы можете отправить ваш ID компьютера администратору в Telegram (@skynet19081983) или прямо в этом чате для получения ключа активации AvitoHunter.",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_read": True
        }]
        write_json_file(CHAT_FILE, clean_msg, chat_lock)
        self.send_json(200, {"success": True, "message": "История чата успешно очищена."})

    # ── Лицензии и Схемы ──────────────────────────────────────────────────────
    def handle_api_license_status(self, remote_ip: str):
        q_user = self.get_query_param("username", "")
        q_req_id = self.get_query_param("request_id", "")
        q_dev_type = self.get_query_param("device_type", "")
        if remote_ip in ("127.0.0.1", "::1", "localhost", ""):
            local_id = get_machine_request_id()
            if not q_req_id or (q_req_id.startswith("EBID") and q_req_id != local_id):
                q_req_id = local_id
                if not q_user or q_user.startswith("EBID"):
                    q_user = local_id
        if avito_api_helper:
            res = avito_api_helper.get_license_status_info(q_user, remote_ip, q_req_id, q_dev_type)
        else:
            res = {"success": True, "status": "active", "unlimited": True}
        self.send_json(200, res)

    def handle_api_license_client_id(self):
        q_dev = self.get_query_param("device_type", "auto")
        q_seed = self.get_query_param("seed", "")
        ua = self.headers.get("User-Agent", "")
        # Определяем устройство по UA если device_type не задан явно
        ua_is_mob = bool(re.search(r"Mobile|Android|iPhone|iPad|iPod|webOS|BlackBerry", ua, re.I))
        is_mob = q_dev in ("mobile", "phone") or (q_dev == "auto" and ua_is_mob)

        if is_mob:
            # Мобильное устройство — генерируем криптографически валидный EBMOB-... ID
            try:
                if hwid_security:
                    seed = q_seed or ua or str(self.get_remote_ip())
                    client_id = hwid_security.generate_mobile_request_id(seed)
                else:
                    import hashlib
                    seed_raw = (q_seed or ua or "mobile").encode("utf-8")
                    client_id = "EBMOB-" + hashlib.sha256(seed_raw).hexdigest()[:20].upper()
                    client_id = f"EBMOB-{client_id[6:10]}-{client_id[10:14]}-{client_id[14:18]}-{client_id[18:22]}-{client_id[22:26]}"
            except Exception:
                import hashlib
                client_id = "EBMOB-" + hashlib.md5(f"mobile_{q_seed}".encode("utf-8")).hexdigest()[:12].upper()
            self.send_json(200, {"success": True, "client_id": client_id, "request_id": client_id, "device_type": "phone"})
        else:
            # Компьютер — возвращаем реальный EBID-... на основе железа сервера
            client_id = get_machine_request_id()
            self.send_json(200, {"success": True, "client_id": client_id, "request_id": client_id, "device_type": "pc"})

    def handle_api_license_activate(self, body: dict, remote_ip: str):
        raw_key = str(body.get("key") or "-").strip()
        req_id = str(body.get("request_id") or "").strip()
        uname = str(body.get("username") or req_id).strip()
        if remote_ip in ("127.0.0.1", "::1", "localhost", ""):
            local_id = get_machine_request_id()
            if not req_id or (req_id.startswith("EBID") and req_id != local_id):
                req_id = local_id
                if not uname or uname.startswith("EBID"):
                    uname = local_id
        if avito_api_helper:
            res = avito_api_helper.activate_license_key(raw_key, uname, remote_ip, req_id)
        else:
            res = {"success": False, "error": "avito_api_helper not available"}
        self.send_json(200, res)

    def handle_api_license_request_trial(self, body: dict, remote_ip: str):
        req_id = str(body.get("request_id") or "").strip()
        uname = str(body.get("username") or req_id).strip()
        if not req_id and remote_ip in ("127.0.0.1", "::1", "localhost", ""):
            req_id = get_machine_request_id()

        # Если запрос идет с самого ПК или в режиме ПК (не мобильный EBMOB),
        # гарантируем, что используется реальный аппаратный HWID этой машины,
        # даже если в браузере закеширован чужой ID от синхронизации профиля:
        if remote_ip in ("127.0.0.1", "::1", "localhost", "") or (req_id and not req_id.startswith("EBMOB")):
            local_mach_id = get_machine_request_id()
            if req_id and req_id.startswith("EBID") and req_id != local_mach_id and (remote_ip in ("127.0.0.1", "::1", "localhost", "") or not remote_ip):
                req_id = local_mach_id
                uname = local_mach_id

        if not req_id:
            self.send_json(200, {"success": False, "error": "Не удалось определить ID код устройства"})
            return

        # 1. Проверяем, использовало ли данное устройство триал
        import devices_db
        import hwid_security
        import datetime
        import html
        import time

        trial_already_used = devices_db.has_device_used_trial(req_id)
        if not trial_already_used and req_id.startswith("EBID"):
            trial_already_used, _ = hwid_security.check_local_trial_used()

        if trial_already_used:
            try:
                import cloud_license
                cloud_license.notify_cloud_trial_rejected(req_id, ip=remote_ip)
            except Exception:
                pass
            self.send_json(200, {
                "success": False,
                "trial_used": True,
                "error": "❌ Ключ уже был ранее активирован на данном устройстве!\nПовторная выдача триал-ключа на данном оборудовании невозможна (в том числе после удаления файлов или переустановки программы).\nДля продления доступа и покупки лицензии обратитесь к администратору: @skynet19081983"
            })
            return

        # 2. Генерируем персональный 3-дневный триал-ключ и активируем прямо в окне программы
        from datetime import datetime, timedelta
        exp_dt = datetime.now() + timedelta(days=3)
        exp_dt_str = exp_dt.strftime("%Y-%m-%d %H:%M:%S")
        trial_key = hwid_security.generate_response_key(req_id, tier="3_days", expires_date=exp_dt)
        devices_db.record_device_trial_activation(req_id, trial_key, exp_dt_str, client_ip=remote_ip, username=uname)

        try:
            import avito_api_helper
            act_res = avito_api_helper.activate_license_key(trial_key, uname, remote_ip, req_id)
        except Exception as e:
            act_res = {"success": False, "error": str(e)}

        if act_res.get("success"):
            try:
                lic_data = {
                    "active_key": trial_key,
                    "tier": "3_days",
                    "status": "active",
                    "request_id": req_id,
                    "expires_at": exp_dt_str,
                    "activated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "is_trial": True
                }
                write_json_file(LICENSE_FILE, lic_data)
            except Exception:
                pass

            self.send_json(200, {
                "success": True,
                "trial_used": True,
                "trial_key": trial_key,
                "expires_at": exp_dt_str,
                "message": f"🎁 Бесплатный ознакомительный период (3 дня) успешно активирован!\nДействует до: {exp_dt.strftime('%d.%m.%Y %H:%M')}",
                "status": act_res.get("status")
            })
        else:
            self.send_json(200, {
                "success": False,
                "trial_used": False,
                "error": act_res.get("error", "Ошибка применения триал-ключа")
            })

    def handle_api_upload_circuit(self, body: dict):
        file_name = body.get("fileName", "circuit.png")
        comp_id = body.get("componentId", "comp")
        comp_name = body.get("componentName", "Компонент")
        b64_data = body.get("base64Data", "")

        ext = os.path.splitext(file_name)[1] or ".png"
        clean_id = re.sub(r"[^a-zA-Z0-9_\-]", "", comp_id).lower()
        saved_name = f"{clean_id}_circuit{ext}"
        saved_path = os.path.join(SCHEMATICS_DIR, saved_name)

        if "base64," in b64_data:
            b64_data = b64_data.split("base64,")[1]

        import base64
        file_bytes = base64.b64decode(b64_data)
        with open(saved_path, "wb") as f:
            f.write(file_bytes)

        rel_img = f"img/schematics/{saved_name}"
        notes = read_json_file(ENGINEERING_NOTES_FILE, default=[])
        existing = next((n for n in notes if clean_id in n.get("keywords", []) or comp_name.lower() in n.get("keywords", [])), None)

        nuan_list = [line.strip() for line in (body.get("nuances") or "").splitlines() if line.strip()]
        if existing:
            existing["circuit_image"] = rel_img
            if body.get("pinout"):
                existing["pinout_scheme"] = body["pinout"]
            if body.get("wiring"):
                existing["wiring_guide"] = body["wiring"]
            if nuan_list:
                existing["nuances"] = nuan_list
        else:
            notes.append({
                "keywords": [clean_id, comp_name.lower()],
                "title": f"{comp_name} — Схема и обвязка",
                "circuit_image": rel_img,
                "pinout_scheme": body.get("pinout") or "Распиновка выводов согласно схеме",
                "wiring_guide": body.get("wiring") or "Схема обвязки загружена администратором.",
                "nuances": nuan_list
            })

        write_json_file(ENGINEERING_NOTES_FILE, notes, notes_lock)
        self.send_json(200, {"success": True, "image": rel_img})

    # ── Avito Мониторинг & Статистика ─────────────────────────────────────────
    def handle_api_avito_stats(self):
        global cached_raw_stats, last_stats_time
        q_user = self.get_query_param("username")
        q_fresh = self.get_query_param("fresh") in ("1", "true", "yes")
        now_ts = time.time()

        with stats_cache_lock:
            if q_fresh or not cached_raw_stats or (now_ts - last_stats_time) >= 1.5:
                if avito_api_helper:
                    try:
                        cached_raw_stats = avito_api_helper.get_stats()
                    except Exception as e:
                        cached_raw_stats = {"success": False, "error": str(e), "searches": [], "items": []}
                else:
                    cached_raw_stats = {"success": True, "stats": {}, "searches": [], "items": []}
                last_stats_time = now_ts

        # Клонируем словарь для персонализации под пользователя
        stat_obj = json.loads(json.dumps(cached_raw_stats))
        q_req = self.get_query_param("request_id")
        target_u, all_users = self.resolve_user_profile(q_user, req_id=q_req)

        if target_u:
            # Вычисляем детерминированный uid
            target_uid = target_u.get("telegram_chat_id")
            if not target_uid:
                u_clean = (target_u.get("request_id") or target_u.get("username") or "user").strip().lower()
                h_hex = hashlib.md5(f"usr_{u_clean}".encode("utf-8")).hexdigest()[:8]
                target_uid = int(h_hex, 16)
            else:
                target_uid = int(target_uid)

            user_searches = target_u.get("avito_searches") or []
            is_admin = (target_u.get("role") == "admin")

            # Синхронизация статуса опроса и инициализации из БД бота
            if len(user_searches) > 0 and stat_obj.get("searches"):
                need_save = False
                for us in user_searches:
                    us_url = (us.get("url") or "").strip().rstrip("/")
                    matched = next((s for s in stat_obj["searches"] if (s.get("user_id") == target_uid and (s.get("url", "").strip().rstrip("/") == us_url or s.get("id") == us.get("id")))), None)
                    if not matched:
                        matched = next((s for s in stat_obj["searches"] if s.get("url", "").strip().rstrip("/") == us_url or s.get("id") == us.get("id")), None)
                    if matched and matched.get("last_polled_at"):
                        if us.get("last_polled_at") != matched["last_polled_at"]:
                            us["last_polled_at"] = matched["last_polled_at"]
                            need_save = True
                    if matched and matched.get("is_initialized") is not None:
                        if us.get("is_initialized") != matched["is_initialized"]:
                            us["is_initialized"] = matched["is_initialized"]
                            need_save = True
                if need_save:
                    write_json_file(USERS_FILE, all_users, users_lock)

            if isinstance(user_searches, list):
                user_searches = sorted(user_searches, key=lambda s: (str(s.get("created_at") or ""), int(s.get("id") or 0)))
            stat_obj["searches"] = user_searches
            stats = stat_obj.setdefault("stats", {})
            stats["total_searches"] = len(user_searches)
            stats["max_searches"] = min(10, 10 if is_admin else int(target_u.get("permissions", {}).get("max_searches", 1)))
            stats["telegram_chat_id"] = target_u.get("telegram_chat_id")
            stats["telegram_username"] = target_u.get("telegram_username")
            stats["telegram_pending"] = target_u.get("telegram_pending")
            user_proxies = target_u.get("proxies") or []
            if user_proxies and len(user_proxies) > 0:
                stats["proxy_count"] = len(user_proxies)

            target_perms = target_u.get("permissions", {})
            user_lic_expired = False
            remote_ip = self.client_address[0] if hasattr(self, 'client_address') and self.client_address else ""
            lic_st = None
            if avito_api_helper:
                try:
                    lic_st = avito_api_helper.get_license_status_info(target_u.get("username") or "", remote_ip, q_req)
                    if lic_st:
                        if lic_st.get("is_expired") is True:
                            user_lic_expired = True
                        elif lic_st.get("is_expired") is False:
                            user_lic_expired = False
                            target_perms["is_expired"] = False
                            if lic_st.get("active_key"):
                                target_perms["active_key"] = lic_st.get("active_key")
                            if lic_st.get("expires_at"):
                                target_perms["avito_expires_at"] = lic_st.get("expires_at")
                            if lic_st.get("duration") and lic_st.get("duration") != "none":
                                target_perms["avito_duration"] = lic_st.get("duration")
                            target_perms["avito"] = True
                            target_perms["avito_bot"] = True
                except Exception:
                    pass
            if not user_lic_expired and (not avito_api_helper or lic_st is None):
                if target_perms.get("is_expired") is True:
                    user_lic_expired = True
                elif not target_perms.get("active_key") and target_perms.get("avito_duration") != "unlimited":
                    user_lic_expired = True
                elif target_perms.get("avito_expires_at"):
                    try:
                        exp_dt = datetime.strptime(target_perms["avito_expires_at"], "%Y-%m-%d %H:%M:%S")
                        if datetime.now() > exp_dt:
                            user_lic_expired = True
                    except Exception:
                        pass

            if user_lic_expired:
                stats["user_monitoring"] = False
                stats["user_tg_bot"] = False
                stats["monitor_enabled"] = False
                stats["bot_running"] = False
                stats["bot_paused"] = True
                stats["proxy_fetching"] = False
                stats["license_expired"] = True
            else:
                is_user_mon = bool(target_perms.get("monitoring", True))
                is_user_tg = bool(target_perms.get("tg_bot", True))
                stats["user_monitoring"] = is_user_mon
                stats["user_tg_bot"] = is_user_tg
                if not is_user_tg:
                    stats["bot_paused"] = True
                stats["monitor_enabled"] = is_user_mon or is_user_tg
                stats["license_expired"] = False

            u_interval = str(target_u.get("active_interval") or target_u.get("target_interval") or "1")
            if u_interval.lower().startswith("rand"):
                u_interval = "1"
            stats["target_interval"] = u_interval

            # Фильтрация объявлений строго по поисковым ссылкам пользователя
            my_names = [str(s.get("name", "")).strip().lower() for s in user_searches if s.get("name")]
            my_urls = [str(s.get("url", "")).strip().lower() for s in user_searches if s.get("url")]
            if stat_obj.get("searches"):
                for s in stat_obj["searches"]:
                    if s.get("url") and s["url"].strip().lower() in my_urls:
                        if s.get("name"):
                            my_names.append(s["name"].strip().lower())
            my_names = list(set(my_names))

            deliv_only_names = set()
            for s in user_searches:
                s_url = (s.get("url") or "").strip().lower()
                if bool(s.get("only_delivery")) or ("d=1" in s_url) or ("cd=1" in s_url):
                    if s.get("name"):
                        deliv_only_names.add(str(s["name"]).strip().lower())

            items = stat_obj.get("items", [])
            if len(user_searches) == 0:
                stat_obj["items"] = []
            elif items:
                filtered_user_items = []
                norm_my_names = {re.sub(r'[\s🚚📦🏷️\(\)\[\]\-_]+', '', n) for n in my_names}
                norm_deliv_names = {re.sub(r'[\s🚚📦🏷️\(\)\[\]\-_]+', '', n) for n in deliv_only_names}
                for it in items:
                    it_sname = str(it.get("search_name", "")).strip().lower()
                    it_norm = re.sub(r'[\s🚚📦🏷️\(\)\[\]\-_]+', '', it_sname)
                    is_match = (it.get("user_id") == target_uid) or (my_names and it_sname in my_names) or (it_norm and it_norm in norm_my_names) or (is_admin and it.get("user_id") in (0, target_uid))
                    if is_match:
                        if (deliv_only_names and it_sname in deliv_only_names) or (it_norm and it_norm in norm_deliv_names):
                            if not bool(it.get("has_delivery")):
                                continue
                        filtered_user_items.append(it)
                stat_obj["items"] = filtered_user_items
            else:
                stat_obj["items"] = []
            stats["total_items"] = len(stat_obj["items"])

            # Расчет безопасного интервала под пул прокси
            user_px = target_u.get("proxies") or []
            user_px_cnt = len(user_px)
            shared_cnt = int(stats.get("proxy_count", 0))
            eff_cnt = user_px_cnt if user_px_cnt > 0 else shared_cnt
            stats["user_proxies_count"] = user_px_cnt
            stats["shared_proxies_count"] = shared_cnt
            stats["is_custom_proxies"] = user_px_cnt > 0
            stats["proxy_count"] = eff_cnt

            if u_interval.isdigit():
                t_sec = int(u_interval)
                needed = min(360, max(15, int(-(-30 // max(1, t_sec))) * 10))
                safe = t_sec if eff_cnt >= needed else max(t_sec, int(-(-30 // max(1, eff_cnt))))
                stats["needed_proxies"] = needed
                stats["safe_interval"] = safe
            else:
                stats["needed_proxies"] = 15
                stats["safe_interval"] = 30
        else:
            stat_obj["searches"] = []
            stat_obj["items"] = []
            stats = stat_obj.setdefault("stats", {})
            stats["total_searches"] = 0
            stats["total_items"] = 0
            stats["max_searches"] = 1

        self.send_json(200, stat_obj)

    def handle_api_avito_searches(self):
        q_user = self.get_query_param("username")
        q_req = self.get_query_param("request_id")
        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)

        user_searches = target_u.get("avito_searches", [])
        if isinstance(user_searches, list):
            user_searches = sorted(user_searches, key=lambda s: (str(s.get("created_at") or ""), int(s.get("id") or 0)))
        is_admin = target_u.get("role") == "admin"
        max_s = min(10, 10 if is_admin else int(target_u.get("permissions", {}).get("max_searches", 1)))

        self.send_json(200, {
            "success": True,
            "searches": user_searches,
            "max_searches": max_s,
            "count": len(user_searches),
            "is_expired": False,
            "username": target_u.get("username", "")
        })

    def handle_api_users_avito_searches(self):
        q_user = self.get_query_param("username")
        q_req = self.get_query_param("request_id")
        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)

        searches = target_u.get("avito_searches", [])
        if isinstance(searches, list):
            searches = sorted(searches, key=lambda s: (str(s.get("created_at") or ""), int(s.get("id") or 0)))
        is_admin = target_u.get("role") == "admin"
        max_s = min(10, 10 if is_admin else int(target_u.get("permissions", {}).get("max_searches", 1)))

        self.send_json(200, {
            "success": True,
            "username": target_u.get("username"),
            "name": target_u.get("name"),
            "searches": searches,
            "max_searches": max_s,
            "avito_duration": target_u.get("permissions", {}).get("avito_duration", "none"),
            "avito_expires_at": target_u.get("permissions", {}).get("avito_expires_at")
        })

    def handle_api_avito_add_search(self, body: dict):
        q_user = (body.get("username") or "").strip()
        url = (body.get("url") or "").strip()
        name = (body.get("name") or "").strip()

        if not url:
            self.send_json(200, {"success": False, "error": "Ссылка не может быть пустой"})
            return
        if not re.match(r"^https?://", url):
            self.send_json(200, {"success": False, "error": "Ссылка должна начинаться с http:// или https://"})
            return

        # Гарантируем сортировку по дате (s=104) для хронологического поиска свежих лотов
        if "s=" not in url:
            delim = '&' if '?' in url else '?'
            url = f"{url}{delim}s=104"

        target_u, users = self.resolve_user_profile(q_user, req_id=body.get("request_id"))
        if not target_u:
            self.send_json(200, {"success": False, "error": "Пользователь не найден"})
            return

        is_admin = target_u.get("role") == "admin"
        existing = target_u.setdefault("avito_searches", [])
        max_s = min(10, 10 if is_admin else int(target_u.get("permissions", {}).get("max_searches", 1)))

        if len(existing) >= max_s:
            self.send_json(200, {
                "success": False,
                "error": f"Достигнут лимит поисковых ссылок (максимум {max_s}, предел системы: 10 шт.). Удалите ненужные ссылки перед добавлением новых."
            })
            return

        if any(s.get("url", "").strip().lower() == url.lower() for s in existing):
            self.send_json(200, {"success": False, "error": "duplicate", "message": "Такая ссылка уже добавлена."})
            return

        if not name:
            m_q = re.search(r"[?&]q=([^&]+)", url)
            if m_q:
                name = unquote(m_q.group(1)).replace("+", " ")
            elif "videokarty" in url:
                name = "Видеокарты"
            elif "protsessory" in url:
                name = "Процессоры"
            elif "telefony" in url:
                name = "Телефоны"
            elif "noutbuki" in url:
                name = "Ноутбуки"
            elif "komplektuyuschie" in url:
                name = "Комплектующие"
            else:
                name = "Поиск Avito"

        # Приписка диапазона цен
        pmin = (re.search(r"[?&]pmin=(\d+)", url) or [None, None])[1]
        pmax = (re.search(r"[?&]pmax=(\d+)", url) or [None, None])[1]
        if pmin and pmax:
            suffix = f"({pmin}-{pmax})"
        elif pmin:
            suffix = f"(от {pmin})"
        elif pmax:
            suffix = f"(до {pmax})"
        else:
            suffix = ""

        if suffix and not re.search(r"\(\s*(?:от|до|\d+)\s*[\d\-–\s]*\)", name):
            name = f"{name} {suffix}"

        owner = target_u.get("username") or "admin"
        only_deliv_val = int(body.get("only_delivery", 1 if ("d=1" in url or "cd=1" in url) else 0))
        is_pending_val = int(body.get("is_pending", 0))
        real_id = None
        if avito_api_helper:
            try:
                res_add = avito_api_helper.add_search(url=url, name=name, username=owner, only_delivery=only_deliv_val, is_pending=is_pending_val)
                if res_add and res_add.get("success") and res_add.get("id"):
                    real_id = res_add["id"]
            except Exception:
                pass

        new_id = real_id if real_id else (int(time.time()) + random.randint(10, 99))
        new_search = {
            "id": new_id,
            "name": name,
            "url": url,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "is_active": 1,
            "is_initialized": 0,
            "only_delivery": only_deliv_val,
            "is_pending": is_pending_val
        }
        norm_url = url.rstrip("/").lower()
        existing = [s for s in existing if (s.get("url") or "").strip().rstrip("/").lower() != norm_url]
        existing.append(new_search)
        existing.sort(key=lambda s: (str(s.get("created_at") or ""), int(s.get("id") or 0)))
        target_u["avito_searches"] = existing

        # Требование 3: При добавлении ссылки мониторинг автоматически переходит в режим ВКЛ
        target_perms = target_u.setdefault("permissions", {})
        target_perms["monitoring"] = True
        if avito_api_helper:
            try:
                avito_api_helper.set_monitor_state(True)
            except Exception:
                pass

        write_json_file(USERS_FILE, users, users_lock)

        global cached_raw_stats, last_stats_time
        with stats_cache_lock:
            cached_raw_stats = None
            last_stats_time = 0

        self.send_json(200, {
            "success": True,
            "id": new_id,
            "name": name,
            "url": url,
            "is_pending": is_pending_val,
            "searches": existing
        })

    def handle_api_avito_activate_pending_searches(self, body: dict = None):
        """Активирует отложенные ссылки поиска после закрытия модального окна генерации."""
        if body is None:
            body = {}
        ids = body.get("ids", [])
        q_user = (body.get("username") or "").strip()
        q_req = (body.get("request_id") or "").strip()
        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)
        if target_u:
            changed = False
            for s in target_u.get("avito_searches", []):
                if isinstance(s, dict) and s.get("is_pending"):
                    if not ids or s.get("id") in ids:
                        s["is_pending"] = 0
                        changed = True
            if changed:
                write_json_file(USERS_FILE, users, users_lock)

        if avito_api_helper:
            try:
                u_name = target_u.get("username") if target_u else None
                avito_api_helper.activate_pending_searches(username=u_name, search_ids=ids if ids else None)
            except Exception:
                pass

        global cached_raw_stats, last_stats_time
        with stats_cache_lock:
            cached_raw_stats = None
            last_stats_time = 0

        self.send_json(200, {"success": True})

    def handle_api_avito_delete_search(self, body: dict):
        global cached_raw_stats, last_stats_time
        q_user = (body.get("username") or "").strip()
        q_req = (body.get("request_id") or "").strip()
        search_id = int(body.get("id", 0)) if str(body.get("id", "")).isdigit() else 0
        target_url = (body.get("url") or "").strip()
        norm_url = target_url.rstrip("/").lower() if target_url else ""

        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)
        ret_searches = []

        if target_u and target_u.get("avito_searches"):
            def _is_target(s):
                s_id = int(s.get("id", 0)) if str(s.get("id", "")).isdigit() else 0
                if search_id > 0 and s_id == search_id:
                    return True
                if norm_url:
                    cur_u = (s.get("url") or "").strip().rstrip("/").lower()
                    if cur_u == norm_url:
                        return True
                return False

            target_u["avito_searches"] = [s for s in target_u["avito_searches"] if not _is_target(s)]
            ret_searches = target_u["avito_searches"]
            write_json_file(USERS_FILE, users, users_lock)

        with stats_cache_lock:
            cached_raw_stats = None
            last_stats_time = 0

        if avito_api_helper:
            try:
                avito_api_helper.delete_search(search_id=search_id, url=target_url)
            except Exception:
                pass

        self.send_json(200, {"success": True, "searches": ret_searches})

    def handle_api_avito_toggle_search(self, body: dict):
        global cached_raw_stats, last_stats_time
        q_user = (body.get("username") or "").strip()
        q_req = (body.get("request_id") or "").strip()
        search_id = int(body.get("id", 0))
        new_active = body.get("is_active")

        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)
        ret_active = 1
        ret_searches = target_u.get("avito_searches", [])

        for s in ret_searches:
            if int(s.get("id", 0)) == search_id:
                if new_active is not None:
                    s["is_active"] = int(new_active)
                else:
                    cur = int(s.get("is_active", 1))
                    s["is_active"] = 0 if cur == 1 else 1
                ret_active = s["is_active"]
                break

        write_json_file(USERS_FILE, users, users_lock)

        with stats_cache_lock:
            cached_raw_stats = None
            last_stats_time = 0

        if avito_api_helper:
            try:
                with avito_api_helper.get_db_connection() as conn:
                    conn.execute("UPDATE tracked_urls SET is_active = ? WHERE id = ?", (ret_active, search_id))
                    conn.commit()
            except Exception:
                pass

        self.send_json(200, {
            "success": True,
            "id": search_id,
            "is_active": ret_active,
            "searches": ret_searches
        })

    def handle_api_avito_edit_search(self, body: dict):
        q_user = (body.get("username") or "").strip()
        q_req = (body.get("request_id") or "").strip()
        search_id = int(body.get("id", 0))
        new_name = (body.get("name") or "").strip()
        new_url = (body.get("url") or "").strip()

        if not new_url or not re.match(r"^https?://", new_url):
            self.send_json(200, {"success": False, "error": "Ссылка должна начинаться с http:// или https://"})
            return

        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)
        ret_searches = target_u.get("avito_searches", [])

        for s in ret_searches:
            if int(s.get("id", 0)) == search_id:
                if new_name:
                    s["name"] = new_name
                s["url"] = new_url
                s["is_initialized"] = 0

        write_json_file(USERS_FILE, users, users_lock)

        global cached_raw_stats, last_stats_time
        with stats_cache_lock:
            cached_raw_stats = None
            last_stats_time = 0

        if avito_api_helper:
            try:
                owner = target_u.get("username") or "admin"
                avito_api_helper.edit_search(search_id, new_url, new_name, owner)
            except Exception:
                pass

        self.send_json(200, {
            "success": True,
            "id": search_id,
            "name": new_name,
            "url": new_url,
            "searches": ret_searches
        })

    def handle_api_avito_update_search_settings(self, body: dict):
        q_user = (body.get("username") or "").strip()
        q_req = (body.get("request_id") or "").strip()
        search_id = int(body.get("id", 0))
        autobuy = int(body.get("autobuy", 0) or 0)
        autoreserve = int(body.get("autoreserve", 0) or 0)
        max_price = float(body.get("max_price", 0) or 0)
        pwd = body.get("price_with_delivery")
        price_with_delivery = 1 if (pwd is None or pwd is True or pwd == 1) else 0
        min_rating = float(body.get("min_rating", 0) or 0)
        only_deliv = body.get("only_delivery")
        only_delivery = (1 if (only_deliv is True or only_deliv == 1) else 0) if only_deliv is not None else None

        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)
        if not target_u:
            self.send_json(200, {"success": False, "error": "Пользователь не найден"})
            return
        ret_searches = target_u.get("avito_searches", [])

        for s in ret_searches:
            if int(s.get("id", 0)) == search_id:
                s["autobuy"] = autobuy
                s["autoreserve"] = autoreserve
                s["max_price"] = max_price
                s["price_with_delivery"] = price_with_delivery
                s["min_rating"] = min_rating
                if only_delivery is not None:
                    s["only_delivery"] = only_delivery
                break

        write_json_file(USERS_FILE, users, users_lock)

        global cached_raw_stats, last_stats_time
        with stats_cache_lock:
            cached_raw_stats = None
            last_stats_time = 0

        if avito_api_helper:
            try:
                with avito_api_helper.get_db_connection() as conn:
                    if only_delivery is not None:
                        conn.execute("""
                            UPDATE tracked_urls 
                            SET autobuy = ?, autoreserve = ?, max_price = ?, price_with_delivery = ?, min_rating = ?, only_delivery = ?
                            WHERE id = ?
                        """, (autobuy, autoreserve, max_price, price_with_delivery, min_rating, only_delivery, search_id))
                        if only_delivery == 1:
                            conn.execute("""
                                DELETE FROM seen_items 
                                WHERE (has_delivery = 0 OR has_delivery IS NULL)
                                  AND item_id NOT IN (SELECT item_id FROM favorites)
                                  AND (
                                    LOWER(search_name) IN (SELECT LOWER(name) FROM tracked_urls WHERE id = ?)
                                    OR url IN (SELECT url FROM tracked_urls WHERE id = ?)
                                  )
                            """, (search_id, search_id))
                    else:
                        conn.execute("""
                            UPDATE tracked_urls 
                            SET autobuy = ?, autoreserve = ?, max_price = ?, price_with_delivery = ?, min_rating = ?
                            WHERE id = ?
                        """, (autobuy, autoreserve, max_price, price_with_delivery, min_rating, search_id))
                    conn.commit()
            except Exception as e:
                logger.error(f"Error updating search automation settings in DB: {e}")

        self.send_json(200, {
            "success": True,
            "id": search_id,
            "autobuy": autobuy,
            "autoreserve": autoreserve,
            "max_price": max_price,
            "price_with_delivery": price_with_delivery,
            "min_rating": min_rating,
            "only_delivery": only_delivery if only_delivery is not None else 0,
            "searches": ret_searches
        })

    def handle_api_avito_check(self):
        if not avito_check_lock.acquire(blocking=False):
            self.send_json(200, {"success": True, "busy": True, "message": "Опрос уже выполняется"})
            return
        try:
            if avito_api_helper:
                try:
                    import asyncio
                    res = asyncio.run(asyncio.wait_for(avito_api_helper.run_check(), timeout=120.0))
                except Exception:
                    res = {"success": True, "busy": False, "new_items": [], "removed_items": []}
            else:
                res = {"success": True}

            global last_stats_time, cached_raw_stats
            with stats_cache_lock:
                last_stats_time = 0
                cached_raw_stats = None

            self.send_json(200, res)
        finally:
            avito_check_lock.release()

    def handle_api_avito_fetch_all(self, body: dict = None):
        if body is None:
            body = {}
        q_user = body.get("username") or self.get_query_param("username") or "skynet83"
        s_name = body.get("search_name") or self.get_query_param("search_name") or ""
        s_url = body.get("search_url") or body.get("url") or self.get_query_param("search_url") or self.get_query_param("url") or ""
        only_deliv = body.get("only_delivery")
        if only_deliv is None:
            only_deliv = self.get_query_param("only_delivery")
        only_delivery = (1 if (only_deliv is True or only_deliv == 1 or str(only_deliv) in ("1", "true")) else 0) if only_deliv is not None else None

        if avito_api_helper:
            try:
                import asyncio
                res = asyncio.run(avito_api_helper.fetch_all_ads(username=q_user, search_name=s_name, search_url=s_url, only_delivery=only_delivery))
            except Exception as e:
                res = {"success": False, "error": str(e)}
        else:
            res = {"success": False, "error": "avito_api_helper not available"}

        global last_stats_time, cached_raw_stats
        with stats_cache_lock:
            last_stats_time = 0
            cached_raw_stats = None

        self.send_json(200, res)

    def handle_api_avito_interval(self, body: dict = None):
        if body:
            sec_arg = str(body.get("interval", "1"))
            if sec_arg.lower().startswith("rand"):
                sec_arg = "1"
            req_user = str(body.get("username", "")).strip()
            req_id = str(body.get("request_id", "")).strip()

            target_u, users = self.resolve_user_profile(req_user, req_id=req_id)

            if target_u:
                is_admin = target_u.get("role") == "admin"
                u_min = int(target_u.get("target_interval", 1))
                req_sec = int(sec_arg) if sec_arg.isdigit() else 1
                if not is_admin and req_sec < u_min:
                    sec_arg = str(u_min)
                target_u["active_interval"] = sec_arg
                write_json_file(USERS_FILE, users, users_lock)

                if is_admin and avito_api_helper:
                    try:
                        avito_api_helper.set_target_interval(sec_arg)
                    except Exception:
                        pass

        # GET или отдача текущего значения
        q_user = (body.get("username") if body else None) or self.get_query_param("username")
        q_req = (body.get("request_id") if body else None) or self.get_query_param("request_id")
        target_u, users = self.resolve_user_profile(q_user, req_id=q_req)

        int_obj = avito_api_helper.get_interval_info() if avito_api_helper else {"success": True, "target_interval": "1", "proxy_count": 0}
        if target_u:
            u_target = str(target_u.get("active_interval") or target_u.get("target_interval") or "1")
            if u_target.lower().startswith("rand"):
                u_target = "1"
            int_obj["target_interval"] = u_target
            p_cnt = int(int_obj.get("proxy_count", 0))
            if u_target.isdigit():
                t_sec = int(u_target)
                needed = min(360, max(15, int(-(-30 // max(1, t_sec))) * 10))
                safe = t_sec if p_cnt >= needed else max(t_sec, int(-(-30 // max(1, p_cnt))))
                int_obj["needed_proxies"] = needed
                int_obj["safe_interval"] = safe
                int_obj["is_random"] = False
            else:
                int_obj["needed_proxies"] = 15
                int_obj["safe_interval"] = "30-60"
                int_obj["is_random"] = True

        self.send_json(200, int_obj)

    def handle_api_avito_proxies(self):
        q_user = self.get_query_param("username")
        if avito_api_helper:
            res = avito_api_helper.get_proxies(username=q_user or None)
        else:
            res = {"success": True, "proxies": []}
        self.send_json(200, res)

    def handle_api_avito_item_reviews(self):
        item_id = self.get_query_param("item_id") or self.get_query_param("id") or self.get_query_param("itemId") or ""
        item_url = self.get_query_param("url") or self.get_query_param("item_url") or ""
        seller = self.get_query_param("seller") or ""
        rating = self.get_query_param("rating") or ""
        refresh = self.get_query_param("refresh") in ("1", "true", "yes") or self.get_query_param("force") == "1"
        fetch_param = self.get_query_param("fetch")
        fetch = True if refresh else (False if fetch_param in ("0", "false", "no") else True)

        if not item_id:
            self.send_json(400, {"success": False, "error": "item_id обязателен"})
            return

        if avito_api_helper:
            try:
                res = avito_api_helper.get_item_reviews(item_id=item_id, item_url=item_url, refresh=refresh, fetch=fetch, seller=seller, rating=rating)
            except Exception as e:
                res = {"success": False, "error": str(e)}
        else:
            res = {"success": False, "error": "avito_api_helper недоступен"}
        self.send_json(200, res)

    def handle_api_avito_item_details(self):
        item_id = self.get_query_param("item_id") or self.get_query_param("id") or self.get_query_param("itemId") or ""
        item_url = self.get_query_param("url") or self.get_query_param("item_url") or ""
        if not item_id:
            self.send_json(400, {"success": False, "error": "item_id обязателен"})
            return

        if avito_api_helper:
            try:
                res = avito_api_helper.get_item_details(item_id=item_id, item_url=item_url)
            except Exception as e:
                res = {"success": False, "error": str(e)}
        else:
            res = {"success": False, "error": "avito_api_helper недоступен"}
        self.send_json(200, res)

    def handle_api_avito_proxy_image(self):
        """Безопасное кэширование и проксирование картинок Avito через пул прокси без утечки реального IP сервера."""
        img_url = self.get_query_param("url")
        if not img_url or not ("avito.st" in img_url or "avito.ru" in img_url):
            self.send_response(400)
            self.end_headers()
            return

        cache_dir = os.path.join(DATA_DIR, "img_cache")
        os.makedirs(cache_dir, exist_ok=True)
        cache_key = hashlib.md5(img_url.encode("utf-8")).hexdigest()
        cache_file = os.path.join(cache_dir, f"{cache_key}.jpg")

        if os.path.exists(cache_file) and os.path.getsize(cache_file) > 500:
            try:
                with open(cache_file, "rb") as f:
                    content = f.read()
                ctype = "image/jpeg"
                if content.startswith(b"RIFF") and b"WEBP" in content[:16]:
                    ctype = "image/webp"
                elif content.startswith(b"\x89PNG"):
                    ctype = "image/png"
                elif content.startswith(b"\xff\xd8\xff"):
                    ctype = "image/jpeg"
                self.send_response(200)
                self.send_header("Content-Type", ctype)
                self.send_header("Cache-Control", "public, max-age=604800")
                self.send_header("Content-Length", str(len(content)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(content)
                return
            except Exception:
                pass

        # Если в кэше нет — скачиваем: сначала пробуем через живой прокси, при сбое — напрямую с Avito CDN
        img_data = None
        img_proxy = avito_api_helper.get_live_proxy_server() if avito_api_helper else None
        if img_proxy:
            try:
                from curl_cffi.requests import Session as _CurlSession
                if img_proxy.startswith("socks5://"):
                    img_proxy = "socks5h://" + img_proxy[9:]
                with _CurlSession(impersonate="safari15_5", proxy=img_proxy, timeout=3.5) as s:
                    headers = {
                        "User-Agent": (
                            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
                            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
                        ),
                        "Referer": "https://www.avito.ru/",
                        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                    }
                    r = s.get(img_url, headers=headers)
                    if r.status_code == 200 and r.content and len(r.content) > 500:
                        img_data = r.content
            except Exception:
                pass

        # Надежный фоллбек: прямое скачивание с CDN Avito (CDN avito.st отдает статику без блокировок)
        if not img_data:
            try:
                import urllib.request
                dl_req = urllib.request.Request(
                    img_url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                        "Referer": "https://www.avito.ru/",
                        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                    }
                )
                with urllib.request.urlopen(dl_req, timeout=5) as dl_resp:
                    if dl_resp.status == 200:
                        raw_c = dl_resp.read()
                        if len(raw_c) > 500:
                            img_data = raw_c
            except Exception:
                pass

        if img_data:
            try:
                with open(cache_file, "wb") as f:
                    f.write(img_data)
            except Exception:
                pass

            ctype = "image/jpeg"
            if img_data.startswith(b"RIFF") and b"WEBP" in img_data[:16]:
                ctype = "image/webp"
            elif img_data.startswith(b"\x89PNG"):
                ctype = "image/png"
            elif img_data.startswith(b"\xff\xd8\xff"):
                ctype = "image/jpeg"

            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "public, max-age=604800")
            self.send_header("Content-Length", str(len(img_data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(img_data)
        else:
            self.send_response(404)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

    # ── Управление звуками оповещения ─────────────────────────────────────────
    def handle_api_sound_list(self):
        sound_dir = os.path.join(BASE_DIR, "sound")
        presets = [
            {"id": "default", "name": "Системный звук (по умолчанию)", "file": "sound/notification.mp3?v=98.0", "duration": "1.5с", "icon": "🔔"}
        ]
        custom_info = None
        if os.path.isdir(sound_dir):
            for fname in os.listdir(sound_dir):
                if fname.startswith("custom_user_sound."):
                    fpath = os.path.join(sound_dir, fname)
                    if os.path.isfile(fpath):
                        custom_info = {
                            "exists": True,
                            "url": f"sound/{fname}?t={int(os.path.getmtime(fpath))}",
                            "filename": fname,
                            "size": os.path.getsize(fpath)
                        }
                        break
        self.send_json(200, {
            "success": True,
            "presets": presets,
            "custom": custom_info
        })

    def handle_api_sound_custom_upload(self, body: dict):
        filename = (body.get("filename") or "custom_sound.mp3").strip()
        data_b64 = body.get("data") or ""
        if not data_b64:
            self.send_json(400, {"success": False, "message": "Данные аудиофайла не получены"})
            return
        if "," in data_b64:
            data_b64 = data_b64.split(",", 1)[1]
        try:
            raw_bytes = base64.b64decode(data_b64)
        except Exception as e:
            self.send_json(400, {"success": False, "message": f"Ошибка декодирования base64: {e}"})
            return
        if len(raw_bytes) > 25 * 1024 * 1024:
            self.send_json(400, {"success": False, "message": "Файл превышает лимит 25 МБ"})
            return

        sound_dir = os.path.join(BASE_DIR, "sound")
        os.makedirs(sound_dir, exist_ok=True)
        ext = os.path.splitext(filename)[1].lower()
        if ext not in (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"):
            ext = ".mp3"

        for f in os.listdir(sound_dir):
            if f.startswith("custom_user_sound."):
                try:
                    os.remove(os.path.join(sound_dir, f))
                except Exception:
                    pass

        target_name = f"custom_user_sound{ext}"
        target_path = os.path.join(sound_dir, target_name)
        try:
            with open(target_path, "wb") as f:
                f.write(raw_bytes)
        except Exception as e:
            self.send_json(500, {"success": False, "message": f"Ошибка записи файла на диск: {e}"})
            return

        now_ts = int(time.time())
        self.send_json(200, {
            "success": True,
            "url": f"sound/{target_name}?t={now_ts}",
            "filename": filename,
            "size": len(raw_bytes)
        })

    def handle_api_sound_load_by_path(self, body: dict):
        raw_path = (body.get("path") or "").strip()
        if (raw_path.startswith('"') and raw_path.endswith('"')) or (raw_path.startswith("'") and raw_path.endswith("'")):
            raw_path = raw_path[1:-1].strip()

        if not raw_path:
            self.send_json(400, {"success": False, "message": "Укажите путь к звуковому файлу на диске"})
            return

        norm_path = os.path.normpath(raw_path)
        if not os.path.isfile(norm_path):
            self.send_json(404, {"success": False, "message": f"Файл не найден по указанному пути:\n{norm_path}"})
            return

        ext = os.path.splitext(norm_path)[1].lower()
        if ext not in (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac"):
            self.send_json(400, {
                "success": False,
                "message": f"Неподдерживаемый аудиоформат '{ext}'. Поддерживаются: .mp3, .wav, .ogg, .m4a"
            })
            return

        try:
            fsize = os.path.getsize(norm_path)
            if fsize > 25 * 1024 * 1024:
                self.send_json(400, {"success": False, "message": "Файл слишком большой (максимум 25 МБ)"})
                return

            sound_dir = os.path.join(BASE_DIR, "sound")
            os.makedirs(sound_dir, exist_ok=True)
            for f in os.listdir(sound_dir):
                if f.startswith("custom_user_sound."):
                    try:
                        os.remove(os.path.join(sound_dir, f))
                    except Exception:
                        pass

            target_name = f"custom_user_sound{ext}"
            target_path = os.path.join(sound_dir, target_name)
            shutil.copy2(norm_path, target_path)

            now_ts = int(time.time())
            self.send_json(200, {
                "success": True,
                "url": f"sound/{target_name}?t={now_ts}",
                "filename": os.path.basename(norm_path),
                "size": fsize
            })
        except Exception as e:
            self.send_json(500, {"success": False, "message": f"Ошибка чтения/копирования файла: {e}"})

    # ── Sniper Обработчики ───────────────────────────────────────────────────
    def handle_api_sniper_status(self):
        global last_sniper_status, last_sniper_time
        now_ts = time.time()
        force = self.get_query_param("force") == "1"
        is_neg = last_sniper_status and not last_sniper_status.get("authenticated")

        if not force and last_sniper_status and (now_ts - last_sniper_time) < 12.0 and not is_neg:
            self.send_json(200, last_sniper_status)
            return

        if avito_sniper:
            try:
                import asyncio
                res = asyncio.run(avito_sniper.check_auth_status())
                last_sniper_status = res
                last_sniper_time = now_ts
            except Exception as e:
                res = {"success": False, "authenticated": False, "error": str(e)}
        else:
            res = {"success": True, "authenticated": False, "message": "avito_sniper not installed"}
        self.send_json(200, res)

    def handle_sniper_checkout(self, body: dict):
        item_id = str(body.get("item_id", ""))
        item_url = str(body.get("url", ""))
        auto_pay = bool(body.get("auto_pay", False))
        headless = bool(body.get("headless", True))
        if avito_sniper:
            try:
                import asyncio
                res = asyncio.run(avito_sniper.instant_checkout(item_id, item_url, auto_pay=auto_pay, headless=headless))
            except Exception as e:
                res = {"success": False, "error": str(e)}
        else:
            res = {"success": False, "error": "avito_sniper not available"}
        self.send_json(200, res)

    def handle_sniper_checkout_preview(self, body: dict):
        item_id = str(body.get("item_id", ""))
        item_url = str(body.get("url", ""))
        if avito_sniper:
            try:
                import asyncio
                res = asyncio.run(avito_sniper.get_checkout_preview(item_id, item_url))
            except Exception as e:
                res = {"success": False, "error": str(e)}
        else:
            res = {"success": False, "error": "avito_sniper not available"}
        self.send_json(200, res)

    def handle_sniper_checkout_confirm(self, body: dict):
        item_id = str(body.get("item_id", ""))
        item_url = str(body.get("url", ""))
        pm = str(body.get("payment_method", "card"))
        sms = str(body.get("sms_code", "")).strip() or None
        if avito_sniper:
            try:
                import asyncio
                res = asyncio.run(avito_sniper.confirm_checkout_order(item_id, item_url, payment_method=pm, sms_code=sms))
            except Exception as e:
                res = {"success": False, "error": str(e)}
        else:
            res = {"success": False, "error": "avito_sniper not available"}
        self.send_json(200, res)

    def handle_sniper_message(self, body: dict):
        item_id = str(body.get("item_id", ""))
        item_url = str(body.get("url", ""))
        msg = str(body.get("message", "Здравствуйте! Товар в наличии?"))
        if avito_sniper:
            try:
                import asyncio
                res = asyncio.run(avito_sniper.send_seller_message(item_id, item_url, msg))
            except Exception as e:
                res = {"success": False, "error": str(e)}
        else:
            res = {"success": False, "error": "avito_sniper not available"}
        self.send_json(200, res)

    def handle_sniper_cancel_order(self, body: dict):
        item_id = str(body.get("item_id", ""))
        item_url = str(body.get("url", ""))
        order_url = str(body.get("order_url", "")) or None
        if avito_sniper:
            try:
                import asyncio
                res = asyncio.run(avito_sniper.cancel_order(item_id, item_url=item_url, order_url=order_url))
            except Exception as e:
                res = {"success": False, "error": str(e)}
        else:
            res = {"success": False, "error": "avito_sniper not available"}
        self.send_json(200, res)

    def handle_sniper_check_cart_orders(self, body: dict):
        items = body.get("items", [])
        if avito_sniper:
            try:
                import asyncio
                res = asyncio.run(avito_sniper.check_cart_orders_status(items))
            except Exception as e:
                res = {"success": False, "error": str(e)}
        else:
            res = {"success": False, "error": "avito_sniper not available"}
        self.send_json(200, res)

    def handle_sniper_open_review(self, body: dict):
        if not avito_sniper:
            self.send_json(200, {"success": False, "error": "Модуль Снайпера (avito_sniper) недоступен"})
            return
        item_id = str((body or {}).get("item_id", "")).strip()
        item_url = str((body or {}).get("item_url", "")).strip()

        def _bg_open():
            try:
                import asyncio
                asyncio.run(avito_sniper.open_review_window(item_id, item_url=item_url))
            except Exception as e:
                print(f"[!] Ошибка запуска окна отзыва Снайпера: {e}", file=sys.stderr)

        threading.Thread(target=_bg_open, daemon=True).start()
        self.send_json(200, {
            "success": True,
            "message": "Окно Снайпера открывается... Поставьте оценку и напишите отзыв!"
        })

    # ── Раздача статических файлов ───────────────────────────────────────────
    def serve_static_file(self, url_path: str):
        # Защита внутреннего порта 8081 от прямого открытия пользователем в браузере
        if server_port == 8081:
            deny_html = """<!DOCTYPE html><html lang="ru"><head><meta charset="UTF-8"><title>403 Доступ закрыт</title>
<style>body{font-family:sans-serif;background:#0f172a;color:#f8fafc;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}
.card{background:#1e293b;border:1px solid #334155;border-radius:16px;padding:2.5rem;max-width:520px;text-align:center;box-shadow:0 10px 25px rgba(0,0,0,0.5)}
h1{color:#ef4444;font-size:1.5rem;margin-top:0}p{color:#94a3b8;font-size:0.95rem;line-height:1.6;margin:1rem 0}
.badge{display:inline-block;background:rgba(239,68,68,0.15);color:#ef4444;border:1px solid rgba(239,68,68,0.3);border-radius:6px;padding:0.2rem 0.5rem;font-family:monospace}
.btn{display:inline-block;background:#0284c7;color:#fff;text-decoration:none;padding:0.7rem 1.4rem;border-radius:10px;font-weight:bold;margin-top:1rem}
.btn:hover{background:#0369a1}</style></head><body><div class="card"><h1>🔒 Доступ к интерфейсу закрыт</h1>
<p>Порт <span class="badge">8081</span> используется исключительно как внутренний API-сервис бэкенда.</p>
<p>Прямое открытие веб-страницы через порт 8081 заблокировано. Откройте сайт по официальному адресу:</p>
<a href="http://localhost/" class="btn">Перейти на сайт (http://localhost)</a></div></body></html>"""
            self.send_html(403, deny_html)
            return

        if url_path in ("/", ""):
            url_path = "/index.html"

        rel_path = url_path.lstrip("/").replace("/", os.sep)
        full_path = os.path.join(BASE_DIR, rel_path)

        if not os.path.exists(full_path) or os.path.isdir(full_path):
            self.send_response(404)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(f"404 Not Found: {url_path}".encode("utf-8"))
            return

        try:
            with open(full_path, "rb") as f:
                data = f.read()

            ext = os.path.splitext(full_path)[1].lower()
            content_type = mimetypes.guess_type(full_path)[0] or "application/octet-stream"

            if ext == ".html":
                content_type = "text/html; charset=utf-8"
            elif ext == ".css":
                content_type = "text/css; charset=utf-8"
            elif ext == ".js":
                content_type = "application/javascript; charset=utf-8"
            elif ext == ".json":
                content_type = "application/manifest+json; charset=utf-8" if "manifest.json" in full_path else "application/json; charset=utf-8"

            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Type", content_type)

            # Кэширование
            if "sw.js" in full_path or "custom_user_sound" in full_path:
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                if "sw.js" in full_path:
                    self.send_header("Service-Worker-Allowed", "/")
            elif ext in (".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".mp3", ".wav", ".ogg", ".m4a", ".pdf"):
                self.send_header("Cache-Control", "public, max-age=86400")
            else:
                self.send_header("Cache-Control", "no-cache, must-revalidate")

            # GZip сжатие для текстовых ресурсов
            accept_enc = self.headers.get("Accept-Encoding", "")
            if "gzip" in accept_enc and ext in (".html", ".css", ".js", ".json", ".svg", ".webmanifest") and len(data) > 1024:
                compressed = gzip.compress(data, compresslevel=6)
                if len(compressed) < len(data):
                    self.send_header("Content-Encoding", "gzip")
                    data = compressed

            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)
        except Exception as e:
            if not is_client_disconnect(e):
                pass

    def render_blacklisted_page(self, remote_ip: str, client_mac: str):
        html = f"""<!DOCTYPE html><html lang='ru'><head><meta charset='utf-8'><title>Доступ заблокирован</title>
<meta name='viewport' content='width=device-width, initial-scale=1.0'>
<style>body{{background:#0f172a;color:#f8fafc;font-family:system-ui,-apple-system,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;padding:1rem;box-sizing:border-box;}}
.card{{background:#1e293b;border:1px solid #ef4444;border-radius:16px;padding:2.5rem 2rem;max-width:480px;text-align:center;box-shadow:0 10px 25px rgba(239,68,68,0.2);}}
.icon{{font-size:3.5rem;margin-bottom:1rem;}}.title{{color:#ef4444;font-size:1.5rem;margin-bottom:0.75rem;font-weight:700;}}
.desc{{color:#94a3b8;font-size:0.95rem;line-height:1.6;margin-bottom:1.5rem;}}
.details{{background:#0f172a;padding:0.75rem 1rem;border-radius:8px;font-family:monospace;font-size:0.82rem;color:#cbd5e1;display:flex;flex-direction:column;gap:0.4rem;text-align:left;}}</style>
</head><body><div class='card'><div class='icon'>🚫</div><div class='title'>Доступ заблокирован</div>
<div class='desc'>Ваше устройство или учетная запись внесены администратором сервера в черный список (ЧС). Обратитесь к администратору для разблокировки.</div>
<div class='details'><div>🌐 IP: {remote_ip}</div><div>🏷️ MAC: {client_mac or 'не определен'}</div></div></div></body></html>"""
        self.send_html(403, html)


# ── Запуск и жизненный цикл ──────────────────────────────────────────────────
def parse_cli_args():
    import argparse
    parser = argparse.ArgumentParser(description="SkyBase Pure-Python Web Server")
    parser.add_argument("--port", "-p", "-Port", type=int, default=0, help="Порт сервера (по умолчанию 8081 или 8080/80)")
    parser.add_argument("--no-browser", "-NoBrowser", action="store_true", help="Не открывать веб-браузер")
    args, unknown = parser.parse_known_args()

    port = args.port
    if port <= 0:
        # Проверяем позиционные аргументы или переменные окружения
        for u in unknown:
            if u.isdigit():
                port = int(u)
                break
    if port <= 0:
        env_p = os.environ.get("SERVER_PORT") or os.environ.get("PORT")
        if env_p and env_p.isdigit():
            port = int(env_p)
        else:
            port = 8081

    return port, args.no_browser


def main():
    global server_port, server_instance
    port, no_browser = parse_cli_args()
    server_port = port

    # Запись PID
    pid = os.getpid()
    try:
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(pid))
    except Exception:
        pass

    def cleanup(sig=None, frame=None):
        print(f"\n[*] Остановка SkyBase Server (PID {pid})...")
        try:
            if avito_api_helper:
                avito_api_helper.bot_toggle("stop")
        except Exception:
            pass
        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass
        sys.exit(0)

    signal.signal(signal.SIGINT, cleanup)
    signal.signal(signal.SIGTERM, cleanup)

    # Инициализация и автозапуск бота синхронно с сервером
    if avito_api_helper:
        try:
            avito_api_helper.bot_toggle("start")
        except Exception as e:
            print(f"[!] Ошибка запуска Telegram-бота: {e}", file=sys.stderr)

    # Фоновая синхронизация счетчика триалов в шапке группы AvitoHunter
    try:
        import cloud_license
        threading.Thread(target=cloud_license.sync_cloud_header_counter, daemon=True).start()
    except Exception:
        pass

    loc_ip = get_local_ip()
    print("=======================================================")
    print(f"       SkyBase Server v2.0 (Pure-Python Backend)")
    print(f"       Порт:      {server_port}")
    print(f"       Localhost: http://localhost:{server_port}/")
    print(f"       LAN IP:    http://{loc_ip}:{server_port}/")
    print(f"       PID:       {pid}")
    print("=======================================================")

    try:
        server_instance = ThreadingHTTPServer(("0.0.0.0", server_port), SkyBaseHandler)
        server_instance.serve_forever()
    except KeyboardInterrupt:
        cleanup()
    except Exception as e:
        print(f"[КРИТИЧЕСКАЯ ОШИБКА] Сбой сервера на порту {server_port}: {e}", file=sys.stderr)
        cleanup()


if __name__ == "__main__":
    main()
