#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SkyBase Control & Diagnostics Tool (ctl.py)
Оперативное управление, диагностика, авто-исправление и мониторинг сервера.
"""

import os
import sys
import time
import json
import socket
import sqlite3
import subprocess

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

try:
    import psutil
except ImportError:
    psutil = None

try:
    import requests
except ImportError:
    requests = None

SITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SITE_DIR not in sys.path:
    sys.path.insert(0, SITE_DIR)
LIB_DIR = os.path.join(SITE_DIR, "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)
GATEWAY_PORT = 80
BACKEND_PORT = 8081
PID_BACKEND = os.path.join(SITE_DIR, "backend.pid")
PID_SERVER = os.path.join(SITE_DIR, "server.pid")
PID_BOT = os.path.join(SITE_DIR, "avito_bot", "bot.pid")
PID_PROXY = os.path.join(SITE_DIR, "avito_bot", "proxy_worker.pid")
PID_LAN_PROXY = os.path.join(SITE_DIR, "lan_proxy.pid")
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

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

def get_real_python_exe():
    if not getattr(sys, 'frozen', False):
        if sys.executable.lower().endswith(("python.exe", "pythonw.exe")) and is_valid_python(sys.executable):
            return sys.executable

    env_py = os.environ.get("PYTHON_EXE")
    if env_py and is_valid_python(env_py):
        return env_py

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
            return c

    import shutil
    for name in ["python", "python3", "py"]:
        p = shutil.which(name)
        if p and is_valid_python(p):
            return p

    return sys.executable if sys.executable else "python"


def is_port_open(port, host="127.0.0.1", timeout=0.3):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


def get_process_on_port(port):
    if not psutil:
        return None
    for conn in psutil.net_connections(kind='inet'):
        if conn.laddr and conn.laddr.port == port and conn.status == psutil.CONN_LISTEN:
            try:
                return psutil.Process(conn.pid)
            except Exception:
                return None
    return None


def read_pid_file(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val.isdigit():
                    return int(val)
        except Exception:
            pass
    return None


def check_pid_alive(pid):
    if not pid or pid <= 0:
        return False
    if psutil:
        try:
            return psutil.pid_exists(pid)
        except Exception:
            pass
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, int(pid))
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        pass
    try:
        out = subprocess.check_output(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], stderr=subprocess.DEVNULL)
        return str(pid) in out.decode("cp866", errors="ignore")
    except Exception:
        return False


def cmd_status():
    print("=" * 60)
    print("      SkyBase System Status & Diagnostics")
    print("=" * 60)
    print(f"Каталог проекта: {SITE_DIR}")

    # 1. Gateway
    gw_open = is_port_open(GATEWAY_PORT)
    gw_proc = get_process_on_port(GATEWAY_PORT)
    gw_str = f"АКТИВЕН (PID {gw_proc.pid})" if (gw_open and gw_proc) else ("ОТКРЫТ" if gw_open else "ВЫКЛЮЧЕН")
    print(f"[*] Публичный шлюз (порт {GATEWAY_PORT}): {gw_str}")

    # 2. Backend
    be_open = is_port_open(BACKEND_PORT)
    be_proc = get_process_on_port(BACKEND_PORT)
    be_pid = read_pid_file(PID_BACKEND) or read_pid_file(PID_SERVER)
    be_str = f"АКТИВЕН (PID {be_proc.pid if be_proc else be_pid})" if be_open else "ВЫКЛЮЧЕН"
    print(f"[*] Основной бэкенд (порт {BACKEND_PORT}): {be_str}")

    # 3. HTTP Power State
    if gw_open:
        try:
            if requests:
                r = requests.get(f"http://127.0.0.1:{GATEWAY_PORT}/api/server/power-state", timeout=1)
                data = r.json()
                print(f"[*] Статус питания через API: {data.get('state', 'unknown')}")
        except Exception as e:
            print(f"[!] Ошибка запроса power-state: {e}")

    # 4. Avito Bot
    bot_pid = read_pid_file(PID_BOT)
    bot_alive = check_pid_alive(bot_pid)
    print(f"[*] Telegram Avito Bot:  {'АКТИВЕН (PID ' + str(bot_pid) + ')' if bot_alive else 'ОСТАНОВЛЕН'}")

    # 5. Proxy Worker
    proxy_pid = read_pid_file(PID_PROXY)
    proxy_alive = check_pid_alive(proxy_pid)
    print(f"[*] Воркер пула прокси:   {'АКТИВЕН (PID ' + str(proxy_pid) + ')' if proxy_alive else 'ОСТАНОВЛЕН'}")


    db_bot = os.path.join(SITE_DIR, "avito_bot", "avito_bot.db")
    if os.path.exists(db_bot):
        try:
            con = sqlite3.connect(db_bot)
            cur = con.cursor()
            cur.execute("PRAGMA quick_check")
            check = cur.fetchone()[0]
            con.close()
            print(f"[*] База бота Avito:      OK (integrity: {check})")
        except Exception as e:
            print(f"[!] База бота Avito:      ОШИБКА: {e}")

    # 7. System Resources
    if psutil:
        mem = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=0.1)
        print(f"[*] Нагрузка системы:     CPU: {cpu}%, RAM свободно: {mem.available // (1024*1024)} MB из {mem.total // (1024*1024)} MB")
    print("=" * 60)


def cmd_fix():
    print("=== [FIX] Диагностика и авто-исправление ===")
    fixes = 0

    # 1. Проверка чистого Python-бэкенда server.py (SkyBase v2.0)
    server_py = os.path.join(SITE_DIR, "server.py")
    if os.path.exists(server_py):
        try:
            import py_compile
            py_compile.compile(server_py, doraise=True)
            print("[OK] SkyBase v2 Python backend (server.py) синтаксически корректен и не требует BOM.")
        except Exception as e:
            print(f"[ERR] Синтаксическая ошибка в server.py: {e}")

    # Резервная проверка устаревшего server.ps1 (если присутствует)
    ps1 = os.path.join(SITE_DIR, "server.ps1")
    if os.path.exists(ps1):
        with open(ps1, "rb") as f:
            head = f.read(3)
        if head != b"\xef\xbb\xbf":
            print(f"[FIX] Добавление UTF-8 BOM в {ps1}...")
            with open(ps1, "rb") as f:
                data = f.read()
            with open(ps1, "wb") as f:
                f.write(b"\xef\xbb\xbf" + data)
            fixes += 1
            print("[OK] UTF-8 BOM добавлен.")
        else:
            print("[OK] server.ps1 имеет корректный UTF-8 BOM.")

    # 2. Проверка синтаксиса server.ps1
    ps_check_code = f"""
$e = $null
$null = [System.Management.Automation.Language.Parser]::ParseFile('{ps1}', [ref]$null, [ref]$e)
if ($e) {{
    $e | ForEach-Object {{ $_.ToString() }}
}}
"""
    try:
        res = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_check_code],
            capture_output=True, encoding="utf-8", errors="replace"
        )
        out = (res.stdout or "").strip()
        if out:
            print(f"[ERR] Синтаксические ошибки в server.ps1:\n{out}")
        else:
            print("[OK] server.ps1 синтаксически корректен (0 ошибок).")
    except Exception as ex:
        print(f"[WARN] Ошибка проверки синтаксиса: {ex}")

    # 3. Валидация JSON-файлов
    for jf in ["data/users.json", "data/chat_messages.json", "manifest.json"]:
        jp = os.path.join(SITE_DIR, jf.replace("/", os.sep))
        if os.path.exists(jp):
            try:
                with open(jp, "r", encoding="utf-8-sig") as f:
                    json.load(f)
                print(f"[OK] {jf} корректный JSON.")
            except Exception as e:
                print(f"[ERR] Ошибка в {jf}: {e}")

    # 4. Проверка и очистка невалидных PID-файлов
    for pf in [PID_BACKEND, PID_SERVER, PID_BOT, PID_PROXY]:
        pid = read_pid_file(pf)
        if pid and psutil and not psutil.pid_exists(pid):
            try:
                os.remove(pf)
                fixes += 1
                print(f"[FIX] Удален устаревший PID-файл {os.path.basename(pf)} (PID {pid} не активен).")
            except Exception:
                pass

    # 6. Проверка и автоустановка Python-библиотек (Avito Bot & Sniper Playwright)
    required_libs = ["aiogram", "curl_cffi", "bs4", "aiosqlite", "aiohttp_socks", "PIL", "playwright"]
    missing = []
    for lib in required_libs:
        try:
            __import__(lib)
        except ImportError:
            missing.append(lib)
    if missing:
        print(f"[FIX] Отсутствуют библиотеки: {', '.join(missing)}. Запуск автоустановки...")
        req_file = os.path.join(SITE_DIR, "avito_bot", "requirements.txt")
        pkgs_dir = os.path.join(SITE_DIR, "avito_bot", "installer", "packages")
        try:
            if os.path.exists(pkgs_dir):
                subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", f"--find-links={pkgs_dir}", "-r", req_file], check=True)
            else:
                subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file], check=True)
            fixes += 1
            print("[OK] Все недостающие библиотеки успешно установлены.")
        except Exception as e:
            print(f"[ERR] Ошибка автоустановки библиотек: {e}")
    else:
        print("[OK] Все необходимые библиотеки Python установлены.")

    print(f"=== Исправление завершено. Внесено исправлений: {fixes} ===")


def kill_port_processes(port):
    """Принудительно освобождает порт, завершая ТОЛЬКО процессы нашего сервера (Python/PowerShell)."""
    try:
        current_pid = os.getpid()
        out = subprocess.check_output("netstat -ano -p tcp", shell=True, text=True, stderr=subprocess.DEVNULL)
        target_pids = set()
        for line in out.splitlines():
            line = line.strip()
            if "LISTENING" in line:
                parts = line.split()
                if len(parts) >= 5:
                    local_addr = parts[1]
                    pid_str = parts[-1]
                    if local_addr.endswith(f":{port}") and pid_str.isdigit():
                        p = int(pid_str)
                        if p > 4 and p != current_pid:
                            target_pids.add(p)

        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        for p in target_pids:
            pname = ""
            try:
                h_proc = kernel32.OpenProcess(0x1000, False, p)
                if h_proc:
                    buf = ctypes.create_unicode_buffer(1024)
                    size = wintypes.DWORD(1024)
                    if kernel32.QueryFullProcessImageNameW(h_proc, 0, buf, ctypes.byref(size)):
                        pname = os.path.basename(buf.value).lower()
                    kernel32.CloseHandle(h_proc)
            except Exception:
                pass

            # Завершаем ТОЛЬКО процессы Python или PowerShell, никогда не трогая другие приложения пользователя
            if any(target in pname for target in ["python", "powershell", "pwsh"]):
                try:
                    subprocess.run(["taskkill", "/F", "/PID", str(p)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except Exception:
                    pass
    except Exception:
        pass


def cmd_stop():
    print("[*] Остановка всех служб SkyBase...")
    # 1. HTTP shutdown шлюза и бэкенда
    for p in [GATEWAY_PORT, 8080, BACKEND_PORT]:
        try:
            import urllib.request
            req = urllib.request.Request(f"http://127.0.0.1:{p}/api/server/shutdown", data=b"{}", headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=0.8)
        except Exception:
            pass

    # 2. Остановка Telegram-бота Avito
    bot_pid = read_pid_file(PID_BOT)
    if bot_pid:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(bot_pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass
    try:
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*avito_bot*bot.py*' -or $_.CommandLine -like '*bot.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        pass

    # 3. Остановка фонового сборщика прокси (proxy_worker)
    proxy_pid = read_pid_file(PID_PROXY)
    if proxy_pid:
        try:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proxy_pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass
    try:
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*proxy_worker.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        pass

    # 4. Остановка PowerShell процессов running server.ps1
    try:
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command", "Get-CimInstance Win32_Process | Where-Object { $_.Name -like '*powershell*' -and $_.CommandLine -like '*server.ps1*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW
        )
    except Exception:
        pass

    # 5. Освобождение портов 80, 8080, 8081
    for p in [80, 8080, BACKEND_PORT]:
        kill_port_processes(p)
    if psutil:
        for p in [80, 8080, BACKEND_PORT]:
            proc = get_process_on_port(p)
            if proc and proc.pid != 4:
                try:
                    proc.terminate()
                    proc.wait(timeout=1)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass

    # 6. Очистка всех PID-файлов
    for pf in [PID_BACKEND, PID_SERVER, PID_BOT, PID_PROXY, PID_LAN_PROXY]:
        if os.path.exists(pf):
            try:
                os.remove(pf)
            except Exception:
                pass
    time.sleep(0.3)
    print("[+] Все службы и фоновые процессы SkyBase полностью остановлены.")



def cmd_start():
    cmd_fix()
    print("[*] Запуск SkyBase Gateway & Backend...")
    if is_port_open(GATEWAY_PORT):
        print(f"[!] Порт {GATEWAY_PORT} уже занят. Выполняем предварительную остановку...")
        cmd_stop()

    gw_script = os.path.join(SITE_DIR, "gateway.py")
    CREATE_NO_WINDOW = 0x08000000
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000
    flags = (CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB) if sys.platform == "win32" else 0

    real_py = get_real_python_exe()
    gw_env = os.environ.copy()
    gw_env["PYTHON_EXE"] = real_py
    try:
        p = subprocess.Popen(
            [real_py, gw_script],
            cwd=SITE_DIR,
            env=gw_env,
            creationflags=flags,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True
        )
    except PermissionError:
        flags_safe = (CREATE_NO_WINDOW | DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP) if sys.platform == "win32" else 0
        p = subprocess.Popen(
            [real_py, gw_script],
            cwd=SITE_DIR,
            env=gw_env,
            creationflags=flags_safe,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True
        )
    print(f"[*] Шлюз запущен (PID {p.pid}). Ожидание готовности API...")

    ready = False
    for i in range(30):
        time.sleep(0.4)
        if (is_port_open(80) or is_port_open(8080)) and is_port_open(BACKEND_PORT):
            ready = True
            break

    if ready:
        active_gw = 80 if is_port_open(80) else 8080
        print(f"[+] Сервер успешно запущен и готов к работе!")
        if active_gw == 80:
            print(f"    На этом ПК:      http://localhost/ или http://127.0.0.1/ (без порта!)")
        else:
            print(f"    На этом ПК:      http://localhost:{active_gw}/")
        print(f"    Внутренний порт: http://127.0.0.1:{BACKEND_PORT}/")
    else:
        print("[!] Сервер запущен, но готовность не подтверждена. Проверьте server_run.log.")


def cmd_restart():
    cmd_stop()
    cmd_start()


def cmd_test():
    print("=== [TEST] Экспресс-тестирование сервисов ===")
    endpoints = [
        ("GET", f"http://127.0.0.1:{GATEWAY_PORT}/", "Статическая главная страница"),
        ("GET", f"http://127.0.0.1:{GATEWAY_PORT}/api/server/power-state", "Статус питания шлюза"),
        ("GET", f"http://127.0.0.1:{GATEWAY_PORT}/api/users", "Список пользователей"),
        ("GET", f"http://127.0.0.1:{GATEWAY_PORT}/api/chat/messages?username=guest", "Сообщения чата"),
        ("GET", f"http://127.0.0.1:{GATEWAY_PORT}/api/avito/stats", "Статистика Avito"),
    ]

    all_ok = True
    for method, url, desc in endpoints:
        t0 = time.time()
        try:
            if requests:
                r = requests.request(method, url, timeout=4)
                code = r.status_code
            else:
                import urllib.request
                req = urllib.request.Request(url, method=method)
                with urllib.request.urlopen(req, timeout=4) as resp:
                    code = resp.getcode()
            dt = int((time.time() - t0) * 1000)
            if code < 400:
                print(f"  [OK] {desc} -> HTTP {code} ({dt}ms)")
            else:
                print(f"  [FAIL] {desc} -> HTTP {code} ({dt}ms)")
                all_ok = False
        except Exception as e:
            dt = int((time.time() - t0) * 1000)
            print(f"  [ERR] {desc} -> Ошибка ({e})")
            all_ok = False

    if all_ok:
        print("[+] Все тесты пройдены успешно!")
    else:
        print("[!] Часть тестов завершилась с ошибкой.")


def cmd_logs(n=30):
    log_files = [
        os.path.join(SITE_DIR, "server_run.log"),
        os.path.join(SITE_DIR, "bot_err.log"),
        os.path.join(SITE_DIR, "avito_bot", "bot.log")
    ]
    for lp in log_files:
        if os.path.exists(lp):
            print(f"\n=== {os.path.basename(lp)} (последние {n} строк) ===")
            try:
                with open(lp, "r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()
                for line in lines[-int(n):]:
                    print("  " + line.rstrip())
            except Exception as e:
                print(f"  Ошибка чтения: {e}")


def main():
    if len(sys.argv) < 2:
        cmd_status()
        print("\nИспользование: python tools/ctl.py [status|start|stop|restart|fix|test|logs [N]]")
        return

    cmd = sys.argv[1].lower()
    if cmd in ("status", "info"):
        cmd_status()
    elif cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    elif cmd == "restart":
        cmd_restart()
    elif cmd in ("fix", "repair"):
        cmd_fix()
    elif cmd in ("test", "ping"):
        cmd_test()
    elif cmd in ("monitor", "watch", "live"):
        from tools import live_logger
        live_logger.main()
    elif cmd == "logs":
        if len(sys.argv) > 2 and sys.argv[2] in ("-f", "--follow", "live", "watch"):
            from tools import live_logger
            live_logger.main()
        else:
            n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 30
            cmd_logs(n)
    elif cmd == "backup":
        from tools import updater
        ok, res = updater.create_recovery_snapshot("manual_user_backup")
        print(f"[{'OK' if ok else 'ERR'}] {res}")
    elif cmd == "restore":
        from tools import updater
        snap = sys.argv[2] if len(sys.argv) > 2 else ""
        b_dir = os.path.join(SITE_DIR, "data", "backups")
        if not snap:
            snaps = [d for d in os.listdir(b_dir) if os.path.isdir(os.path.join(b_dir, d))] if os.path.exists(b_dir) else []
            print("Укажите имя снимка. Доступные точки восстановления в data/backups/:")
            for s in snaps:
                print(f"  - {s}")
            return
        snap_path = snap if os.path.isabs(snap) else os.path.join(b_dir, snap)
        ok, res = updater.restore_snapshot(snap_path)
        print(f"[{'OK' if ok else 'ERR'}] {res}")
    elif cmd == "update":
        from tools import updater
        pkg = sys.argv[2] if len(sys.argv) > 2 else ""
        if not pkg:
            print("Укажите путь к ZIP-архиву или папке обновления:")
            print("  python tools/ctl.py update <путь_к_обновлению.zip>")
            return
        res = updater.apply_update_package(pkg)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print(f"Неизвестная команда: {cmd}")
        print("Доступные команды: status, start, stop, restart, fix, test, logs, monitor, backup, restore, update")


if __name__ == "__main__":
    main()