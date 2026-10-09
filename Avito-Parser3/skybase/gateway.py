#!/usr/bin/env python3
"""
SkyBase Gateway & Watchdog Supervisor
Кроссплатформенный дежурный диспетчер (Windows & Linux Debian).
1. Слушает публичный порт 8080.
2. Раздает статические файлы (HTML/CSS/JS/картинки/звуки) даже когда основной бэкенд выключен.
3. Управляет жизненным циклом основного сервера (запуск, перезапуск, выключение).
4. Прозрачно проксирует API на внутренний порт 8081.
"""

import os
import sys
import time
import json
import socket
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
try:
    from http.server import ThreadingHTTPServer
except ImportError:
    ThreadingHTTPServer = HTTPServer
import mimetypes
import hashlib
import uuid

def find_preferred_gateway_port():
    env_port = os.environ.get("GATEWAY_PORT")
    if env_port and env_port.isdigit():
        return int(env_port)
    # Приоритет: порт 80 (позволяет открывать сайт без указания порта в браузере)
    for p in [80, 8080, 8000, 8888, 5000]:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("0.0.0.0", p))
            s.close()
            return p
        except Exception:
            continue
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("0.0.0.0", 0))
    p = s.getsockname()[1]
    s.close()
    return p

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

_WINDOWS_JOB_OBJECT_HANDLE = None
_WINDOWS_CTRL_HANDLER_REF = None

def enable_kill_child_processes_on_exit():
    """
    Привязывает процесс и всех потомков к Windows Job Object с флагом JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE (0x2000).
    Когда окно консоли закрывается (по крестику 'X' или завершению родителя),
    ядро Windows автоматически и мгновенно уничтожает все дочерние процессы (сервер, бот, воркеры).
    """
    global _WINDOWS_JOB_OBJECT_HANDLE
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.argtypes = [wintypes.LPVOID, wintypes.LPCWSTR]
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE

        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE

        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL

        kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            return None

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("ReadOperationCount", ctypes.c_uint64),
                ("WriteOperationCount", ctypes.c_uint64),
                ("OtherOperationCount", ctypes.c_uint64),
                ("ReadTransferCount", ctypes.c_uint64),
                ("WriteTransferCount", ctypes.c_uint64),
                ("OtherTransferCount", ctypes.c_uint64),
            ]

        class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("PerProcessUserTimeLimit", ctypes.c_int64),
                ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD),
                ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t),
                ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t),
                ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD),
            ]

        class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t),
            ]

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x00002000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

        if not kernel32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info)):
            return None

        hCurrent = kernel32.GetCurrentProcess()
        if not kernel32.AssignProcessToJobObject(job, hCurrent):
            return None

        _WINDOWS_JOB_OBJECT_HANDLE = job
        return job
    except Exception:
        return None

def setup_windows_console_ctrl_handler():
    """
    Регистрирует обработчик закрытия окна консоли (CTRL_CLOSE_EVENT, нажатие на крестик).
    Гарантирует вызов stop_backend() и полное завершение всех фоновых процессов программы.
    """
    global _WINDOWS_CTRL_HANDLER_REF
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        HandlerRoutine = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)

        def ctrl_handler(ctrl_type):
            # 0=CTRL_C, 1=CTRL_BREAK, 2=CTRL_CLOSE, 5=CTRL_LOGOFF, 6=CTRL_SHUTDOWN
            try:
                stop_backend()
            except Exception:
                pass
            return False

        _WINDOWS_CTRL_HANDLER_REF = HandlerRoutine(ctrl_handler)
        kernel32.SetConsoleCtrlHandler.argtypes = [HandlerRoutine, wintypes.BOOL]
        kernel32.SetConsoleCtrlHandler.restype = wintypes.BOOL
        kernel32.SetConsoleCtrlHandler(_WINDOWS_CTRL_HANDLER_REF, True)
    except Exception:
        pass

def is_valid_python(path):
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
    """Определяет реальный путь к интерпретатору python.exe, исключая скомпилированные .exe и заглушки WindowsApps."""
    p = None
    if not getattr(sys, 'frozen', False):
        if sys.executable.lower().endswith(("python.exe", "pythonw.exe")) and is_valid_python(sys.executable):
            p = sys.executable

    # Автономный встроенный интерпретатор python-embed
    if not p:
        embed_candidates = [
            os.path.join(STATIC_DIR, "python.exe"),
            os.path.join(os.path.dirname(STATIC_DIR), "python.exe"),
            os.path.join(STATIC_DIR, "python-embed", "python.exe"),
            os.path.join(os.path.dirname(STATIC_DIR), "python-embed", "python.exe"),
        ]
        for c in embed_candidates:
            if c and os.path.exists(c) and is_valid_python(c):
                p = c
                break

    if not p:
        env_py = os.environ.get("PYTHON_EXE")
        if env_py and is_valid_python(env_py):
            p = env_py

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

    if not p:
        import shutil
        for name in ["python", "python3", "py"]:
            candidate = shutil.which(name)
            if candidate and is_valid_python(candidate):
                p = candidate
                break

    if not p:
        return sys.executable if sys.executable else "python"

    if prefer_windowless and sys.platform == "win32":
        pw = os.path.join(os.path.dirname(p), "pythonw.exe")
        if os.path.exists(pw):
            return pw
    return p

# Базовые параметры портов и путей
GATEWAY_PORT = find_preferred_gateway_port()
BACKEND_PORT = int(os.environ.get("BACKEND_PORT", 8081))
STATIC_DIR = os.path.dirname(os.path.abspath(__file__))
LIB_DIR = os.path.join(STATIC_DIR, "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)
PID_FILE = os.path.join(STATIC_DIR, "backend.pid")

class TeeLogger:
    def __init__(self, filename, orig_stream):
        self.orig_stream = orig_stream
        try:
            self.file = open(filename, "a", encoding="utf-8", buffering=1)
        except Exception:
            self.file = None

    def write(self, data):
        if self.orig_stream:
            try:
                self.orig_stream.write(data)
                self.orig_stream.flush()
            except Exception:
                pass
        if self.file:
            try:
                self.file.write(data)
                self.file.flush()
            except Exception:
                pass

    def flush(self):
        if self.orig_stream:
            try:
                self.orig_stream.flush()
            except Exception:
                pass
        if self.file:
            try:
                self.file.flush()
            except Exception:
                pass

    def reconfigure(self, **kwargs):
        if self.orig_stream and hasattr(self.orig_stream, "reconfigure"):
            try:
                self.orig_stream.reconfigure(**kwargs)
            except Exception:
                pass

try:
    _gw_log_path = os.path.join(STATIC_DIR, "gateway.log")
    sys.stdout = TeeLogger(_gw_log_path, sys.stdout)
    sys.stderr = TeeLogger(_gw_log_path, sys.stderr)
except Exception:
    pass

# Подключение модуля туннелей WAN
tools_dir = os.path.join(STATIC_DIR, "tools")
if tools_dir not in sys.path:
    sys.path.insert(0, tools_dir)
try:
    import ngrok_service
except Exception:
    ngrok_service = None

# Блокировка для потокобезопасного управления процессами
backend_lock = threading.Lock()
backend_process = None
backend_state = "off"  # "running", "off", "starting"

mimetypes.init()
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("application/json", ".json")
mimetypes.add_type("image/png", ".png")
mimetypes.add_type("image/jpeg", ".jpg")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("audio/mpeg", ".mp3")


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


def is_port_open(host, port, timeout=0.4):
    """Быстрая проверка открытости TCP-порта."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def get_backend_pid():
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val.isdigit():
                    return int(val)
        except Exception:
            pass
    return None


def is_backend_alive():
    global backend_process, backend_state
    if is_port_open("127.0.0.1", BACKEND_PORT, timeout=0.3):
        backend_state = "running"
        return True

    pid = get_backend_pid()
    if pid:
        # Проверяем наличие процесса в ОС
        if sys.platform == "win32":
            try:
                out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/NH"], text=True, creationflags=CREATE_NO_WINDOW)
                if str(pid) in out:
                    return is_port_open("127.0.0.1", BACKEND_PORT, timeout=0.5)
            except Exception:
                pass
        else:
            try:
                os.kill(pid, 0)
                return is_port_open("127.0.0.1", BACKEND_PORT, timeout=0.5)
            except Exception:
                pass

    if backend_state != "starting":
        backend_state = "off"
    return False


def ensure_ps1_bom(ps1_path):
    """Гарантирует наличие UTF-8 BOM в .ps1 скриптах для корректного чтения PowerShell 5.1."""
    try:
        if os.path.exists(ps1_path):
            with open(ps1_path, "rb") as f:
                b = f.read()
            if b and not b.startswith(b"\xef\xbb\xbf"):
                with open(ps1_path, "wb") as f:
                    f.write(b"\xef\xbb\xbf" + b)
    except Exception:
        pass

def start_backend():
    """Запускает основной сервер на порту 8081."""
    global backend_process, backend_state
    with backend_lock:
        if is_backend_alive():
            backend_state = "running"
            return True, "Основной сервер уже работает."

        backend_state = "starting"
        env = os.environ.copy()
        env["SERVER_PORT"] = str(BACKEND_PORT)
        # Передаем точный путь к реальному интерпретатору Python (CLI python.exe с рабочими stdout/stderr)
        real_py = get_real_python_exe(prefer_windowless=False)
        env["PYTHON_EXE"] = real_py

        try:
            log_file = open(os.path.join(STATIC_DIR, "server_backend.log"), "w", encoding="utf-8")
            py_server = os.path.join(STATIC_DIR, "server.py")
            if os.path.exists(py_server):
                cmd = [real_py, py_server, "--port", str(BACKEND_PORT), "--no-browser"]
                backend_process = subprocess.Popen(
                    cmd,
                    cwd=STATIC_DIR,
                    env=env,
                    creationflags=CREATE_NO_WINDOW,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=log_file
                )
            elif sys.platform == "win32":
                ps_script = os.path.join(STATIC_DIR, "server.ps1")
                ensure_ps1_bom(ps_script)
                cmd = ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps_script, "-Port", str(BACKEND_PORT), "-NoBrowser"]
                backend_process = subprocess.Popen(
                    cmd,
                    cwd=STATIC_DIR,
                    env=env,
                    creationflags=CREATE_NO_WINDOW,
                    stdin=subprocess.DEVNULL,
                    stdout=log_file,
                    stderr=log_file
                )
            else:
                # На Linux Debian
                sh_script = os.path.join(STATIC_DIR, "server.sh")
                if os.path.exists(sh_script):
                    backend_process = subprocess.Popen(
                        ["bash", sh_script],
                        cwd=STATIC_DIR,
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
                else:
                    # Попытка запустить PowerShell Core или сервер
                    backend_process = subprocess.Popen(
                        ["pwsh", "-NoProfile", "-File", os.path.join(STATIC_DIR, "server.ps1")],
                        cwd=STATIC_DIR,
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )

            if backend_process and backend_process.pid:
                if _WINDOWS_JOB_OBJECT_HANDLE:
                    try:
                        import ctypes
                        from ctypes import wintypes
                        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
                        k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
                        k32.AssignProcessToJobObject.restype = wintypes.BOOL
                        k32.AssignProcessToJobObject(_WINDOWS_JOB_OBJECT_HANDLE, wintypes.HANDLE(backend_process._handle))
                    except Exception:
                        pass
                try:
                    with open(PID_FILE, "w", encoding="utf-8") as f:
                        f.write(str(backend_process.pid))
                except Exception:
                    pass

            # Запускаем Telegram-бота синхронно с сервером (в фоновом скрытом режиме)
            try:
                py_helper = os.path.join(STATIC_DIR, "avito_api_helper.py")
                if os.path.exists(py_helper):
                    subprocess.Popen(
                        [real_py, py_helper, "bot-toggle", "start"],
                        cwd=STATIC_DIR,
                        creationflags=CREATE_NO_WINDOW,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL
                    )
            except Exception:
                pass

            # Ожидание готовности порта до 8 секунд
            for _ in range(40):
                time.sleep(0.2)
                if is_port_open("127.0.0.1", BACKEND_PORT, timeout=0.3):
                    backend_state = "running"
                    return True, "Сервер и Telegram-бот успешно запущены."

            backend_state = "running" if is_port_open("127.0.0.1", BACKEND_PORT) else "off"
            return True, "Команда на запуск отдана."
        except Exception as e:
            backend_state = "off"
            return False, f"Ошибка запуска сервера: {e}"


def stop_backend():
    """Корректно останавливает основной сервер и связанный Telegram-бот."""
    global backend_process, backend_state
    with backend_lock:
        backend_state = "off"

        # 1. Останавливаем Telegram-бота и воркер прокси
        try:
            py_helper = os.path.join(STATIC_DIR, "avito_api_helper.py")
            if os.path.exists(py_helper):
                real_py = get_real_python_exe(prefer_windowless=True)
                subprocess.call([real_py, py_helper, "bot-toggle", "stop"], cwd=STATIC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                subprocess.call([real_py, py_helper, "fetch-proxies", "stop"], cwd=STATIC_DIR, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass
        
        # Сброс счётчика попыток активации
        try:
            locks_file = os.path.join(STATIC_DIR, "data", "activation_locks.json")
            if os.path.exists(locks_file):
                with open(locks_file, "w", encoding="utf-8") as f:
                    json.dump({}, f)
        except Exception:
            pass

        # 2. Мягкий HTTP shutdown — просим сервер завершиться самостоятельно
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:{BACKEND_PORT}/api/server/shutdown",
                data=b"{}",
                headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=2)
        except Exception:
            pass

        # 3. Ждём мягкого завершения до 6 секунд (сервер закрывает listener и убирает PID)
        if backend_process and backend_process.poll() is None:
            try:
                backend_process.wait(timeout=6)
            except Exception:
                pass

        # 4. Если ещё жив — мягкий terminate (WM_CLOSE / SIGTERM)
        if backend_process and backend_process.poll() is None:
            try:
                backend_process.terminate()
            except Exception:
                pass
            try:
                backend_process.wait(timeout=4)
            except Exception:
                pass

        # 5. Принудительное завершение всех дочерних процессов по всем PID-файлам
        pid_files = [
            os.path.join(STATIC_DIR, "backend.pid"),
            os.path.join(STATIC_DIR, "server.pid"),
            os.path.join(STATIC_DIR, "avito_bot", "bot.pid"),
            os.path.join(STATIC_DIR, "avito_bot", "proxy_worker.pid"),
            os.path.join(STATIC_DIR, "data", "bot.pid"),
            os.path.join(STATIC_DIR, "data", "server.pid")
        ]
        my_pid = os.getpid()
        for pfile in pid_files:
            if os.path.exists(pfile):
                try:
                    with open(pfile, "r", encoding="utf-8") as pf:
                        content = pf.read().strip()
                        spid = int(content) if content.isdigit() else None
                    if spid and spid != my_pid:
                        if sys.platform == "win32":
                            subprocess.call(
                                ["taskkill", "/PID", str(spid), "/F", "/T"],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                creationflags=CREATE_NO_WINDOW
                            )
                        else:
                            import signal as _sig
                            os.kill(spid, _sig.SIGKILL)
                    os.remove(pfile)
                except Exception:
                    pass

        # 6. Финальная зачистка объекта процесса и PID-файла
        if backend_process:
            try:
                if backend_process.poll() is None:
                    if sys.platform == "win32":
                        subprocess.call(["taskkill", "/PID", str(backend_process.pid), "/F", "/T"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                    else:
                        backend_process.kill()
            except Exception:
                pass
            backend_process = None

        if os.path.exists(PID_FILE):
            try:
                os.remove(PID_FILE)
            except Exception:
                pass

        return True, "Сервер и Telegram-бот выключены."


# Ошибки штатного разрыва соединения клиентом (закрытие вкладки браузера, обновление страницы, таймаут)
_CLIENT_DISCONNECT_ERRORS = (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)

def is_client_disconnect(exc):
    """Проверяет, является ли ошибка штатным разрывом TCP-соединения клиентом."""
    if not exc:
        return False
    if isinstance(exc, _CLIENT_DISCONNECT_ERRORS):
        return True
    if isinstance(exc, OSError):
        # 10053: WSAECONNABORTED, 10054: WSAECONNRESET, 10038: WSAENOTSOCK, 10058: WSAESHUTDOWN, 32: Broken pipe
        if getattr(exc, "winerror", None) in (10053, 10054, 10038, 10058):
            return True
        if getattr(exc, "errno", None) in (10053, 10054, 32):
            return True
    cause = getattr(exc, "__cause__", None) or getattr(exc, "__context__", None)
    if cause and cause is not exc:
        return is_client_disconnect(cause)
    return False


class GatewayHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, format, *args):
        # Отключаем спам в консоль
        pass

    def handle(self):
        """Перехватываем разрывы соединения на уровне handle() — не даём им всплыть в stderr."""
        try:
            super().handle()
        except Exception as e:
            if not is_client_disconnect(e):
                raise

    def end_headers(self):
        has_cache_header = any(h.lower().startswith(b"cache-control:") for h in getattr(self, "_headers_buffer", []))
        if not has_cache_header:
            req_path = getattr(self, "path", "").split("?")[0].lower()
            if req_path.endswith((".png", ".jpg", ".jpeg", ".svg", ".ico", ".woff", ".woff2", ".mp3")):
                self.send_header("Cache-Control", "public, max-age=86400")
            else:
                self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
        super().end_headers()

    def send_json(self, status_code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
            self.end_headers()
            self.wfile.write(body)
        except Exception as e:
            if not is_client_disconnect(e):
                pass

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        url_path = self.path.split("?")[0]

        # 1. API проверки статуса питания сервера
        if url_path == "/api/server/power-state":
            is_running = is_backend_alive()
            self.send_json(200, {
                "success": True,
                "state": "running" if is_running else backend_state,
                "backend_port": BACKEND_PORT,
                "gateway_port": GATEWAY_PORT
            })
            return

        # 1.0 API реального локального IP сервера
        if url_path in ("/api/server/network-info", "/api/server/info"):
            ip = get_local_ip()
            port = GATEWAY_PORT
            net_url = f"http://{ip}" if port == 80 else f"http://{ip}:{port}"
            self.send_json(200, {
                "success": True,
                "local_ip": ip,
                "port": port,
                "network_url": net_url,
                "network_access": True,
                "visitors": []
            })
            return

        # 1.1 API статуса и конфигурации WAN туннеля (обрабатывается мгновенно шлюзом)
        if url_path in ("/api/server/ngrok", "/api/server/ngrok/status"):
            if ngrok_service:
                st = ngrok_service.check_status()
                self.send_json(200, st)
                return

        if url_path == "/api/server/wan/config":
            if ngrok_service:
                cfg = ngrok_service.get_masked_config()
                self.send_json(200, cfg)
                return

        # 1.2 Проверка текущего пользователя при выключенном сервере
        if url_path == "/api/me" and not is_backend_alive():
            users_file = os.path.join(STATIC_DIR, "data", "users.json")
            admin_u = None
            if os.path.exists(users_file):
                try:
                    with open(users_file, "r", encoding="utf-8-sig") as f:
                        users = json.load(f)
                    for u in users:
                        if u.get("role") == "admin" or u.get("username") == "skynet83":
                            admin_u = u
                            break
                    if not admin_u and users:
                        admin_u = users[0]
                except Exception:
                    pass
            if not admin_u:
                admin_u = {
                    "username": "skynet83",
                    "role": "admin",
                    "permissions": {
                        "avito": True, "avito_bot": True, "tg_bot": True,
                        "monitoring": True, "max_searches": 999999,
                        "target_interval": "1", "unlimited": True
                    }
                }
            self.send_json(200, {"success": True, "user": admin_u})
            return

        if url_path == "/api/system/update/status":
            from tools import updater
            b_dir = os.path.join(STATIC_DIR, "data", "backups")
            snaps = [d for d in os.listdir(b_dir) if os.path.isdir(os.path.join(b_dir, d))] if os.path.exists(b_dir) else []
            self.send_json(200, {
                "success": True,
                "version": updater.get_current_version(),
                "backups": snaps
            })
            return

        # 2. Обработка запросов к API
        if url_path.startswith("/api/"):
            if not is_backend_alive():
                self.send_json(503, {
                    "success": False,
                    "error": "server_off",
                    "message": "Основной сервер выключен",
                    "state": "off"
                })
                return
            self.proxy_request("GET")
            return

        # 3. Раздача статических файлов
        super().do_GET()

    def do_POST(self):
        url_path = self.path.split("?")[0]

        # API: Включение сервера
        if url_path == "/api/server/start":
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] [ВКЛЮЧЕНИЕ] Запрос на запуск сервера и Telegram-бота...")
            ok, msg = start_backend()
            if ok:
                print(f"[{ts}] [ВКЛЮЧЕНИЕ] Сервер и Telegram-бот успешно запущены!")
            else:
                print(f"[{ts}] [ОШИБКА] Ошибка запуска сервера: {msg}")
            self.send_json(200 if ok else 500, {
                "success": ok,
                "state": backend_state,
                "message": msg
            })
            return

        # API: Выключение сервера (переход в дежурный режим ожидания)
        if url_path == "/api/server/shutdown":
            ts = time.strftime("%H:%M:%S")
            print(f"[{ts}] [ДЕЖУРНЫЙ РЕЖИМ] Запрос на выключение. Остановка основного сервера и Telegram-бота...")
            ok, msg = stop_backend()
            print(f"[{ts}] [ДЕЖУРНЫЙ РЕЖИМ] Основной сервер выключен. Дежурный сервер активен на порту {GATEWAY_PORT} и ожидает команду включения.")
            self.send_json(200, {
                "success": True,
                "state": "off",
                "message": msg
            })
            return

        # API: Перезапуск сервера
        if url_path == "/api/server/restart":
            stop_backend()
            time.sleep(0.5)
            ok, msg = start_backend()
            self.send_json(200 if ok else 500, {
                "success": ok,
                "state": backend_state,
                "message": msg
            })
            return

        # API: Создание точки восстановления (горячий бэкап)
        if url_path == "/api/system/backup":
            from tools import updater
            ok, res = updater.create_recovery_snapshot("web_api_backup")
            self.send_json(200 if ok else 500, {
                "success": ok,
                "snapshot": os.path.basename(res) if ok else None,
                "path": res if ok else None,
                "error": None if ok else res
            })
            return

        # API: Управление туннелем WAN (старт, остановка, прерывание)
        if url_path == "/api/server/ngrok/toggle":
            action = "toggle"
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length > 0:
                    body = self.rfile.read(length).decode("utf-8")
                    data = json.loads(body)
                    action = data.get("action", "toggle")
            except Exception:
                pass

            if ngrok_service:
                if action == "start":
                    res = ngrok_service.start_tunnel()
                elif action in ("stop", "abort"):
                    res = ngrok_service.stop_tunnel()
                elif action in ("status", "info"):
                    res = ngrok_service.check_status()
                else:
                    curr = ngrok_service.check_status()
                    if curr.get("running"):
                        res = ngrok_service.stop_tunnel()
                    else:
                        res = ngrok_service.start_tunnel()
                self.send_json(200, res)
                return

        # API: Сохранение настроек WAN туннеля
        if url_path == "/api/server/wan/config":
            payload = {}
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length > 0:
                    body = self.rfile.read(length).decode("utf-8")
                    payload = json.loads(body)
            except Exception:
                pass

            if ngrok_service:
                cur = ngrok_service.get_config()
                for k, v in payload.items():
                    cur[k] = v
                ok = ngrok_service.save_config(cur)
                self.send_json(200 if ok else 500, {
                    "success": ok,
                    "config": ngrok_service.get_masked_config()
                })
                return

        # Авторизация и выход при выключенном основном сервере (Сервисный режим)
        if url_path == "/api/login" and not is_backend_alive():
            try:
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length).decode("utf-8", errors="ignore")
                data = json.loads(body) if body else {}
                target_user = (data.get("username") or "").strip().lower()
                target_pass = (data.get("password") or "").strip()
                target_hash = hashlib.sha256(target_pass.encode("utf-8")).hexdigest()

                users_file = os.path.join(STATIC_DIR, "data", "users.json")
                users = []
                if os.path.exists(users_file):
                    with open(users_file, "r", encoding="utf-8-sig") as f:
                        users = json.load(f)

                matched_user = None
                for u in users:
                    u_name = (u.get("username") or "").strip().lower()
                    if u_name == target_user:
                        if u.get("password") in (target_hash, target_pass) or u.get("plain_password") == target_pass:
                            matched_user = u
                            break

                if matched_user:
                    token = uuid.uuid4().hex
                    matched_user["session_token"] = token
                    matched_user["last_seen"] = time.strftime("%Y-%m-%d %H:%M:%S")
                    try:
                        with open(users_file, "w", encoding="utf-8") as f:
                            json.dump(users, f, ensure_ascii=False, indent=4)
                    except Exception:
                        pass
                    self.send_json(200, {
                        "success": True,
                        "user": matched_user,
                        "session_token": token
                    })
                    return
                else:
                    self.send_json(401, {"success": False, "error": "Неверный логин или пароль"})
                    return
            except Exception as e:
                self.send_json(500, {"success": False, "error": str(e)})
                return

        if url_path == "/api/logout" and not is_backend_alive():
            self.send_json(200, {"success": True})
            return

        # Проксирование всех остальных POST запросов
        if url_path.startswith("/api/"):
            if not is_backend_alive():
                self.send_json(503, {
                    "success": False,
                    "error": "server_off",
                    "message": "Основной сервер выключен",
                    "state": "off"
                })
                return
            self.proxy_request("POST")
            return

        self.send_error(404, "Not Found")

    def proxy_request(self, method):
        """Прозрачно передает запрос на порт 8081 основного сервера."""
        backend_url = f"http://127.0.0.1:{BACKEND_PORT}{self.path}"
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else None

        headers = {}
        for k, v in self.headers.items():
            if k.lower() not in ["host", "content-length"]:
                headers[k] = v

        client_ip = self.client_address[0]
        if client_ip in ("127.0.0.1", "::1"):
            try:
                real_local = get_local_ip()
                if real_local and real_local != "127.0.0.1":
                    client_ip = real_local
            except Exception:
                pass
        headers["X-Forwarded-For"] = client_ip
        headers["X-Real-IP"] = client_ip
        headers["X-Internal-Gateway"] = "ElectroBase-Supervisor"

        try:
            req_timeout = 150 if ("/fetch-all" in self.path or "/proxies/fetch" in self.path or "/sync-batch" in self.path or "/check" in self.path) else 35
            req = urllib.request.Request(backend_url, data=body, headers=headers, method=method)
            with urllib.request.urlopen(req, timeout=req_timeout) as resp:
                resp_body = resp.read()
                self.send_response(resp.status)
                for hk, hv in resp.headers.items():
                    if hk.lower() not in ["transfer-encoding", "content-length"]:
                        self.send_header(hk, hv)
                self.send_header("Content-Length", str(len(resp_body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    self.wfile.write(resp_body)
                except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                    pass
        except urllib.error.HTTPError as he:
            err_body = he.read()
            try:
                self.send_response(he.code)
                for hk, hv in he.headers.items():
                    if hk.lower() not in ["transfer-encoding", "content-length"]:
                        self.send_header(hk, hv)
                self.send_header("Content-Length", str(len(err_body)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(err_body)
            except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
                pass
        except Exception as e:
            if is_client_disconnect(e):
                return
            self.send_json(502, {
                "success": False,
                "error": "backend_unreachable",
                "message": f"Бэкенд временно недоступен: {e}"
            })


# Кастомный сервер: подавляет вывод трейсбеков при разрывах соединения клиентом
class QuietThreadingHTTPServer(ThreadingHTTPServer):
    def handle_error(self, request, client_address):
        """Не выводим трейсбеки в stderr для штатных разрывов соединения."""
        import sys as _sys
        exc = _sys.exc_info()[1]
        if is_client_disconnect(exc):
            return
        # Для реальных ошибок — стандартное поведение
        super().handle_error(request, client_address)


def main():
    enable_kill_child_processes_on_exit()
    setup_windows_console_ctrl_handler()
    import atexit
    atexit.register(stop_backend)

    print("=" * 60)
    print("         SkyBase Gateway & Watchdog Supervisor")
    print("=" * 60)
    local_ip = get_local_ip()
    if GATEWAY_PORT == 80:
        print(f"[*] Публичный шлюз:  http://0.0.0.0:80 (доступен без указания порта!)")
        print(f"[*] На этом ПК:      http://localhost/ или http://127.0.0.1/")
        print(f"[*] В локальной сети: http://{local_ip}/")
    else:
        print(f"[*] Публичный шлюз:  http://0.0.0.0:{GATEWAY_PORT}")
        print(f"[*] На этом ПК:      http://localhost:{GATEWAY_PORT}/")
        print(f"[*] В локальной сети: http://{local_ip}:{GATEWAY_PORT}/")
    print(f"[*] Основной бэкенд: http://127.0.0.1:{BACKEND_PORT}")
    print("[*] Статический каталог:", STATIC_DIR)

    # Автоматически стартуем основной сервер при запуске шлюза
    print("[*] Запуск основного бэкенда...")
    ok, msg = start_backend()
    if ok:
        print(f"[+] {msg}")
    else:
        print(f"[!] {msg}")

    # Автоматически стартуем Avito Bot
    try:
        import avito_api_helper
        if not avito_api_helper.is_bot_running():
            print("[*] Запуск Avito Bot...")
            avito_api_helper.bot_toggle("start")
    except Exception as _eb:
        print(f"[!] Ошибка запуска Avito Bot: {_eb}")

    def bot_supervisor_worker():
        while True:
            time.sleep(5)
            try:
                if backend_state != "off":
                    import avito_api_helper
                    if not avito_api_helper.is_bot_running():
                        avito_api_helper.bot_toggle("start")
            except Exception:
                pass

    threading.Thread(target=bot_supervisor_worker, daemon=True, name="BotSupervisor").start()

    server = QuietThreadingHTTPServer(("0.0.0.0", GATEWAY_PORT), GatewayHandler)
    server.daemon_threads = True

    # Если основной шлюз на порту 80, пробуем поднять параллельный слушатель на 8080 для обратной совместимости
    compat_server = None
    if GATEWAY_PORT == 80:
        try:
            compat_server = QuietThreadingHTTPServer(("0.0.0.0", 8080), GatewayHandler)
            compat_server.daemon_threads = True
            threading.Thread(target=compat_server.serve_forever, daemon=True, name="CompatGateway8080").start()
            print("[*] Дополнительный шлюз для совместимости активен на порту 8080.")
        except Exception:
            pass

    if GATEWAY_PORT == 80:
        print(f"\n[+] Сервер готов к работе без указания порта (порт 80)!")
        print("    Просто введите в браузере: 127.0.0.1 или localhost")
    else:
        print(f"\n[+] Сервер готов к работе на порту {GATEWAY_PORT}!")
    print("    Нажмите Ctrl+C для остановки.\n")

    # Автоматическое открытие страницы сайта в браузере после завершения проверок
    def bring_browser_to_front(hwnd):
        if not hwnd or sys.platform != "win32":
            return
        try:
            import ctypes
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
            # Для развернутых на весь экран (IsZoomed) ShowWindow НЕ вызываем, чтобы не сбрасывать максимизацию!
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

    def get_browser_hwnds_for_pids(pids=None):
        if sys.platform != "win32":
            return []
        try:
            import ctypes
            from ctypes import wintypes
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

            if pids is None:
                pids = set()
                try:
                    import psutil
                    for p in psutil.process_iter(['pid', 'name']):
                        pname = (p.info.get('name') or '').lower()
                        if any(b in pname for b in ['chrome', 'msedge', 'firefox', 'opera', 'brave', 'vivaldi', 'browser', 'yandex']):
                            pids.add(p.info['pid'])
                except Exception:
                    pass

            def enum_cb(hwnd, lparam):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        if not pids or pid.value in pids:
                            hwnds.append(hwnd)
                return True

            WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
            cb = WNDENUMPROC(enum_cb)
            if hdesk:
                user32.EnumDesktopWindows(hdesk, cb, 0)
            else:
                user32.EnumWindows(cb, 0)
            return hwnds
        except Exception:
            return []

    def _open_site_in_browser():
        target_url = "http://localhost/" if GATEWAY_PORT == 80 else f"http://localhost:{GATEWAY_PORT}/"
        # Ждем готовности порта шлюза (до 6 секунд)
        for _ in range(30):
            if is_port_open("127.0.0.1", GATEWAY_PORT, timeout=0.2):
                break
            time.sleep(0.2)
        time.sleep(0.5)

        print(f"[+] Автозапуск страницы в браузере: {target_url}\n")
        opened = False

        # 1. Сначала проверяем DevTools CDP (Chrome / Edge / Yandex в режиме отладки с remote debugging port)
        # Если браузер запущен с CDP (например, порт 9222), создаем гарантированно новую вкладку через PUT /json/new
        cdp_ports = [9222, 9223]
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
                v_url = f"http://127.0.0.1:{port}/json/version"
                req_v = urllib.request.Request(v_url, headers={"User-Agent": "AvitoHunterGateway"})
                with urllib.request.urlopen(req_v, timeout=0.8) as resp:
                    if resp.status == 200:
                        encoded_target = urllib.parse.quote(target_url, safe=':/?&=#')
                        new_url = f"http://127.0.0.1:{port}/json/new?{encoded_target}"
                        req_new = urllib.request.Request(new_url, method="PUT")
                        with urllib.request.urlopen(req_new, timeout=1.5) as n_resp:
                            if n_resp.status == 200:
                                tab_data = json.loads(n_resp.read().decode('utf-8'))
                                tab_id = tab_data.get('id')
                                if tab_id:
                                    try:
                                        act_req = urllib.request.Request(f"http://127.0.0.1:{port}/json/activate/{tab_id}", method="POST")
                                        urllib.request.urlopen(act_req, timeout=0.8)
                                    except Exception:
                                        pass
                                opened = True
                                print(f"[+] Новая вкладка успешно открыта в браузере через CDP (порт {port}).")
                                break
            except Exception:
                pass

        if opened:
            try:
                for h in get_browser_hwnds_for_pids():
                    bring_browser_to_front(h)
            except Exception:
                pass
            return

        # 2. Прямой запуск установленных браузеров по путям (открывает новую вкладку в уже запущенном окне)
        if sys.platform == "win32":
            browser_paths = [
                os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
                os.path.expandvars(r"%LocalAppData%\Yandex\YandexBrowser\Application\browser.exe"),
                os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
            ]
            for cand in browser_paths:
                if os.path.exists(cand):
                    try:
                        subprocess.Popen([cand, target_url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                        opened = True
                        print(f"[+] Новая вкладка открыта напрямую: {os.path.basename(cand)}")
                        break
                    except Exception:
                        pass

        # 3. Вызов через Windows Explorer (запуск от имени рабочего стола пользователя, обход UIPI)
        if not opened and sys.platform == "win32":
            try:
                subprocess.Popen(["explorer.exe", target_url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                opened = True
                print(f"[+] Новая вкладка открыта через explorer.exe.")
            except Exception:
                pass

        # 4. Модуль webbrowser Python (open_new_tab)
        if not opened:
            try:
                import webbrowser
                opened = webbrowser.open_new_tab(target_url)
                if opened:
                    print(f"[+] Новая вкладка открыта через webbrowser.open_new_tab.")
            except Exception:
                pass

        # 5. Системный вызов Windows ShellExecute (os.startfile)
        if not opened and sys.platform == "win32":
            try:
                os.startfile(target_url)
                opened = True
                print(f"[+] Браузер запущен через os.startfile.")
            except Exception:
                pass

        # 6. Вызов команды start через cmd.exe
        if not opened and sys.platform == "win32":
            try:
                subprocess.Popen(["cmd.exe", "/c", "start", "", target_url], creationflags=CREATE_NO_WINDOW)
                opened = True
                print(f"[+] Браузер запущен через cmd start.")
            except Exception:
                pass

        # Активация окна браузера на передний план
        try:
            for h in get_browser_hwnds_for_pids():
                bring_browser_to_front(h)
        except Exception:
            pass

    threading.Thread(target=_open_site_in_browser, daemon=True, name="AutoBrowserOpen").start()

    # Обработчик сигналов SIGTERM (kill, systemd stop и т.п.) — запускает тот же cleanup что и Ctrl+C
    import signal as _signal

    def _handle_signal(signum, frame):
        raise SystemExit(0)

    try:
        _signal.signal(_signal.SIGTERM, _handle_signal)
        if hasattr(_signal, "SIGBREAK"):  # Windows Ctrl+Break
            _signal.signal(_signal.SIGBREAK, _handle_signal)
    except Exception:
        pass

    try:
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        print("\n[*] Завершение работы шлюза...")
    finally:
        # Останавливаем оба HTTP-сервера перед завершением бэкенда
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass
        if compat_server:
            try:
                compat_server.shutdown()
                compat_server.server_close()
            except Exception:
                pass
        stop_backend()
        print("[+] Шлюз и бэкенд полностью остановлены.")



if __name__ == "__main__":
    main()
