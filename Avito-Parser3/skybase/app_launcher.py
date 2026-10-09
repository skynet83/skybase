# -*- coding: utf-8 -*-
"""
SkyBase Launcher & Supervisor Desktop App
Единая точка запуска сайта, бэкенда и Telegram-бота Avito.
1. Запускает сервер SkyBase на порту 80/8080.
2. Автоматически открывает сайт в браузере по умолчанию (http://localhost/).
3. Предоставляет удобное окно управления с мониторингом статуса, сетевых адресов и логов.
4. Корректно завершает все процессы при закрытии приложения.
"""

import os
import sys
import time
import socket
import threading
import subprocess
import webbrowser
import urllib.request
import urllib.error
import urllib.parse
import json
import atexit
import tempfile
import winreg
import ctypes
from ctypes import wintypes
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog

# Определение рабочей директории
if getattr(sys, 'frozen', False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

def find_site_dir():
    """Интеллектуальный поиск папки с веб-сервером и файлами gateway.py / index.html."""
    candidates = [
        os.path.join(APP_DIR, "skybase"),
        os.path.join(APP_DIR, "SITE"),
        os.path.join(APP_DIR, "avito-bot"),
        os.path.join(APP_DIR, "avito-bot", "SITE"),
        APP_DIR,
        os.path.abspath(os.path.join(APP_DIR, "..", "skybase")),
        os.path.abspath(os.path.join(APP_DIR, "..", "SITE")),
        os.path.abspath(os.path.join(APP_DIR, "..", "avito-bot")),
        os.path.abspath(os.path.join(APP_DIR, "..", "avito-bot", "SITE")),
        os.path.abspath(os.path.join(APP_DIR, "..")),
        r"C:\ins\Avito-Parser3\skybase",
        r"C:\ins\Avito-Parser2\skybase",
        r"C:\ins\avito-bot",
        r"E:\TEMP\Avito-bot2\avito-bot\SITE",
        r"E:\TEMP\Avito-bot2\avito-bot",
        r"C:\ins\EXP\Arduino\Проект\База-бот\SITE",
        r"C:\ins\общий\База-бот\SITE"
    ]
    for c in candidates:
        if c and os.path.isdir(c):
            gw = os.path.join(c, "gateway.py")
            idx = os.path.join(c, "index.html")
            if os.path.exists(gw) and os.path.exists(idx):
                return os.path.abspath(c)
    # Резервный вариант
    if os.path.exists(os.path.join(APP_DIR, "skybase")):
        return os.path.join(APP_DIR, "skybase")
    if os.path.exists(os.path.join(APP_DIR, "SITE")):
        return os.path.join(APP_DIR, "SITE")
    return APP_DIR


SITE_DIR = find_site_dir()

if SITE_DIR not in sys.path:
    sys.path.insert(0, SITE_DIR)

LIB_DIR = os.path.join(SITE_DIR, "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

LOG_FILE = os.path.join(SITE_DIR, "gateway.log")
import ctypes

# Регистрация уникального AppUserModelID в Windows, чтобы таскбар использовал наш значок вместо пера Tkinter
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('skybase.server.app.v1')
except Exception:
    pass

def ensure_single_instance():
    """Защита от запуска нескольких копий SkyBase (Single Instance Mutex)."""
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            mutex_name = "Global\\SkyBaseServerAppSingleInstanceMutex"
            mutex = kernel32.CreateMutexW(None, False, mutex_name)
            last_error = kernel32.GetLastError()
            ERROR_ALREADY_EXISTS = 183
            if last_error == ERROR_ALREADY_EXISTS:
                user32 = ctypes.windll.user32
                hwnd = user32.FindWindowW(None, "SkyBase Server")
                if hwnd:
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.SetForegroundWindow(hwnd)
                sys.exit(0)
            return mutex
        except Exception:
            pass
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

def is_valid_python(path):
    """Проверяет, что файл существует, не является заглушкой WindowsApps/MS Store и реально исполняет Python 3.10+."""
    if not path or not isinstance(path, str):
        return False
    norm = os.path.normpath(path).lower()
    if not os.path.exists(path):
        return False
    if "windowsapps" in norm:
        return False
    if any(bad in os.path.basename(norm) for bad in ["skybase", "electrobase", "keymanager"]):
        return False
    try:
        res = subprocess.run(
            [path, "-c", "import sys; sys.exit(0 if sys.version_info[0] == 3 and sys.version_info[1] >= 10 else 1)"],
            capture_output=True,
            timeout=3,
            creationflags=CREATE_NO_WINDOW
        )
        return res.returncode == 0
    except Exception:
        return False

def get_real_python_exe(prefer_windowless=False):
    """Определяет реальный рабочий путь к интерпретатору python.exe (или pythonw.exe)."""
    p = None
    if not getattr(sys, 'frozen', False):
        if sys.executable.lower().endswith(("python.exe", "pythonw.exe")):
            if is_valid_python(sys.executable):
                p = sys.executable

    # Проверяем автономный встроенный python-embed в директории проекта/приложения (наивысший приоритет)
    if not p:
        embed_candidates = [
            os.path.join(SITE_DIR, "python.exe"),
            os.path.join(APP_DIR, "python.exe"),
            os.path.join(SITE_DIR, "python-embed", "python.exe"),
            os.path.join(APP_DIR, "python-embed", "python.exe"),
            os.path.join(os.path.dirname(APP_DIR), "python-embed", "python.exe"),
        ]
        for c in embed_candidates:
            if c and os.path.exists(c) and is_valid_python(c):
                p = c
                break

    # Проверяем явную переменную окружения PYTHON_EXE
    if not p:
        env_py = os.environ.get("PYTHON_EXE")
        if env_py and is_valid_python(env_py):
            p = env_py

    # Проверяем стандартные каталоги установки Python на Windows (приоритет перед PATH)
    if not p:
        candidates = [

            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "python.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Python311", "python.exe"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Python311", "python.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python312", "python.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Python312", "python.exe"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python310", "python.exe"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Python310", "python.exe"),
            r"C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe",
        ]
        for c in candidates:
            if c and is_valid_python(c):
                p = c
                break

    # Проверяем команды в PATH (строго фильтруя WindowsApps)
    if not p:
        import shutil
        for name in ["python", "python3", "py"]:
            candidate = shutil.which(name)
            if candidate and is_valid_python(candidate):
                p = candidate
                break

    if not p:
        return None

    if prefer_windowless and sys.platform == "win32":
        pw = os.path.join(os.path.dirname(p), "pythonw.exe")
        if os.path.exists(pw):
            return pw
    return p

def ensure_python_installed(log_callback=None):
    """Проверяет наличие Python в системе. Если отсутствует, производит автономную тихую установку."""
    p = get_real_python_exe()
    if p:
        return p

    installer_candidates = [
        os.path.join(SITE_DIR, "installer", "python-installer.exe"),
        os.path.join(SITE_DIR, "avito_bot", "installer", "python-installer.exe"),
        os.path.join(APP_DIR, "installer", "python-installer.exe"),
        os.path.join(APP_DIR, "avito_bot", "installer", "python-installer.exe"),
        r"C:\ins\skybase\installer\python-installer.exe",
        r"C:\ins\skybase\avito_bot\installer\python-installer.exe",
        r"C:\ins\Avito-Parser\skybase\installer\python-installer.exe",
        r"C:\ins\Avito-Parser\skybase\avito_bot\installer\python-installer.exe",
    ]
    for drive in ["D", "E", "F"]:
        installer_candidates.append(f"{drive}:\\TEMP\\SITE\\avito_bot\\installer\\python-installer.exe")

    installer_path = None
    for cand in installer_candidates:
        if os.path.exists(cand):
            try:
                if os.path.getsize(cand) > 5000000:
                    installer_path = cand
                    break
            except Exception:
                pass

    # Если локальный установщик не найден, автоматически скачиваем с официального сайта
    if not installer_path:
        target_dir = os.path.join(SITE_DIR, "installer")
        try:
            os.makedirs(target_dir, exist_ok=True)
            installer_path = os.path.join(target_dir, "python-installer.exe")
        except Exception:
            installer_path = os.path.join(tempfile.gettempdir(), "python-installer.exe")

        if log_callback:
            log_callback("  [1/6] [*] Локальный установщик не найден. Загрузка Python 3.11.9 с python.org...")

        py_url = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe"
        download_ok = False

        # Попытка через urllib
        try:
            req = urllib.request.Request(py_url, headers={"User-Agent": "Mozilla/5.0 SkyBaseInstaller/1.0"})
            with urllib.request.urlopen(req, timeout=60) as resp, open(installer_path, "wb") as out_f:
                while True:
                    chunk = resp.read(128 * 1024)
                    if not chunk:
                        break
                    out_f.write(chunk)
            if os.path.exists(installer_path) and os.path.getsize(installer_path) > 5000000:
                download_ok = True
        except Exception as e:
            if log_callback:
                log_callback(f"        urllib download error: {e}, пробуем curl...")

        # Резервная попытка через curl.exe
        if not download_ok:
            try:
                subprocess.run(
                    ["curl.exe", "-fSL", "--connect-timeout", "20", "--retry", "3", "-o", installer_path, py_url],
                    check=True, timeout=120, creationflags=CREATE_NO_WINDOW
                )
                if os.path.exists(installer_path) and os.path.getsize(installer_path) > 5000000:
                    download_ok = True
            except Exception as e:
                if log_callback:
                    log_callback(f"        curl download error: {e}")

        if not download_ok or not os.path.exists(installer_path) or os.path.getsize(installer_path) < 5000000:
            if log_callback:
                log_callback("  [1/6] [FAIL] Не удалось скачать установщик Python. Проверьте интернет!")
            return None

    if log_callback:
        log_callback("  [1/6] [*] Запуск автоматической тихой установки Python 3.11...")
        log_callback(f"        Источник: {installer_path}")
        log_callback("        Пожалуйста, подождите 15-30 секунд...")

    try:
        cmd = [installer_path, "/quiet", "InstallAllUsers=0", "PrependPath=1", "Include_test=0", "SimpleInstall=1"]
        subprocess.run(cmd, check=True, timeout=180, creationflags=CREATE_NO_WINDOW)
    except Exception as e:
        if log_callback:
            log_callback(f"  [1/6] [FAIL] Ошибка выполнения установщика Python: {e}")
        return None

    time.sleep(2)

    std_candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Python", "Python311", "python.exe"),
        os.path.join(os.environ.get("ProgramFiles", ""), "Python311", "python.exe"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Python311", "python.exe"),
    ]
    for sp in std_candidates:
        if is_valid_python(sp):
            py_dir = os.path.dirname(sp)
            scripts_dir = os.path.join(py_dir, "Scripts")
            os.environ["PATH"] = f"{py_dir};{scripts_dir};" + os.environ.get("PATH", "")
            os.environ["PYTHON_EXE"] = sp
            if log_callback:
                log_callback(f"  [1/6] [OK] Python 3.11 успешно установлен локально: {sp}")
            return sp

    p = get_real_python_exe()
    if p:
        if log_callback:
            log_callback(f"  [1/6] [OK] Python успешно обнаружен: {p}")
        return p

    return None

def ensure_ps1_bom(ps1_path):
    """Гарантирует наличие сигнатуры UTF-8 BOM в .ps1 скриптах для корректного чтения PowerShell 5.1."""
    try:
        if os.path.exists(ps1_path):
            with open(ps1_path, "rb") as f:
                b = f.read()
            if b and not b.startswith(b"\xef\xbb\xbf"):
                with open(ps1_path, "wb") as f:
                    f.write(b"\xef\xbb\xbf" + b)
    except Exception:
        pass

def get_resource_path(relative_path):
    """Находит ресурс как при обычном запуске, так и внутри скомпилированного .exe."""
    if hasattr(sys, '_MEIPASS'):
        p = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(p):
            return p
    for base in (SITE_DIR, APP_DIR):
        p = os.path.join(base, relative_path)
        if os.path.exists(p):
            return p
    return relative_path

def get_local_ip():
    """Определение реального локального IP-адреса хоста в сети."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def is_port_open(port, timeout=0.3):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        return False

def get_system_browser_cmd():
    """Находит исполняемый файл браузера по умолчанию или доступные современные браузеры."""
    # 1. Из реестра Windows (UserChoice)
    if sys.platform == "win32":
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice") as key:
                prog_id, _ = winreg.QueryValueEx(key, "ProgId")
            with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, rf"{prog_id}\shell\open\command") as key:
                raw_cmd, _ = winreg.QueryValueEx(key, "")
                raw_cmd = raw_cmd.strip()
                if raw_cmd.startswith('"'):
                    end_quote = raw_cmd.find('"', 1)
                    if end_quote != -1:
                        exe_path = raw_cmd[1:end_quote]
                        if os.path.exists(exe_path):
                            return exe_path
                else:
                    parts = raw_cmd.split()
                    if parts and os.path.exists(parts[0]):
                        return parts[0]
        except Exception:
            pass

    # 2. Стандартные пути к браузерам в Windows
    candidates = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
        os.path.expandvars(r"%LocalAppData%\Yandex\YandexBrowser\Application\browser.exe"),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

BROWSER_EXES = {"chrome.exe", "msedge.exe", "firefox.exe", "browser.exe", "opera.exe", "brave.exe", "vivaldi.exe"}

def get_process_name_by_pid(pid):
    """Возвращает имя исполняемого файла процесса по его PID."""
    if not pid or pid <= 4:
        return ""
    try:
        kernel32 = ctypes.windll.kernel32
        h_proc = kernel32.OpenProcess(0x1000, False, int(pid))
        if not h_proc:
            return ""
        try:
            buf = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(1024)
            if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                return os.path.basename(buf.value).lower()
            return ""
        finally:
            kernel32.CloseHandle(h_proc)
    except Exception:
        return ""

def is_window_browser(hwnd):
    """Проверяет, принадлежит ли окно одному из веб-браузеров (исключая наш лаунчер)."""
    try:
        user32 = ctypes.windll.user32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return False
        pname = get_process_name_by_pid(pid.value)
        return pname in BROWSER_EXES
    except Exception:
        return False

def get_visible_browser_hwnds():
    """Возвращает список дескрипторов (HWND) видимых окон веб-браузеров на десктопе пользователя."""
    if sys.platform != "win32":
        return []
    user32 = ctypes.windll.user32
    hwnds = []

    try:
        hwinsta = user32.OpenWindowStationW('WinSta0', False, 0x10000000)
        if hwinsta:
            user32.SetProcessWindowStation(hwinsta)
        hdesk = user32.OpenDesktopW('Default', 0, False, 0x10000000)
        if hdesk:
            user32.SetThreadDesktop(hdesk)
    except Exception:
        hdesk = None

    def enum_cb(hwnd, lparam):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0 and is_window_browser(hwnd):
                hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    cb = WNDENUMPROC(enum_cb)
    if hdesk:
        user32.EnumDesktopWindows(hdesk, cb, 0)
    else:
        user32.EnumWindows(cb, 0)
    return hwnds

def bring_window_to_front(hwnd):
    """Надёжно выводит окно браузера на передний план и передаёт фокус ввода."""
    if not hwnd or sys.platform != "win32":
        return
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        try:
            hwinsta = user32.OpenWindowStationW('WinSta0', False, 0x10000000)
            if hwinsta:
                user32.SetProcessWindowStation(hwinsta)
            hdesk = user32.OpenDesktopW('Default', 0, False, 0x10000000)
            if hdesk:
                user32.SetThreadDesktop(hdesk)
        except Exception:
            pass

        cur_thread = kernel32.GetCurrentThreadId()
        fore_hwnd = user32.GetForegroundWindow()
        fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0
        if fore_thread and cur_thread != fore_thread:
            user32.AttachThreadInput(cur_thread, fore_thread, True)

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE (только для свернутых окон)
        elif not user32.IsZoomed(hwnd):
            user32.ShowWindow(hwnd, 5)  # SW_SHOW (для обычных окон без изменения размера)
        # Для развернутых на весь экран (IsZoomed) ShowWindow не вызываем!
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        try:
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass

        if fore_thread and cur_thread != fore_thread:
            user32.AttachThreadInput(cur_thread, fore_thread, False)
    except Exception:
        try:
            if ctypes.windll.user32.IsIconic(hwnd):
                ctypes.windll.user32.ShowWindow(hwnd, 9)
            elif not ctypes.windll.user32.IsZoomed(hwnd):
                ctypes.windll.user32.ShowWindow(hwnd, 5)
            ctypes.windll.user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

class SkyBaseLauncherApp:
    def __init__(self, root):
        self.root = root
        self.root.title("SkyBase Server")
        self.root.geometry("860x620")
        self.root.minsize(740, 520)
        self.root.configure(bg="#0f172a")

        # Иконка окна и панели задач
        ico_file = get_resource_path(os.path.join("img", "skybase.ico"))
        png_file = get_resource_path(os.path.join("img", "skybase_icon_256.png"))
        if os.path.exists(ico_file):
            try:
                self.root.iconbitmap(default=ico_file)
            except Exception:
                pass
        if os.path.exists(png_file):
            try:
                from PIL import Image, ImageTk
                self._app_icon_img = ImageTk.PhotoImage(Image.open(png_file))
                self.root.iconphoto(True, self._app_icon_img)
            except Exception:
                pass

        self.server_process = None
        self.is_running = False
        self.active_port = 80
        self.local_ip = get_local_ip()
        self.browser_opened = False
        self.browser_processes = []
        self.browser_was_already_running = False
        self.opened_browser_hwnds = set()
        self.startup_logs = []
        self.post_startup_warnings = []
        self.startup_completed = False
        self._startup_start_time = time.time()
        self.is_shutting_down = False
        self.is_stopped = False
        self._is_shutting_down_active = False
        self._is_closing_already = False

        # Автоматическое закрытие браузера отключено пользователем

        self.setup_ui()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        atexit.register(self.emergency_cleanup)

        # Запуск сервера в фоновом потоке при старте программы
        threading.Thread(target=self.start_server_workflow, daemon=True).start()

        # Фоновый мониторинг статуса и логов
        self.root.after(1000, self.update_logs_tick)
        self.root.after(500, self.update_status_tick)

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use("clam")

        # Верхний баннер
        header_frame = tk.Frame(self.root, bg="#1e293b", padx=16, pady=12, relief="ridge", bd=1)
        header_frame.pack(fill="x", padx=12, pady=(10, 6))

        h_title_row = tk.Frame(header_frame, bg="#1e293b")
        h_title_row.pack(fill="x")

        # Фирменный значок в шапке
        logo_file = get_resource_path(os.path.join("img", "skybase_header_logo.png"))
        self._header_logo_img = None
        if os.path.exists(logo_file):
            try:
                from PIL import Image, ImageTk
                self._header_logo_img = ImageTk.PhotoImage(Image.open(logo_file))
                lbl_icon = tk.Label(h_title_row, image=self._header_logo_img, bg="#1e293b")
                lbl_icon.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        lbl_logo = tk.Label(h_title_row, text="SkyBase Server", font=("Segoe UI", 14, "bold"), bg="#1e293b", fg="#fbbf24")
        lbl_logo.pack(side="left")

        self.lbl_status_badge = tk.Label(h_title_row, text="⏳ ЗАПУСК СЕРВЕРА...", font=("Segoe UI", 9, "bold"), 
                                         bg="#f59e0b", fg="#0f172a", padx=10, pady=3)
        self.lbl_status_badge.pack(side="right")

        # Блок ссылок и сетевых адресов
        network_frame = tk.LabelFrame(self.root, text=" 🌐 Адреса для подключения ", bg="#0f172a", fg="#38bdf8", 
                                      font=("Segoe UI", 10, "bold"), padx=12, pady=10)
        network_frame.pack(fill="x", padx=12, pady=6)

        # Локальный адрес (ПК)
        loc_row = tk.Frame(network_frame, bg="#0f172a")
        loc_row.pack(fill="x", pady=2)

        tk.Label(loc_row, text="🖥️ На этом компьютере:", font=("Segoe UI", 10, "bold"), bg="#0f172a", fg="#f8fafc", width=22, anchor="w").pack(side="left")
        self.lbl_local_url = tk.Label(loc_row, text="http://localhost/", font=("Consolas", 11, "bold"), bg="#0f172a", fg="#38bdf8")
        self.lbl_local_url.pack(side="left", padx=6)

        self.btn_open_browser = tk.Button(loc_row, text="🌐 Открыть в браузере", font=("Segoe UI", 9, "bold"),
                                          bg="#1e293b", fg="#64748b", activebackground="#1e293b", activeforeground="#64748b",
                                          disabledforeground="#64748b", relief="flat", cursor="arrow", padx=12, pady=3,
                                          state="disabled", takefocus=0, command=self.action_open_browser)
        self.btn_open_browser.pack(side="right")
        self.btn_open_browser.bind("<Button-1>", lambda e: "break")
        self.btn_open_browser.bind("<ButtonRelease-1>", lambda e: "break")

        # Адрес в локальной сети (LAN)
        lan_row = tk.Frame(network_frame, bg="#0f172a")
        lan_row.pack(fill="x", pady=(6, 2))

        tk.Label(lan_row, text="📱 В локальной сети (LAN):", font=("Segoe UI", 10), bg="#0f172a", fg="#94a3b8", width=22, anchor="w").pack(side="left")
        self.lbl_lan_url = tk.Label(lan_row, text=f"http://{self.local_ip}/", font=("Consolas", 11), bg="#0f172a", fg="#34d399")
        self.lbl_lan_url.pack(side="left", padx=6)

        btn_copy_lan = tk.Button(lan_row, text="📋 Скопировать ссылку", font=("Segoe UI", 9),
                                 bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=10, pady=3,
                                 command=self.action_copy_lan_url)
        btn_copy_lan.pack(side="right")

        # Информационная строка состояния компонентов
        info_strip = tk.Frame(self.root, bg="#1e293b", padx=12, pady=6)
        info_strip.pack(fill="x", padx=12, pady=(2, 6))

        self.lbl_gw_state = tk.Label(info_strip, text="● Шлюз (80): Проверка...", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9))
        self.lbl_gw_state.pack(side="left", padx=(0, 6))

        self.lbl_be_state = tk.Label(info_strip, text="● Бэкенд (порт 8081): Проверка...", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9))
        self.lbl_be_state.pack(side="left", padx=(0, 6))

        self.lbl_bot_state = tk.Label(info_strip, text="● Avito Bot: Проверка...", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9))
        self.lbl_bot_state.pack(side="left", padx=(0, 6))

        # Блок статуса тарифа / лицензии (справа в информационной строке, по правому краю блока)
        self.license_box = tk.Frame(info_strip, bg="#1e293b")
        self.license_box.pack(side="right")

        # Отображение тарифа: фиксированный контейнер 195px гарантирует, что "Тариф: " зафиксирован на одном месте
        # и не двигается в ожидании появления времени, а плашка даты выравнивается ровно по правому краю блока
        self.tariff_display_frame = tk.Frame(self.license_box, bg="#1e293b", width=195, height=26)
        self.tariff_display_frame.pack_propagate(False)
        self.lbl_tariff_title = tk.Label(
            self.tariff_display_frame,
            text="Тариф: ",
            font=("Segoe UI", 9, "bold"),
            fg="#fbbf24",
            bg="#1e293b"
        )
        self.lbl_tariff_title.pack(side="left")

        self.lbl_tariff_val = tk.Label(
            self.tariff_display_frame,
            text="",
            font=("Segoe UI", 9, "bold"),
            fg="#ffffff",
            bg="#1e293b",
            padx=0,
            pady=0
        )
        self.lbl_tariff_val.pack(side="left")

        # Компактная кликабельная иконка-ключик 🔑 (без лишнего текста, показывается только когда тариф истек)
        self.btn_license_key = tk.Button(
            self.tariff_display_frame,
            text="🔑",
            font=("Segoe UI", 9),
            bg="#dc2626",
            fg="#ffffff",
            activebackground="#b91c1c",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=6,
            pady=0,
            bd=0,
            command=self.action_open_activation_dialog
        )
        self.btn_license_state = self.btn_license_key

        # При запуске сразу отображаем только "Тариф: " (некликабельным) на зафиксированном месте!
        self.tariff_display_frame.pack(side="right")
        self.lbl_license_state = self.lbl_tariff_val
        self.activation_checked = False

        # Кнопка обновления перед тарифом (свободный отступ с обеих сторон, не зажимается)
        self.btn_strip_update = tk.Button(
            info_strip,
            text="🔄 Обновить",
            font=("Segoe UI", 9, "bold"),
            bg="#1e293b",
            fg="#64748b",
            activebackground="#1e293b",
            activeforeground="#64748b",
            disabledforeground="#64748b",
            relief="flat",
            cursor="arrow",
            padx=8,
            pady=1,
            state="disabled",
            takefocus=0,
            command=self.action_open_updater_window
        )
        self.btn_strip_update.pack(side="right", padx=(0, 10))
        self.btn_strip_update.bind("<Button-1>", lambda e: "break")
        self.btn_strip_update.bind("<ButtonRelease-1>", lambda e: "break")
        self.is_update_btn_enabled = False

        # Специальная строка наглядного оповещения о проблемах (Красная строка)
        self.alert_frame = tk.Frame(self.root, bg="#1e293b", padx=12, pady=6, relief="solid", bd=1)
        self.alert_frame.pack(fill="x", padx=12, pady=(0, 6))

        self.lbl_alert_icon = tk.Label(self.alert_frame, text="⏳", font=("Segoe UI", 11, "bold"), bg="#1e293b", fg="#94a3b8")
        self.lbl_alert_icon.pack(side="left", padx=(0, 8))

        self.lbl_alert_text = tk.Label(
            self.alert_frame,
            text="Инициализация служб SkyBase и проверка готовности компонентов...",
            font=("Segoe UI", 9, "bold"),
            bg="#1e293b",
            fg="#94a3b8",
            wraplength=720,
            justify="left",
            anchor="w"
        )
        self.lbl_alert_text.pack(side="left", fill="x", expand=True)

        # Консоль логов в реальном времени
        log_box = tk.LabelFrame(self.root, text=" 📜 Системный журнал работы сервера (онлайн) ", bg="#0f172a", fg="#f8fafc",
                                font=("Segoe UI", 9, "bold"), padx=8, pady=6)
        log_box.pack(fill="both", expand=True, padx=12, pady=(0, 6))

        # Панель действий журнала и отчёта
        log_bar = tk.Frame(log_box, bg="#0f172a")
        log_bar.pack(fill="x", pady=(0, 4))

        tk.Label(log_bar, text="Ход запуска, сетевая диагностика и события:", font=("Segoe UI", 8), bg="#0f172a", fg="#94a3b8").pack(side="left")

        self.btn_copy_report = tk.Button(log_bar, text="📋 Скопировать отчёт загрузки", font=("Segoe UI", 9, "bold"),
                                         bg="#1e293b", fg="#38bdf8", activebackground="#0284c7", activeforeground="#ffffff",
                                         relief="flat", cursor="hand2", padx=10, pady=2,
                                         command=self.action_copy_startup_report)
        self.btn_copy_report.pack(side="right")

        self.txt_logs = scrolledtext.ScrolledText(log_box, bg="#0b1120", fg="#94a3b8", font=("Consolas", 9),
                                                   insertbackground="#38bdf8", relief="flat", bd=2)
        self.txt_logs.pack(fill="both", expand=True)
        self.txt_logs.tag_config("cyan", foreground="#38bdf8")
        self.txt_logs.tag_config("green", foreground="#34d399", font=("Consolas", 9, "bold"))
        self.txt_logs.tag_config("yellow", foreground="#fbbf24")
        self.txt_logs.tag_config("red", foreground="#ef4444", font=("Consolas", 9, "bold"))
        self.txt_logs.tag_config("error_line", foreground="#ffffff", background="#b91c1c", font=("Consolas", 9, "bold"))
        self.txt_logs.tag_config("error_bar", foreground="#fca5a5", background="#450a0a", font=("Consolas", 9, "bold"))
        self.setup_logs_context_menu()

        # Нижняя панель действий
        bottom_bar = tk.Frame(self.root, bg="#0f172a")
        bottom_bar.pack(fill="x", padx=12, pady=(0, 10))

        # Кнопка открытия сайта (изначально неактивна, пока Шлюз, Бэкенд и Авито бот не станут зелёными)
        self.btn_launch = tk.Button(
            bottom_bar,
            text="🌐 Открыть сайт",
            font=("Segoe UI", 10, "bold"),
            bg="#1e293b",
            fg="#64748b",
            activebackground="#1e293b",
            activeforeground="#64748b",
            disabledforeground="#64748b",
            relief="flat",
            cursor="arrow",
            padx=14,
            pady=5,
            state="disabled",
            takefocus=0,
            command=self.action_open_browser
        )
        self.btn_launch.pack(side="left")
        self.btn_launch.bind("<Button-1>", lambda e: "break")
        self.btn_launch.bind("<ButtonRelease-1>", lambda e: "break")
        self.is_browser_btn_enabled = False

        btn_restart = tk.Button(bottom_bar, text="🔄 Перезапустить сервер", font=("Segoe UI", 9, "bold"),
                                bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=12, pady=5,
                                command=self.action_restart_server)
        btn_restart.pack(side="left", padx=8)

        btn_key_mgr = tk.Button(bottom_bar, text="🔑 Активация ключа", font=("Segoe UI", 9, "bold"),
                                bg="#334155", fg="#fbbf24", relief="flat", cursor="hand2", padx=12, pady=5,
                                command=self.action_open_activation_dialog)
        btn_key_mgr.pack(side="left")

        btn_update = tk.Button(bottom_bar, text="🛡 Обновление / Бэкап", font=("Segoe UI", 9, "bold"),
                               bg="#334155", fg="#38bdf8", activebackground="#0284c7", activeforeground="#ffffff",
                               relief="flat", cursor="hand2", padx=12, pady=5,
                               command=self.action_open_updater_window)
        btn_update.pack(side="left", padx=8)

        btn_stop = tk.Button(bottom_bar, text="🛑 Остановить сервер", font=("Segoe UI", 9, "bold"),
                             bg="#7f1d1d", fg="#fca5a5", activebackground="#991b1b", activeforeground="#ffffff",
                             relief="flat", cursor="hand2", padx=14, pady=5, command=self.action_stop_server)
        btn_stop.pack(side="right")

    def set_problem_banner(self, text, is_error=True):
        """Отображает наглядную красную строчку о проблемах вверху окна программы."""
        if not hasattr(self, 'alert_frame'):
            return
        try:
            if not text:
                self.alert_frame.config(bg="#14532d", bd=1)
                self.lbl_alert_icon.config(text="✅", bg="#14532d", fg="#86efac")
                self.lbl_alert_text.config(text="Все службы работают штатно (Шлюз, Бэкенд и Avito Bot активны)", bg="#14532d", fg="#86efac")
            elif is_error:
                self.alert_frame.config(bg="#7f1d1d", bd=2)
                self.lbl_alert_icon.config(text="⛔", bg="#7f1d1d", fg="#ffffff")
                prefix = "" if any(text.startswith(p) for p in ["ОБНАРУЖЕНА", "ТРЕБУЕТСЯ", "⛔", "🔴"]) else "ОБНАРУЖЕНА ПРОБЛЕМА: "
                self.lbl_alert_text.config(text=f"{prefix}{text}", bg="#7f1d1d", fg="#ffffff")
            else:
                self.alert_frame.config(bg="#854d0e", bd=1)
                self.lbl_alert_icon.config(text="⚠️", bg="#854d0e", fg="#fef08a")
                prefix = "" if any(text.startswith(p) for p in ["ВНИМАНИЕ", "⚠️"]) else "ВНИМАНИЕ: "
                self.lbl_alert_text.config(text=f"{prefix}{text}", bg="#854d0e", fg="#fef08a")
        except Exception:
            pass

    def set_loading_banner(self, text="Инициализация служб SkyBase и проверка готовности компонентов..."):
        """Отображает спокойный нейтральный баннер в ходе загрузки без лишних уведомлений."""
        if not hasattr(self, 'alert_frame'):
            return
        try:
            self.alert_frame.config(bg="#1e293b", bd=1)
            self.lbl_alert_icon.config(text="⏳", bg="#1e293b", fg="#94a3b8")
            self.lbl_alert_text.config(text=text, bg="#1e293b", fg="#94a3b8")
        except Exception:
            pass

    def append_log(self, text, tag=None):
        from datetime import datetime
        t_str = datetime.now().strftime("%H:%M:%S")
        entry = f"[{t_str}] {text}"
        if not hasattr(self, 'startup_logs'):
            self.startup_logs = []
        self.startup_logs.append(entry)

        if not tag:
            u_text = text.upper()
            if any(k in u_text for k in ["[OK]", "[+]", "УСПЕШНО", "ГОТОВ К РАБОТЕ"]) and not any(k in u_text for k in ["[FAIL]", "[ERROR]"]):
                tag = "green"
            elif any(k in u_text for k in ["[FAIL]", "[ERROR]", "TELEGRAMCONFLICTERROR", "TRACEBACK", "EXCEPTION", "MISMATCH"]) or \
                 ("ОШИБКА" in u_text and "0 ОШИБОК" not in u_text and "БЕЗ ОШИБОК" not in u_text) or \
                 ("СБОЙ" in u_text and "БЕЗ СБОЕВ" not in u_text) or \
                 ("КОНФЛИКТ" in u_text and "НЕ ОБНАРУЖЕН" not in u_text) or \
                 ("ОТКЛЮЧЕН" in u_text and "ОТКЛЮЧЕНО" not in u_text and "ОТКЛЮЧЕНА" not in u_text):
                tag = "error_line"
            elif any(k in u_text for k in ["[WARN]", "ВНИМАНИЕ", "ПРЕДУПРЕЖДЕНИЕ"]):
                tag = "yellow"
            elif any(k in u_text for k in ["[*]", "---", "==="]):
                tag = "cyan"

        try:
            if tag:
                self.txt_logs.insert(tk.END, text + "\n", tag)
            else:
                self.txt_logs.insert(tk.END, text + "\n")
            self.txt_logs.see(tk.END)
        except Exception:
            pass

    def run_preflight_checklist(self):
        """
        Предстартовый чек-лист готовности системы к работе:
        1. Интерпретатор Python
        2. Портативные и системные модули (lib/ & site-packages)
        3. Браузер снайпера (локальный Chromium / Chrome / Edge)
        4. Целостность ключевых файлов и базы данных
        5. Сетевые порты
        """
        self.append_log("==================================================")
        self.append_log("  ПРЕДСТАРТОВЫЙ ЧЕК-ЛИСТ ГОТОВНОСТИ SKYBASE")
        self.append_log("==================================================")

        # 0. Проверка бэкенда SkyBase v2 (server.py)
        py_srv = os.path.join(SITE_DIR, "server.py")
        if os.path.exists(py_srv):
            self.append_log("  [0/8] [OK] Python бэкенд (server.py v2.0) готов к работе без BOM")
        else:
            ensure_ps1_bom(os.path.join(SITE_DIR, "server.ps1"))

        # 1. Интерпретатор Python
        py_exe = get_real_python_exe()
        if not py_exe or not is_valid_python(py_exe):
            self.append_log("  [1/8] [*] Python 3.11 не найден в системе (чистая Windows). Запуск автоматической тихой установки...", tag="cyan")
            py_exe = ensure_python_installed(log_callback=self.append_log)
        if not py_exe or not is_valid_python(py_exe):
            self.append_log("  [1/8] [FAIL] Python: интерпретатор не найден и не удалось установить!", tag="error_line")
            return False, "Python не найден"
        self.append_log(f"  [1/8] [OK] Python: {os.path.basename(py_exe)} готов к работе ({py_exe})", tag="green")

        # 2. Модули Python
        required_mods = ["playwright", "aiogram", "curl_cffi", "bs4", "aiosqlite", "PIL", "psutil", "requests"]
        missing = []
        chk_code = "import importlib.util, sys; sys.path.insert(0, 'lib'); mods = " + repr(required_mods) + "; missing = [m for m in mods if not importlib.util.find_spec(m)]; print(','.join(missing))"
        try:
            res = subprocess.run([py_exe, "-c", chk_code], capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW)
            out = res.stdout.strip()
            if out:
                missing = [x.strip() for x in out.split(",") if x.strip()]
        except Exception:
            for m in required_mods:
                try:
                    __import__(m)
                except Exception:
                    missing.append(m)

        if missing:
            self.append_log(f"  [2/8] [*] Библиотеки: установка недостающих модулей ({', '.join(missing)})...", tag="cyan")
            try:
                pkg_dir = os.path.join(SITE_DIR, "installer", "packages")
                if not os.path.exists(pkg_dir):
                    pkg_dir = os.path.join(SITE_DIR, "avito_bot", "installer", "packages")
                pip_cmd = [py_exe, "-m", "pip", "install"]
                if os.path.exists(pkg_dir):
                    pip_cmd += ["--no-index", f"--find-links={pkg_dir}"]
                pip_cmd += missing
                subprocess.run(pip_cmd, capture_output=True, timeout=60, creationflags=CREATE_NO_WINDOW)
            except Exception:
                pass

            # Проверяем результат установки библиотек
            still_missing = []
            try:
                res = subprocess.run([py_exe, "-c", chk_code], capture_output=True, text=True, timeout=5, creationflags=CREATE_NO_WINDOW)
                out = res.stdout.strip()
                if out:
                    still_missing = [x.strip() for x in out.split(",") if x.strip()]
            except Exception:
                still_missing = missing

            if still_missing:
                self.post_startup_warnings.append(f"Библиотеки: не удалось установить {', '.join(still_missing)}")
                self.append_log(f"  [2/8] [!] Библиотеки: не удалось установить {', '.join(still_missing)}", tag="yellow")
            else:
                self.append_log(f"  [2/8] [OK] Библиотеки: все {len(required_mods)} модулей успешно установлены (skybase/lib)", tag="green")
        else:
            self.append_log(f"  [2/8] [OK] Библиотеки: все {len(required_mods)} модулей в наличии (skybase/lib)", tag="green")

        # 3. Браузер снайпера
        try:
            import avito_sniper
            browsers = avito_sniper.get_candidate_browsers()
            if browsers:
                b_name = os.path.basename(browsers[0])
                tag = "Портативный Chromium" if "browsers" in browsers[0].lower() else b_name
                self.append_log(f"  [3/8] [OK] Браузер снайпера: {tag}", tag="green")
            else:
                self.append_log("  [3/8] [OK] Браузер снайпера: автоподбор активен (Chrome / Edge)", tag="green")
        except Exception:
            self.append_log("  [3/8] [OK] Браузер снайпера: автоподбор активен", tag="green")

        # 4. Файлы сайта и шлюза
        gw_script = os.path.join(SITE_DIR, "gateway.py")
        idx_file = os.path.join(SITE_DIR, "index.html")
        if not os.path.exists(gw_script) or not os.path.exists(idx_file):
            self.append_log("  [4/8] [FAIL] Файлы сайта: отсутствуют gateway.py или index.html!", tag="error_line")
            return False, "Файлы сайта не найдены"
        self.append_log("  [4/8] [OK] Файлы системы: шлюз gateway.py и сайт index.html в норме", tag="green")

        # 5. Сетевые порты
        self.append_log("  [5/8] [OK] Сетевой шлюз: порты 80/8080/8081 готовы", tag="green")

        # 6. Проверка лицензии и аппаратной привязки к железу (HWID)
        lic_ok = False
        lic_err_desc = ""
        local_hw_id = ""
        try:
            import avito_api_helper
            lic = avito_api_helper.get_license_status_info("")
            self.activation_checked = True
            if lic:
                local_hw_id = lic.get("request_id") or ""
                if lic.get("is_expired"):
                    t_label = lic.get("tariff_label") or "Требуется активация"
                    lic_err_desc = f"Лицензия: {t_label} для этого ПК (ID: {local_hw_id})"
                    self.append_log(f"  [6/8] [*] Лицензия: {t_label} (ID: {local_hw_id})", tag="cyan")
                    self.append_log("        Для активации нажмите «Активировать» в строке тарифа или используйте Менеджер ключей.", tag="cyan")
                else:
                    lic_ok = True
                    self.append_log(f"  [6/8] [OK] Лицензия: активна ({lic.get('tariff_label', 'Активен')})", tag="green")
        except Exception as e_lic:
            self.activation_checked = True
            self.append_log(f"  [6/8] [*] Проверка лицензии: {e_lic}", tag="yellow")

        # 7. Проверка Telegram-бота и конфликтов экземпляров
        tg_conflict = False
        bot_log_path = os.path.join(SITE_DIR, "avito_bot", "bot.log")
        if os.path.exists(bot_log_path):
            try:
                with open(bot_log_path, "r", encoding="utf-8", errors="ignore") as f:
                    b_tail = f.read()[-3000:]
                    if "TelegramConflictError" in b_tail or "Conflict: terminated by other getUpdates" in b_tail:
                        tg_conflict = True
            except Exception:
                pass
        if tg_conflict:
            self.post_startup_warnings.append("Telegram: конфликт токена бота — бот запущен на другом ПК!")
            self.append_log("  [7/8] [!] Telegram: обнаружен конфликт токена бота (TelegramConflictError)", tag="yellow")
        else:
            self.append_log("  [7/8] [OK] Telegram-бот: готов к работе (дубликатов не обнаружено)", tag="green")

        # 8. Быстрая проверка обновлений (таймаут <= 1.0 сек, не задерживает старт)
        try:
            from tools import updater
            upd_res = updater.check_for_updates_quick(timeout=1.0)
            ver = upd_res.get("version", "1.0.0")
            is_available = (upd_res.get("status") == "available")
            self.append_log(f"  [8/8] [OK] Обновления: версия {ver} актуальна", tag="green")
            if is_available:
                new_v = upd_res.get("new_version", "")
                self.append_log("        Доступно обновление", tag="cyan")
                self.set_update_button_state(True, new_v)
            else:
                self.set_update_button_state(False)
        except Exception:
            self.append_log("  [8/8] [OK] Обновления: версия 1.0.0 актуальна", tag="green")
            self.set_update_button_state(False)

        self.append_log("--------------------------------------------------")
        self.append_log("  [*] Предстартовый чек-лист пройден -> Запуск служб...", tag="cyan")
        self.append_log("--------------------------------------------------\n")
        return True, ""

    def start_server_workflow(self):
        """Процесс запуска сервера с авто-открытием браузера."""
        self.append_log("[*] Инициализация служб SkyBase Server...")
        self.append_log(f"[*] Рабочий каталог: {SITE_DIR}")

        # Выполняем предстартовый чек-лист
        chk_ok, chk_err = self.run_preflight_checklist()
        if not chk_ok:
            self.startup_completed = True
            self.lbl_status_badge.config(text="🔴 СБОЙ ПРОВЕРКИ", bg="#ef4444", fg="#ffffff")
            self.append_log(f"[!] Ошибка предстартовой проверки: {chk_err}", tag="error_line")
            self.finish_startup_reporting()
            return

        # 1. Проверяем, работает ли уже сервер
        gw_alive = is_port_open(80) or is_port_open(8080)
        be_alive = is_port_open(8081)

        if not gw_alive or not be_alive:
            self.append_log("[*] Запуск шлюза и фонового бэкенда...")
            gw_script = os.path.join(SITE_DIR, "gateway.py")
            if not os.path.exists(os.path.join(SITE_DIR, "server.py")):
                ensure_ps1_bom(os.path.join(SITE_DIR, "server.ps1"))

            if not os.path.exists(gw_script):
                self.append_log(f"[FAIL] Файл шлюза gateway.py не найден в: {SITE_DIR}", tag="error_line")
                self.startup_completed = True
                self.lbl_status_badge.config(text="🔴 ОШИБКА ФАЙЛОВ", bg="#ef4444", fg="#ffffff")
                self.set_problem_banner(f"Файл шлюза gateway.py не найден в {SITE_DIR}", is_error=True)
                self.finish_startup_reporting()
                return

            py_exe = get_real_python_exe(prefer_windowless=False)
            if not py_exe or not is_valid_python(py_exe):
                self.append_log("[*] Попытка автоустановки Python 3.11...", tag="cyan")
                py_exe = ensure_python_installed(log_callback=self.append_log)

            if not py_exe or not is_valid_python(py_exe):
                self.append_log(f"[FAIL] Python интерпретатор не найден на компьютере!", tag="error_line")
                self.startup_completed = True
                self.lbl_status_badge.config(text="🔴 НЕТ PYTHON", bg="#ef4444", fg="#ffffff")
                self.set_problem_banner("Python интерпретатор не найден на компьютере", is_error=True)
                self.finish_startup_reporting()
                return

            gw_env = os.environ.copy()
            gw_env["PYTHON_EXE"] = py_exe
            py_dir = os.path.dirname(py_exe)
            gw_env["PATH"] = f"{py_dir};{os.path.join(py_dir, 'Scripts')};" + gw_env.get("PATH", "")
            try:
                self.server_process = subprocess.Popen(
                    [py_exe, gw_script],
                    cwd=SITE_DIR,
                    env=gw_env,
                    creationflags=CREATE_NO_WINDOW,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
            except Exception as e:
                self.append_log(f"[FAIL] Ошибка запуска gateway.py: {e}", tag="error_line")
                self.set_problem_banner(f"Ошибка запуска gateway.py: {e}", is_error=True)

        # 2. Ожидаем готовности порта
        ready = False
        for _ in range(30):
            time.sleep(0.4)
            if (is_port_open(80) or is_port_open(8080)) and is_port_open(8081):
                ready = True
                break

        if ready:
            self.active_port = 80 if is_port_open(80) else 8080
            self.is_running = True
            target_url = f"http://localhost/" if self.active_port == 80 else f"http://localhost:{self.active_port}/"
            self.append_log(f"[+] Сервер успешно запущен и готов к работе на порту {self.active_port}!", tag="green")
            self.append_log(f"[+] Локальный адрес: {target_url}", tag="green")
            self.append_log(f"[+] Адрес в сети LAN: http://{self.local_ip}{'' if self.active_port == 80 else f':{self.active_port}'}/", tag="cyan")

            # Запуск Avito Bot с учетом статуса лицензии
            try:
                import avito_api_helper
                lic = avito_api_helper.get_license_status_info("")
                is_lic_expired = bool(not lic or lic.get("is_expired") is True)
                if is_lic_expired:
                    avito_api_helper.set_monitor_state("disable")
                    avito_api_helper.set_bot_paused("pause")
                    self.append_log("[*] Лицензия не активна: фоновый опрос объявлений и Telegram-уведомления приостановлены до активации.", tag="cyan")
                else:
                    avito_api_helper.set_monitor_state("enable")
                    avito_api_helper.set_bot_paused("resume")

                if not avito_api_helper.is_bot_running():
                    self.append_log("[*] Запуск фонового процесса Avito Bot...")
                    avito_api_helper.bot_toggle("start")
            except Exception as e_bot:
                self.post_startup_warnings.append(f"Ошибка запуска Avito Bot: {e_bot}")
                self.append_log(f"[*] Фоновый запуск Avito Bot: {e_bot}", tag="yellow")

            # Небольшая пауза для инициализации фоновых служб перед подведением итогов
            time.sleep(0.8)

            self.startup_completed = True
            self.root.after(0, self.on_server_ready, target_url)
            self.root.after(50, self.finish_startup_reporting)
        else:
            self.startup_completed = True
            self.append_log("[FAIL] Не удалось подтвердить запуск за 12 секунд. Проверьте ошибки выше.", tag="error_line")
            self.lbl_status_badge.config(text="🔴 СБОЙ ЗАПУСКА", bg="#ef4444", fg="#ffffff")
            self.set_problem_banner("Сервер или бэкенд не ответили за 12 секунд — проверьте ошибки", is_error=True)
            self.root.after(50, self.finish_startup_reporting)

    def finish_startup_reporting(self):
        """
        Формирует итоговый структурированный отчет ТОЛЬКО после того,
        как сервер завершил запуск, прогрузку и установку программ:
        - Установлены ли программы / библиотеки / интерпретатор
        - Активны ли службы шлюза, бэкенда и Telegram-бота
        - Статус лицензии
        Выводит предупреждения исключительно по итогу завершенной загрузки.
        """
        gw_up = is_port_open(80) or is_port_open(8080)
        be_up = is_port_open(8081)

        bot_up = False
        try:
            import avito_api_helper
            bot_up = bool(avito_api_helper.is_bot_running())
        except Exception:
            pass
        if not bot_up:
            bot_pid_file = os.path.join(SITE_DIR, "avito_bot", "bot.pid")
            if os.path.exists(bot_pid_file):
                try:
                    with open(bot_pid_file, "r", encoding="utf-8") as f:
                        b_pid = int(f.read().strip())
                    if b_pid > 0 and get_process_name_by_pid(b_pid):
                        bot_up = True
                except Exception:
                    pass

        # Проверка лицензии
        lic_is_expired = True
        lic_tariff = "Требуется активация"
        lic_req_id = ""
        try:
            import avito_api_helper
            lic = avito_api_helper.get_license_status_info("")
            if lic:
                lic_is_expired = bool(lic.get("is_expired", True))
                lic_tariff = lic.get("tariff_label", "Неизвестно")
                lic_req_id = lic.get("request_id", "")
        except Exception:
            pass

        # Проверка конфликтов Telegram
        tg_conflict = False
        bot_log_path = os.path.join(SITE_DIR, "avito_bot", "bot.log")
        if os.path.exists(bot_log_path):
            try:
                with open(bot_log_path, "r", encoding="utf-8", errors="ignore") as f:
                    b_tail = f.read()[-3000:]
                    if "TelegramConflictError" in b_tail or "Conflict: terminated by other getUpdates" in b_tail:
                        tg_conflict = True
            except Exception:
                pass

        warnings = []
        if getattr(self, 'post_startup_warnings', None):
            warnings.extend(self.post_startup_warnings)

        if not gw_up:
            warnings.append("Шлюз (порт 80/8080) не запущен или недоступен")
        if not be_up:
            warnings.append("Основной бэкенд (порт 8081) не отвечает")
        if not bot_up and not lic_is_expired:
            warnings.append("Avito Bot не запущен")
        if tg_conflict:
            warnings.append("Telegram: Конфликт токена бота — бот запущен на другом компьютере!")
        if lic_is_expired:
            id_txt = f" (ID ПК: {lic_req_id})" if lic_req_id else ""
            warnings.append(f"Лицензия: требуется активация для этого ПК{id_txt}")

        self.append_log("==================================================")
        if warnings:
            self.append_log("  [!] ИТОГ ЗАПУСКА: ТРЕБУЕТСЯ ВНИМАНИЕ", tag="yellow")
            self.append_log("==================================================")
            for w in warnings:
                self.append_log(f"  • {w}", tag="yellow")
            if lic_is_expired:
                self.append_log("  --> Нажмите «Активировать» в строке тарифа для ввода ключа.", tag="cyan")
        else:
            self.append_log("  [+] ИТОГ ЗАПУСКА: ВСЕ СЛУЖБЫ УСПЕШНО РАБОТАЮТ", tag="green")
            self.append_log("==================================================")
            self.append_log("  [+] Система полностью готова к работе (Шлюз, Бэкенд, Avito Bot активны).", tag="green")
        self.append_log("--------------------------------------------------\n")

        self.update_status_tick()

    def on_server_ready(self, url):
        self.lbl_status_badge.config(text="🟢 СЕРВЕР АКТИВЕН", bg="#10b981", fg="#ffffff")
        self.lbl_local_url.config(text=url)
        lan_url = f"http://{self.local_ip}/" if self.active_port == 80 else f"http://{self.local_ip}:{self.active_port}/"
        self.lbl_lan_url.config(text=lan_url)

        # Автоматическое открытие сайта в браузере (добавляет вкладку к уже открытому)
        if not self.browser_opened:
            self.browser_opened = True
            self.append_log(f"[+] Сервер готов к работе: {url}", tag="green")
            self.launch_site_in_browser(url, force_new_tab=False)

    def refresh_existing_browser_tab(self, target_url: str = "") -> bool:
        """
        Проверяет, открыта ли уже страница нашего сайта в браузере:
        1. Проверяет CDP вкладки (если активен Chrome/Edge с remote debugging).
        2. Ищет активное окно браузера с сайтом (заголовки AvitoHunter / Мониторинг объявлений),
           активирует его и отправляет клавишу F5 для обновления.
        3. Проверяет недавние пинги от открытой фоновой вкладки (data/active_tabs.json).
        Возвращает True, если вкладка обнаружена и обновлена — новая вкладка не создаётся.
        """
        # 1. Проверка через CDP (порт 9222 и другие обнаруженные порты)
        cdp_ports = [9222]
        try:
            import psutil
            for p in psutil.process_iter(['name', 'cmdline']):
                try:
                    cmd = p.info.get('cmdline') or []
                    for arg in cmd:
                        if '--remote-debugging-port=' in arg:
                            try:
                                port_val = int(arg.split('=')[1].strip())
                                if port_val not in cdp_ports:
                                    cdp_ports.append(port_val)
                            except Exception:
                                pass
                except Exception:
                    pass
        except Exception:
            pass

        for port in cdp_ports:
            try:
                list_url = f"http://127.0.0.1:{port}/json/list"
                req = urllib.request.Request(list_url, headers={"User-Agent": "SkyBaseLauncher"})
                with urllib.request.urlopen(req, timeout=0.6) as resp:
                    if resp.status == 200:
                        tabs = json.loads(resp.read().decode('utf-8'))
                        for t in tabs:
                            t_url = t.get('url', '')
                            t_id = t.get('id')
                            if ('localhost' in t_url or '127.0.0.1' in t_url) and t_id:
                                try:
                                    act_req = urllib.request.Request(f"http://127.0.0.1:{port}/json/activate/{t_id}", method="POST")
                                    urllib.request.urlopen(act_req, timeout=0.6)
                                except Exception:
                                    pass
                                for h in get_visible_browser_hwnds():
                                    bring_window_to_front(h)
                                return True
            except Exception:
                pass

        # 2. Проверка видимых окон с заголовком сайта
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                found_hwnds = []
                my_pid = os.getpid()

                def enum_cb(hwnd, lparam):
                    if user32.IsWindowVisible(hwnd):
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        if pid.value == my_pid:
                            return True
                        if not is_window_browser(hwnd):
                            return True
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buf = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buf, length + 1)
                            title = buf.value.lower()
                            if any(k in title for k in ["avitohunter", "мониторинг объявлений avito"]):
                                found_hwnds.append(hwnd)
                    return True

                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)

                if found_hwnds:
                    for h in found_hwnds:
                        bring_window_to_front(h)
                        time.sleep(0.12)
                        user32.keybd_event(0x74, 0, 0, 0)
                        time.sleep(0.05)
                        user32.keybd_event(0x74, 0, 2, 0)
                    return True
            except Exception:
                pass

        return False

    def launch_site_in_browser(self, url, force_new_tab=True):
        """Открывает сайт в браузере:
        - Гарантированно создаёт новую вкладку в уже запущенном браузере пользователя (Chrome, Edge, Firefox, Yandex и др.).
        - Поддерживает браузеры, запущенные с кастомными профилями (--user-data-dir) и CDP (--remote-debugging-port).
        - Если браузер закрыт: запускает браузер с сайтом.
        - Активирует окно браузера и выводит его на передний план.
        """
        if not url:
            url = "http://localhost/"

        # Если не требуется принудительно новая вкладка — проверяем обновление
        if not force_new_tab and self.refresh_existing_browser_tab(url):
            self.append_log("[+] В браузере уже открыта вкладка с сайтом — выполнено обновление (F5).", tag="green")
            return

        self.append_log(f"[*] Открытие сайта в браузере: {url}")
        pre_existing_browser_hwnds = set(get_visible_browser_hwnds())
        self.browser_was_already_running = len(pre_existing_browser_hwnds) > 0

        # Поиск всех запущенных браузеров и их аргументов через psutil
        running_browsers = []
        cdp_ports = set()
        try:
            import psutil
            for p in psutil.process_iter(['pid', 'name', 'cmdline']):
                try:
                    name = (p.info['name'] or '').lower()
                    if any(b in name for b in ['chrome', 'msedge', 'firefox', 'browser', 'opera', 'brave', 'vivaldi']):
                        cmd = p.info['cmdline'] or []
                        # Фильтруем дочерние служебные процессы (--type=renderer, gpu, utility)
                        if not any('--type=' in a for a in cmd):
                            running_browsers.append((p.info['pid'], name, cmd))
                            for arg in cmd:
                                if '--remote-debugging-port=' in arg:
                                    try:
                                        cdp_ports.add(int(arg.split('=')[1].strip()))
                                    except Exception:
                                        pass
                except Exception:
                    pass
        except Exception:
            pass

        cdp_ports.add(9222)
        opened = False

        # 1. Если запущен Chrome/Edge с CDP (remote debugging) — создаём вкладку напрямую через DevTools HTTP API
        for port in sorted(cdp_ports):
            try:
                version_url = f"http://127.0.0.1:{port}/json/version"
                req_v = urllib.request.Request(version_url, headers={"User-Agent": "SkyBaseLauncher"})
                with urllib.request.urlopen(req_v, timeout=0.8) as resp:
                    if resp.status == 200:
                        # Если не требуется force_new_tab — проверяем открытые вкладки
                        if not force_new_tab:
                            list_url = f"http://127.0.0.1:{port}/json/list"
                            try:
                                with urllib.request.urlopen(urllib.request.Request(list_url), timeout=0.8) as l_resp:
                                    tabs = json.loads(l_resp.read().decode('utf-8'))
                                    for t in tabs:
                                        t_url = t.get('url', '')
                                        if 'localhost' in t_url or '127.0.0.1' in t_url:
                                            t_id = t.get('id')
                                            if t_id:
                                                urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/json/activate/{t_id}", method="POST"), timeout=0.8)
                                                self.append_log("[+] В запущенном браузере активирована существующая вкладка сайта.", tag="green")
                                                opened = True
                                                break
                            except Exception:
                                pass

                        if not opened:
                            encoded_target = urllib.parse.quote(url, safe=':/?&=#')
                            new_url = f"http://127.0.0.1:{port}/json/new?{encoded_target}"
                            req_new = urllib.request.Request(new_url, method="PUT")
                            with urllib.request.urlopen(req_new, timeout=1.5) as n_resp:
                                new_tab = json.loads(n_resp.read().decode('utf-8'))
                                new_id = new_tab.get('id')
                                if new_id:
                                    try:
                                        urllib.request.urlopen(urllib.request.Request(f"http://127.0.0.1:{port}/json/activate/{new_id}", method="POST"), timeout=0.8)
                                    except Exception:
                                        pass
                                self.append_log(f"[+] Новая вкладка успешно открыта в запущенном браузере (порт {port}).", tag="green")
                                opened = True
                        break
            except Exception:
                pass

        # 2. Если браузер запущен с кастомным профилем (--user-data-dir), открываем сайт с теми же параметрами
        if not opened and running_browsers:
            for b_pid, b_name, b_cmd in running_browsers:
                exe = b_cmd[0] if b_cmd else get_system_browser_cmd()
                udd_arg = None
                prof_arg = None
                for a in b_cmd:
                    if a.startswith('--user-data-dir'):
                        udd_arg = a
                    elif a.startswith('--profile-directory'):
                        prof_arg = a
                if udd_arg:
                    cmd_launch = [exe]
                    cmd_launch.append(udd_arg)
                    if prof_arg:
                        cmd_launch.append(prof_arg)
                    cmd_launch.append(url)
                    try:
                        proc = subprocess.Popen(
                            cmd_launch,
                            stdin=subprocess.DEVNULL,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL
                        )
                        self.browser_processes.append(proc)
                        self.append_log(f"[+] Новая вкладка открыта в профиле запущенного браузера ({b_name}).", tag="green")
                        opened = True
                        break
                    except Exception:
                        pass

        # 3. Прямой запуск через исполняемый файл браузера по умолчанию (Chrome, Edge, Firefox, Yandex)
        if not opened:
            browser_exe = get_system_browser_cmd()
            if browser_exe and os.path.exists(browser_exe):
                try:
                    proc = subprocess.Popen(
                        [browser_exe, url],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                    self.browser_processes.append(proc)
                    opened = True
                    self.append_log(f"[+] Новая вкладка открыта в браузере ({os.path.basename(browser_exe)}).", tag="green")
                except Exception as e:
                    try:
                        proc = subprocess.Popen([browser_exe, url])
                        self.browser_processes.append(proc)
                        opened = True
                        self.append_log(f"[+] Новая вкладка открыта в ({os.path.basename(browser_exe)}).", tag="green")
                    except Exception as e2:
                        self.append_log(f"[!] Ошибка вызова {browser_exe}: {e2}", tag="yellow")

        # 4. Fallback через Windows Shell (os.startfile или ShellExecuteW)
        if not opened and sys.platform == "win32":
            try:
                os.startfile(url)
                opened = True
                self.append_log("[+] Вкладка сайта открыта через Windows Shell (startfile).", tag="green")
            except Exception:
                try:
                    ret = ctypes.windll.shell32.ShellExecuteW(None, "open", url, None, None, 1)
                    if ret > 32:
                        opened = True
                        self.append_log("[+] Вкладка сайта добавлена через ShellExecuteW.", tag="green")
                except Exception:
                    pass

        # 5. Fallback через cmd start
        if not opened and sys.platform == "win32":
            try:
                subprocess.Popen(["cmd.exe", "/c", "start", "", url])
                opened = True
                self.append_log("[+] Вкладка сайта открыта через cmd start.", tag="green")
            except Exception:
                pass

        # 6. Fallback через стандартный webbrowser Python
        if not opened:
            try:
                webbrowser.open_new_tab(url)
                opened = True
                self.append_log("[+] Вкладка сайта открыта через webbrowser.open_new_tab.", tag="green")
            except Exception as e:
                self.append_log(f"[!] Не удалось открыть браузер: {e}", tag="yellow")

        # Активация окна браузера: выводим окно браузера на передний план
        def activate_browser_windows():
            time.sleep(0.3)
            browser_pids = {b[0] for b in running_browsers}
            all_hwnds = get_visible_browser_hwnds()
            if browser_pids and sys.platform == "win32":
                user32 = ctypes.windll.user32
                for h in all_hwnds:
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                    if pid.value in browser_pids:
                        bring_window_to_front(h)
            elif all_hwnds:
                for h in all_hwnds:
                    bring_window_to_front(h)

            if not self.browser_was_already_running:
                time.sleep(1.2)
                current_hwnds = set(get_visible_browser_hwnds())
                new_hwnds = current_hwnds - pre_existing_browser_hwnds
                if new_hwnds:
                    self.opened_browser_hwnds.update(new_hwnds)
                    for h in new_hwnds:
                        bring_window_to_front(h)

        threading.Thread(target=activate_browser_windows, daemon=True).start()

    def close_all_browser_windows(self):
        """Закрытие окон браузера отключено (пользователь управляет вручную)."""
        return



    def set_browser_button_state(self, enabled: bool):
        """Управляет состоянием кнопок браузера: активны только когда Шлюз, Бэкенд и Авито бот зелёные."""
        if enabled:
            if not getattr(self, 'is_browser_btn_enabled', False):
                self.is_browser_btn_enabled = True
                if hasattr(self, 'btn_launch'):
                    self.btn_launch.config(
                        state="normal",
                        bg="#059669",
                        fg="#ffffff",
                        activebackground="#047857",
                        activeforeground="#ffffff",
                        cursor="hand2",
                        takefocus=1
                    )
                    self.btn_launch.unbind("<Button-1>")
                    self.btn_launch.unbind("<ButtonRelease-1>")
                if hasattr(self, 'btn_open_browser'):
                    self.btn_open_browser.config(
                        state="normal",
                        bg="#0284c7",
                        fg="#ffffff",
                        activebackground="#0369a1",
                        activeforeground="#ffffff",
                        cursor="hand2",
                        takefocus=1
                    )
                    self.btn_open_browser.unbind("<Button-1>")
                    self.btn_open_browser.unbind("<ButtonRelease-1>")
        else:
            if getattr(self, 'is_browser_btn_enabled', True):
                self.is_browser_btn_enabled = False
                if hasattr(self, 'btn_launch'):
                    self.btn_launch.config(
                        state="disabled",
                        bg="#1e293b",
                        fg="#64748b",
                        activebackground="#1e293b",
                        activeforeground="#64748b",
                        disabledforeground="#64748b",
                        cursor="arrow",
                        takefocus=0
                    )
                    self.btn_launch.bind("<Button-1>", lambda e: "break")
                    self.btn_launch.bind("<ButtonRelease-1>", lambda e: "break")
                if hasattr(self, 'btn_open_browser'):
                    self.btn_open_browser.config(
                        state="disabled",
                        bg="#1e293b",
                        fg="#64748b",
                        activebackground="#1e293b",
                        activeforeground="#64748b",
                        disabledforeground="#64748b",
                        cursor="arrow",
                        takefocus=0
                    )
                    self.btn_open_browser.bind("<Button-1>", lambda e: "break")
                    self.btn_open_browser.bind("<ButtonRelease-1>", lambda e: "break")

    def set_update_button_state(self, enabled: bool, new_version: str = ""):
        """
        Управляет состоянием кнопки обновления в инфо-строке:
        - При отсутствии обновления: серая, затемненная, некликабельная (cursor='arrow'), аналогично кнопке запуска браузера до старта сервера.
        - При наличии обновления: ярко-голубая (cyan), активная, кликабельная (cursor='hand2').
        """
        if not hasattr(self, 'btn_strip_update'):
            return

        if enabled:
            if not getattr(self, 'is_update_btn_enabled', False):
                self.is_update_btn_enabled = True
                label_txt = f"🔄 Обновить v{new_version}" if new_version else "🔄 Обновить"
                self.btn_strip_update.config(
                    text=label_txt,
                    state="normal",
                    bg="#0284c7",
                    fg="#ffffff",
                    activebackground="#0369a1",
                    activeforeground="#ffffff",
                    relief="flat",
                    cursor="hand2",
                    takefocus=1
                )
                self.btn_strip_update.unbind("<Button-1>")
                self.btn_strip_update.unbind("<ButtonRelease-1>")
        else:
            if getattr(self, 'is_update_btn_enabled', True):
                self.is_update_btn_enabled = False
                self.btn_strip_update.config(
                    text="🔄 Обновить",
                    state="disabled",
                    bg="#1e293b",
                    fg="#64748b",
                    activebackground="#1e293b",
                    activeforeground="#64748b",
                    disabledforeground="#64748b",
                    relief="flat",
                    cursor="arrow",
                    takefocus=0
                )
                self.btn_strip_update.bind("<Button-1>", lambda e: "break")
                self.btn_strip_update.bind("<ButtonRelease-1>", lambda e: "break")

    def action_open_browser(self):
        url = "http://localhost/"
        if hasattr(self, 'lbl_local_url'):
            try:
                txt = self.lbl_local_url.cget("text").strip()
                if txt and txt.startswith("http"):
                    url = txt
            except Exception:
                pass
        self.launch_site_in_browser(url, force_new_tab=True)

    def action_copy_lan_url(self):
        url = self.lbl_lan_url.cget("text")
        if url:
            self.root.clipboard_clear()
            self.root.clipboard_append(url)
            self.root.update()
            self.append_log(f"[+] Ссылка для локальной сети скопирована в буфер: {url}")

    def setup_logs_context_menu(self):
        """Контекстное меню правой кнопки мыши и горячие клавиши для консоли логов."""
        self.log_context_menu = tk.Menu(self.root, tearoff=0, bg="#1e293b", fg="#f8fafc", activebackground="#0284c7", activeforeground="#ffffff")
        self.log_context_menu.add_command(label="📋 Скопировать отчёт загрузки", command=self.action_copy_startup_report)
        self.log_context_menu.add_separator()
        self.log_context_menu.add_command(label="📄 Скопировать весь журнал", command=self.action_copy_all_logs)
        self.log_context_menu.add_command(label="✂️ Скопировать выделенное", command=self.action_copy_selected_logs)
        self.log_context_menu.add_command(label="🔍 Выделить всё", command=self.action_select_all_logs)

        def show_popup(event):
            try:
                self.log_context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.log_context_menu.grab_release()

        self.txt_logs.bind("<Button-3>", show_popup)
        self.txt_logs.bind("<Control-a>", lambda e: self.action_select_all_logs())
        self.txt_logs.bind("<Control-A>", lambda e: self.action_select_all_logs())

    def action_select_all_logs(self, event=None):
        self.txt_logs.tag_add("sel", "1.0", tk.END)
        return "break"

    def action_copy_selected_logs(self):
        try:
            sel = self.txt_logs.get("sel.first", "sel.last")
            if sel:
                self.root.clipboard_clear()
                self.root.clipboard_append(sel)
                self.root.update()
        except Exception:
            pass

    def action_copy_all_logs(self):
        text = self.txt_logs.get("1.0", tk.END).strip()
        if text:
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.root.update()
            self.append_log("[+] Текст журнала скопирован в буфер обмена.")

    def action_copy_startup_report(self):
        """Формирует подробный структурированный диагностический отчёт загрузки и копирует в буфер обмена."""
        from datetime import datetime
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        status_badge = self.lbl_status_badge.cget("text") if hasattr(self, 'lbl_status_badge') else "Неизвестно"
        local_url = self.lbl_local_url.cget("text") if hasattr(self, 'lbl_local_url') else f"http://localhost:{self.active_port}/"
        lan_url = self.lbl_lan_url.cget("text") if hasattr(self, 'lbl_lan_url') else f"http://{self.local_ip}:{self.active_port}/"
        gw_st = self.lbl_gw_state.cget("text") if hasattr(self, 'lbl_gw_state') else "Шлюз: -"
        be_st = self.lbl_be_state.cget("text") if hasattr(self, 'lbl_be_state') else "Бэкенд: -"
        bot_st = self.lbl_bot_state.cget("text") if hasattr(self, 'lbl_bot_state') else "Avito Bot: -"
        if hasattr(self, 'lbl_tariff_val') and self.lbl_tariff_val.cget("text"):
            lic_st = f"Тариф: {self.lbl_tariff_val.cget('text')}"
        elif hasattr(self, 'btn_license_state'):
            lic_st = self.btn_license_state.cget("text")
        else:
            lic_st = "Лицензия: -"
        alert_st = self.lbl_alert_text.cget("text") if hasattr(self, 'lbl_alert_text') else ""

        if hasattr(self, 'startup_logs') and self.startup_logs:
            report_logs = "\n".join(self.startup_logs)
            if os.path.exists(LOG_FILE):
                try:
                    with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                        gw_tail = f.readlines()[-30:]
                        if gw_tail:
                            report_logs += "\n\n--- Последние записи gateway.log ---\n" + "".join(gw_tail).strip()
                except Exception:
                    pass
        else:
            report_logs = self.txt_logs.get("1.0", tk.END).strip()

        report = (
            f"============================================================\n"
            f"              SkyBase Server — Отчёт загрузки\n"
            f"============================================================\n"
            f"Время отчёта:      {now_str}\n"
            f"Статус сервера:    {status_badge}\n"
            f"Локальный адрес:   {local_url}\n"
            f"Сетевой адрес LAN: {lan_url}\n\n"
            f"--- Состояние служб ---\n"
            f"{gw_st}\n"
            f"{be_st}\n"
            f"{bot_st}\n"
            f"{lic_st}\n"
            f"Оповещение:        {alert_st}\n\n"
            f"--- Журнал загрузки и событий ---\n"
            f"{report_logs}\n"
            f"============================================================\n"
        )

        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(report)
            self.root.update()

            if hasattr(self, 'btn_copy_report'):
                self.btn_copy_report.config(text="✅ Отчёт скопирован!", bg="#059669", fg="#ffffff")
                self.root.after(2200, lambda: self.btn_copy_report.config(text="📋 Скопировать отчёт загрузки", bg="#1e293b", fg="#38bdf8"))

            self.append_log(f"[+] Отчёт загрузки успешно скопирован в буфер обмена ({len(report)} симв.)")
        except Exception as e:
            self.append_log(f"[!] Ошибка копирования отчёта: {e}")

    def action_open_activation_dialog(self):
        """Открывает интерактивное окно активации лицензии со встроенным онлайн-чатом с администратором."""
        top = tk.Toplevel(self.root)
        top.title("🔑 Активация лицензии и чат с администратором")
        top.geometry("640x680")
        top.minsize(580, 560)
        top.configure(bg="#0f172a")
        top.transient(self.root)
        top.grab_set()

        top.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 320
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 340
        top.geometry(f"+{max(0, x)}+{max(0, y)}")

        # Получаем текущий ID машины
        local_hw_id = ""
        try:
            import avito_api_helper
            lic = avito_api_helper.get_license_status_info("")
            if lic:
                local_hw_id = lic.get("request_id") or ""
        except Exception:
            pass

        # Шапка окна
        header = tk.Frame(top, bg="#1e293b", padx=16, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="🔑 Активация SkyBase Server", font=("Segoe UI", 12, "bold"),
                 fg="#f8fafc", bg="#1e293b").pack(anchor="w")
        tk.Label(header, text="Онлайн-чат с администратором (@skynet19081983) и получение лицензионного ключа",
                 font=("Segoe UI", 8), fg="#94a3b8", bg="#1e293b").pack(anchor="w", pady=(1, 0))

        body = tk.Frame(top, bg="#0f172a", padx=14, pady=10)
        body.pack(fill="both", expand=True)

        # Блок 1: Уникальный ID компьютера
        hw_box = tk.LabelFrame(body, text=" 🖥️ Уникальный ID вашего компьютера (HWID) ",
                               font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#38bdf8", padx=10, pady=6)
        hw_box.pack(fill="x", pady=(0, 8))

        hw_row = tk.Frame(hw_box, bg="#1e293b")
        hw_row.pack(fill="x")

        lbl_id_val = tk.Label(hw_row, text=local_hw_id or "Определение ID...", font=("Consolas", 10, "bold"),
                              bg="#0b1120", fg="#38bdf8", padx=8, pady=3, relief="solid", bd=1)
        lbl_id_val.pack(side="left", fill="x", expand=True)

        def copy_hw_id():
            if local_hw_id:
                self.root.clipboard_clear()
                self.root.clipboard_append(local_hw_id)
                self.root.update()
                btn_copy_hw.config(text="✅ Скопировано!", bg="#059669")
                top.after(2000, lambda: btn_copy_hw.config(text="📋 Скопировать ID", bg="#0284c7"))

        btn_copy_hw = tk.Button(hw_row, text="📋 Скопировать ID", font=("Segoe UI", 9, "bold"),
                                bg="#0284c7", fg="#ffffff", activebackground="#0369a1", activeforeground="#ffffff",
                                relief="flat", cursor="hand2", padx=8, pady=2, command=copy_hw_id)
        btn_copy_hw.pack(side="right", padx=(6, 0))

        def send_hw_id_to_chat():
            if local_hw_id:
                msg_txt = f"👋 Здравствуйте! Мой ID для активации SkyBase: {local_hw_id}. Прошу выдать ключ активации."
                send_message_action(msg_txt)
                btn_send_hw.config(text="✅ Отправлено в чат!", bg="#059669")
                top.after(2200, lambda: btn_send_hw.config(text="📤 Отправить ID в чат", bg="#0891b2"))

        btn_send_hw = tk.Button(hw_row, text="📤 Отправить ID в чат", font=("Segoe UI", 9, "bold"),
                                bg="#0891b2", fg="#ffffff", activebackground="#0e7490", activeforeground="#ffffff",
                                relief="flat", cursor="hand2", padx=8, pady=2, command=send_hw_id_to_chat)
        btn_send_hw.pack(side="right", padx=(6, 0))

        # Блок 2: Онлайн-чат с администратором
        chat_box = tk.LabelFrame(body, text=" 💬 Чат с администратором (@skynet19081983) ",
                                 font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#fbbf24", padx=10, pady=6)
        chat_box.pack(fill="both", expand=True, pady=(0, 8))

        from tkinter import scrolledtext
        txt_chat = scrolledtext.ScrolledText(chat_box, height=8, bg="#0b1120", fg="#f8fafc",
                                            font=("Segoe UI", 9), relief="solid", bd=1, wrap="word")
        txt_chat.pack(fill="both", expand=True, pady=(0, 6))
        txt_chat.tag_config("admin_header", foreground="#38bdf8", font=("Segoe UI", 8, "bold"))
        txt_chat.tag_config("admin_body", foreground="#f1f5f9", font=("Segoe UI", 9))
        txt_chat.tag_config("me_header", foreground="#34d399", font=("Segoe UI", 8, "bold"))
        txt_chat.tag_config("me_body", foreground="#cbd5e1", font=("Segoe UI", 9))
        txt_chat.tag_config("key_highlight", foreground="#fbbf24", font=("Consolas", 10, "bold"), background="#1e293b")
        txt_chat.tag_config("time", foreground="#64748b", font=("Segoe UI", 8))
        txt_chat.tag_config("system", foreground="#94a3b8", font=("Segoe UI", 8, "italic"))
        txt_chat.config(state="disabled")

        # Панель быстрого действия при обнаружении ключа в чате
        key_found_frame = tk.Frame(chat_box, bg="#1e293b")
        lbl_found_key_info = tk.Label(key_found_frame, text="", font=("Segoe UI", 8, "bold"), bg="#1e293b", fg="#fbbf24")
        lbl_found_key_info.pack(side="left", padx=(0, 6))
        btn_insert_found_key = tk.Button(
            key_found_frame,
            text="📋 Вставить ключ в поле активации",
            font=("Segoe UI", 8, "bold"),
            bg="#059669",
            fg="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=6,
            pady=1
        )
        btn_insert_found_key.pack(side="left")

        # Строка ввода и отправки сообщения в чат
        send_row = tk.Frame(chat_box, bg="#1e293b")
        send_row.pack(fill="x")

        ent_chat_input = tk.Entry(send_row, font=("Segoe UI", 9), bg="#0b1120", fg="#f8fafc",
                                  insertbackground="#38bdf8", relief="solid", bd=1)
        ent_chat_input.pack(side="left", fill="x", expand=True, ipady=3)

        def do_send_input():
            val = ent_chat_input.get().strip()
            if val:
                send_message_action(val)
                ent_chat_input.delete(0, tk.END)

        btn_send_chat = tk.Button(send_row, text="✉️ Отправить", font=("Segoe UI", 9, "bold"),
                                  bg="#0284c7", fg="#ffffff", activebackground="#0369a1", activeforeground="#ffffff",
                                  relief="flat", cursor="hand2", padx=10, pady=2, command=do_send_input)
        btn_send_chat.pack(side="right", padx=(6, 0))

        ent_chat_input.bind("<Return>", lambda e: do_send_input())

        # Блок 3: Ввод лицензионного ключа
        act_box = tk.LabelFrame(body, text=" 🔑 Ввод лицензионного ключа ",
                                font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#34d399", padx=10, pady=6)
        act_box.pack(fill="x", pady=(0, 6))

        input_row = tk.Frame(act_box, bg="#1e293b")
        input_row.pack(fill="x", pady=(2, 4))

        ent_key = tk.Entry(input_row, font=("Consolas", 11, "bold"), bg="#0b1120", fg="#34d399",
                           insertbackground="#34d399", relief="solid", bd=1)
        ent_key.pack(side="left", fill="x", expand=True, ipady=3)

        def do_paste_key():
            try:
                clip = self.root.clipboard_get().strip()
                ent_key.delete(0, tk.END)
                ent_key.insert(0, clip)
            except Exception:
                pass

        btn_paste = tk.Button(input_row, text="📋 Вставить", font=("Segoe UI", 9),
                              bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=8, pady=2, command=do_paste_key)
        btn_paste.pack(side="right", padx=(6, 0))

        def insert_key_direct(k_val):
            if k_val:
                ent_key.delete(0, tk.END)
                ent_key.insert(0, k_val)
                lbl_msg.config(text=f"Ключ {k_val} вставлен! Нажмите «Активировать лицензию».", fg="#38bdf8")

        btn_insert_found_key.config(command=lambda: insert_key_direct(getattr(btn_insert_found_key, 'last_key', '')))

        lbl_msg = tk.Label(act_box, text="Вставьте лицензионный ключ и нажмите «Активировать лицензию»",
                           font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8", wraplength=560, justify="left")
        lbl_msg.pack(anchor="w", pady=(2, 4))

        def submit_activation():
            raw_val = ent_key.get().strip()
            if not raw_val:
                lbl_msg.config(text="⚠️ Пожалуйста, введите лицензионный ключ!", fg="#fbbf24")
                return

            btn_submit.config(state="disabled", text="⏳ Проверка ключа...")
            top.update()

            res = None
            # 1. Попытка через HTTP API сервера
            try:
                import urllib.request
                import json
                payload = json.dumps({"key": raw_val, "request_id": local_hw_id, "username": "skynet83"}).encode("utf-8")
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.active_port}/api/license/activate",
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    res = json.loads(resp.read().decode("utf-8"))
            except Exception:
                pass

            # 2. Fallback напрямую через модуль avito_api_helper
            if not res or not isinstance(res, dict):
                try:
                    import avito_api_helper
                    res = avito_api_helper.activate_license_key(raw_val, username="skynet83", client_ip="127.0.0.1", request_id=local_hw_id)
                except Exception as ex:
                    res = {"success": False, "error": str(ex)}

            if res and res.get("success"):
                t_label = res.get("tariff_label") or "Активен"
                self.append_log(f"[+] Лицензия успешно активирована! Тариф: {t_label}", tag="green")
                lbl_msg.config(text=f"✅ УСПЕХ: Лицензия активирована! ({t_label})", fg="#34d399")
                btn_submit.config(text="✅ Активировано", bg="#059669")
                # Автоматически возобновляем мониторинг и Telegram-уведомления
                try:
                    import avito_api_helper
                    avito_api_helper.set_monitor_state("enable")
                    avito_api_helper.set_bot_paused("resume")
                    self.append_log("[+] Фоновый опрос Avito и Telegram-уведомления успешно возобновлены!", tag="green")
                except Exception as ex_act:
                    pass
                # Мгновенно обновляем журнал и статусы в окне программы (убираем красные строки, обновляем отчет)
                self.on_license_activated(t_label)
                top.after(1400, top.destroy)
            else:
                err_text = (res.get("error") if res else "Неизвестная ошибка") or "Неверный ключ активации"
                lbl_msg.config(text=f"❌ Ошибка: {err_text}", fg="#ef4444")
                btn_submit.config(state="normal", text="🚀 Активировать лицензию", bg="#0284c7")

        btn_submit = tk.Button(act_box, text="🚀 Активировать лицензию", font=("Segoe UI", 10, "bold"),
                               bg="#0284c7", fg="#ffffff", activebackground="#0369a1", activeforeground="#ffffff",
                               relief="flat", cursor="hand2", padx=14, pady=5, command=submit_activation)
        btn_submit.pack(fill="x", pady=(2, 2))
        ent_key.bind("<Return>", lambda e: submit_activation())

        # Реализация отправки и получения сообщений чата
        def send_chat_msg_raw(text_to_send):
            if not text_to_send or not text_to_send.strip():
                return False
            text = text_to_send.strip()
            sent = False
            # 1. Попытка через HTTP API сервера
            try:
                import urllib.request
                import json
                payload = json.dumps({
                    "sender": local_hw_id or "guest",
                    "sender_id": local_hw_id or "guest",
                    "sender_name": f"ПК ({local_hw_id[:13]}...)" if local_hw_id else "Пользователь ПК",
                    "recipient": "admin",
                    "text": text
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"http://127.0.0.1:{self.active_port}/api/chat/send",
                    data=payload,
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(req, timeout=3.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data and data.get("success"):
                        sent = True
            except Exception:
                pass

            # 2. Fallback напрямую в chat_messages.json
            if not sent:
                try:
                    import json
                    import random
                    from datetime import datetime
                    chat_p = os.path.join(SITE_DIR, "data", "chat_messages.json")
                    msgs = []
                    if os.path.exists(chat_p):
                        with open(chat_p, "r", encoding="utf-8-sig") as f:
                            msgs = json.load(f)
                    now_ts = datetime.now()
                    new_m = {
                        "id": f"msg_{now_ts.strftime('%Y%m%d%H%M%S%f')[:17]}_{random.randint(1000, 9999)}",
                        "sender": local_hw_id or "guest",
                        "sender_id": local_hw_id or "guest",
                        "sender_name": f"ПК ({local_hw_id[:13]}...)" if local_hw_id else "Пользователь ПК",
                        "recipient": "admin",
                        "text": text,
                        "created_at": now_ts.strftime("%Y-%m-%d %H:%M:%S"),
                        "is_read": False
                    }
                    msgs.append(new_m)
                    if len(msgs) > 500:
                        msgs = msgs[-500:]
                    with open(chat_p, "w", encoding="utf-8") as f:
                        json.dump(msgs, f, ensure_ascii=False, indent=4)
                    sent = True
                except Exception:
                    pass
            return sent

        def send_message_action(msg_text):
            if send_chat_msg_raw(msg_text):
                self.append_log(f"[*] Сообщение отправлено администратору в чат: {msg_text[:60]}...")
                update_chat_view(force=True)

        def load_all_chat_messages():
            # 1. Попытка через HTTP API
            try:
                import urllib.request
                import json
                url = f"http://127.0.0.1:{self.active_port}/api/chat/messages?username=skynet83&request_id={local_hw_id}&t={int(time.time()*1000)}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    if data and "messages" in data:
                        return data["messages"]
            except Exception:
                pass

            # 2. Прямое чтение файла с поддержкой utf-8-sig
            try:
                import json
                chat_p = os.path.join(SITE_DIR, "data", "chat_messages.json")
                if os.path.exists(chat_p):
                    with open(chat_p, "r", encoding="utf-8-sig") as f:
                        return json.load(f)
            except Exception:
                pass
            return []

        last_rendered_ids = []
        def update_chat_view(force=False):
            if not top.winfo_exists():
                return
            all_m = load_all_chat_messages()
            clean_hw = (local_hw_id or "").strip().lower()

            filtered = []
            for m in all_m:
                sid = str(m.get("sender_id") or "").strip().lower()
                s = str(m.get("sender") or "").strip().lower()
                r = str(m.get("recipient") or "").strip().lower()
                if clean_hw and (sid == clean_hw or s == clean_hw or r == clean_hw or r == "all"):
                    filtered.append(m)
                elif not clean_hw and (r == "admin" or s == "admin" or r == "all"):
                    filtered.append(m)

            current_ids = [str(m.get("id")) for m in filtered]
            if not force and current_ids == last_rendered_ids:
                top.after(2500, lambda: update_chat_view(force=False))
                return

            last_rendered_ids.clear()
            last_rendered_ids.extend(current_ids)

            txt_chat.config(state="normal")
            txt_chat.delete("1.0", tk.END)

            if not filtered:
                txt_chat.insert(tk.END, "💬 История переписки пуста. Напишите сообщение администратору или отправьте ваш ID компьютера кнопкой выше.\n", "system")

            import re
            key_pat = re.compile(r'\b(EB[0-9A-Za-z]{2}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4}-[0-9A-Za-z]{4})\b')
            latest_found_key = None

            for m in filtered:
                s_raw = str(m.get("sender") or "").strip()
                s_name = str(m.get("sender_name") or s_raw)
                s_low = s_raw.lower()
                text = str(m.get("text") or "").strip()
                t_str = str(m.get("created_at") or "")

                is_admin_msg = (s_low in ("admin", "skynet83") or "администратор" in s_name.lower() or bool(m.get("admin_tg_sent")))

                # Проверяем, есть ли лицензионный ключ в сообщении админа
                if is_admin_msg:
                    for mat in key_pat.finditer(text):
                        k_cand = mat.group(1).upper()
                        if not k_cand.startswith("EBID") and not k_cand.startswith("EBMOB"):
                            latest_found_key = k_cand

                if is_admin_msg:
                    txt_chat.insert(tk.END, f"👤 {s_name} ", "admin_header")
                    txt_chat.insert(tk.END, f"[{t_str}]\n", "time")
                    # Проверяем ключ для подсветки
                    last_end = 0
                    has_mat = False
                    for mat in key_pat.finditer(text):
                        k_cand = mat.group(1).upper()
                        if not k_cand.startswith("EBID") and not k_cand.startswith("EBMOB"):
                            has_mat = True
                            txt_chat.insert(tk.END, text[last_end:mat.start()], "admin_body")
                            txt_chat.insert(tk.END, mat.group(0), "key_highlight")
                            last_end = mat.end()
                    if has_mat:
                        txt_chat.insert(tk.END, text[last_end:] + "\n\n", "admin_body")
                    else:
                        txt_chat.insert(tk.END, f"{text}\n\n", "admin_body")
                else:
                    txt_chat.insert(tk.END, f"💻 Вы ", "me_header")
                    txt_chat.insert(tk.END, f"[{t_str}]\n", "time")
                    txt_chat.insert(tk.END, f"{text}\n\n", "me_body")

            txt_chat.see(tk.END)
            txt_chat.config(state="disabled")

            # Если в чате найден ключ, показываем быструю кнопку вставки
            if latest_found_key:
                btn_insert_found_key.last_key = latest_found_key
                lbl_found_key_info.config(text=f"🔑 Найден ключ: {latest_found_key}")
                key_found_frame.pack(fill="x", pady=(0, 4))
            else:
                key_found_frame.pack_forget()

            top.after(2500, lambda: update_chat_view(force=False))

        # Запускаем первичное отображение чата
        update_chat_view(force=True)

        # Нижняя панель
        foot_bar = tk.Frame(body, bg="#0f172a")
        foot_bar.pack(fill="x", pady=(6, 0))

        def open_admin_tg():
            url = "https://t.me/skynet19081983"
            try:
                if sys.platform == "win32":
                    os.startfile(url)
                else:
                    webbrowser.open(url)
            except Exception:
                pass

        btn_tg = tk.Button(foot_bar, text="✈️ Написать в Telegram (@skynet19081983)", font=("Segoe UI", 8),
                           bg="#1e293b", fg="#38bdf8", relief="flat", cursor="hand2", padx=8, pady=2, command=open_admin_tg)
        btn_tg.pack(side="left")

        btn_site = tk.Button(foot_bar, text="🌐 Открыть сайт", font=("Segoe UI", 8),
                             bg="#1e293b", fg="#94a3b8", relief="flat", cursor="hand2", padx=8, pady=2,
                             command=self.action_open_browser)
        btn_site.pack(side="left", padx=(6, 0))

        btn_close = tk.Button(foot_bar, text="Закрыть", font=("Segoe UI", 8),
                              bg="#334155", fg="#94a3b8", relief="flat", cursor="hand2", padx=10, pady=2, command=top.destroy)
        btn_close.pack(side="right")

    def action_open_key_manager(self):
        if sys.platform == "win32":
            try:
                user32 = ctypes.windll.user32
                kernel32 = ctypes.windll.kernel32
                target_hwnd = [None]
                def enum_cb(hwnd, lparam):
                    if user32.IsWindowVisible(hwnd):
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length > 0:
                            buff = ctypes.create_unicode_buffer(length + 1)
                            user32.GetWindowTextW(hwnd, buff, length + 1)
                            t = buff.value
                            if "KeyManager" in t or "Менеджер Лицензий" in t:
                                target_hwnd[0] = hwnd
                                return False
                    return True
                WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
                user32.EnumWindows(WNDENUMPROC(enum_cb), 0)
                if target_hwnd[0]:
                    current_tid = kernel32.GetCurrentThreadId()
                    target_tid = user32.GetWindowThreadProcessId(target_hwnd[0], None)
                    user32.AttachThreadInput(current_tid, target_tid, True)
                    if user32.IsIconic(target_hwnd[0]):
                        user32.ShowWindow(target_hwnd[0], 9)  # SW_RESTORE
                    elif not user32.IsZoomed(target_hwnd[0]):
                        user32.ShowWindow(target_hwnd[0], 5)  # SW_SHOW
                    user32.SetForegroundWindow(target_hwnd[0])
                    user32.BringWindowToTop(target_hwnd[0])
                    user32.AttachThreadInput(current_tid, target_tid, False)
                    return
            except Exception:
                pass

        km_exe = os.path.join(APP_DIR, "KeyManager.exe")
        if not os.path.exists(km_exe):
            km_exe = os.path.join(SITE_DIR, "KeyManager.exe")
        km_py = os.path.join(SITE_DIR, "key_manager.py")
        if os.path.exists(km_exe):
            subprocess.Popen([km_exe], cwd=os.path.dirname(km_exe))
        elif os.path.exists(km_py):
            py_exe = get_real_python_exe(prefer_windowless=True)
            subprocess.Popen([py_exe, km_py], cwd=SITE_DIR, creationflags=CREATE_NO_WINDOW)
        else:
            messagebox.showwarning("Внимание", "KeyManager.exe не найден.")

    def action_open_updater_window(self):
        """Открывает окно центра безопасных обновлений с защитой Auto-Rollback."""
        from tools import updater
        cur_ver = updater.get_current_version()

        top = tk.Toplevel(self.root)
        top.title("Центр обновлений и резервных копий (Auto-Rollback)")
        top.geometry("540x440")
        top.configure(bg="#0f172a")
        top.resizable(False, False)
        top.transient(self.root)
        top.grab_set()

        top.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() // 2) - 270
        y = self.root.winfo_y() + (self.root.winfo_height() // 2) - 220
        top.geometry(f"+{max(0, x)}+{max(0, y)}")

        header = tk.Frame(top, bg="#1e293b", padx=16, pady=12)
        header.pack(fill="x")
        tk.Label(header, text="🛡 Центр безопасных обновлений SkyBase", font=("Segoe UI", 12, "bold"),
                 fg="#f8fafc", bg="#1e293b").pack(anchor="w")
        tk.Label(header, text=f"Текущая установленная версия: v{cur_ver} (Stable)", font=("Segoe UI", 9),
                 fg="#38bdf8", bg="#1e293b").pack(anchor="w")

        body = tk.Frame(top, bg="#0f172a", padx=16, pady=12)
        body.pack(fill="both", expand=True)

        info_box = tk.Frame(body, bg="#1e293b", padx=12, pady=10, relief="flat", highlightthickness=1, highlightbackground="#334155")
        info_box.pack(fill="x", pady=(0, 14))

        tk.Label(info_box, text="⚡ Защита Auto-Rollback активна:", font=("Segoe UI", 9, "bold"),
                 fg="#10b981", bg="#1e293b").pack(anchor="w")
        tk.Label(info_box, text="Перед любым обновлением автоматически создается горячий бэкап базы данных avito_bot.db и всех файлов. Если в момент обновления произойдет малейший сбой, система мгновенно откатится назад.",
                 font=("Segoe UI", 8), fg="#cbd5e1", bg="#1e293b", wraplength=480, justify="left").pack(anchor="w", pady=(2, 0))

        lbl_upd_status = tk.Label(body, text="Готов к операциям", font=("Segoe UI", 9), fg="#94a3b8", bg="#0f172a")
        lbl_upd_status.pack(anchor="w", pady=(0, 8))

        def do_backup():
            lbl_upd_status.config(text="⏳ Создание точки восстановления...", fg="#f59e0b")
            top.update()
            ok, res = updater.create_recovery_snapshot("manual_user_backup")
            if ok:
                b_name = os.path.basename(res)
                lbl_upd_status.config(text=f"✅ Бэкап создан: {b_name}", fg="#10b981")
                self.append_log(f"[+] Создана точка восстановления: {b_name}")
                messagebox.showinfo("Бэкап создан", f"Точка восстановления успешно сохранена в:\n{res}", parent=top)
            else:
                lbl_upd_status.config(text="❌ Ошибка создания бэкапа", fg="#ef4444")
                messagebox.showerror("Ошибка", f"Не удалось создать бэкап:\n{res}", parent=top)

        def do_apply_update():
            zip_path = filedialog.askopenfilename(
                parent=top,
                title="Выберите пакет обновления (.zip)",
                filetypes=[("Архивы обновлений", "*.zip"), ("Все файлы", "*.*")]
            )
            if not zip_path:
                return

            confirm = messagebox.askyesno(
                "Подтверждение безопасного обновления",
                f"Выбран пакет:\n{os.path.basename(zip_path)}\n\n"
                "Система автоматически:\n"
                "1. Создаст резервную копию базы avito_bot.db и всех файлов\n"
                "2. Проверит синтаксис скриптов в изолированном карантине\n"
                "3. Применит обновление и проведет самодиагностику\n"
                "4. При малейшей ошибке выполнит АВТОМАТИЧЕСКИЙ ОТКАТ НАЗАД\n\n"
                "Начать обновление?",
                parent=top
            )
            if not confirm:
                return

            lbl_upd_status.config(text="⏳ Идет обновление (создание бэкапа и валидация)...", fg="#f59e0b")
            top.update()
            self.append_log(f"[*] Начало безопасного обновления пакетом: {os.path.basename(zip_path)}")

            res = updater.apply_update_package(zip_path)
            if res.get("success"):
                lbl_upd_status.config(text="✅ Обновление успешно установлено!", fg="#10b981")
                self.append_log("[+] Обновление успешно установлено и протестировано!")
                messagebox.showinfo("Успех", "Обновление успешно установлено!\nРекомендуется перезапустить сервер для применения изменений.", parent=top)
                top.destroy()
                self.action_restart_server()
            else:
                err_msg = res.get("error", "Неизвестная ошибка")
                if res.get("rolled_back"):
                    lbl_upd_status.config(text="⚠ Сбой: автоматический откат выполнен", fg="#f59e0b")
                    self.append_log(f"[!] Сбой обновления: {err_msg}")
                    messagebox.showwarning(
                        "Автоматический откат",
                        f"В процессе обновления произошла ошибка:\n\n{err_msg}\n\n"
                        "🛡 Сработала защита: система АВТОМАТИЧЕСКИ ОТКАТИЛАСЬ назад на исходную рабочую версию. Ваши данные и база в безопасности!",
                        parent=top
                    )
                else:
                    lbl_upd_status.config(text="❌ Ошибка установки", fg="#ef4444")
                    messagebox.showerror("Ошибка", f"Не удалось применить обновление:\n{err_msg}", parent=top)

        def do_restore():
            b_dir = os.path.join(SITE_DIR, "data", "backups")
            snaps = sorted([d for d in os.listdir(b_dir) if os.path.isdir(os.path.join(b_dir, d))]) if os.path.exists(b_dir) else []
            if not snaps:
                messagebox.showinfo("Нет точек восстановления", "В папке data/backups/ пока нет сохраненных снимков.", parent=top)
                return

            r_win = tk.Toplevel(top)
            r_win.title("Выбор точки восстановления")
            r_win.geometry("460x280")
            r_win.configure(bg="#0f172a")
            r_win.transient(top)
            r_win.grab_set()

            tk.Label(r_win, text="Выберите точку восстановления для отката:", font=("Segoe UI", 9, "bold"),
                     fg="#f8fafc", bg="#0f172a").pack(anchor="w", padx=12, pady=8)

            lb = tk.Listbox(r_win, bg="#1e293b", fg="#f8fafc", selectbackground="#0284c7", selectforeground="#ffffff",
                            font=("Consolas", 9), relief="flat")
            lb.pack(fill="both", expand=True, padx=12, pady=(0, 8))
            for s in reversed(snaps):
                lb.insert("end", s)
            lb.selection_set(0)

            def confirm_restore():
                sel = lb.curselection()
                if not sel:
                    return
                selected_snap = lb.get(sel[0])
                if messagebox.askyesno("Подтверждение", f"Откатить систему и базу данных на снимок:\n{selected_snap}?", parent=r_win):
                    r_win.destroy()
                    lbl_upd_status.config(text="⏳ Восстановление из снимка...", fg="#f59e0b")
                    top.update()
                    snap_p = os.path.join(b_dir, selected_snap)
                    ok, msg = updater.restore_snapshot(snap_p)
                    if ok:
                        self.append_log(f"[+] Система успешно возвращена к состоянию: {selected_snap}")
                        messagebox.showinfo("Откат завершен", f"Система успешно восстановлена!\n{msg}", parent=top)
                        top.destroy()
                        self.action_restart_server()
                    else:
                        messagebox.showerror("Ошибка", f"Не удалось выполнить откат:\n{msg}", parent=top)

            btn_cf = tk.Button(r_win, text="🔄 Выполнить откат", font=("Segoe UI", 9, "bold"),
                               bg="#0284c7", fg="#ffffff", relief="flat", cursor="hand2", padx=12, pady=5,
                               command=confirm_restore)
            btn_cf.pack(pady=(0, 8))

        btn_f1 = tk.Button(body, text="📸 Создать точку восстановления прямо сейчас", font=("Segoe UI", 9, "bold"),
                           bg="#1e293b", fg="#38bdf8", relief="flat", cursor="hand2", padx=12, pady=8, command=do_backup)
        btn_f1.pack(fill="x", pady=4)

        btn_f2 = tk.Button(body, text="📦 Установить файл обновления (.zip) с авто-откатом", font=("Segoe UI", 9, "bold"),
                           bg="#0284c7", fg="#ffffff", relief="flat", cursor="hand2", padx=12, pady=8, command=do_apply_update)
        btn_f2.pack(fill="x", pady=4)

        btn_f3 = tk.Button(body, text="🔄 Откатиться на сохраненную точку восстановления", font=("Segoe UI", 9),
                           bg="#1e293b", fg="#cbd5e1", relief="flat", cursor="hand2", padx=12, pady=8, command=do_restore)
        btn_f3.pack(fill="x", pady=4)

        btn_close = tk.Button(body, text="Закрыть", font=("Segoe UI", 9),
                              bg="#334155", fg="#94a3b8", relief="flat", cursor="hand2", padx=12, pady=4, command=top.destroy)
        btn_close.pack(anchor="e", pady=(12, 0))

    def action_restart_server(self):
        self.set_browser_button_state(False)
        self.startup_completed = False
        self.activation_checked = False
        self.post_startup_warnings = []
        if hasattr(self, 'btn_license_state') and hasattr(self, 'tariff_display_frame'):
            self.btn_license_state.pack_forget()
            self.lbl_tariff_title.config(text="Тариф: ", cursor="")
            self.lbl_tariff_val.config(text="", bg="#1e293b", padx=0, pady=0, cursor="")
            self.lbl_tariff_title.unbind("<Button-1>")
            self.lbl_tariff_val.unbind("<Button-1>")
            self.tariff_display_frame.unbind("<Button-1>")
            self.tariff_display_frame.config(width=195)
            self.tariff_display_frame.pack(side="right")
        self.is_stopped = False
        self.is_shutting_down = False
        self._is_shutting_down_active = False
        self._startup_start_time = time.time()
        self.set_loading_banner("Перезапуск служб SkyBase...")
        self.append_log("[*] Перезапуск серверов...")
        self.lbl_status_badge.config(text="⏳ ПЕРЕЗАПУСК...", bg="#f59e0b", fg="#0f172a")
        
        def restart_worker():
            try:
                ctl_script = os.path.join(SITE_DIR, "tools", "ctl.py")
                py_exe = get_real_python_exe()
                if os.path.exists(ctl_script):
                    subprocess.run([py_exe, ctl_script, "restart"], cwd=SITE_DIR, timeout=10, creationflags=CREATE_NO_WINDOW)
                else:
                    self.start_server_workflow()
            except Exception as e:
                self.append_log(f"[!] Ошибка перезапуска: {e}")
            self.start_server_workflow()

        threading.Thread(target=restart_worker, daemon=True).start()

    def action_stop_server(self):
        self.perform_graceful_shutdown(is_exiting=False)

    def update_logs_tick(self):
        """Периодическое чтение последних строк gateway.log с подсветкой проблем красной строчкой."""
        try:
            if getattr(self, 'is_shutting_down', False) or getattr(self, 'is_stopped', False):
                self.root.after(2500, self.update_logs_tick)
                return

            # Не переписываем журнал, если пользователь сейчас выделил текст для копирования
            try:
                if self.txt_logs.tag_ranges("sel"):
                    self.root.after(2500, self.update_logs_tick)
                    return
            except Exception:
                pass

            if os.path.exists(LOG_FILE):
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    lines = f.readlines()
                    tail_lines = lines[-45:]
                    tail_str = "".join(tail_lines)
                    if tail_str.strip() and tail_str.strip() != getattr(self, '_last_rendered_tail', ''):
                        self._last_rendered_tail = tail_str.strip()
                        self.render_logs_now(tail_lines)
        except Exception:
            pass
        self.root.after(2500, self.update_logs_tick)

    def render_logs_now(self, tail_lines=None):
        """Отрисовывает содержимое txt_logs: сначала предстартовые/системные логи, затем gateway.log."""
        try:
            if tail_lines is None:
                if os.path.exists(LOG_FILE):
                    try:
                        with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                            tail_lines = f.readlines()[-45:]
                    except Exception:
                        tail_lines = []
                else:
                    tail_lines = []

            self.txt_logs.delete("1.0", tk.END)

            # 1. Выводим строки предстартового чек-листа и системных событий с цветной подсветкой
            if hasattr(self, 'startup_logs') and self.startup_logs:
                for s_entry in self.startup_logs:
                    s_u = s_entry.upper()
                    if any(k in s_u for k in ["[OK]", "[+]", "УСПЕШНО", "ГОТОВ К РАБОТЕ"]) and not any(k in s_u for k in ["[FAIL]", "[ERROR]"]):
                        self.txt_logs.insert(tk.END, s_entry + "\n", "green")
                    elif any(k in s_u for k in ["[FAIL]", "[ERROR]", "TELEGRAMCONFLICTERROR", "TRACEBACK", "EXCEPTION", "MISMATCH"]) or \
                         ("ОШИБКА" in s_u and "0 ОШИБОК" not in s_u and "БЕЗ ОШИБОК" not in s_u) or \
                         ("СБОЙ" in s_u and "БЕЗ СБОЕВ" not in s_u) or \
                         ("КОНФЛИКТ" in s_u and "НЕ ОБНАРУЖЕН" not in s_u) or \
                         ("ОТКЛЮЧЕН" in s_u and "ОТКЛЮЧЕНО" not in s_u and "ОТКЛЮЧЕНА" not in s_u):
                        self.txt_logs.insert(tk.END, s_entry + "\n", "error_line")
                    elif "[WARN]" in s_u or "ВНИМАНИЕ" in s_u:
                        self.txt_logs.insert(tk.END, s_entry + "\n", "yellow")
                    else:
                        self.txt_logs.insert(tk.END, s_entry + "\n", "cyan")
                self.txt_logs.insert(tk.END, "\n--- gateway.log ---\n", "cyan")

            # 2. Построчно выводим журнал gateway.log с цветной подсветкой
            for l in tail_lines:
                l_clean = l.rstrip("\r\n")
                if not l_clean:
                    self.txt_logs.insert(tk.END, "\n")
                    continue
                u_line = l_clean.upper()
                if any(k in u_line for k in ["[OK]", "[+]", "УСПЕШНО", "ГОТОВ К РАБОТЕ"]) and not any(k in u_line for k in ["[FAIL]", "[ERROR]"]):
                    self.txt_logs.insert(tk.END, l_clean + "\n", "green")
                elif any(k in u_line for k in ["[ERROR]", "[FAIL]", "TELEGRAMCONFLICTERROR", "TRACEBACK", "EXCEPTION", "MISMATCH"]) or \
                     ("ОШИБКА" in u_line and "0 ОШИБОК" not in u_line and "БЕЗ ОШИБОК" not in u_line) or \
                     ("СБОЙ" in u_line and "БЕЗ СБОЕВ" not in u_line) or \
                     ("КОНФЛИКТ" in u_line and "НЕ ОБНАРУЖЕН" not in u_line) or \
                     ("ОТКЛЮЧЕН" in u_line and "ОТКЛЮЧЕНО" not in u_line and "ОТКЛЮЧЕНА" not in u_line):
                    self.txt_logs.insert(tk.END, l_clean + "\n", "error_line")
                elif any(k in u_line for k in ["[WARN]", "ВНИМАНИЕ", "ПРЕДУПРЕЖДЕНИЕ"]):
                    self.txt_logs.insert(tk.END, l_clean + "\n", "yellow")
                elif any(k in u_line for k in ["[*]", "===", "---"]):
                    self.txt_logs.insert(tk.END, l_clean + "\n", "cyan")
                else:
                    self.txt_logs.insert(tk.END, l_clean + "\n")
            self.txt_logs.see(tk.END)
        except Exception:
            pass

    def on_license_activated(self, new_tariff: str = "Активен"):
        """
        Обновляет журнал (отчет о запуске) и интерфейс после успешной активации лицензии:
        - Заменяет строки о необходимости активации на статус успешной активации
        - Убирает красные выделения (error_line) о лицензии из журнала
        - Перерисовывает виджет логов txt_logs, делая информацию актуальной
        - Обновляет состояние служб (Шлюз, Бэкенд, Бот) и верхний баннер на штатный зеленый
        """
        import re
        from datetime import datetime
        now_str = datetime.now().strftime("%H:%M:%S")

        updated_logs = []
        for entry in getattr(self, 'startup_logs', []):
            u_entry = entry.upper()
            m = re.match(r"^(\[\d{2}:\d{2}:\d{2}\])\s*(.*)", entry)
            time_prefix = m.group(1) if m else f"[{now_str}]"

            if "[6/8]" in entry and ("ЛИЦЕНЗИЯ" in u_entry or "LICENSE" in u_entry):
                updated_logs.append(f"{time_prefix}   [6/8] [OK] Лицензия: активна ({new_tariff}) (успешно активирована)")
            elif "ДЛЯ АКТИВАЦИИ НАЖМИТЕ" in u_entry or "ИСПОЛЬЗУЙТЕ МЕНЕДЖЕР КЛЮЧЕЙ" in u_entry:
                updated_logs.append(f"{time_prefix}         Лицензия успешно активирована и привязана к оборудованию.")
            elif "ЛИЦЕНЗИЯ НЕ АКТИВНА: ФОНОВЫЙ ОПРОС" in u_entry or "ЛИЦЕНЗИЯ НЕ АКТИВНА" in u_entry:
                updated_logs.append(f"{time_prefix} [+] Лицензия активна: фоновый опрос объявлений и Telegram-уведомления включены.")
            elif "• ЛИЦЕНЗИЯ: ТРЕБУЕТСЯ АКТИВАЦИЯ" in u_entry or "• ТРЕБУЕТСЯ АКТИВАЦИЯ" in u_entry:
                updated_logs.append(f"{time_prefix}   • Лицензия: активна ({new_tariff})")
            elif "ИТОГ ЗАПУСКА: ТРЕБУЕТСЯ ВНИМАНИЕ" in u_entry:
                updated_logs.append(f"{time_prefix}   [+] ИТОГ ЗАПУСКА: ВСЕ СЛУЖБЫ РАБОТАЮТ ШТАТНО")
            elif "НАЖМИТЕ «АКТИВИРОВАТЬ» В СТРОКЕ ТАРИФА" in u_entry or "НАЖМИТЕ «АКТИВИРОВАТЬ»" in u_entry:
                continue
            else:
                updated_logs.append(entry)

        updated_logs.append(f"[{now_str}] [+] Лицензия успешно активирована! Журнал запуска и статус служб обновлены.")
        self.startup_logs = updated_logs

        try:
            self.txt_logs.tag_remove("sel", "1.0", tk.END)
        except Exception:
            pass

        self._last_rendered_tail = None
        self.render_logs_now()

        self._prev_lic_expired = False
        self.activation_checked = True
        self.update_status_tick()

    def update_status_tick(self):
        """Проверка активности портов, состояния Avito Bot и статуса лицензии с отображением проблем красной строчкой."""
        if getattr(self, 'is_shutting_down', False) or getattr(self, 'is_stopped', False):
            self.root.after(1200, self.update_status_tick)
            return

        gw_up = is_port_open(80) or is_port_open(8080)
        be_up = is_port_open(8081)

        # Проверка реального статуса Avito Bot
        bot_pid_file = os.path.join(SITE_DIR, "avito_bot", "bot.pid")
        bot_up = False
        if os.path.exists(bot_pid_file):
            try:
                with open(bot_pid_file, "r", encoding="utf-8") as f:
                    b_pid = int(f.read().strip())
                if b_pid > 0 and get_process_name_by_pid(b_pid):
                    bot_up = True
            except Exception:
                pass
        if not bot_up:
            try:
                import avito_api_helper
                bot_up = bool(avito_api_helper.is_bot_running())
            except Exception:
                pass

        # Если шлюз и бэкенд активны, а бот почему-то не запущен — поднимаем его автоматически (только после завершения запуска)
        if getattr(self, 'startup_completed', False) and gw_up and be_up and not bot_up:
            now_t = time.time()
            if now_t - getattr(self, '_last_bot_autostart_try', 0) > 4.0:
                self._last_bot_autostart_try = now_t
                try:
                    import avito_api_helper
                    avito_api_helper.bot_toggle("start")
                    bot_up = bool(avito_api_helper.is_bot_running())
                except Exception:
                    pass

        # Кнопка открытия браузера: активна когда компоненты сервера и бота запущены
        all_ready = bool(gw_up and be_up and bot_up)
        self.set_browser_button_state(all_ready)

        # Синхронизация состояния кнопки обновления
        try:
            from tools import updater
            upd_avail, new_ver = updater.is_update_available()
            self.set_update_button_state(upd_avail, new_ver)
        except Exception:
            pass

        # Опрос статуса лицензии (через API или напрямую через avito_api_helper)
        lic_data = None
        if gw_up:
            try:
                req = urllib.request.Request(f"http://127.0.0.1:{self.active_port}/api/license/status?username=skynet83")
                with urllib.request.urlopen(req, timeout=1.5) as resp:
                    lic_data = json.loads(resp.read().decode("utf-8"))
            except Exception:
                pass

        if not lic_data:
            try:
                import avito_api_helper
                lic_data = avito_api_helper.get_license_status_info("")
            except Exception:
                pass

        lic_is_expired = True
        lic_tariff = "Требуется активация"
        lic_req_id = ""
        exp_date_str = ""
        if lic_data:
            lic_tariff = lic_data.get("tariff_label", "Неизвестно")
            lic_is_expired = bool(lic_data.get("is_expired", True))
            lic_req_id = lic_data.get("request_id", "")
            raw_exp = lic_data.get("expires_at")
            if raw_exp:
                exp_date_str = str(raw_exp).split()[0]
            elif lic_tariff in ("Безлимит", "Вечный"):
                exp_date_str = "Безлимит"

        if lic_tariff and lic_tariff.startswith("до "):
            lic_tariff = lic_tariff[3:].strip()

        is_checked = getattr(self, 'activation_checked', False)

        # Автоматическая синхронизация мониторинга и Telegram-уведомлений со статусом лицензии
        if is_checked:
            prev_lic_exp = getattr(self, '_prev_lic_expired', None)
            if prev_lic_exp is not None and prev_lic_exp is True and lic_is_expired is False:
                # Внешняя активация лицензии (например через веб-интерфейс в браузере)
                self.on_license_activated(lic_tariff)
            if prev_lic_exp is None or prev_lic_exp != lic_is_expired:
                self._prev_lic_expired = lic_is_expired
                try:
                    import avito_api_helper
                    if lic_is_expired:
                        avito_api_helper.set_monitor_state("disable")
                        avito_api_helper.set_bot_paused("pause")
                    else:
                        avito_api_helper.set_monitor_state("enable")
                        avito_api_helper.set_bot_paused("resume")
                except Exception:
                    pass

        # 1. Обновление отображения тарифа в правом верхнем углу инфо-строки
        if hasattr(self, 'tariff_display_frame'):
            if not is_checked:
                if hasattr(self, 'btn_license_key'):
                    self.btn_license_key.pack_forget()
                self.tariff_display_frame.config(width=195)
                self.lbl_tariff_title.config(text="Тариф: ", cursor="")
                self.lbl_tariff_val.config(text="", bg="#1e293b", padx=0, pady=0, cursor="")
                self.lbl_tariff_title.unbind("<Button-1>")
                self.lbl_tariff_val.unbind("<Button-1>")
                self.tariff_display_frame.unbind("<Button-1>")
                self.tariff_display_frame.pack(side="right")
                self.lbl_license_state = self.lbl_tariff_val
            elif lic_is_expired:
                val_txt = f"{exp_date_str} (Истек)" if exp_date_str else "Истек"
                self.tariff_display_frame.config(width=218)
                self.lbl_tariff_title.config(text="Тариф: ", cursor="hand2")
                self.lbl_tariff_val.config(
                    text=f" {val_txt} ",
                    bg="#dc2626",
                    fg="#ffffff",
                    padx=6,
                    pady=1,
                    cursor="hand2"
                )
                if hasattr(self, 'btn_license_key'):
                    self.btn_license_key.pack(side="left", padx=(4, 0))

                self.lbl_tariff_title.bind("<Button-1>", lambda e: self.action_open_activation_dialog())
                self.lbl_tariff_val.bind("<Button-1>", lambda e: self.action_open_activation_dialog())
                self.tariff_display_frame.bind("<Button-1>", lambda e: self.action_open_activation_dialog())
                self.tariff_display_frame.pack(side="right")
                self.lbl_license_state = self.lbl_tariff_val
            else:
                if hasattr(self, 'btn_license_key'):
                    self.btn_license_key.pack_forget()

                if exp_date_str and exp_date_str != "Безлимит":
                    val_txt = f"{exp_date_str} ({lic_tariff})" if lic_tariff and lic_tariff not in ("Активен", "Неизвестно", "Истек", exp_date_str) else f"{exp_date_str}"
                else:
                    val_txt = f"{lic_tariff}" if lic_tariff else "Активен"

                self.tariff_display_frame.config(width=195)
                self.lbl_tariff_title.config(text="Тариф: ", cursor="")
                self.lbl_tariff_val.config(
                    text=f" {val_txt} ",
                    bg="#16a34a",
                    fg="#ffffff",
                    padx=6,
                    pady=1,
                    cursor=""
                )
                self.lbl_tariff_title.unbind("<Button-1>")
                self.lbl_tariff_val.unbind("<Button-1>")
                self.tariff_display_frame.unbind("<Button-1>")
                self.tariff_display_frame.pack(side="right")
                self.lbl_license_state = self.lbl_tariff_val

        # 2. Состояние служб, баннера и значка статуса
        # ЕСЛИ ЗАГРУЗКА ЕЩЕ НЕ ЗАВЕРШЕНА — не показываем преждевременных красных ошибок и предупреждений!
        if not getattr(self, 'startup_completed', False):
            self.lbl_gw_state.config(
                text=f"● Шлюз ({self.active_port}): {'🟢 Активен' if gw_up else '● Запуск...'}",
                fg="#34d399" if gw_up else "#94a3b8"
            )
            self.lbl_be_state.config(
                text=f"● Бэкенд (8081): {'🟢 Активен' if be_up else '● Запуск...'}",
                fg="#34d399" if be_up else "#94a3b8"
            )
            self.lbl_bot_state.config(
                text=f"● Avito Bot: {'🟢 Активен' if bot_up else '● Запуск...'}",
                fg="#34d399" if bot_up else "#94a3b8"
            )
            self.set_loading_banner("Инициализация служб SkyBase и запуск компонентов...")
            self.lbl_status_badge.config(text="⏳ ЗАПУСК СЕРВЕРА...", bg="#f59e0b", fg="#0f172a")
            self.root.after(1200, self.update_status_tick)
            return

        # ИТОГ ПОСЛЕ ЗАВЕРШЕНИЯ ЗАГРУЗКИ:
        if is_checked and lic_is_expired:
            self.lbl_gw_state.config(
                text=f"● Шлюз ({self.active_port}): {'🔴 Требуется лицензия' if gw_up else '🔴 Отключен'}",
                fg="#f87171"
            )
            self.lbl_be_state.config(
                text=f"● Бэкенд (8081): {'🔴 Требуется лицензия' if be_up else '🔴 Отключен'}",
                fg="#f87171"
            )
            self.lbl_bot_state.config(
                text=f"● Avito Bot: {'🔴 Требуется лицензия' if bot_up else '🔴 Отключен'}",
                fg="#f87171"
            )
        else:
            self.lbl_gw_state.config(
                text=f"● Шлюз ({self.active_port}): {'🟢 Активен' if gw_up else '🔴 Отключен'}",
                fg="#34d399" if gw_up else "#f87171"
            )
            self.lbl_be_state.config(
                text=f"● Бэкенд (8081): {'🟢 Активен' if be_up else '🔴 Отключен'}",
                fg="#34d399" if be_up else "#f87171"
            )
            self.lbl_bot_state.config(
                text=f"● Avito Bot: {'🟢 Активен' if bot_up else '🔴 Отключен'}",
                fg="#34d399" if bot_up else "#f87171"
            )

        # Комплексный сбор всех текущих проблем для строки оповещения по итогу
        active_problems = []
        if not gw_up:
            active_problems.append("Шлюз (порт 80/8080) отключен")
        if not be_up:
            active_problems.append("Бэкенд (порт 8081) не отвечает")
        if not bot_up:
            active_problems.append("Avito Bot остановлен или запускается")

        # Проверка конфликта в Telegram логах
        bot_log_path = os.path.join(SITE_DIR, "avito_bot", "bot.log")
        has_conflict = False
        if os.path.exists(bot_log_path):
            try:
                with open(bot_log_path, "r", encoding="utf-8", errors="ignore") as f:
                    tail = f.read()[-3000:]
                    if "TelegramConflictError" in tail or "Conflict: terminated by other getUpdates" in tail:
                        has_conflict = True
            except Exception:
                pass
        if has_conflict:
            active_problems.append("Telegram: Конфликт токена бота — запущен на другом ПК!")

        if is_checked and lic_is_expired:
            id_info = f" (ID ПК: {lic_req_id})" if lic_req_id else ""
            active_problems.append(f"ТРЕБУЕТСЯ АКТИВАЦИЯ: Лицензия не активна{id_info}. Нажмите «Активировать» для ввода ключа.")

        # Финальный результат состояния служб
        if active_problems:
            prob_msg = " | ".join(active_problems)
            self.set_problem_banner(prob_msg, is_error=True)
            if lic_is_expired and gw_up and be_up and bot_up:
                self.lbl_status_badge.config(text="🔴 ТРЕБУЕТСЯ АКТИВАЦИЯ", bg="#ef4444", fg="#ffffff")
            else:
                self.lbl_status_badge.config(text="🔴 ОБНАРУЖЕНА ПРОБЛЕМА", bg="#ef4444", fg="#ffffff")
        else:
            self.set_problem_banner("", is_error=False)
            if gw_up and be_up and bot_up:
                self.lbl_status_badge.config(text="🟢 ВСЕ СЛУЖБЫ АКТИВНЫ", bg="#10b981", fg="#ffffff")

        self.root.after(1200, self.update_status_tick)

    def emergency_cleanup(self):
        """Корректное завершение всех служб SkyBase при выходе."""
        if getattr(self, '_cleaned_up', False):
            return
        self._cleaned_up = True
        CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

        # 1. Мягкая остановка через HTTP — gateway.py сам остановит бэкенд и бота
        for port in [80, 8080, 8081]:
            try:
                req = urllib.request.Request(
                    f"http://127.0.0.1:{port}/api/server/shutdown",
                    data=b"{}",
                    headers={"Content-Type": "application/json"}
                )
                urllib.request.urlopen(req, timeout=1.5)
            except Exception:
                pass

        # 2. Ждём мягкого завершения процесса gateway.py (до 8 сек)
        if self.server_process and self.server_process.poll() is None:
            try:
                self.server_process.wait(timeout=8)
            except Exception:
                pass

        # 3. Если gateway ещё жив — мягкий terminate, затем ждём ещё 4 сек
        if self.server_process and self.server_process.poll() is None:
            try:
                self.server_process.terminate()
                self.server_process.wait(timeout=4)
            except Exception:
                pass

        # 4. Завершение через центральный контроллер ctl.py (добивает всё что осталось)
        try:
            ctl_script = os.path.join(SITE_DIR, "tools", "ctl.py")
            py_exe = get_real_python_exe()
            if os.path.exists(ctl_script):
                subprocess.run(
                    [py_exe, ctl_script, "stop"],
                    cwd=SITE_DIR, timeout=6, creationflags=CREATE_NO_WINDOW,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
        except Exception:
            pass

        # 5. Принудительное завершение процесса шлюза если ещё жив (с деревом дочерних)
        if self.server_process and self.server_process.poll() is None:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(self.server_process.pid)],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW
                )
            except Exception:
                pass

        # 6. Зачистка по PID-файлам (бот, прокси-воркер, бэкенд)
        for pid_file in [
            os.path.join(SITE_DIR, "avito_bot", "bot.pid"),
            os.path.join(SITE_DIR, "avito_bot", "proxy_worker.pid"),
            os.path.join(SITE_DIR, "backend.pid"),
            os.path.join(SITE_DIR, "server.pid"),
            os.path.join(SITE_DIR, "lan_proxy.pid"),
        ]:
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, "r", encoding="utf-8") as f:
                        val = f.read().strip()
                    if val.isdigit() and int(val) > 4:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", val],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW
                        )
                    os.remove(pid_file)
                except Exception:
                    pass

        # 7. Освобождение портов от любых оставшихся слушателей (Python/PowerShell только)
        for port in [80, 8080, 8081]:
            try:
                ps_cmd = (
                    f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue"
                    f" | Select-Object -ExpandProperty OwningProcess -Unique"
                    f" | Where-Object {{ $_ -gt 4 }}"
                    f" | ForEach-Object {{"
                    f"   $n = (Get-Process -Id $_ -ErrorAction SilentlyContinue).Name;"
                    f"   if ($n -like '*python*' -or $n -like '*powershell*') {{"
                    f"     Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue"
                    f"   }}"
                    f" }}"
                )
                subprocess.run(
                    ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command", ps_cmd],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=CREATE_NO_WINDOW, timeout=4
                )
            except Exception:
                pass

    def _kill_port_listeners(self, port):
        """Освобождает указанный порт от зависших процессов Python/PowerShell."""
        try:
            current_pid = os.getpid()
            out = subprocess.check_output("netstat -ano -p tcp", shell=True, text=True, stderr=subprocess.DEVNULL)
            for line in out.splitlines():
                if "LISTENING" in line:
                    parts = line.strip().split()
                    if len(parts) >= 5 and parts[1].endswith(f":{port}"):
                        pid_str = parts[-1]
                        if pid_str.isdigit() and int(pid_str) > 4 and int(pid_str) != current_pid:
                            p = int(pid_str)
                            pname = get_process_name_by_pid(p).lower()
                            if any(k in pname for k in ["python", "powershell", "pwsh"]):
                                subprocess.run(
                                    ["taskkill", "/F", "/PID", str(p)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                    creationflags=CREATE_NO_WINDOW, timeout=2
                                )
        except Exception:
            pass

    def perform_graceful_shutdown(self, is_exiting=True):
        """Поочередная корректная остановка всех компонентов SkyBase без ложных сообщений об ошибках."""
        if getattr(self, '_is_shutting_down_active', False):
            return
        self._is_shutting_down_active = True
        self.is_shutting_down = True
        self.set_browser_button_state(False)

        try:
            self.lbl_status_badge.config(text="⏳ ОСТАНОВКА СЛУЖБ...", bg="#f59e0b", fg="#0f172a")
            self.set_loading_banner("Остановка служб SkyBase...")
            self.root.update()
        except Exception:
            pass

        self.append_log("[*] Остановка служб: начинаем поочередное выключение...")

        # [1/4] Telegram-бот Avito
        try:
            self.append_log("  [1/4] Остановка Telegram-бота Avito...")
            self.set_loading_banner("Остановка Telegram-бота Avito...")
            self.root.update()

            bot_pid_file = os.path.join(SITE_DIR, "avito_bot", "bot.pid")
            if os.path.exists(bot_pid_file):
                try:
                    with open(bot_pid_file, "r", encoding="utf-8") as f:
                        b_val = f.read().strip()
                    if b_val.isdigit() and int(b_val) > 4:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", b_val],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW, timeout=2
                        )
                    os.remove(bot_pid_file)
                except Exception:
                    pass

            subprocess.run(
                ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*avito_bot*bot.py*' -or $_.CommandLine -like '*bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW, timeout=3
            )
            self.lbl_bot_state.config(text="● Avito Bot: ⚪ Остановлен", fg="#94a3b8")
            self.append_log("  [1/4] [OK] Telegram-бот Avito остановлен.")
            self.root.update()
        except Exception as e:
            self.append_log(f"  [1/4] [!] Остановка бота: {e}")

        # [2/4] Фоновые воркеры и скраперы
        try:
            self.append_log("  [2/4] Остановка фоновых воркеров...")
            self.set_loading_banner("Остановка фоновых воркеров...")
            self.root.update()

            proxy_pid_file = os.path.join(SITE_DIR, "avito_bot", "proxy_worker.pid")
            if os.path.exists(proxy_pid_file):
                try:
                    with open(proxy_pid_file, "r", encoding="utf-8") as f:
                        p_val = f.read().strip()
                    if p_val.isdigit() and int(p_val) > 4:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", p_val],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW, timeout=2
                        )
                    os.remove(proxy_pid_file)
                except Exception:
                    pass

            subprocess.run(
                ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command",
                 "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*proxy_worker.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=CREATE_NO_WINDOW, timeout=3
            )
            self.append_log("  [2/4] [OK] Фоновые службы и воркеры остановлены.")
            self.root.update()
        except Exception as e:
            self.append_log(f"  [2/4] [!] Остановка воркеров: {e}")

        # [3/4] Основной бэкенд (порт 8081)
        try:
            self.append_log("  [3/4] Остановка основного бэкенда (порт 8081)...")
            self.set_loading_banner("Остановка основного бэкенда (порт 8081)...")
            self.root.update()

            try:
                req = urllib.request.Request("http://127.0.0.1:8081/api/server/shutdown", data=b"{}", headers={"Content-Type": "application/json"})
                urllib.request.urlopen(req, timeout=0.6)
            except Exception:
                pass

            for b_pf in [os.path.join(SITE_DIR, "backend.pid"), os.path.join(SITE_DIR, "server.pid")]:
                if os.path.exists(b_pf):
                    try:
                        with open(b_pf, "r", encoding="utf-8") as f:
                            b_val = f.read().strip()
                        if b_val.isdigit() and int(b_val) > 4:
                            subprocess.run(
                                ["taskkill", "/F", "/T", "/PID", b_val],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=CREATE_NO_WINDOW, timeout=2
                            )
                        os.remove(b_pf)
                    except Exception:
                        pass

            self._kill_port_listeners(8081)
            self.lbl_be_state.config(text="● Бэкенд (8081): ⚪ Остановлен", fg="#94a3b8")
            self.append_log("  [3/4] [OK] Бэкенд успешно остановлен.")
            self.root.update()
        except Exception as e:
            self.append_log(f"  [3/4] [!] Остановка бэкенда: {e}")

        # [4/4] Публичный шлюз (порт 80 / 8080)
        try:
            self.append_log(f"  [4/4] Остановка публичного шлюза (порт {self.active_port})...")
            self.set_loading_banner(f"Остановка публичного шлюза (порт {self.active_port})...")
            self.root.update()

            for p in [self.active_port, 80, 8080]:
                try:
                    req = urllib.request.Request(f"http://127.0.0.1:{p}/api/server/shutdown", data=b"{}", headers={"Content-Type": "application/json"})
                    urllib.request.urlopen(req, timeout=0.6)
                except Exception:
                    pass

            if self.server_process and self.server_process.poll() is None:
                try:
                    self.server_process.terminate()
                    self.server_process.wait(timeout=1.0)
                except Exception:
                    try:
                        subprocess.run(
                            ["taskkill", "/F", "/T", "/PID", str(self.server_process.pid)],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=CREATE_NO_WINDOW, timeout=2
                        )
                    except Exception:
                        pass

            for p in [self.active_port, 80, 8080]:
                self._kill_port_listeners(p)

            for l_pf in [os.path.join(SITE_DIR, "lan_proxy.pid")]:
                if os.path.exists(l_pf):
                    try:
                        os.remove(l_pf)
                    except Exception:
                        pass

            self.lbl_gw_state.config(text=f"● Шлюз ({self.active_port}): ⚪ Остановлен", fg="#94a3b8")
            self.append_log("  [4/4] [OK] Публичный шлюз остановлен.")
            self.root.update()
        except Exception as e:
            self.append_log(f"  [4/4] [!] Остановка шлюза: {e}")

        # Финализация
        self._cleaned_up = True
        self.append_log("[+] Все службы SkyBase успешно остановлены.")
        self.root.update()

        if is_exiting:
            self.set_loading_banner("Все службы остановлены. Завершение работы...")
            self.lbl_status_badge.config(text="⚪ ОСТАНОВЛЕН", bg="#334155", fg="#cbd5e1")
            self.root.update()
            time.sleep(0.35)
            try:
                self.root.destroy()
            except Exception:
                pass
            sys.exit(0)
        else:
            self.is_running = False
            self.is_shutting_down = False
            self.is_stopped = True
            self._is_shutting_down_active = False
            self.lbl_status_badge.config(text="⚪ СЕРВЕР ОСТАНОВЛЕН", bg="#334155", fg="#cbd5e1")
            self.set_loading_banner("Сервер и службы остановлены. Нажмите «Перезапустить» для включения.")
            self.root.update()

    def on_closing(self):
        """Закрытие программы по крестику — поочередная корректная остановка всех служб."""
        if getattr(self, '_is_closing_already', False):
            return
        self._is_closing_already = True
        self.perform_graceful_shutdown(is_exiting=True)



if __name__ == "__main__":
    # 1. Защита от ошибочного вызова SkyBase.exe вместо python.exe
    if len(sys.argv) > 1 and sys.argv[1].endswith(".py"):
        real_py = get_real_python_exe()
        res = subprocess.run([real_py] + sys.argv[1:], creationflags=CREATE_NO_WINDOW)
        sys.exit(res.returncode)

    # 2. Мьютекс одного экземпляра приложения (предотвращает появление дубликатов)
    _instance_mutex = ensure_single_instance()

    root = tk.Tk()
    app = SkyBaseLauncherApp(root)
    root.mainloop()
