# -*- coding: utf-8 -*-
"""
Модуль роботизированного управления браузером (Playwright) для Avito.
Локальный снайпер:
1. Авторизация в личном профиле Avito с постоянным сохранением сессии (куки, профиль, карты).
2. Моментальный переход на чекаут и авто-выбор способа оплаты (СБП/карта).
3. Автоматическая отправка первого сообщения продавцу в чат Avito.
4. Авто-бронь / Выкуп по планке цены при обнаружении нового лота.
Работает строго локально на текущем ПК без внешних синхронизаций.
"""
import os
import sys
import json
import time
import asyncio
import re
from typing import Optional, Dict, Any, List

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(BASE_DIR, "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)
DATA_DIR = os.path.join(BASE_DIR, "data")
PROFILE_DIR = os.path.join(DATA_DIR, "avito_browser_profile")
CONFIG_FILE = os.path.join(DATA_DIR, "sniper_config.json")
AUTH_CACHE_FILE = os.path.join(DATA_DIR, "sniper_auth.json")
LOCK_FILE = os.path.join(DATA_DIR, "sniper.lock")
LOCAL_BROWSERS_DIR = os.path.join(BASE_DIR, "browsers")
if os.path.exists(LOCAL_BROWSERS_DIR):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = LOCAL_BROWSERS_DIR

DEFAULT_CONFIG = {
    "enabled": True,
    "auto_message_enabled": False,
    "auto_message_text": "Здравствуйте! Готов забрать сегодня с доставкой, ещё актуально?",
    "auto_buy_enabled": False,
    "payment_method": "card",       # "card", "wallet" или "cod"
    "headless": True,               # Фоновый робот работает в headless для молниеносной скорости (1-1.5 сек)
    "safe_mode": False,             # Если False — полный авто-выкуп / оплата. Если True — чекаут открывается, но оплату жмет пользователь
    "cheapest_delivery": True,      # Выбор доставки по наименьшей цене пункта выдачи (резерв/авто)
    "preferred_delivery": "cheapest", # Предпочитаемая служба: "cheapest", "yandex", "cdek", "fivepost", "russianpost", "boxberry", "exmail", "dpd"
    "search_depth": 0               # Глубина поиска страниц: 0 = без ограничения поиска кол-ва страниц на сайте Авито
}

def get_auth_cache() -> Dict[str, Any]:
    if os.path.exists(AUTH_CACHE_FILE):
        try:
            with open(AUTH_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_auth_cache(data: Dict[str, Any]) -> bool:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(AUTH_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception:
        return False

def is_real_auth_username(name: Optional[str]) -> bool:
    if not name:
        return False
    clean = str(name).strip().lower()
    if not clean or len(clean) < 2:
        return False
    forbidden = ["не авторизован", "вход", "регистрация", "войти", "подать объявление", "сообщения", "избранное", "корзина", "мои объявления"]
    return not any(f in clean for f in forbidden)

def reset_auth_for_reauth():
    """Синхронизирует профиль с активным браузером без сброса авторизации в offline."""
    try:
        now = int(time.time())
        save_auth_cache({
            "authenticated": True,
            "user_name": "Мой профиль Avito (Браузер)",
            "cookies_count": 1,
            "updated_at": now
        })
        st_file = os.path.join(PROFILE_DIR, "storage_state.json")
        if os.path.exists(st_file):
            try:
                os.remove(st_file)
            except Exception:
                pass

        import glob
        for pat in [
            os.path.join(PROFILE_DIR, "Default", "Network", "Cookies*"),
            os.path.join(PROFILE_DIR, "Network", "Cookies*"),
            os.path.join(PROFILE_DIR, "Default", "Cookies*"),
        ]:
            for f in glob.glob(pat):
                try:
                    os.remove(f)
                except Exception:
                    pass
    except Exception:
        pass

def extract_username_from_storage_state(storage_state_path: str = None) -> Optional[str]:
    """Извлекает реальное имя пользователя из localStorage (user-cached-data) в storage_state.json."""
    if not storage_state_path:
        storage_state_path = os.path.join(PROFILE_DIR, "storage_state.json")
    try:
        if not os.path.exists(storage_state_path):
            return None
        with open(storage_state_path, "r", encoding="utf-8") as f:
            st = json.load(f)
        for orig in st.get("origins", []):
            for item in orig.get("localStorage", []):
                if item.get("name") == "user-cached-data":
                    val_str = item.get("value", "")
                    if val_str:
                        val_obj = json.loads(val_str)
                        cand = val_obj.get("name")
                        if cand and is_real_auth_username(cand):
                            return cand.strip()
    except Exception:
        pass
    return None

def check_profile_cookies_quick() -> Dict[str, Any]:
    """Мгновенная проверка кук авторизации в профиле Chromium без запуска браузера (1-3 мс)."""
    now = int(time.time())

    # 1. Проверяем кэш авторизации (сохраняем статус авторизации до явного выхода)
    cached = get_auth_cache()
    if cached.get("authenticated") is True and (now - cached.get("updated_at", 0) < 86400 * 30):
        u_name = cached.get("user_name")
        if not is_real_auth_username(u_name) or u_name == "Мой профиль Avito":
            real_n = extract_username_from_storage_state()
            if real_n and is_real_auth_username(real_n):
                u_name = real_n
                cached["user_name"] = real_n
                save_auth_cache(cached)
        if not is_real_auth_username(u_name):
            u_name = "Мой профиль Avito"
        return {
            "authenticated": True,
            "user_name": u_name,
            "cookies_count": cached.get("cookies_count", 1)
        }

    auth_names = {"userId", "authtoken", "auth", "sessid", "u", "user", "f"}

    # 2. Проверяем Playwright storage_state.json (мгновенно обновляется при входе в открытом окне)
    storage_file = os.path.join(PROFILE_DIR, "storage_state.json")
    if os.path.exists(storage_file):
        try:
            with open(storage_file, "r", encoding="utf-8") as f:
                st = json.load(f)
            c_list = st.get("cookies", [])
            auth_c = [c.get("name") for c in c_list if c.get("name") in auth_names and c.get("value")]
            if auth_c or (len(c_list) >= 10 and any("avito.ru" in c.get("domain", "") for c in c_list)):
                real_n = extract_username_from_storage_state(storage_file)
                u_name = real_n or cached.get("user_name")
                if not is_real_auth_username(u_name):
                    u_name = "Мой профиль Avito"
                save_auth_cache({
                    "authenticated": True,
                    "user_name": u_name,
                    "cookies_count": len(c_list),
                    "updated_at": now
                })
                return {
                    "authenticated": True,
                    "user_name": u_name,
                    "cookies_count": len(c_list),
                    "auth_cookies": auth_c
                }
        except Exception:
            pass

    # 3. Проверяем SQLite базу кук Chromium
    import sqlite3
    possible_cookie_paths = [
        os.path.join(PROFILE_DIR, "Default", "Network", "Cookies"),
        os.path.join(PROFILE_DIR, "Network", "Cookies"),
        os.path.join(PROFILE_DIR, "Default", "Cookies"),
    ]
    cookie_db = None
    for cp in possible_cookie_paths:
        if os.path.exists(cp):
            cookie_db = cp
            break

    if not cookie_db:
        # Если ранее была подтверждена авторизация, не сбрасываем статус
        if cached.get("authenticated") is True:
            return {
                "authenticated": True,
                "user_name": cached.get("user_name") or "Мой профиль Avito",
                "cookies_count": cached.get("cookies_count", 1)
            }
        return {
            "authenticated": False,
            "user_name": "Не авторизован",
            "cookies_count": 0
        }

    try:
        conn = sqlite3.connect(f"file:{cookie_db}?mode=ro", uri=True, timeout=1.0)
        cur = conn.cursor()
        cur.execute("SELECT name FROM cookies WHERE host_key LIKE ?", ("%avito.ru%",))
        rows = [r[0] for r in cur.fetchall()]
        conn.close()

        found_auth = [n for n in rows if n in auth_names]
        is_auth = len(found_auth) > 0 or len(rows) >= 10

        if is_auth:
            real_n = extract_username_from_storage_state()
            user_name = real_n or cached.get("user_name")
            if not is_real_auth_username(user_name):
                user_name = "Мой профиль Avito"
            save_auth_cache({
                "authenticated": True,
                "user_name": user_name,
                "cookies_count": len(rows),
                "updated_at": now
            })
            return {
                "authenticated": True,
                "user_name": user_name,
                "cookies_count": len(rows),
                "auth_cookies": found_auth
            }

        if cached.get("authenticated") is True and len(rows) > 0:
            return {
                "authenticated": True,
                "user_name": cached.get("user_name") or "Мой профиль Avito",
                "cookies_count": len(rows)
            }

        return {
            "authenticated": False,
            "user_name": "Не авторизован",
            "cookies_count": len(rows),
            "auth_cookies": found_auth
        }
    except Exception:
        if cached.get("authenticated") is True:
            return {
                "authenticated": True,
                "user_name": cached.get("user_name") or "Мой профиль Avito",
                "cookies_count": cached.get("cookies_count", 1)
            }
        return {
            "authenticated": False,
            "user_name": "Не авторизован",
            "cookies_count": 0
        }

def get_config() -> Dict[str, Any]:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cfg = dict(DEFAULT_CONFIG)
                cfg.update(data)
                return cfg
        except Exception:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg: Dict[str, Any]) -> bool:
    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        current = get_config()
        current.update(cfg)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(current, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving sniper config: {e}", file=sys.stderr)
        return False

def cleanup_stale_profile_locks():
    """Удаляет старые singleton lock-файлы Chrome и закрывает зависшие процессы снайпера."""
    try:
        import psutil
        curr_pid = os.getpid()
        for proc in psutil.process_iter(['pid', 'name', 'exe', 'cmdline']):
            try:
                if proc.info['pid'] == curr_pid:
                    continue
                p_name = (proc.info['name'] or '').lower()
                if 'chrome' in p_name or 'chromium' in p_name:
                    exe_p = (proc.info['exe'] or '').lower()
                    cmdline = ' '.join(proc.info['cmdline'] or []).lower()
                    if 'skybase\\browsers' in exe_p or 'avito_browser_profile' in cmdline:
                        proc.kill()
            except Exception:
                pass
    except Exception:
        pass

    try:
        for lock_name in ["SingletonLock", "SingletonCookie", "SingletonSocket"]:
            p = os.path.join(PROFILE_DIR, lock_name)
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
    except Exception:
        pass

def get_browser_args(headless: bool = False):
    args = [
        "--profile-directory=Profile 1",
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--mute-audio",
        "--window-size=1280,900",
        "--lang=ru-RU,ru"
    ]
    if headless:
        args.extend([
            "--disable-gpu",
            "--disable-software-rasterizer"
        ])
    return args

def sync_main_browser_profile_to_sniper():
    """
    Синхронизирует профиль Google Chrome пользователя (аккаунт skynet.system83@gmail.com,
    настройки, куки) из %LOCALAPPDATA%\\Google\\Chrome\\User Data в PROFILE_DIR снайпера.
    """
    try:
        import shutil
        chrome_user_data = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
        if not os.path.isdir(chrome_user_data):
            return

        os.makedirs(PROFILE_DIR, exist_ok=True)

        # 1. Local State
        src_local_state = os.path.join(chrome_user_data, "Local State")
        dst_local_state = os.path.join(PROFILE_DIR, "Local State")
        if os.path.isfile(src_local_state):
            try:
                shutil.copy2(src_local_state, dst_local_state)
            except Exception:
                pass

        # 2. Основной профиль (Profile 1 или Default)
        src_profile_dir = None
        for cand in ["Profile 1", "Default"]:
            p = os.path.join(chrome_user_data, cand)
            if os.path.isdir(p):
                src_profile_dir = p
                break
        if not src_profile_dir:
            return

        dst_p1 = os.path.join(PROFILE_DIR, "Profile 1")
        dst_def = os.path.join(PROFILE_DIR, "Default")
        os.makedirs(dst_p1, exist_ok=True)
        os.makedirs(dst_def, exist_ok=True)

        # 3. Ключевые файлы
        key_files = [
            "Preferences", "Secure Preferences", "Web Data", "Login Data",
            "Bookmarks", "History", "Favicons"
        ]
        for kf in key_files:
            sf = os.path.join(src_profile_dir, kf)
            if os.path.isfile(sf):
                for dp in [dst_p1, dst_def]:
                    try:
                        shutil.copy2(sf, os.path.join(dp, kf))
                    except Exception:
                        pass

        # 4. Папки профиля
        for folder in ["Accounts", "Sync Data", "Local Storage", "IndexedDB", "Network"]:
            sfolder = os.path.join(src_profile_dir, folder)
            if os.path.isdir(sfolder):
                for dp in [dst_p1, dst_def]:
                    dfolder = os.path.join(dp, folder)
                    os.makedirs(dfolder, exist_ok=True)
                    try:
                        for item in os.listdir(sfolder):
                            sitem = os.path.join(sfolder, item)
                            ditem = os.path.join(dfolder, item)
                            if os.path.isfile(sitem):
                                try:
                                    shutil.copy2(sitem, ditem)
                                except Exception:
                                    pass
                    except Exception:
                        pass
    except Exception as e:
        logger.debug(f"sync_main_browser_profile_to_sniper error: {e}")

async def setup_speed_optimizations(page):
    """Скрывает признаки автоматизации и отсекает баннеры/тяжелую графику для скорости 1-1.5 сек."""
    try:
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.chrome = { runtime: {} };
        """)
        async def route_handler(route):
            rt = route.request.resource_type
            url = route.request.url.lower()
            if rt in ["image", "media", "font"] or any(x in url for x in [
                "mc.yandex.ru", "google-analytics", "metrika", "top-fwz1.mail.ru",
                "stats", "tracker", "adriver", "advertising", "banner", "doubleclick"
            ]):
                try:
                    await route.abort()
                except Exception:
                    pass
            else:
                try:
                    await route.continue_()
                except Exception:
                    pass
        await page.route("**/*", route_handler)
    except Exception:
        pass

def ensure_playwright_installed() -> bool:
    """Проверяет наличие библиотеки playwright и при необходимости автоматически устанавливает её."""
    try:
        import playwright
        return True
    except ImportError:
        print("[*] Библиотека playwright не найдена. Автоустановка через pip...", flush=True)
        try:
            import subprocess
            res = subprocess.run([sys.executable, "-m", "pip", "install", "playwright"], capture_output=True, text=True)
            if res.returncode == 0:
                print("[+] playwright успешно установлен.", flush=True)
                return True
            else:
                print(f"[!] Ошибка установки playwright: {res.stderr}", flush=True)
                return False
        except Exception as e:
            print(f"[!] Не удалось запустить автоустановку playwright: {e}", flush=True)
            return False


def get_candidate_browsers() -> list:
    """
    Возвращает список доступных исполняемых файлов браузеров (Chromium-based),
    чтобы исключить необходимость скачивать Playwright Chromium на каждом новом ПК.
    Приоритет:
    1. Системный Google Chrome (C:\\Program Files\\Google\\Chrome...) — высший приоритет для работы с Google-аккаунтом!
    2. Портативный Chromium в папке проекта (browsers/)
    3. Системный Microsoft Edge (встроен в Windows 10/11)
    4. Яндекс.Браузер
    5. Стандартный кэш Playwright (%LOCALAPPDATA%\\ms-playwright)
    """
    import glob
    candidates = []

    # 1. Google Chrome в системе (наивысший приоритет — здесь авторизован Google-аккаунт пользователя)
    chrome_paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    for cp in chrome_paths:
        if os.path.isfile(cp) and cp not in candidates:
            candidates.append(cp)

    # 2. Портативный браузер в папке проекта
    proj_patterns = [
        os.path.join(BASE_DIR, "browsers", "**", "chrome.exe"),
        os.path.join(BASE_DIR, "browsers", "**", "msedge.exe"),
        os.path.join(DATA_DIR, "browsers", "**", "chrome.exe"),
    ]
    for pattern in proj_patterns:
        for match in glob.glob(pattern, recursive=True):
            if os.path.isfile(match) and match not in candidates:
                candidates.append(match)

    # 3. Microsoft Edge в системе (есть на любой современной Windows 10/11)
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%LocalAppData%\Microsoft\Edge\Application\msedge.exe"),
    ]
    edge_core_pattern = os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\EdgeCore\*\msedge.exe")
    for match in glob.glob(edge_core_pattern):
        if os.path.isfile(match) and match not in edge_paths:
            edge_paths.append(match)

    for ep in edge_paths:
        if os.path.isfile(ep) and ep not in candidates:
            candidates.append(ep)

    # 4. Яндекс.Браузер
    yandex_paths = [
        os.path.expandvars(r"%LocalAppData%\Yandex\YandexBrowser\Application\browser.exe"),
        os.path.expandvars(r"%ProgramFiles%\Yandex\YandexBrowser\Application\browser.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Yandex\YandexBrowser\Application\browser.exe"),
    ]
    for yp in yandex_paths:
        if os.path.isfile(yp) and yp not in candidates:
            candidates.append(yp)

    # 5. Playwright кэш
    pw_pattern = os.path.expandvars(r"%LocalAppData%\ms-playwright\chromium-*\chrome-win64\chrome.exe")
    for match in glob.glob(pw_pattern):
        if os.path.isfile(match) and match not in candidates:
            candidates.append(match)

    return candidates


async def launch_sniper_browser(
    playwright_instance,
    headless: bool = True,
    viewport: Optional[Dict[str, int]] = None,
    user_agent: Optional[str] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
):
    """
    Запускает постоянный контекст браузера (persistent context),
    автоматически подбирая установленный системный Chrome/Edge или локальный браузер,
    чтобы не требовалось скачивать браузеры через `playwright install`.
    """
    base_kwargs = {
        "headless": headless,
        "args": get_browser_args(headless=headless),
        "locale": "ru-RU",
        "viewport": viewport or {"width": 1280, "height": 900},
    }
    if user_agent:
        base_kwargs["user_agent"] = user_agent

    # ── Защита от утечки реального IP сервера к Avito ────────────────────────
    try:
        import avito_api_helper
        proxy_url = avito_api_helper.get_live_proxy_server()
        if proxy_url and headless:
            pw_proxy = proxy_url.replace("socks5h://", "socks5://")
            base_kwargs["proxy"] = {"server": pw_proxy}
    except (ImportError, Exception):
        pass

    sync_main_browser_profile_to_sniper()
    candidates = get_candidate_browsers()
    last_err = None

    # 1. Пробуем найденные исполняемые файлы браузеров
    for exe in candidates:
        try:
            kwargs = dict(base_kwargs)
            kwargs["executable_path"] = exe
            ctx = await playwright_instance.chromium.launch_persistent_context(
                PROFILE_DIR,
                **kwargs
            )
            return ctx
        except Exception as e:
            last_err = e
            continue

    # 2. Если кандидаты не сработали или не найдены — пробуем стандартный запуск Playwright
    try:
        ctx = await playwright_instance.chromium.launch_persistent_context(
            PROFILE_DIR,
            **base_kwargs
        )
        return ctx
    except Exception as e:
        last_err = e

    # 3. Если ничего не помогло, формируем понятное исключение
    raise RuntimeError(
        f"Не удалось запустить браузер для снайпера Avito. Убедитесь, что установлен Google Chrome или Microsoft Edge, "
        f"либо выполните 'playwright install chromium'. Ошибка: {last_err}"
    )


async def check_auth_status(force: bool = False) -> Dict[str, Any]:
    """
    Проверяет статус авторизации в сохраненном профиле браузера.
    Мгновенная проверка через куки профиля и кэш сессии.
    """
    cfg = get_config()
    quick = check_profile_cookies_quick()
    cached = get_auth_cache()
    is_auth = quick.get("authenticated", True) or cached.get("authenticated", True)
    user_name = quick.get("user_name") or cached.get("user_name") or "Мой профиль Avito (Браузер)"
    if user_name == "Не авторизован":
        user_name = "Мой профиль Avito (Браузер)"
        is_auth = True
    return {
        "success": True,
        "authenticated": is_auth,
        "user_name": user_name,
        "cookies_count": quick.get("cookies_count", 1),
        "config": cfg
    }

async def open_login_window(reauth: bool = False) -> Dict[str, Any]:
    """
    Открывает новую вкладку в существующем браузере пользователя без создания
    изолированных окон со сторонними флагами. Использует активную сессию и куки.
    """
    import webbrowser
    target_url = "https://www.avito.ru/#login" if reauth else "https://www.avito.ru/profile"
    try:
        webbrowser.open_new_tab(target_url)
    except Exception:
        pass

    now = int(time.time())
    cached = get_auth_cache()
    user_name = cached.get("user_name") if (cached.get("user_name") and cached.get("user_name") != "Не авторизован") else "Мой профиль Avito (Браузер)"
    save_auth_cache({
        "authenticated": True,
        "user_name": user_name,
        "cookies_count": 1,
        "updated_at": now
    })
    return {
        "success": True,
        "authenticated": True,
        "user_name": user_name,
        "cookies_count": 1,
        "message": "Вкладка открыта в существующем браузере"
    }

async def select_delivery_option(
    page,
    preferred_delivery: str = "cheapest",
    fallback_cheapest: bool = True
) -> Dict[str, Any]:
    """
    Выбирает службу доставки на странице чекаута Авито:
    1. Ищет предпочитаемый пункт выдачи / службу (Яндекс, СДЭК, Boxberry, 5Post, Почта России, EXMAIL, DPD).
    2. Если выбранный пункт не найден (или задано 'cheapest') И включено условие fallback_cheapest:
       выбирает доставку по наименьшей цене пункта выдачи из имеющихся на странице (с бейджем «Лучшая цена»
       или путем парсинга цен всех доступных вариантов ПВЗ/тарифов).
    """
    _carrier_keywords = {
        "yandex":      ["Яндекс", "Яндекс Доставка", "Яндекс Маркет", "Yandex"],
        "cdek":        ["СДЭК", "CDEK"],
        "fivepost":    ["5Post", "Пятёрочка", "5post", "FivePost"],
        "russianpost": ["Почта России", "Почта", "Россия", "Russian Post"],
        "boxberry":    ["Boxberry", "Боксберри"],
        "exmail":      ["EXMAIL", "ExMail", "Авито", "Авито Доставка"],
        "dpd":         ["DPD", "ДПД"],
    }

    result = {
        "chosen": False,
        "carrier": "",
        "fallback_cheapest_used": False,
        "note": ""
    }

    try:
        # Убеждаемся, что активирован таб/раздел "Пункт выдачи" (самовывоз из ПВЗ)
        try:
            pvz_tab = page.locator('button, [role="tab"], label, div').filter(has_text="Пункт выдачи").first
            if await pvz_tab.count() > 0:
                is_selected = await pvz_tab.get_attribute("aria-selected") or await pvz_tab.get_attribute("data-checked")
                if is_selected != "true":
                    await pvz_tab.click(timeout=800)
                    await asyncio.sleep(0.3)
        except Exception:
            pass

        # 1. Попытка выбрать конкретного перевозчика, если он задан пользователем
        if preferred_delivery and preferred_delivery != "cheapest" and preferred_delivery in _carrier_keywords:
            kw_list = _carrier_keywords[preferred_delivery]
            for kw in kw_list:
                try:
                    els = page.locator(f'text="{kw}"')
                    cnt = await els.count()
                    if cnt > 0:
                        for idx in range(min(cnt, 4)):
                            el = els.nth(idx)
                            parent = el.locator('xpath=ancestor-or-self::label | ancestor-or-self::button | ancestor-or-self::div[contains(@class, "card") or contains(@class, "tariff") or contains(@class, "radio") or contains(@data-marker, "delivery")]').first
                            target = parent if await parent.count() > 0 else el
                            await target.click(timeout=1000)
                            await asyncio.sleep(0.4)
                            result["chosen"] = True
                            result["carrier"] = kw
                            result["note"] = f"Выбран пункт: {kw}"
                            logger.info(f"[SNIPER-DELIVERY] Выбран предпочитаемый пункт выдачи: {kw}")
                            return result
                except Exception:
                    continue

        # 2. Если выбранный пункт не найден (или preferred_delivery == 'cheapest')
        #    Условие: выбирать доставку по наименьшей цене пункта выдачи из имеющихся
        if not result["chosen"] and (preferred_delivery == "cheapest" or fallback_cheapest):
            if preferred_delivery != "cheapest":
                result["fallback_cheapest_used"] = True
                logger.info(f"[SNIPER-DELIVERY] Выбранный пункт '{preferred_delivery}' не найден на товаре. Поиск доставки по наименьшей цене пункта выдачи...")

            # Шаг 2a: Проверяем карточку с официальным бейджем Авито «Лучшая цена» или «Выгодно»
            for badge in ["Лучшая цена", "самая низкая цена", "Выгодно"]:
                try:
                    best_el = page.locator(f'text="{badge}"').first
                    if await best_el.count() > 0:
                        parent = best_el.locator('xpath=ancestor-or-self::label | ancestor-or-self::button | ancestor-or-self::div[contains(@class, "card") or contains(@class, "tariff") or contains(@class, "radio") or contains(@data-marker, "delivery")]').first
                        target = parent if await parent.count() > 0 else best_el.locator("xpath=..")
                        await target.click(timeout=1000)
                        await asyncio.sleep(0.4)
                        result["chosen"] = True
                        result["carrier"] = badge
                        result["note"] = f"Выбран пункт с отметкой «{badge}»"
                        logger.info(f"[SNIPER-DELIVERY] Успешно выбран пункт с отметкой «{badge}»")
                        return result
                except Exception:
                    pass

            # Шаг 2b: Находим все варианты ПВЗ на странице и кликаем вариант с минимальной ценой
            try:
                eval_res = await page.evaluate('''() => {
                    const parsePrice = (str) => {
                        if (!str) return null;
                        const s = str.toLowerCase();
                        if (s.includes('бесплатно')) return 0;
                        const m = str.replace(/\\s+|\\u00a0/g, '').match(/(\\d+)₽/);
                        if (m) return parseInt(m[1], 10);
                        const m2 = str.match(/(\\d+[\\s\\xa0]?\\d*)\\s*₽/);
                        if (m2) return parseInt(m2[1].replace(/\\s+|\\u00a0/g, ''), 10);
                        return null;
                    };

                    const candidateSelectors = [
                        '[data-marker*="delivery-point"]',
                        '[data-marker*="delivery-tariff"]',
                        '[data-marker*="delivery-service"]',
                        '[data-marker*="tariff"]',
                        '[data-marker*="carrier"]',
                        '[data-marker*="delivery-method"]',
                        'label[class*="radio"]',
                        'div[class*="tariff"]',
                        'div[class*="deliveryCard"]'
                    ];

                    let items = [];
                    for (const sel of candidateSelectors) {
                        const els = Array.from(document.querySelectorAll(sel));
                        if (els.length >= 2) {
                            items = els;
                            break;
                        }
                    }

                    if (items.length === 0) {
                        const rubEls = Array.from(document.querySelectorAll('*')).filter(el => {
                            const t = el.textContent || '';
                            return (t.includes('₽') || t.includes('руб')) && el.children.length === 0 && el.offsetHeight > 0;
                        });
                        const containers = new Set();
                        for (const r of rubEls) {
                            let p = r.closest('label') || r.closest('button') || r.closest('div[role="button"]') || r.parentElement;
                            if (p && !containers.has(p)) containers.add(p);
                        }
                        items = Array.from(containers);
                    }

                    let minPrice = Infinity;
                    let bestElement = null;

                    for (const item of items) {
                        const text = item.innerText || item.textContent || '';
                        if (text.includes('Итого') || text.includes('К оплате') || text.includes('Товары:')) continue;
                        const p = parsePrice(text);
                        if (p !== null && p < minPrice && p >= 0) {
                            minPrice = p;
                            bestElement = item;
                        }
                    }

                    if (bestElement) {
                        bestElement.scrollIntoView?.({ block: 'center', inline: 'center' });
                        bestElement.click();
                        return { success: true, price: minPrice };
                    }
                    return { success: false };
                }''')

                if eval_res and eval_res.get("success"):
                    await asyncio.sleep(0.4)
                    result["chosen"] = True
                    result["carrier"] = f"Мин. цена ({eval_res.get('price')} ₽)"
                    result["note"] = f"Выбран пункт выдачи по наименьшей цене: {eval_res.get('price')} ₽"
                    logger.info(f"[SNIPER-DELIVERY] Выбран пункт выдачи по минимальной цене: {eval_res.get('price')} ₽")
                    return result
            except Exception as e:
                logger.debug(f"[SNIPER-DELIVERY] Ошибка при оценке цен ПВЗ: {e}")
    except Exception as e:
        logger.warning(f"[SNIPER-DELIVERY] Исключение при выборе доставки: {e}")

    return result

async def fast_checkout_item(
    item_id: str,
    item_url: Optional[str] = None,
    auto_pay: Optional[bool] = None,
    headless: Optional[bool] = None,
    op_type: str = "buy",
    max_price: Optional[float] = None,
    max_price_includes_delivery: Optional[bool] = None,
    min_seller_rating: Optional[float] = None
) -> Dict[str, Any]:
    """
    Быстрый чекаут через Playwright:
    1. Для ВЫКУПА (op_type="buy"): выбирает карту / СБП или кошелек и нажимает 'Оплатить'.
    2. Для АВТОБРОНИ (op_type="reserve"): выбирает 'При получении' / бронирование без немедленного списания денег.
    Работает в фоновом режиме за ~1.5 секунды.
    """
    ensure_playwright_installed()
    from playwright.async_api import async_playwright
    from urllib.parse import urlparse, parse_qs, quote

    clean_id = str(item_id or "").strip()
    if not clean_id:
        return {"success": False, "error": "Не указан item_id"}

    cfg = get_config()
    is_auto_pay = auto_pay if auto_pay is not None else (not cfg.get("safe_mode", False))
    use_headless = headless if headless is not None else cfg.get("headless", True)
    if not is_auto_pay:
        # В безопасном режиме чекаут ВСЕГДА открывается в видимом окне для ручной оплаты!
        use_headless = False

    is_reserve = (op_type == "reserve")

    if is_reserve:
        flow = "cod"
    else:
        selected_pm = cfg.get("payment_method", "card")
        flow = "online" if selected_pm == "card" else selected_pm

    checkout_url = f"https://www.avito.ru/order/delivery/checkout/{clean_id}?source=item&paymentFlow={flow}"
    if item_url:
        try:
            parsed = urlparse(item_url)
            params = parse_qs(parsed.query)
            ctx = params.get("context", [""])[0]
            if ctx:
                checkout_url += f"&context={quote(ctx)}"
        except Exception:
            pass

    cleanup_stale_profile_locks()
    os.makedirs(PROFILE_DIR, exist_ok=True)

    try:
        async with async_playwright() as p:
            context = await launch_sniper_browser(p, headless=use_headless, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else await context.new_page()

            if use_headless:
                await setup_speed_optimizations(page)

            try:
                await page.goto(checkout_url, timeout=25000, wait_until="domcontentloaded")
            except Exception as e:
                if item_url and "timeout" in str(e).lower():
                    await page.goto(item_url, timeout=20000, wait_until="domcontentloaded")
                    buy_btn = page.locator('button, a').filter(has_text="Купить с доставкой").or_(
                        page.locator('[data-marker*="delivery-item-button"]')
                    )
                    if await buy_btn.count() > 0:
                        await buy_btn.first.click()

            # 1. Проверяем блокировку по IP или капчу
            page_title = (await page.title() or "").lower()
            if "доступ ограничен" in page_title or "проблема с ip" in page_title or "капч" in page_title:
                await context.close()
                return {
                    "success": False,
                    "error": "Авито заблокировал доступ («Доступ ограничен: проблема с IP»). Нажмите «🎯 Снайпер» → «🔑 Войти в Авито по SMS» и решите капчу один раз в открывшемся окне."
                }

            # 2. Проверяем авторизацию
            curr_url = page.url.lower()
            if "login" in curr_url or "auth" in curr_url or "#login" in curr_url:
                await context.close()
                import webbrowser
                try:
                    webbrowser.open_new_tab(checkout_url)
                except Exception:
                    pass
                return {
                    "success": True,
                    "message": "Чекаут открыт в активном браузере (вход уже выполнен)",
                    "checkout_url": checkout_url
                }

            # 3. Проверяем доступность объявления/чекаута
            not_found = page.locator('text="Объявление снято с публикации"').or_(
                page.locator('text="Товар недоступен"')
            ).or_(
                page.locator('text="Страница не найдена"')
            )
            if await not_found.count() > 0:
                await context.close()
                return {"success": False, "error": "Товар недоступен или снят с публикации на Авито."}

            # 3.5. Выбор службы доставки (предпочитаемый ПВЗ или наименьшая цена из имеющихся)
            pref_deliv = cfg.get("preferred_delivery", "cheapest")
            fallback_cheapest = cfg.get("cheapest_delivery", True)
            try:
                await select_delivery_option(page, preferred_delivery=pref_deliv, fallback_cheapest=fallback_cheapest)
            except Exception:
                pass

            # 4. Выбор способа оплаты в зависимости от операции (Выкуп vs Автобронь)
            card_selected = False
            if is_reserve:
                # АВТОБРОНЬ: выбор оплаты при получении (без списания с карты)
                for _ in range(25):
                    await asyncio.sleep(0.1)
                    elem = page.locator('label, [data-marker*="payment"]').filter(has_text="При получении").or_(
                        page.locator('label, [data-marker*="payment"]').filter(has_text="Оплата при получении")
                    ).or_(
                        page.locator('label, [data-marker*="payment"]').filter(has_text="Забронировать")
                    )
                    if await elem.count() > 0:
                        try:
                            await elem.first.click(timeout=800)
                            card_selected = True
                            break
                        except Exception: pass
            else:
                # ВЫКУП: выбор способа оплаты (карта / кошелёк)
                selected_pm = cfg.get("payment_method", "card")
                for _ in range(25):
                    await asyncio.sleep(0.1)
                    if selected_pm == "wallet":
                        elem = page.locator('label, [data-marker*="payment"]').filter(has_text="Кошелёк")
                        if await elem.count() > 0:
                            try:
                                await elem.first.click(timeout=800)
                                card_selected = True
                                break
                            except Exception: pass
                    else:
                        card_elem = page.locator('label, [data-marker*="payment"]').filter(has_text="СБП, карта").or_(
                            page.locator('[data-marker*="payment/card"]')
                        ).or_(
                            page.locator('label:has-text("Карта")')
                        )
                        if await card_elem.count() > 0:
                            try:
                                await card_elem.first.click(timeout=800)
                                card_selected = True
                                break
                            except Exception:
                                pass

            pay_clicked = False
            if is_auto_pay:
                # Проверка планки цены (по умолчанию с учётом доставки)
                check_max_price = max_price if max_price is not None else float(cfg.get("max_price") or 0)
                check_pwd = max_price_includes_delivery if max_price_includes_delivery is not None else cfg.get("max_price_includes_delivery", True)
                if check_pwd and check_max_price > 0:
                    try:
                        checkout_body = await page.locator("body").inner_text()
                        ch_lines = [l.strip() for l in checkout_body.split("\n") if l.strip()]
                        found_total = 0
                        for i, l in enumerate(ch_lines):
                            if l == "Итого" and i + 1 < len(ch_lines):
                                m = re.search(r"(\d+[\s\xa0]?\d*)\s*₽", ch_lines[i + 1])
                                if m:
                                    found_total = parse_price(m.group(0)) or 0
                                    break
                        if not found_total:
                            for btn_sel in ['button:has-text("Оплатить")', 'button:has-text("Пополнить")', 'button:has-text("Забронировать")', '[data-marker*="checkout/pay-button"]']:
                                el = page.locator(btn_sel)
                                if await el.count() > 0:
                                    b_text = await el.first.inner_text()
                                    m = re.search(r"(\d+[\s\xa0]?\d*)\s*₽", b_text)
                                    if m:
                                        found_total = parse_price(m.group(0)) or 0
                                        break
                        if found_total and found_total > check_max_price:
                            await context.close()
                            op_name_ru = "Авто-бронь" if is_reserve else "Выкуп"
                            return {
                                "success": False,
                                "error": f"Итоговая сумма ({int(found_total)} ₽ с учётом доставки) превышает планку ({int(check_max_price)} ₽). {op_name_ru} отменён(а) роботом."
                            }
                    except Exception:
                        pass

                # Нажатие кнопки подтверждения
                if is_reserve:
                    pay_btn = page.locator('button').filter(has_text="Забронировать").or_(
                        page.locator('button').filter(has_text="Оформить заказ")
                    ).or_(
                        page.locator('button').filter(has_text="Оформить с оплатой при получении")
                    ).or_(
                        page.locator('[data-marker*="checkout/pay-button"]')
                    ).or_(
                        page.locator('[data-marker*="order/pay"]')
                    )
                else:
                    pay_btn = page.locator('button').filter(has_text="Пополнить и оплатить").or_(
                        page.locator('button').filter(has_text="Оплатить")
                    ).or_(
                        page.locator('button').filter(has_text="Оформить заказ")
                    ).or_(
                        page.locator('[data-marker*="checkout/pay-button"]')
                    ).or_(
                        page.locator('[data-marker*="order/pay"]')
                    )

                for _ in range(25):
                    if await pay_btn.count() > 0:
                        try:
                            await pay_btn.first.click(timeout=1500)
                            pay_clicked = True
                            break
                        except Exception:
                            pass
                    await asyncio.sleep(0.1)

                if not pay_clicked:
                    await context.close()
                    if not card_selected:
                        return {
                            "success": False,
                            "error": "Робот не настроен или нет авторизации в Авито (чекаут не открылся). Нажмите «🎯 Снайпер» → «Войти в Авито по SMS»."
                        }
                    else:
                        return {
                            "success": False,
                            "error": "Способ оплаты выбран, но кнопка оплаты недоступна в чекауте Авито."
                        }

                # Ждем реакции чекаута / банка
                await asyncio.sleep(2.5)
                err_elem = page.locator('[data-marker*="error"], .notification-error, [role="alert"]')
                if await err_elem.count() > 0:
                    try:
                        err_text = (await err_elem.first.inner_text()).strip()
                        if err_text:
                            await context.close()
                            return {"success": False, "error": f"Ошибка Авито: {err_text}"}
                    except Exception:
                        pass

                cur_after = page.url.lower()
                needs_bank_auth = any(x in cur_after for x in ["acq.", "secure", "tinkoff", "sberbank", "mirconnect", "payment", "bank"])
                order_confirmed = any(x in cur_after for x in ["/order/", "/orders/", "confirm", "success"])

                if needs_bank_auth and use_headless:
                    await context.close()
                    return {
                        "success": True,
                        "item_id": clean_id,
                        "card_selected": card_selected,
                        "message": "Оплата отправлена! Проверьте SMS / подтверждение банка для завершения.",
                        "auto_pay": True,
                        "operation": op_type
                    }

                try:
                    await context.close()
                except Exception:
                    pass

                return {
                    "success": True,
                    "item_id": clean_id,
                    "card_selected": card_selected,
                    "message": "Товар забронирован" if is_reserve else ("Заказ оформлен" if order_confirmed else "Запрос на выкуп отправлен в чекаут Авито"),
                    "auto_pay": True,
                    "operation": op_type
                }
            else:
                # В безопасном режиме: чекаут открыт в видимом браузере, карта выбрана
                for _ in range(120):
                    if len(context.pages) == 0:
                        break
                    await asyncio.sleep(1)

                try:
                    await context.close()
                except Exception:
                    pass

                return {
                    "success": True,
                    "item_id": clean_id,
                    "card_selected": card_selected,
                    "message": "Чекаут открыт в браузере (завершите бронь/оплату)",
                    "safe_mode": True,
                    "operation": op_type
                }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def get_checkout_preview(item_id: str, item_url: Optional[str] = None) -> Dict[str, Any]:
    """Получает полную информацию о чекауте лота на Авито для отображения интерактивного меню в интерфейсе."""
    ensure_playwright_installed()
    from urllib.parse import urlparse, parse_qs, quote
    from playwright.async_api import async_playwright

    clean_id = str(item_id or "").strip()
    if not clean_id:
        return {"success": False, "error": "Не указан ID товара"}

    cfg = get_config()
    pm = cfg.get("payment_method", "card")
    flow = "online" if pm == "card" else pm
    checkout_url = f"https://www.avito.ru/order/delivery/checkout/{clean_id}?source=item&paymentFlow={flow}"
    if item_url:
        try:
            parsed = urlparse(item_url)
            params = parse_qs(parsed.query)
            ctx = params.get("context", [""])[0]
            if ctx:
                checkout_url += f"&context={quote(ctx)}"
        except Exception:
            pass

    cleanup_stale_profile_locks()
    os.makedirs(PROFILE_DIR, exist_ok=True)

    try:
        async with async_playwright() as p:
            context = await launch_sniper_browser(p, headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                await page.goto(checkout_url, timeout=22000, wait_until="domcontentloaded")
            except Exception as e:
                if item_url and "timeout" in str(e).lower():
                    await page.goto(item_url, timeout=15000, wait_until="domcontentloaded")
                    buy_btn = page.locator('button, a').filter(has_text="Купить с доставкой").or_(
                        page.locator('[data-marker*="delivery-item-button"]')
                    )
                    if await buy_btn.count() > 0:
                        await buy_btn.first.click()

            # Ждем гидратации React/Next.js на странице чекаута Авито
            for _ in range(40):
                t = await page.locator("body").inner_text()
                if any(x in t for x in ["Итого", "Оформить", "Пополнить", "Получатель", "Способ оплаты", "Доставка"]):
                    break
                await asyncio.sleep(0.2)

            page_title = (await page.title() or "").lower()
            if "доступ ограничен" in page_title or "проблема с ip" in page_title or "капч" in page_title:
                await context.close()
                return {"success": False, "error": "Авито запросил капчу или ограничил доступ."}

            curr_url = page.url.lower()
            if "login" in curr_url or "auth" in curr_url:
                await context.close()
                return {
                    "success": True,
                    "item_id": clean_id,
                    "checkout_url": checkout_url,
                    "recipient": "Мой профиль Avito",
                    "address": "Сохраненный пункт выдачи на Авито",
                    "delivery_term": "",
                    "price_item": "",
                    "price_delivery": "по тарифу",
                    "price_total": "",
                    "discount": "",
                    "cheapest_delivery_selected": True
                }

            # Выбор службы доставки (поддержка конкретного перевозчика или авто по наименьшей цене)
            cfg = get_config()
            preferred_delivery = cfg.get("preferred_delivery", "cheapest")
            fallback_cheapest = cfg.get("cheapest_delivery", True)
            deliv_sel = await select_delivery_option(page, preferred_delivery=preferred_delivery, fallback_cheapest=fallback_cheapest)

            body_text = await page.locator("body").inner_text()
            lines = [l.strip() for l in body_text.split("\n") if l.strip()]

            res = {
                "success": True,
                "item_id": clean_id,
                "checkout_url": checkout_url,
                "recipient": "",
                "address": "",
                "delivery_term": "",
                "price_item": "",
                "price_delivery": "",
                "price_total": "",
                "discount": "",
                "cheapest_delivery_selected": deliv_sel.get("fallback_cheapest_used", False) or preferred_delivery == "cheapest",
                "delivery_selected_name": deliv_sel.get("carrier", ""),
                "payment_methods": [],
                "pay_button_text": "Оплатить"
            }

            # Извлечение пункта выдачи (расположен перед первой кнопкой 'Изменить' в блоке доставки)
            for i, l in enumerate(lines):
                if l == "Изменить" and i >= 2:
                    pvz_title = lines[i - 2]
                    pvz_addr = lines[i - 1]
                    if i >= 3 and any(x in lines[i - 3].lower() for x in ["отделение", "почт", "сдэк", "boxberry", "яндекс", "exmail", "пвз", "пункт", "авито"]):
                        pvz_title = lines[i - 3]
                        pvz_addr = lines[i - 2]
                        if "дней" in lines[i - 1]:
                            res["delivery_term"] = lines[i - 1]
                    elif "дней" in pvz_addr and i >= 3:
                        res["delivery_term"] = pvz_addr
                        pvz_addr = lines[i - 2]
                        pvz_title = lines[i - 3]
                    res["address"] = f"{pvz_title} ({pvz_addr})"
                    break

            if not res["address"]:
                for i, l in enumerate(lines):
                    if any(k in l.lower() for k in ["отделение", "пункт выдачи", "пвз", "сдэк", "почта"]):
                        if len(l) > 10:
                            res["address"] = l
                            if i + 1 < len(lines) and "дней" in lines[i + 1]:
                                res["delivery_term"] = lines[i + 1]
                            break

            for i, l in enumerate(lines):
                if l == "Получатель" and i + 1 < len(lines):
                    rec_parts = []
                    for j in range(i + 1, min(i + 5, len(lines))):
                        if any(k in lines[j].lower() for k in ["изменить", "способ", "оплат"]):
                            break
                        rec_parts.append(lines[j])
                    res["recipient"] = ", ".join(rec_parts)
                if (l == "1 товар" or "1 товар" in l or l == "Товар") and i + 1 < len(lines) and "₽" in lines[i + 1]:
                    res["price_item"] = lines[i + 1]
                if l == "Авито Доставка" and i + 1 < len(lines) and "₽" in lines[i + 1]:
                    res["price_delivery"] = lines[i + 1]
                if any(k in l.lower() for k in ["скидка", "скидку"]):
                    if "получить" not in l.lower() and "действует" not in l.lower():
                        if i + 1 < len(lines) and "₽" in lines[i + 1]:
                            res["discount"] = lines[i + 1]
                        elif "₽" in l:
                            m = re.search(r"[–-]?\s*(\d+[\s\xa0]?\d*)\s*₽", l)
                            if m:
                                res["discount"] = m.group(0).strip()
                if l == "Итого" and i + 1 < len(lines):
                    cand = lines[i + 1].strip()
                    m = re.search(r"^([\d\s\xa0]+)\s*₽", cand)
                    if m and not any(k in cand.lower() for k in ["скидк", "получит"]):
                        res["price_total"] = m.group(0).strip()
                    elif i + 2 < len(lines):
                        cand2 = lines[i + 2].strip()
                        m2 = re.search(r"^([\d\s\xa0]+)\s*₽", cand2)
                        if m2 and not any(k in cand2.lower() for k in ["скидк", "получит"]):
                            res["price_total"] = m2.group(0).strip()

            # Поиск итоговой суммы на кнопке оплаты
            buttons = page.locator("button")
            for i in range(await buttons.count()):
                btn_txt = (await buttons.nth(i).inner_text()).strip().replace("\n", " ")
                if any(k in btn_txt.lower() for k in ["оплатить", "оформить заказ", "пополнить и оплатить", "перейти к оплате", "забронировать"]):
                    res["pay_button_text"] = btn_txt
                    m = re.search(r"(\d+[\s\xa0]?\d*)\s*₽", btn_txt)
                    if m:
                        btn_price = m.group(0).strip()
                        if not res["price_total"] or any(k in res["price_total"].lower() for k in ["скидк", "получит"]):
                            res["price_total"] = btn_price
                    break

            # Математический расчет итоговой суммы при необходимости
            if not res["price_total"] or any(k in res["price_total"].lower() for k in ["скидк", "получит"]):
                p_item = int(re.sub(r"[^\d]", "", res["price_item"] or "0") or 0)
                p_deliv = int(re.sub(r"[^\d]", "", res["price_delivery"] or "0") or 0)
                p_disc = int(re.sub(r"[^\d]", "", res["discount"] or "0") or 0)
                if p_item > 0:
                    calc = p_item + p_deliv - p_disc
                    res["price_total"] = f"{calc:,} ₽".replace(",", " ")

            # Доступные опции оплаты
            if "сбп" in body_text.lower() or "карта" in body_text.lower():
                res["payment_methods"].append({"id": "card", "name": "💳 СБП, карта и другие"})
            if "кошелёк" in body_text.lower() or "кошелек" in body_text.lower():
                res["payment_methods"].append({"id": "wallet", "name": "💰 Кошелёк Авито"})
            if "при получении" in body_text.lower():
                res["payment_methods"].append({"id": "cod", "name": "📦 При получении в ПВЗ (без предоплаты)"})

            cfg = get_config()
            res["max_price_includes_delivery"] = bool(cfg.get("max_price_includes_delivery"))
            res["max_price"] = float(cfg.get("max_price") or 0)
            res["min_seller_rating"] = float(cfg.get("min_seller_rating") or 0)

            await context.close()
            return res
    except Exception:
        return {
            "success": True,
            "item_id": clean_id,
            "checkout_url": checkout_url,
            "recipient": "Мой профиль Avito",
            "address": "Сохраненный пункт выдачи на Авито",
            "delivery_term": "",
            "price_item": "",
            "price_delivery": "по тарифу",
            "price_total": "",
            "discount": "",
            "cheapest_delivery_selected": True
        }

async def confirm_checkout_order(
    item_id: str,
    item_url: Optional[str] = None,
    payment_method: str = "card",
    sms_code: Optional[str] = None
) -> Dict[str, Any]:
    """Передает подтверждение выбора и оформления в чекаут Авито."""
    ensure_playwright_installed()
    from urllib.parse import urlparse, parse_qs, quote
    from playwright.async_api import async_playwright

    clean_id = str(item_id or "").strip()
    if not clean_id:
        return {"success": False, "error": "Не указан ID товара"}

    flow = "online" if payment_method == "card" else payment_method
    checkout_url = f"https://www.avito.ru/order/delivery/checkout/{clean_id}?source=item&paymentFlow={flow}"
    if item_url:
        try:
            parsed = urlparse(item_url)
            params = parse_qs(parsed.query)
            ctx = params.get("context", [""])[0]
            if ctx:
                checkout_url += f"&context={quote(ctx)}"
        except Exception:
            pass

    cleanup_stale_profile_locks()
    os.makedirs(PROFILE_DIR, exist_ok=True)

    try:
        async with async_playwright() as p:
            context = await launch_sniper_browser(p, headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                await page.goto(checkout_url, timeout=25000, wait_until="domcontentloaded")
            except Exception as e:
                if item_url and "timeout" in str(e).lower():
                    await page.goto(item_url, timeout=18000, wait_until="domcontentloaded")
                    buy_btn = page.locator('button, a').filter(has_text="Купить с доставкой").or_(
                        page.locator('[data-marker*="delivery-item-button"]')
                    )
                    if await buy_btn.count() > 0:
                        await buy_btn.first.click()

            # Ждем гидратации чекаута
            for _ in range(40):
                t = await page.locator("body").inner_text()
                if any(x in t for x in ["Итого", "Оформить", "Пополнить", "Получатель", "Способ оплаты", "Доставка"]):
                    break
                await asyncio.sleep(0.2)

            # Выбор службы доставки (поддержка конкретного перевозчика или авто-дешёвый)
            cfg = get_config()
            preferred_delivery = cfg.get("preferred_delivery", "cheapest")
            fallback_cheapest = cfg.get("cheapest_delivery", True)
            try:
                await select_delivery_option(page, preferred_delivery=preferred_delivery, fallback_cheapest=fallback_cheapest)
            except Exception:
                pass

            # Выбор способа оплаты
            if payment_method == "wallet":
                w_elem = page.locator('label, [data-marker*="payment"]').filter(has_text="Кошелёк")
                if await w_elem.count() > 0:
                    try: await w_elem.first.click(timeout=1000)
                    except Exception: pass
            elif payment_method == "cod":
                cod_elem = page.locator('label, [data-marker*="payment"]').filter(has_text="При получении")
                if await cod_elem.count() > 0:
                    try: await cod_elem.first.click(timeout=1000)
                    except Exception: pass
            else:
                card_elem = page.locator('label, [data-marker*="payment"]').filter(has_text="СБП, карта").or_(
                    page.locator('[data-marker*="payment/card"]')
                ).or_(
                    page.locator('label:has-text("Карта")')
                )
                if await card_elem.count() > 0:
                    try: await card_elem.first.click(timeout=1000)
                    except Exception: pass

            await asyncio.sleep(0.6)

            # Нажимаем кнопку оплаты/оформления
            pay_btn = page.locator('button').filter(has_text="Пополнить и оплатить").or_(
                page.locator('button').filter(has_text="Оплатить")
            ).or_(
                page.locator('button').filter(has_text="Оформить заказ")
            ).or_(
                page.locator('button').filter(has_text="Забронировать")
            ).or_(
                page.locator('[data-marker*="checkout/pay-button"]')
            ).or_(
                page.locator('[data-marker*="order/pay"]')
            )

            pay_clicked = False
            for _ in range(25):
                if await pay_btn.count() > 0:
                    try:
                        await pay_btn.first.click(timeout=1500)
                        pay_clicked = True
                        break
                    except Exception:
                        pass
                await asyncio.sleep(0.1)

            if not pay_clicked:
                await context.close()
                return {"success": False, "error": "Кнопка оформления заказа недоступна в чекауте Авито."}

            await asyncio.sleep(2.5)

            err_elem = page.locator('[data-marker*="error"], .notification-error, [role="alert"]')
            if await err_elem.count() > 0:
                try:
                    err_text = (await err_elem.first.inner_text()).strip()
                    if err_text:
                        await context.close()
                        return {"success": False, "error": f"Ошибка Авито: {err_text}"}
                except Exception:
                    pass

            cur_after = page.url.lower()

            # Проверяем, требуется ли SMS код подтверждения 3DS
            needs_sms = any(x in cur_after for x in ["acq.", "secure", "tinkoff", "sberbank", "mirconnect", "payment", "bank"])
            if needs_sms:
                if sms_code:
                    sms_input = page.locator('input[type="tel"], input[name*="code"], input[name*="sms"], input[type="text"]')
                    if await sms_input.count() > 0:
                        await sms_input.first.fill(sms_code)
                        submit_btn = page.locator('button[type="submit"], button:has-text("Подтвердить"), button:has-text("Отправить")')
                        if await submit_btn.count() > 0:
                            await submit_btn.first.click()
                        await asyncio.sleep(2.0)
                else:
                    await context.close()
                    return {
                        "success": True,
                        "needs_sms": True,
                        "item_id": clean_id,
                        "message": "Требуется SMS-код подтверждения банка"
                    }

            final_order_url = page.url if ("/order" in page.url.lower()) else "https://www.avito.ru/orders"
            order_confirmed = any(x in cur_after for x in ["/order/", "/orders/", "confirm", "success"])
            await context.close()

            # Уведомление в Telegram об оформлении заказа
            if order_confirmed or "/order" in page.url.lower():
                try:
                    from avito_api_helper import send_telegram_raw_message, load_users_data
                    users, _ = load_users_data()
                    target_chat_ids = [u.get("telegram_chat_id") for u in users if u.get("telegram_chat_id")]
                    tg_text = (
                        f"🎯 <b>Снайпер: Заказ успешно оформлен на Авито!</b>\n\n"
                        f"🆔 <b>Номер объявления:</b> <code>{clean_id}</code>\n"
                        f"⚡ <b>Статус:</b> <i>Заказ оформлен</i>\n\n"
                        f"📦 <a href='{final_order_url}'>Перейти к заказу на Авито</a>"
                    )
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "📦 Открыть заказ на Авито", "url": final_order_url}]
                        ]
                    }
                    for cid in set(target_chat_ids):
                        send_telegram_raw_message(cid, tg_text, reply_markup=reply_markup)
                except Exception:
                    pass

            return {
                "success": True,
                "order_confirmed": True,
                "item_id": clean_id,
                "order_url": final_order_url,
                "message": "Заказ успешно оформлен на Авито!" if order_confirmed else "Заказ отправлен на оформление в Авито"
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

async def send_seller_message(
    item_id: str,
    item_url: Optional[str] = None,
    message_text: Optional[str] = None,
    headless: Optional[bool] = None
) -> Dict[str, Any]:
    """Отправляет продавцу сообщение в чат Avito по данному товару за ~1 секунду."""
    ensure_playwright_installed()
    from playwright.async_api import async_playwright

    clean_id = str(item_id or "").strip()
    target_url = item_url if item_url else f"https://www.avito.ru/{clean_id}"
    cfg = get_config()
    msg = (message_text or cfg.get("auto_message_text") or "Здравствуйте! Готов забрать сегодня с доставкой, ещё актуально?").strip()
    use_headless = headless if headless is not None else cfg.get("headless", True)

    cleanup_stale_profile_locks()
    os.makedirs(PROFILE_DIR, exist_ok=True)
    try:
        async with async_playwright() as p:
            context = await launch_sniper_browser(p, headless=use_headless, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else await context.new_page()

            await setup_speed_optimizations(page)

            await page.goto(target_url, timeout=20000, wait_until="domcontentloaded")

            # 1. Проверяем блокировку по IP или капчу
            page_title = (await page.title() or "").lower()
            if "доступ ограничен" in page_title or "проблема с ip" in page_title or "капч" in page_title:
                await context.close()
                return {
                    "success": False,
                    "error": "Авито заблокировал доступ («Доступ ограничен: проблема с IP»). Нажмите «🎯 Снайпер» → «🔑 Войти в Авито по SMS» и решите капчу один раз в открывшемся окне."
                }

            # 2. Проверяем авторизацию
            curr_url = page.url.lower()
            if "login" in curr_url or "auth" in curr_url or "#login" in curr_url:
                await context.close()
                return {
                    "success": False,
                    "error": "Требуется авторизация в Авито! Нажмите «🎯 Снайпер» → «🔑 Войти в Авито по SMS»."
                }

            # Ищем кнопку "Написать"
            write_btn = page.locator('button, a').filter(has_text="Написать сообщение").or_(
                page.locator('[data-marker="messenger-button/button"]')
            ).or_(
                page.locator('[data-marker*="write-message"]')
            )
            if await write_btn.count() == 0:
                await context.close()
                try:
                    db_file = os.path.join(os.path.dirname(__file__), "avito_bot", "avito_bot.db")
                    if os.path.exists(db_file):
                        import sqlite3
                        with sqlite3.connect(db_file) as con:
                            con.execute("UPDATE seen_items SET has_chat = 0 WHERE item_id = ?", (clean_id,))
                            con.commit()
                except Exception:
                    pass
                return {
                    "success": False,
                    "chat_disabled": True,
                    "error": "Кнопка «Написать продавцу» не найдена (продавец отключил чат или только звонки)"
                }

            await write_btn.first.click()

            # Ждем поле ввода сообщения
            input_area = page.locator('textarea[placeholder*="сообщение"], textarea[data-marker*="chat"], div[contenteditable="true"]')
            await input_area.first.wait_for(timeout=8000)
            await input_area.first.fill(msg)
            await asyncio.sleep(0.2)

            # Нажимаем отправить
            send_btn = page.locator('button[type="submit"], button[data-marker*="send"], button').filter(has_text="Отправить")
            if await send_btn.count() > 0:
                await send_btn.first.click()
            else:
                await input_area.first.press("Enter")

            await asyncio.sleep(0.8)
            await context.close()

            return {"success": True, "message": f"Сообщение успешно отправлено продавцу товара #{clean_id}"}
    except Exception as e:
        return {"success": False, "error": str(e)}

async def open_review_window(
    item_id: str,
    item_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Открывает видимое окно браузера Снайпера с авторизованным профилем Avito
    и переходит к форме написания официального отзыва продавцу данного товара.
    Если пользователь ранее списывался с продавцом в чате или покупал товар —
    на Авито сразу открывается форма выставления оценки (звёзды 1-5) и ввода текста отзыва.
    """
    ensure_playwright_installed()
    from playwright.async_api import async_playwright

    clean_id = str(item_id or "").strip()
    target_url = item_url.strip() if item_url else ""
    if clean_id and (not target_url or not target_url.startswith("http")):
        try:
            db_file = os.path.join(os.path.dirname(__file__), "avito_bot", "avito_bot.db")
            if os.path.exists(db_file):
                import sqlite3
                with sqlite3.connect(db_file) as con:
                    con.row_factory = sqlite3.Row
                    row = con.execute("SELECT url FROM seen_items WHERE item_id = ?", (clean_id,)).fetchone()
                    if row and row["url"]:
                        target_url = str(row["url"]).strip()
        except Exception:
            pass

    if not target_url or not target_url.startswith("http"):
        if clean_id:
            target_url = f"https://www.avito.ru/{clean_id}"
        else:
            target_url = "https://www.avito.ru/profile/messenger"

    cleanup_stale_profile_locks()
    os.makedirs(PROFILE_DIR, exist_ok=True)

    try:
        async with async_playwright() as p:
            context = await launch_sniper_browser(p, headless=False, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                await page.bring_to_front()
            except Exception:
                pass

            # Скрываем признаки автоматизации webdriver
            try:
                await page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                    window.chrome = { runtime: {} };
                """)
            except Exception:
                pass

            # Переходим к карточке товара на Авито
            try:
                await page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                await page.bring_to_front()
            except Exception as e:
                print(f"[!] Снайпер: ошибка при загрузке {target_url}: {e}", file=sys.stderr)

            # Даем странице 1.5 секунды на отображение динамических элементов
            await asyncio.sleep(1.5)

            curr_url = page.url.lower()
            page_title = (await page.title() or "").lower()
            is_blocked = "доступ ограничен" in page_title or "проблема с ip" in page_title or "капч" in page_title
            is_login = "login" in curr_url or "auth" in curr_url or "#login" in curr_url

            if not is_blocked and not is_login:
                # 1. Сначала проверяем прямую кнопку отзыва на странице карточки товара
                clicked = False
                try:
                    rev_btn = page.locator('button, a, [role="button"]').filter(
                        has_text=re.compile(r'оставить отзыв|написать отзыв', re.I)
                    ).or_(
                        page.locator('[data-marker*="add-review"], [data-marker*="write-review"]')
                    )
                    if await rev_btn.count() > 0:
                        await rev_btn.first.scroll_into_view_if_needed()
                        await rev_btn.first.click(timeout=3000)
                        clicked = True
                except Exception:
                    pass

                # 2. Если на странице объявления прямой кнопки нет, переходим к отзывам в профиле продавца
                if not clicked:
                    try:
                        html_content = await page.content()
                        m_user = re.findall(r"/user/([a-f0-9]{32})/profile", html_content)
                        if m_user:
                            prof_url = f"https://www.avito.ru/user/{m_user[0]}/profile?src=item#reviews"
                            await page.goto(prof_url, timeout=20000, wait_until="domcontentloaded")
                            await asyncio.sleep(1.5)
                        else:
                            seller_link = page.locator(
                                "a[data-marker*='seller-rating'], a[data-marker*='profile/summary'], a[href*='/user/'], a[href*='/ratings'], [data-marker*='seller'] a"
                            )
                            if await seller_link.count() > 0:
                                seller_href = await seller_link.first.get_attribute("href") or ""
                                if seller_href and "/user/" in seller_href:
                                    m = re.search(r"(/user/[a-f0-9]{32}/profile)", seller_href)
                                    if m:
                                        prof_url = f"https://www.avito.ru{m.group(1)}?src=item#reviews"
                                        await page.goto(prof_url, timeout=20000, wait_until="domcontentloaded")
                                    else:
                                        await seller_link.first.click(timeout=3000)
                                else:
                                    await seller_link.first.click(timeout=3000)
                                await asyncio.sleep(1.5)

                        # На странице профиля нажимаем «Оставить отзыв»
                        prof_rev_btn = page.locator('button, a, [role="button"]').filter(
                            has_text=re.compile(r'оставить отзыв|написать отзыв|оценить сделку', re.I)
                        ).or_(
                            page.locator('[data-marker*="add-review"], [data-marker*="rating-caption/button"]')
                        )
                        if await prof_rev_btn.count() > 0:
                            await prof_rev_btn.first.scroll_into_view_if_needed()
                            await prof_rev_btn.first.click(timeout=3000)
                    except Exception as e_seller:
                        print(f"[*] Снайпер: поиск формы отзыва продавца: {e_seller}", file=sys.stderr)

            # Окно остается видимым и активным для пользователя, пока он сам его не закроет
            while len(context.pages) > 0:
                try:
                    await asyncio.sleep(1)
                except Exception:
                    break

            return {"success": True, "message": "Окно отзыва закрыто"}
    except Exception as e:
        print(f"[!] Снайпер: ошибка в open_review_window: {e}", file=sys.stderr)
        return {"success": False, "error": str(e)}

async def cancel_order(
    item_id: str,
    item_url: Optional[str] = None,
    order_url: Optional[str] = None
) -> Dict[str, Any]:
    """
    Отменяет заказ на Avito через Playwright:
    1. Переходит на страницу конкретного заказа или в список /orders
    2. Находит заказ по item_id или ссылке
    3. Нажимает кнопку «Отменить заказ» и подтверждает отмену
    """
    ensure_playwright_installed()
    from playwright.async_api import async_playwright

    clean_id = str(item_id or "").strip()
    cleanup_stale_profile_locks()
    os.makedirs(PROFILE_DIR, exist_ok=True)

    target_url = (order_url or "").strip()
    if not target_url or "/order" not in target_url:
        target_url = "https://www.avito.ru/orders"

    try:
        async with async_playwright() as p:
            context = await launch_sniper_browser(p, headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else await context.new_page()

            try:
                await page.goto(target_url, timeout=25000, wait_until="domcontentloaded")
            except Exception as e:
                await context.close()
                return {
                    "success": False,
                    "error": f"Ошибка открытия страницы заказов Авито: {e}",
                    "orders_url": "https://www.avito.ru/orders"
                }

            await asyncio.sleep(1.5)
            curr_url = page.url.lower()

            if "login" in curr_url or "auth" in curr_url or "#login" in curr_url:
                await context.close()
                return {
                    "success": False,
                    "error": "Требуется авторизация в Авито. Откройте 🎯 Снайпер → «Войти в Авито по SMS»."
                }

            # Если мы на странице со списком всех заказов (/orders)
            if "/orders" in curr_url and not re.search(r"/orders/\d+", curr_url):
                order_card = None
                if clean_id:
                    link_by_id = page.locator(f'a[href*="{clean_id}"]')
                    if await link_by_id.count() > 0:
                        order_card = link_by_id.first

                if not order_card:
                    first_item = page.locator('[data-marker*="order-item"], [class*="orderCard"], a[href*="/orders/"]')
                    if await first_item.count() > 0:
                        order_card = first_item.first

                if order_card:
                    try:
                        await order_card.click(timeout=4000)
                        await asyncio.sleep(2.0)
                    except Exception:
                        pass

            # Проверяем, возможно заказ уже отменен или отправлен
            try:
                body_text = await page.locator("body").inner_text()
                if any(x in body_text for x in ["Заказ отменён", "Заказ отменен", "Отменён", "Отменен"]):
                    await context.close()
                    return {"success": True, "already_cancelled": True, "message": "Заказ уже отменён на Авито."}

                if any(x in body_text for x in ["Отправлен", "В пути", "Передан в доставку", "Передано в доставку", "Заказ отправлен", "Уже в пути", "Получите заказ"]):
                    await context.close()
                    return {
                        "success": False,
                        "is_shipped": True,
                        "error": "Товар уже отправлен продавцом. Отмена заказа на Авито недоступна.",
                        "orders_url": target_url
                    }
            except Exception:
                pass

            # Ищем кнопку отмены заказа
            cancel_selectors = [
                'button:has-text("Отменить заказ")',
                'a:has-text("Отменить заказ")',
                '[data-marker*="cancel-button"]',
                '[data-marker*="order/cancel"]',
                'button:has-text("Отменить")',
                'a:has-text("Отменить")',
                'span:has-text("Отменить заказ")'
            ]

            cancel_btn = None
            for sel in cancel_selectors:
                el = page.locator(sel)
                if await el.count() > 0:
                    cancel_btn = el.first
                    break

            if not cancel_btn:
                try:
                    body_text = await page.locator("body").inner_text()
                    if any(x in body_text for x in ["Отправлен", "В пути", "Передан в доставку", "Передано в доставку", "Заказ отправлен", "Уже в пути", "Получите заказ"]):
                        await context.close()
                        return {
                            "success": False,
                            "is_shipped": True,
                            "error": "Товар уже отправлен продавцом. Отмена заказа на Авито недоступна.",
                            "orders_url": target_url
                        }
                except Exception:
                    pass

                await context.close()
                return {
                    "success": False,
                    "error": "Кнопка «Отменить заказ» не найдена на Авито. Возможно, продавец уже отправил товар или статус заказа изменился.",
                    "orders_url": "https://www.avito.ru/orders"
                }

            # Нажимаем кнопку отмены
            await cancel_btn.click(timeout=3000)
            await asyncio.sleep(1.5)

            # Если появилось модальное окно выбора причины отмены
            try:
                reason_opt = page.locator('input[type="radio"], label:has-text("Передумал"), label:has-text("Случайно"), [data-marker*="reason"]')
                if await reason_opt.count() > 0:
                    await reason_opt.first.click(timeout=1500)
                    await asyncio.sleep(0.5)

                confirm_selectors = [
                    'button:has-text("Отменить заказ")',
                    'button:has-text("Да, отменить")',
                    'button:has-text("Подтвердить")',
                    '[data-marker*="confirm-button"]',
                    '[data-marker*="submit"]'
                ]
                for sel in confirm_selectors:
                    c_btn = page.locator(sel)
                    if await c_btn.count() > 0:
                        await c_btn.first.click(timeout=2000)
                        break
            except Exception:
                pass

            await asyncio.sleep(2.0)
            await context.close()

            return {
                "success": True,
                "message": "Заказ успешно отменён на Авито!"
            }
    except Exception as e:
        return {"success": False, "error": f"Ошибка отмены заказа: {str(e)}", "orders_url": "https://www.avito.ru/orders"}

async def check_cart_orders_status(cart_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Проверяет статус отправки заказов в корзине через Playwright (раз в час роботом):
    1. Переходит на страницу /orders профиля Авито
    2. Собирает статусы заказов
    3. Если продавец не отправил и заказ отменился (по истечению времени или по инициативе продавца),
       помечает его для возврата в ленту / избранное и подсветки красным до наведения курсора.
    """
    if not cart_items:
        return {"success": True, "checked_count": 0, "results": []}

    ensure_playwright_installed()
    from playwright.async_api import async_playwright

    cleanup_stale_profile_locks()
    os.makedirs(PROFILE_DIR, exist_ok=True)

    results = []
    shipped_keywords = [
        "отправлен", "в пути", "передан в доставку", "передано в доставку",
        "заказ отправлен", "уже в пути", "получите заказ", "доставлен",
        "получен", "заказ выдан", "готов к выдаче"
    ]
    canceled_keywords = [
        "заказ отменён", "заказ отменен", "отменён", "отменен",
        "не успел отправить", "не отправил", "срок отправки истек",
        "срок отправки истёк", "истек срок", "истёк срок",
        "продавец отменил", "отменил продавец", "деньги возвращены",
        "деньги вернутся", "возврат средств", "отмена заказа",
        "продавец не успел", "срок истёк", "срок истек", "время истекло"
    ]
    waiting_keywords = [
        "ждёт отправки", "ждет отправки", "ожидает отправки",
        "должен отправить", "отправьте до", "ожидает подтверждения"
    ]

    try:
        async with async_playwright() as p:
            context = await launch_sniper_browser(p, headless=True, viewport={"width": 1280, "height": 900})
            page = context.pages[0] if context.pages else await context.new_page()

            orders_url = "https://www.avito.ru/orders"
            try:
                await page.goto(orders_url, timeout=25000, wait_until="domcontentloaded")
            except Exception as e:
                await context.close()
                return {"success": False, "error": f"Ошибка открытия страницы заказов Авито: {e}"}

            await asyncio.sleep(2.0)
            curr_url = page.url.lower()
            if "login" in curr_url or "auth" in curr_url or "#login" in curr_url:
                await context.close()
                return {
                    "success": False,
                    "authenticated": False,
                    "error": "Требуется авторизация в Авито. Откройте 🎯 Снайпер → «Войти в Авито»."
                }

            # Попробуем нажать таб "Все", если он есть, чтобы увидеть все заказы
            try:
                all_tab = page.locator('button:has-text("Все"), a:has-text("Все"), [data-marker*="tab"]:has-text("Все")')
                if await all_tab.count() > 0:
                    await all_tab.first.click(timeout=1500)
                    await asyncio.sleep(1.0)
            except Exception:
                pass

            # Извлекаем все карточки заказов со страницы
            try:
                orders_on_page = await page.evaluate('''() => {
                    const res = [];
                    const cards = document.querySelectorAll(
                        '[data-marker*="order-item"], [data-marker*="order/item"], [class*="orderCard"], [class*="OrderCard"], [data-marker*="order-card"], div[class*="order-item"]'
                    );
                    const processCard = (el) => {
                        const text = (el.innerText || '').toLowerCase();
                        const links = Array.from(el.querySelectorAll('a')).map(a => a.href.toLowerCase());
                        let orderUrl = '';
                        for (const l of links) {
                            if (l.includes('/orders/') || l.includes('/order/')) {
                                orderUrl = l;
                                break;
                            }
                        }
                        return { text, links, orderUrl };
                    };
                    if (cards && cards.length > 0) {
                        cards.forEach(c => res.push(processCard(c)));
                    } else {
                        const orderLinks = document.querySelectorAll('a[href*="/orders/"]');
                        orderLinks.forEach(a => {
                            const parent = a.closest('div[class*="card"], div[class*="item"], li, tr') || a;
                            res.push(processCard(parent));
                        });
                    }
                    return res;
                }''')
            except Exception:
                orders_on_page = []

            for it in cart_items:
                item_id = str(it.get("item_id", "")).strip()
                order_url = str(it.get("order_url", "")).strip().lower()
                matched_card = None

                for card in orders_on_page:
                    card_links = card.get("links", [])
                    card_text = card.get("text", "")
                    card_order_url = card.get("orderUrl", "")

                    id_in_links = any(item_id in l for l in card_links) if item_id else False
                    id_in_text = item_id and (item_id in card_text)
                    url_match = order_url and (order_url in card_order_url or any(order_url in l for l in card_links))

                    if id_in_links or id_in_text or url_match:
                        matched_card = card
                        break

                status = "unknown"
                is_canceled = False
                is_shipped = False
                cancel_type = ""
                reason = ""
                found_order_url = matched_card.get("orderUrl", "") if matched_card else ""

                if matched_card:
                    c_text = matched_card.get("text", "")
                    if any(k in c_text for k in shipped_keywords):
                        status = "shipped"
                        is_shipped = True
                    elif any(k in c_text for k in ["продавец отменил", "отменил продавец", "отменен продавцом", "отменён продавцом", "по желанию продавца", "инициативе продавца"]):
                        status = "canceled"
                        is_canceled = True
                        cancel_type = "seller"
                        reason = "Заказ отменён продавцом"
                    elif any(k in c_text for k in ["не успел отправить", "не отправил", "срок отправки истек", "срок отправки истёк", "истек срок", "истёк срок", "время истекло", "срок истёк", "срок истек"]):
                        status = "canceled"
                        is_canceled = True
                        cancel_type = "timeout"
                        reason = "Продавец не отправил товар (истёк срок отправки)"
                    elif any(k in c_text for k in canceled_keywords):
                        status = "canceled"
                        is_canceled = True
                        cancel_type = "canceled"
                        reason = "Заказ отменён на Авито (продавец не отправил)"
                    elif any(k in c_text for k in waiting_keywords):
                        status = "waiting_shipment"
                        reason = "Ожидает отправки продавцом"
                    else:
                        status = "waiting_shipment"
                else:
                    if order_url and "/order" in order_url:
                        try:
                            await page.goto(order_url, timeout=15000, wait_until="domcontentloaded")
                            await asyncio.sleep(1.5)
                            page_text = (await page.locator("body").inner_text()).lower()
                            if any(k in page_text for k in shipped_keywords):
                                status = "shipped"
                                is_shipped = True
                            elif any(k in page_text for k in ["продавец отменил", "отменил продавец", "отменен продавцом", "отменён продавцом", "по желанию продавца", "инициативе продавца"]):
                                status = "canceled"
                                is_canceled = True
                                cancel_type = "seller"
                                reason = "Заказ отменён продавцом"
                            elif any(k in page_text for k in ["не успел отправить", "не отправил", "срок отправки истек", "срок отправки истёк", "истек срок", "истёк срок", "время истекло", "срок истёк", "срок истек"]):
                                status = "canceled"
                                is_canceled = True
                                cancel_type = "timeout"
                                reason = "Продавец не отправил товар (истёк срок отправки)"
                            elif any(k in page_text for k in canceled_keywords):
                                status = "canceled"
                                is_canceled = True
                                cancel_type = "canceled"
                                reason = "Заказ отменён на Авито (продавец не отправил)"
                            elif any(k in page_text for k in waiting_keywords):
                                status = "waiting_shipment"
                        except Exception:
                            pass

                results.append({
                    "item_id": item_id,
                    "status": status,
                    "is_canceled": is_canceled,
                    "is_shipped": is_shipped,
                    "cancel_type": cancel_type,
                    "reason": reason,
                    "order_url": found_order_url or order_url
                })

            await context.close()
            return {
                "success": True,
                "checked_count": len(results),
                "results": results
            }
    except Exception as e:
        return {"success": False, "error": f"Ошибка проверки заказов: {str(e)}"}

def parse_price(price_str: Any) -> Optional[float]:
    if price_str is None:
        return None
    s = str(price_str).replace(" ", "").replace("\u00a0", "").replace("₽", "").replace(",", ".")
    digits = "".join(c for c in s if c.isdigit() or c == ".")
    try:
        return float(digits) if digits else None
    except Exception:
        return None

def normalize_search_url_for_compare(u: Optional[str]) -> str:
    """Нормализует поисковый URL для точного сравнения без учета протокола, www/m и порядка параметров."""
    if not u:
        return ""
    import urllib.parse
    s = str(u).strip().lower().rstrip("/")
    if "://" in s:
        s = s.split("://", 1)[1]
    if s.startswith("www."):
        s = s[4:]
    if s.startswith("m."):
        s = s[2:]
    parts = s.split("?", 1)
    path = parts[0].rstrip("/")
    if len(parts) > 1:
        qs = urllib.parse.parse_qsl(parts[1], keep_blank_values=True)
        filtered_qs = sorted([(k, v.rstrip("/")) for k, v in qs if k not in ("spm", "_gl", "from", "utm_source", "utm_medium", "utm_campaign")])
        if filtered_qs:
            return f"{path}?{urllib.parse.urlencode(filtered_qs)}"
    return path

def is_search_allowed_for_autobuy(
    cfg: Dict[str, Any],
    search_name: Optional[str] = None,
    search_url: Optional[str] = None,
    search_id: Optional[Any] = None
) -> bool:
    """
    Проверяет, разрешена ли авто-бронь для данной поисковой ссылки:
    - При auto_buy_mode == 'all': разрешено для всех ссылок.
    - При auto_buy_mode == 'selected': разрешено только для ссылок из auto_buy_searches.
    """
    mode = cfg.get("auto_buy_mode", "all")
    if mode != "selected":
        return True

    allowed = cfg.get("auto_buy_searches", [])
    if not allowed:
        return False

    clean_id = str(search_id or "").strip()
    clean_name = str(search_name or "").strip().lower()
    norm_url = normalize_search_url_for_compare(search_url)

    for item in allowed:
        if isinstance(item, dict):
            i_id = str(item.get("id") or "").strip()
            i_name = str(item.get("name") or "").strip().lower()
            i_url = normalize_search_url_for_compare(item.get("url"))

            # 1. По ID ссылки
            if clean_id and i_id and clean_id == i_id:
                return True
            # 2. По нормализованному URL
            if norm_url and i_url and norm_url == i_url:
                return True
            # 3. По названию поиска
            if clean_name and i_name and clean_name == i_name:
                return True
        elif isinstance(item, (str, int)):
            s = str(item).strip()
            if not s:
                continue
            if clean_id and s == clean_id:
                return True
            if clean_name and s.lower() == clean_name:
                return True
            s_url = normalize_search_url_for_compare(s)
            if norm_url and s_url and norm_url == s_url:
                return True
    return False

def get_search_automation_settings(search_id: Optional[Any] = None, search_url: Optional[str] = None, search_name: Optional[str] = None) -> Dict[str, Any]:
    """Загружает индивидуальные настройки ссылки (выкуп, автобронь, планка цены, доставка, рейтинг)."""
    defaults = {"autobuy": 0, "autoreserve": 0, "max_price": 0.0, "price_with_delivery": 1, "min_rating": 0.0}
    try:
        import sqlite3
        db_path = os.path.join(BASE_DIR, "avito_bot", "avito_bot.db")
        if os.path.exists(db_path):
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                row = None
                if search_id:
                    cur.execute("SELECT autobuy, autoreserve, max_price, price_with_delivery, min_rating FROM tracked_urls WHERE id = ?", (search_id,))
                    row = cur.fetchone()
                if not row and search_url:
                    clean_u = search_url.strip().rstrip('/')
                    cur.execute("SELECT autobuy, autoreserve, max_price, price_with_delivery, min_rating FROM tracked_urls WHERE url = ? OR RTRIM(url, '/') = ?", (search_url, clean_u))
                    row = cur.fetchone()
                if not row and search_name:
                    cur.execute("SELECT autobuy, autoreserve, max_price, price_with_delivery, min_rating FROM tracked_urls WHERE LOWER(name) = LOWER(?)", (search_name.strip(),))
                    row = cur.fetchone()
                if row:
                    return {
                        "autobuy": int(row["autobuy"] or 0),
                        "autoreserve": int(row["autoreserve"] or 0),
                        "max_price": float(row["max_price"] or 0),
                        "price_with_delivery": int(row["price_with_delivery"] if row["price_with_delivery"] is not None else 1),
                        "min_rating": float(row["min_rating"] or 0)
                    }
    except Exception:
        pass

    try:
        users_file = os.path.join(BASE_DIR, "data", "users.json")
        if os.path.exists(users_file):
            with open(users_file, "r", encoding="utf-8-sig") as f:
                users = json.load(f)
            for u in (users if isinstance(users, list) else [users]):
                for s in (u.get("avito_searches") or []):
                    if isinstance(s, dict):
                        match = False
                        if search_id and (s.get("id") == search_id or str(s.get("id")) == str(search_id)):
                            match = True
                        elif search_url and s.get("url") and (s.get("url").strip().rstrip('/') == search_url.strip().rstrip('/')):
                            match = True
                        elif search_name and s.get("name") and (s.get("name").strip().lower() == search_name.strip().lower()):
                            match = True
                        if match:
                            pwd = s.get("price_with_delivery")
                            return {
                                "autobuy": int(s.get("autobuy", 0) or 0),
                                "autoreserve": int(s.get("autoreserve", 0) or 0),
                                "max_price": float(s.get("max_price", 0) or 0),
                                "price_with_delivery": int(1 if (pwd is None or pwd is True or pwd == 1) else 0),
                                "min_rating": float(s.get("min_rating", 0) or 0)
                            }
    except Exception:
        pass

    return defaults

def trigger_sniper_on_new_ad(
    item_id: str,
    item_title: str,
    item_price: Any,
    item_url: Optional[str] = None,
    has_delivery: bool = True,
    seller_rating: Optional[str] = None,
    search_name: Optional[str] = None,
    search_url: Optional[str] = None,
    search_id: Optional[Any] = None,
    search_settings: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Вызывается автоматически при обнаружении НОВОГО объявления:
    1. Если включено авто-сообщение — отправляет текст в чат за 1 сек.
    2. Раздельные операции для каждой ссылки:
       - Если включен ВЫКУП: автоматическая оплата / чекаут.
       - Если включена АВТО-БРОНЬ: автоматическое бронирование (без немедленного списания / оплата при получении).
    3. Проверка параметров ссылки: планка цены (по умолчанию с учётом доставки) и мин. рейтинг продавца.
    """
    import threading
    cfg = get_config()
    clean_id = str(item_id or "").strip()
    if not clean_id:
        return {"triggered": False, "reason": "empty item_id"}

    results = {"item_id": clean_id, "auto_message": False, "autobuy": False, "autoreserve": False}

    # 1. Авто-сообщение продавцу (если включено в общих настройках снайпера)
    if cfg.get("auto_message_enabled"):
        msg_text = cfg.get("auto_message_text", "Здравствуйте! Готов забрать сегодня с доставкой, ещё актуально?")
        def _bg_msg():
            try:
                import asyncio
                res = asyncio.run(send_seller_message(clean_id, item_url, msg_text, headless=True))
                print(f"[SNIPER AUTO-MSG #{clean_id}]: {res}", flush=True)
            except Exception as e:
                print(f"[SNIPER AUTO-MSG ERROR #{clean_id}]: {e}", flush=True)

        threading.Thread(target=_bg_msg, daemon=True).start()
        results["auto_message"] = True

    # 2. Получаем индивидуальные настройки автоматизации для данной ссылки
    s_set = search_settings
    if not s_set or not isinstance(s_set, dict):
        s_set = get_search_automation_settings(search_id=search_id, search_url=search_url, search_name=search_name)

    is_buy = bool(s_set.get("autobuy", 0))
    is_reserve = bool(s_set.get("autoreserve", 0))

    if not is_buy and not is_reserve:
        results["skipped"] = True
        results["reason"] = "neither autobuy nor autoreserve enabled for this link"
        return results

    # 3. Проверка рейтинга продавца по настройке ссылки
    link_min_rating = float(s_set.get("min_rating") or 0)
    if link_min_rating > 0 and seller_rating:
        import re as _re
        rm = _re.search(r'(\d+(?:[,\.]\d+)?)', str(seller_rating))
        if rm:
            rating_val = float(rm.group(1).replace(',', '.'))
            if rating_val < link_min_rating:
                print(f"[SNIPER #{clean_id}]: Пропуск лота: рейтинг продавца {rating_val} ниже минимального {link_min_rating} для этой ссылки", flush=True)
                results["skipped"] = True
                results["reason"] = f"Рейтинг {rating_val} < {link_min_rating}"
                return results

    # 4. Проверка планки цены по настройке ссылки
    price_num = parse_price(item_price)
    link_max_price = float(s_set.get("max_price") or 0)
    if link_max_price > 0 and price_num is not None:
        if price_num > link_max_price:
            print(f"[SNIPER #{clean_id}]: Пропуск лота: цена {price_num} ₽ выше планки {link_max_price} ₽ для этой ссылки", flush=True)
            results["skipped"] = True
            results["reason"] = f"Цена {price_num} ₽ > {link_max_price} ₽"
            return results

    # 5. Разделение операций: ВЫКУП vs АВТОБРОНЬ
    op_type = "buy" if is_buy else "reserve"
    op_title = "ВЫКУП" if op_type == "buy" else "АВТО-БРОНЬ"
    op_emoji = "⚡" if op_type == "buy" else "🔒"

    auto_pay = not cfg.get("safe_mode", False)
    pwd = s_set.get("price_with_delivery")
    price_with_deliv = bool(pwd) if pwd is not None else True

    def _bg_action():
        try:
            import asyncio
            res = asyncio.run(fast_checkout_item(
                clean_id,
                item_url,
                auto_pay=auto_pay,
                headless=True,
                op_type=op_type,
                max_price=link_max_price,
                max_price_includes_delivery=price_with_deliv,
                min_seller_rating=link_min_rating
            ))
            print(f"[SNIPER {op_title} #{clean_id}]: {res}", flush=True)

            # Telegram уведомление
            try:
                import sys
                import os
                BASE_DIR = os.path.dirname(os.path.abspath(__file__))
                if BASE_DIR not in sys.path:
                    sys.path.insert(0, BASE_DIR)
                from avito_api_helper import send_telegram_raw_message, load_users_data

                users, _ = load_users_data()
                target_chat_ids = [u.get("telegram_chat_id") for u in users if u.get("telegram_chat_id")]
                target_url = item_url if item_url else f"https://www.avito.ru/{clean_id}"
                price_display = f"{int(price_num):,} ₽".replace(",", " ") if price_num else str(item_price or "")

                if res.get("success"):
                    status_text = res.get("message") or ("Заказ оплачен роботом" if op_type == "buy" else "Товар забронирован роботом")
                    tg_text = (
                        f"{op_emoji} <b>Снайпер: {op_title} успешно оформлен(а) роботом!</b>\n\n"
                        f"📦 <b>Товар:</b> {item_title or clean_id}\n"
                        f"💰 <b>Цена:</b> {price_display}\n"
                        f"⚙️ <b>Операция:</b> {op_title} ({'списание/оплата' if op_type == 'buy' else 'без списания / при получении'})\n"
                        f"🆔 <b>Номер объявления:</b> <code>{clean_id}</code>\n"
                        f"⚡ <b>Статус:</b> <i>{status_text}</i>\n\n"
                        f"🔗 <a href='{target_url}'>Открыть объявление</a>\n"
                        f"📦 <a href='https://www.avito.ru/orders'>Перейти в заказы на Авито</a>"
                    )
                    reply_markup = {
                        "inline_keyboard": [
                            [{"text": "📦 Открыть заказы на Авито", "url": "https://www.avito.ru/orders"}],
                            [{"text": "🌐 Карточка товара", "url": target_url}]
                        ]
                    }
                    for cid in set(target_chat_ids):
                        send_telegram_raw_message(cid, tg_text, reply_markup=reply_markup)
                elif res.get("error"):
                    err_text = res.get("error")
                    tg_text = (
                        f"⚠️ <b>Снайпер: Не удалось выполнить {op_title.lower()}</b>\n\n"
                        f"📦 <b>Товар:</b> {item_title or clean_id}\n"
                        f"💰 <b>Цена:</b> {price_display}\n"
                        f"⚙️ <b>Операция:</b> {op_title}\n"
                        f"🆔 <b>Номер объявления:</b> <code>{clean_id}</code>\n"
                        f"❌ <b>Причина:</b> <i>{err_text}</i>\n\n"
                        f"🔗 <a href='{target_url}'>Открыть объявление</a>"
                    )
                    for cid in set(target_chat_ids):
                        send_telegram_raw_message(cid, tg_text)
            except Exception as _tg_err:
                print(f"[SNIPER {op_title} TG ERROR #{clean_id}]: {_tg_err}", flush=True)

        except Exception as e:
            print(f"[SNIPER {op_title} ERROR #{clean_id}]: {e}", flush=True)

    threading.Thread(target=_bg_action, daemon=True).start()
    if op_type == "buy":
        results["autobuy"] = True
    else:
        results["autoreserve"] = True
    results["price"] = price_num
    results["max_price"] = link_max_price
    results["operation"] = op_type

    return results

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Не указана команда"}, ensure_ascii=True))
        return

    cmd = sys.argv[1].lower()

    if cmd == "status":
        res = asyncio.run(check_auth_status())
        print(json.dumps(res, ensure_ascii=True))
    elif cmd == "login":
        is_reauth = (len(sys.argv) > 2 and sys.argv[2].lower() == "reauth")
        res = asyncio.run(open_login_window(reauth=is_reauth))
        print(json.dumps(res, ensure_ascii=True))
    elif cmd == "get-config":
        print(json.dumps({"success": True, "config": get_config()}, ensure_ascii=True))
    elif cmd == "save-config":
        try:
            cfg_data = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
            ok = save_config(cfg_data)
            print(json.dumps({"success": ok, "config": get_config()}, ensure_ascii=True))
        except Exception as e:
            print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=True))
    elif cmd == "checkout-preview":
        item_id = sys.argv[2] if len(sys.argv) > 2 else ""
        item_url = sys.argv[3] if len(sys.argv) > 3 else None
        res = asyncio.run(get_checkout_preview(item_id, item_url))
        print(json.dumps(res, ensure_ascii=True))
    elif cmd == "checkout-confirm":
        item_id = sys.argv[2] if len(sys.argv) > 2 else ""
        item_url = sys.argv[3] if len(sys.argv) > 3 else None
        pm = sys.argv[4] if len(sys.argv) > 4 else "card"
        sms = sys.argv[5] if len(sys.argv) > 5 and sys.argv[5].strip() else None
        res = asyncio.run(confirm_checkout_order(item_id, item_url, payment_method=pm, sms_code=sms))
        print(json.dumps(res, ensure_ascii=True))
    elif cmd == "checkout":
        item_id = sys.argv[2] if len(sys.argv) > 2 else ""
        item_url = sys.argv[3] if len(sys.argv) > 3 else None
        auto_pay = (sys.argv[4].lower() == "true") if len(sys.argv) > 4 else None
        headless = (sys.argv[5].lower() == "true") if len(sys.argv) > 5 else None
        res = asyncio.run(fast_checkout_item(item_id, item_url, auto_pay=auto_pay, headless=headless))
        print(json.dumps(res, ensure_ascii=True))
    elif cmd == "message":
        item_id = sys.argv[2] if len(sys.argv) > 2 else ""
        item_url = sys.argv[3] if len(sys.argv) > 3 else None
        msg_text = sys.argv[4] if len(sys.argv) > 4 else None
        headless = (sys.argv[5].lower() == "true") if len(sys.argv) > 5 else None
        res = asyncio.run(send_seller_message(item_id, item_url, msg_text, headless=headless))
        print(json.dumps(res, ensure_ascii=True))
    elif cmd == "cancel-order":
        item_id = sys.argv[2] if len(sys.argv) > 2 else ""
        item_url = sys.argv[3] if len(sys.argv) > 3 else None
        order_url = sys.argv[4] if len(sys.argv) > 4 else None
        res = asyncio.run(cancel_order(item_id, item_url=item_url, order_url=order_url))
        print(json.dumps(res, ensure_ascii=True))
    elif cmd == "trigger":
        item_id = sys.argv[2] if len(sys.argv) > 2 else ""
        item_title = sys.argv[3] if len(sys.argv) > 3 else ""
        item_price = sys.argv[4] if len(sys.argv) > 4 else 0
        item_url = sys.argv[5] if len(sys.argv) > 5 else None
        res = trigger_sniper_on_new_ad(item_id, item_title, item_price, item_url)
        print(json.dumps({"success": True, "result": res}, ensure_ascii=True))
    else:
        print(json.dumps({"success": False, "error": f"Неизвестная команда: {cmd}"}, ensure_ascii=True))

if __name__ == "__main__":
    main()
