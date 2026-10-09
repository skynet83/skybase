import re

with open(r'C:\ins\skybase\app_launcher.py', 'r', encoding='utf-8') as f:
    src = f.read()

old_cleanup = '''    def emergency_cleanup(self):
        """Гарантированное завершение всех дочерних процессов при выходе."""
        if getattr(self, '_cleaned_up', False):
            return
        self._cleaned_up = True
        CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

        # 1. Завершение через центральный контроллер ctl.py
        try:
            ctl_script = os.path.join(SITE_DIR, "tools", "ctl.py")
            py_exe = get_real_python_exe()
            if os.path.exists(ctl_script):
                subprocess.run([py_exe, ctl_script, "stop"], cwd=SITE_DIR, timeout=7, creationflags=CREATE_NO_WINDOW)
        except Exception:
            pass

        # 2. Гарантированное завершение процесса шлюза и всех его дочерних процессов
        if self.server_process and self.server_process.poll() is None:
            try:
                if sys.platform == "win32":
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.server_process.pid)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                else:
                    self.server_process.terminate()
            except Exception:
                pass

        # 3. Прямая зачистка всех известных PID-файлов и связанных деревьев процессов
        for pid_file in [
            os.path.join(SITE_DIR, "avito_bot", "bot.pid"),
            os.path.join(SITE_DIR, "avito_bot", "proxy_worker.pid"),
            os.path.join(SITE_DIR, "backend.pid"),
            os.path.join(SITE_DIR, "server.pid"),
            os.path.join(SITE_DIR, "lan_proxy.pid")
        ]:
            if os.path.exists(pid_file):
                try:
                    with open(pid_file, "r", encoding="utf-8") as f:
                        val = f.read().strip()
                    if val.isdigit() and int(val) > 4:
                        subprocess.run(["taskkill", "/F", "/T", "/PID", val],
                                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW)
                    os.remove(pid_file)
                except Exception:
                    pass

        # 4. Освобождение сетевых портов 80, 8080, 8081 от любых оставшихся слушателей
        for port in [80, 8080, 8081]:
            try:
                if sys.platform == "win32":
                    ps_free = f"Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | Where-Object {{ $_ -gt 4 }} | ForEach-Object {{ Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }}"
                    subprocess.run(["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command", ps_free],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=CREATE_NO_WINDOW, timeout=3)
            except Exception:
                pass'''

new_cleanup = '''    def emergency_cleanup(self):
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
                pass'''

if old_cleanup in src:
    src = src.replace(old_cleanup, new_cleanup)
    print("cleanup: REPLACED OK")
else:
    print("cleanup: NOT FOUND - trying partial match")
    # Show first 200 chars of actual content around line 1288
    lines = src.splitlines()
    print('\n'.join(lines[1287:1295]))

with open(r'C:\ins\skybase\app_launcher.py', 'w', encoding='utf-8') as f:
    f.write(src)
print("File written.")
