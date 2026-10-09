"""
ElectroBase Dev Tools - Профессиональный инструментарий разработчика ElectroBase
Команды:
  python tools/dev.py sync           - Быстрая синхронизация между E:\\TEMP и C:\\ins
  python tools/dev.py check          - Полная проверка: PowerShell AST, UTF-8 BOM, JS скобки, JSON
  python tools/dev.py restart        - Безопасный перезапуск сервера на 8080 с проверкой
  python tools/dev.py test           - Экспресс-тест API и статики
  python tools/dev.py search <query> - Компактный поиск по ключевым файлам проекта
  python tools/dev.py func <имя>     - Точные границы функции (строки start..end) и просмотр
  python tools/dev.py funcs [filter] - Список всех функций js/app.js с номерами строк
  python tools/dev.py routes         - Каталог всех API маршрутов server.ps1 с номерами строк
  python tools/dev.py users          - Состояние пользователей, ролей, тарифов и лимитов
  python tools/dev.py db <sql>       - Мгновенный SQL-запрос к базе деталей store.sqlite
  python tools/dev.py logs [N]       - Просмотр последних N строк лога сервера
  python tools/dev.py backup         - Создание локального слепка .bak/ перед правками
  python tools/dev.py db-backup      - Горячее резервное копирование баз SQLite и users.json
  python tools/dev.py diff           - Просмотр только измененных строк относительно .bak/
  python tools/dev.py rollback       - Мгновенный откат всех файлов из .bak/
  python tools/dev.py api <url> [f]  - Точечный запрос к API с фильтрацией поля
"""

import sys
import os
import re
import json
import time
import shutil
import hashlib
import sqlite3
import subprocess
import urllib.request
import urllib.error

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

SITE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PRIMARY_MIRRORS = [
    r"C:\ins\EXP\Arduino\Проект\База-бот\SITE",
    r"C:\ins\общий\База-бот\SITE"
]
TARGET_MIRRORS = [
    p for p in PRIMARY_MIRRORS
    if os.path.exists(p) and os.path.abspath(SITE_DIR).lower() != os.path.abspath(p).lower()
]
if not TARGET_MIRRORS:
    if os.path.exists(r"D:\TEMP\SITE") and os.path.abspath(SITE_DIR).lower() != os.path.abspath(r"D:\TEMP\SITE").lower():
        TARGET_MIRRORS.append(r"D:\TEMP\SITE")

COMBAT_DIR = TARGET_MIRRORS[0] if TARGET_MIRRORS else SITE_DIR
ALT_DIR = COMBAT_DIR
PATH_E = SITE_DIR
PATH_C = ALT_DIR

CORE_FILES = [
    "server.ps1",
    "index.html",
    "css/style.css",
    "manifest.json",
    "sw.js",
    "js/app.js",
    "data/users.json",
    "data/chat_messages.json",
    "data/radio_components.json",
    "tools/dev.py",
    "tools/schema.json",
    "GEMINI.md",
    "gateway.py",
    "start_server.bat",
    "start_server.sh",
    "install_service.sh",
    "DEBIAN_GUIDE.md",
    "avito_api_helper.py",
    "avito_bot/config.py",
    "avito_bot/bot.py",
    "avito_bot/database.py",
    "avito_bot/parser.py",
    "avito_bot/proxy_worker.py",
    "avito_bot/monitor_state.json",
    "avito_bot/proxies.txt",
    "tools/ngrok_service.py"
]

def get_db_path():
    for base in [PATH_E, PATH_C]:
        for sub in [r"data\store.sqlite", r"Base деталей\Base\store.sqlite", r"База деталей\Base\store.sqlite"]:
            p = os.path.join(base, sub)
            if os.path.exists(p):
                return p
    return None

def get_hash(fpath):
    if not os.path.exists(fpath):
        return None
    with open(fpath, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def sync_users_data(path_e, path_c):
    """Сливает пользователей и поисковые ссылки между E и C без потерь данных."""
    p_e = os.path.join(path_e, "data", "users.json")
    p_c = os.path.join(path_c, "data", "users.json")
    if not os.path.exists(p_e) and not os.path.exists(p_c):
        return False
    if not os.path.exists(p_e):
        shutil.copy2(p_c, p_e)
        return True
    if not os.path.exists(p_c):
        shutil.copy2(p_e, p_c)
        return True

    def load_users(p):
        try:
            with open(p, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
                return data if isinstance(data, list) else []
        except Exception:
            return []

    users_e = {u.get("username"): u for u in load_users(p_e) if u.get("username")}
    users_c = {u.get("username"): u for u in load_users(p_c) if u.get("username")}
    all_usernames = list(dict.fromkeys(list(users_e.keys()) + list(users_c.keys())))

    merged_users = []
    for uname in all_usernames:
        ue = users_e.get(uname, {})
        uc = users_c.get(uname, {})

        # Данные боевого сервера C приоритетнее для runtime-статусов
        base = dict(ue)
        base.update(uc)

        perms = dict(ue.get("permissions", {}))
        perms.update(uc.get("permissions", {}))
        base["permissions"] = perms

        # Ссылки поиска сливаем без дубликатов по url/id
        searches_e = ue.get("avito_searches", []) or []
        searches_c = uc.get("avito_searches", []) or []
        merged_searches = []
        seen_keys = set()
        for s in (searches_c + searches_e):
            s_key = s.get("url") or s.get("id")
            if s_key and s_key not in seen_keys:
                seen_keys.add(s_key)
                merged_searches.append(s)
        base["avito_searches"] = merged_searches
        merged_users.append(base)

    content = json.dumps(merged_users, ensure_ascii=False, indent=2)
    changed = False
    for p in [p_e, p_c]:
        try:
            old = ""
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8-sig") as f:
                    old = f.read()
            if old.strip() != content.strip():
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                changed = True
        except Exception as err:
            print(f"[WARN] Ошибка сохранения {p}: {err}")
    return changed

def cmd_sync(direction="auto"):
    """Синхронизирует файлы между рабочей директорией и всеми боевыми зеркалами."""
    print("=== [SYNC] Синхронизация репозиториев ===")
    mirrors = TARGET_MIRRORS if TARGET_MIRRORS else [PATH_C]

    total_synced_count = 0
    for dst_dir in mirrors:
        src_dir = PATH_E
        if direction == "c2e":
            src_dir, dst_dir = dst_dir, PATH_E

        synced = []

        # 1. Безопасная синхронизация пользовательских данных (слияние без потерь)
        if sync_users_data(PATH_E, dst_dir):
            synced.append("data/users.json (безопасное слияние)")

        # 2. Чат: сохраняем более свежий
        p_chat_e = os.path.join(PATH_E, "data", "chat_messages.json")
        p_chat_c = os.path.join(dst_dir, "data", "chat_messages.json")
        if os.path.exists(p_chat_c) and os.path.exists(p_chat_e):
            if os.path.getmtime(p_chat_c) > os.path.getmtime(p_chat_e) and get_hash(p_chat_c) != get_hash(p_chat_e):
                shutil.copy2(p_chat_c, p_chat_e)
                synced.append("data/chat_messages.json (C->E)")
            elif os.path.getmtime(p_chat_e) > os.path.getmtime(p_chat_c) and get_hash(p_chat_e) != get_hash(p_chat_c):
                shutil.copy2(p_chat_e, p_chat_c)
                synced.append("data/chat_messages.json (E->C)")

        # 3. Исходный код и ресурсы (пропускаем файлы runtime-данных, обработанные выше)
        skip_data_files = {"data/users.json", "data/chat_messages.json"}
        for rel in CORE_FILES:
            if rel in skip_data_files:
                continue
            p_src = os.path.join(src_dir, rel.replace("/", "\\"))
            p_dst = os.path.join(dst_dir, rel.replace("/", "\\"))
            h_src = get_hash(p_src)
            h_dst = get_hash(p_dst)
            if h_src and h_src != h_dst:
                os.makedirs(os.path.dirname(p_dst), exist_ok=True)
                shutil.copy2(p_src, p_dst)
                synced.append(rel)

        img_src_dir = os.path.join(src_dir, "img")
        if os.path.exists(img_src_dir):
            for img in os.listdir(img_src_dir):
                rel = f"img/{img}"
                p_src = os.path.join(src_dir, rel.replace("/", "\\"))
                p_dst = os.path.join(dst_dir, rel.replace("/", "\\"))
                if os.path.isfile(p_src) and get_hash(p_src) != get_hash(p_dst):
                    os.makedirs(os.path.dirname(p_dst), exist_ok=True)
                    shutil.copy2(p_src, p_dst)
                    synced.append(rel)

        if synced:
            print(f"[OK] {dst_dir}: синхронизировано {len(synced)} файлов: {', '.join(synced)}")
            total_synced_count += len(synced)
        else:
            print(f"[OK] {dst_dir}: файлы уже актуальны.")

    if total_synced_count == 0:
        print("[OK] Все зеркала уже идеально синхронизированы.")

def validate_js_syntax(filepath):
    """Проверяет синтаксис JS через AST-анализатор esprima."""
    if not os.path.exists(filepath):
        return [f"Файл {filepath} не найден"]
    try:
        import esprima
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            raw = f.read()
        # Преобразуем операторы ES2020 (?., ??) для совместимости с парсером
        sanitized = re.sub(r'\?\.', '.', raw)
        sanitized = re.sub(r'\?\?', '||', sanitized)
        tree = esprima.parseScript(sanitized, {'tolerant': True})
        if tree.errors:
            return [f"Строка {e.lineNumber}, колонка {e.column}: {e.description}" for e in tree.errors]
        return []
    except Exception as e:
        return [str(e)]

def cmd_check():
    """Проверяет целостность, BOM и синтаксис файлов."""
    print("=== [CHECK] Проверка синтаксиса и кодировок ===")
    errors = 0

    # 1. Проверка UTF-8 BOM для server.ps1
    for base in [PATH_E, PATH_C]:
        ps_path = os.path.join(base, "server.ps1")
        if os.path.exists(ps_path):
            with open(ps_path, "rb") as f:
                header = f.read(3)
            if header != b"\xef\xbb\xbf":
                print(f"[WARN] server.ps1 в {base} без UTF-8 BOM! Добавляем...")
                with open(ps_path, "rb") as f:
                    content = f.read()
                with open(ps_path, "wb") as f:
                    f.write(b"\xef\xbb\xbf" + content)
                print(f"[FIXED] UTF-8 BOM добавлен в {ps_path}")

    # 2. Синтаксический анализ PowerShell
    ps_file = os.path.join(PATH_C, "server.ps1")
    if os.path.exists(ps_file):
        ps_cmd = (
            f"$e = $null; "
            f"[System.Management.Automation.PSParser]::Tokenize("
            f"(Get-Content '{ps_file}' -Raw -Encoding UTF8), [ref]$e) | Out-Null; "
            f"if ($e.Count -gt 0) {{ $e | ForEach-Object {{ Write-Host $_ }} }} else {{ Write-Host 'PS_OK' }}"
        )
        res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True)
        if "PS_OK" not in res.stdout:
            print(f"[ERR] Ошибка синтаксиса server.ps1:\n{res.stdout}\n{res.stderr}")
            errors += 1
        else:
            print("[OK] Синтаксис server.ps1: корректен")

    # 3. Синтаксический анализ JS скобок
    js_file = os.path.join(PATH_E, "js", "app.js")
    js_errs = validate_js_syntax(js_file)
    if js_errs:
        for err in js_errs[:5]:
            print(f"[ERR JS] {err}")
        errors += len(js_errs)
    else:
        print("[OK] Синтаксис скобок и строк js/app.js: корректен")

    # 4. Валидация JSON
    for jf in ["data/users.json", "data/radio_components.json"]:
        full_p = os.path.join(PATH_C, jf.replace("/", "\\"))
        if os.path.exists(full_p):
            try:
                with open(full_p, "r", encoding="utf-8-sig") as f:
                    json.load(f)
                print(f"[OK] JSON {jf}: валиден")
            except Exception as e:
                print(f"[ERR] Ошибка в {jf}: {e}")
                errors += 1

    # 5. Валидация HTML структуры
    html_file = os.path.join(PATH_E, "index.html")
    if os.path.exists(html_file):
        try:
            from bs4 import BeautifulSoup
            with open(html_file, "r", encoding="utf-8", errors="ignore") as f:
                soup = BeautifulSoup(f.read(), "html.parser")
            ids = [tag["id"] for tag in soup.find_all(id=True)]
            seen = set()
            dupes = set()
            for i in ids:
                if i in seen:
                    dupes.add(i)
                seen.add(i)
            if dupes:
                print(f"[WARN HTML] Найдены дублирующиеся ID: {', '.join(list(dupes)[:5])}")
            else:
                print(f"[OK] index.html: валиден ({len(ids)} уникальных ID элементов)")
        except Exception as e:
            print(f"[WARN HTML] {e}")

    # 6. Валидация CSS
    css_file = os.path.join(PATH_E, "css", "style.css")
    if os.path.exists(css_file):
        try:
            with open(css_file, "r", encoding="utf-8", errors="ignore") as f:
                c_txt = f.read()
            open_b = c_txt.count("{")
            close_b = c_txt.count("}")
            if open_b != close_b:
                print(f"[ERR CSS] Дисбаланс фигурных скобок в style.css: открыто {open_b}, закрыто {close_b}")
                errors += 1
            else:
                print(f"[OK] CSS style.css: скобки сбалансированы ({open_b} правил)")
        except Exception as e:
            print(f"[WARN CSS] {e}")

    # 7. Валидация Python модулей
    py_files = ["avito_api_helper.py", "tools/dev.py", "avito_bot/bot.py", "avito_bot/parser.py", "avito_bot/database.py", "avito_bot/config.py"]
    py_errors = 0
    for pf in py_files:
        full_pf = os.path.join(PATH_E, pf.replace("/", "\\"))
        if os.path.exists(full_pf):
            try:
                with open(full_pf, "r", encoding="utf-8") as f:
                    compile(f.read(), full_pf, "exec")
            except Exception as pe:
                print(f"[ERR PY] Синтаксическая ошибка в {pf}: {pe}")
                py_errors += 1
    if py_errors == 0:
        print(f"[OK] Python модули: проверено {len(py_files)} файлов, синтаксис корректен")
    else:
        errors += py_errors

    if errors == 0:
        print("[SUCCESS] Все проверки пройдены без ошибок!")
    return errors == 0

def cmd_routes(filt=None, show=False):
    """Каталог всех API маршрутов в server.ps1 с номерами строк."""
    print("=== [ROUTES] API маршруты в server.ps1 ===")
    ps_file = os.path.join(PATH_E, "server.ps1")
    if not os.path.exists(ps_file):
        return
    with open(ps_file, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    
    pat = re.compile(r'(\$request\.HttpMethod\s+-eq\s+"(\w+)"|\$request\.HttpMethod\s+-in\s+@\([^)]+\)).*?(\$localPath\s+-eq\s+"([^"]+)"|\$localPath\s+-like\s+"([^"]+)")')
    pat_comment = re.compile(r'#\s*API:\s*(.+)')

    curr_desc = ""
    routes = []
    for idx, line in enumerate(lines, start=1):
        m_comm = pat_comment.search(line)
        if m_comm:
            curr_desc = m_comm.group(1).strip()
        m = pat.search(line)
        if m:
            route = m.group(4) or m.group(5) or "unknown"
            method = m.group(2) if m.group(2) else "GET/POST"
            desc = f" ({curr_desc})" if curr_desc else ""
            if not filt or filt.lower() in route.lower() or filt.lower() in desc.lower() or filt.lower() in method.lower():
                routes.append((idx, method, route, desc))
            curr_desc = ""

    for idx, method, route, desc in routes:
        print(f"  Строка {idx:4d} | {method:7s} {route:<30s}{desc}")

    if show and routes:
        target_idx = routes[0][0]
        end_idx = len(lines)
        brace_count = 0
        started = False
        for j in range(target_idx - 1, len(lines)):
            l = lines[j]
            brace_count += l.count('{') - l.count('}')
            if '{' in l:
                started = True
            if started and brace_count <= 0:
                end_idx = j + 1
                break
        print(f"\n--- [HANDLER] {routes[0][2]} (строки {target_idx}..{end_idx}) ---")
        for k in range(target_idx - 1, min(end_idx, target_idx + 80)):
            print(f"{k + 1:4d}: {lines[k].rstrip()}")

def cmd_funcs(filt=None, target_file="js/app.js"):
    """Список функций с номерами строк (поддерживает js/app.js, py и ps1)."""
    full_path = os.path.join(PATH_E, target_file.replace("/", os.sep))
    if not os.path.exists(full_path):
        print(f"[ERR] Файл {target_file} не найден!")
        return
    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    ext = os.path.splitext(target_file)[1].lower()
    if ext == ".ps1":
        pat = re.compile(r'^\s*function\s+([a-zA-Z0-9_-]+)', re.IGNORECASE)
    elif ext == ".py":
        pat = re.compile(r'^\s*(?:async\s+)?def\s+([a-zA-Z0-9_]+)\s*\(')
    else:
        pat = re.compile(r'^\s*(?:async\s+)?function\s+([a-zA-Z0-9_$]+)\s*\(|^\s*(?:const|let|var|window\.)([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[a-zA-Z0-9_$]+)\s*=>|^\s*(?:const|let|var)\s+([a-zA-Z0-9_$]+)\s*=\s*(?:async\s*)?function')

    matches = 0
    for idx, line in enumerate(lines, start=1):
        m = pat.search(line)
        if m:
            fname = next((g for g in m.groups() if g), None)
            if fname and (not filt or filt.lower() in fname.lower()):
                matches += 1
                print(f"  Строка {idx:4d} | {fname}")
                if matches >= 50 and not filt:
                    print("  ... (укажите фильтр: python tools/dev.py funcs <подстрока> [файл])")
                    break
    if matches == 0:
        print(f"  Функции{' с фильтром ' + repr(filt) if filt else ''} не найдены в {target_file}")

def cmd_dom(filt=None):
    """Быстрый поиск ключевых элементов интерфейса в index.html."""
    html_p = os.path.join(PATH_E, "index.html")
    if not os.path.exists(html_p):
        return
    with open(html_p, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    print("=== [DOM] Элементы интерфейса в index.html ===")
    pat = re.compile(r'<(div|button|section|modal|form|input|select|nav|tab)\s+[^>]*id=["\']([^"\']+)["\']', re.IGNORECASE)
    matches = 0
    for idx, l in enumerate(lines, start=1):
        m = pat.search(l)
        if m:
            tag, elem_id = m.group(1), m.group(2)
            if not filt or filt.lower() in elem_id.lower() or filt.lower() in l.lower():
                matches += 1
                snippet = l.strip()[:80]
                print(f"  Строка {idx:4d} | <{tag} id=\"{elem_id}\">  {snippet}")
                if matches >= 40 and not filt:
                    print("  ... (укажите фильтр: python tools/dev.py dom <подстрока>)")
                    break
    if matches == 0:
        print(f"  Элементы DOM{' с фильтром ' + repr(filt) if filt else ''} не найдены.")

def cmd_trace(query):
    """Архитектурный поиск вхождения query по стеку: index.html -> js/app.js -> server.ps1 -> avito_api_helper.py."""
    print(f"=== [TRACE] Архитектурная трассировка '{query}' ===")
    targets = [
        ("index.html", "HTML / DOM разметка"),
        ("js/app.js", "JS клиентская логика"),
        ("server.ps1", "PowerShell бэкенд / API"),
        ("avito_api_helper.py", "Python API хелпер"),
        ("avito_bot/bot.py", "Telegram Bot"),
        ("avito_bot/database.py", "База данных бота")
    ]
    total_found = 0
    for rel, desc in targets:
        full_p = os.path.join(PATH_E, rel.replace("/", os.sep))
        if not os.path.exists(full_p):
            continue
        with open(full_p, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        matches = []
        for idx, l in enumerate(lines, start=1):
            if query.lower() in l.lower():
                matches.append((idx, l.strip()[:90]))
        if matches:
            total_found += len(matches)
            print(f"\n[*] {rel} [{desc}] — найдено {len(matches)} вхождений:")
            for idx, text in matches[:8]:
                print(f"  {idx:4d}: {text}")
            if len(matches) > 8:
                print(f"  ... (+еще {len(matches) - 8} вхождений)")
    if total_found == 0:
        print(f"[NOT FOUND] Ничего не найдено для '{query}'")

def cmd_slice(filename, start_line, count=30):
    """Быстрый компактный срез строк файла с номерами строк."""
    full_path = os.path.join(PATH_E, filename.replace("/", os.sep))
    if not os.path.exists(full_path):
        print(f"[ERR] Файл {filename} не найден!")
        return
    with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()
    start = max(1, int(start_line))
    end = min(len(lines), start + int(count) - 1)
    print(f"=== [SLICE] {filename} (строки {start}..{end} из {len(lines)}) ===")
    for i in range(start - 1, end):
        print(f"{i + 1:4d}: {lines[i].rstrip()}")

def cmd_users():
    """Компактный просмотр всех пользователей и их тарифов."""
    users_file = os.path.join(PATH_E, "data", "users.json")
    if not os.path.exists(users_file):
        return
    with open(users_file, "r", encoding="utf-8-sig") as f:
        users = json.load(f)
    print("=== [USERS] Список пользователей и тарифных планов ===")
    for u in users:
        perms = u.get("permissions", {})
        dur = perms.get("avito_duration", "-")
        exp = perms.get("avito_expires_at", "-")
        max_s = perms.get("max_searches", 1)
        role = u.get("role", "user")
        uname = u.get("username", "-")
        print(f"  @{uname:<12s} [{role.upper():<5s}] | Ссылок: {max_s:>3} | Тариф: {dur:<9s} | Истекает: {exp}")

def cmd_db(query):
    """Быстрый SQL запрос к SQLite базе данных."""
    dbp = get_db_path()
    if not dbp:
        print("[ERR] База store.sqlite не найдена!")
        return
    print(f"=== [SQLITE] {os.path.basename(dbp)} ===")
    try:
        conn = sqlite3.connect(dbp)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(query)
        rows = cur.fetchall()
        if not rows:
            print("  (Запрос выполнен успешно, 0 строк)")
        else:
            headers = [d[0] for d in cur.description]
            print("  " + " | ".join(headers))
            print("  " + "-" * 40)
            for r in rows[:15]:
                vals = [str(r[h])[:30] for h in headers]
                print("  " + " | ".join(vals))
            if len(rows) > 15:
                print(f"  ... всего строк: {len(rows)}")
        conn.close()
    except Exception as e:
        print(f"[SQL ERR] {e}")

def cmd_schema():
    """Создает компактный кэш схемы БД (store.sqlite и avito_bot.db) в tools/schema.json."""
    print("=== [SCHEMA] Сканирование структуры баз данных ===")
    schemas = {}
    dbs = {
        "store.sqlite": get_db_path(),
        "avito_bot.db": os.path.join(PATH_C, "avito_bot", "avito_bot.db")
    }

    for name, db_path in dbs.items():
        if not db_path or not os.path.exists(db_path):
            continue
        try:
            con = sqlite3.connect(db_path)
            cur = con.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = [r[0] for r in cur.fetchall()]
            schemas[name] = {}
            for t in tables:
                cur.execute(f"PRAGMA table_info('{t}')")
                cols = [{"name": c[1], "type": c[2], "pk": bool(c[5])} for c in cur.fetchall()]
                try:
                    cur.execute(f"SELECT count(*) FROM '{t}'")
                    count = cur.fetchone()[0]
                except Exception:
                    count = 0
                schemas[name][t] = {"rows": count, "columns": cols}
            con.close()
        except Exception as e:
            print(f"  Ошибка чтения {name}: {e}")

    out_file = os.path.join(PATH_E, "tools", "schema.json")
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(schemas, f, ensure_ascii=False, indent=2)

    for db_name, tbls in schemas.items():
        print(f"База: {db_name}")
        for t, info in tbls.items():
            cols = [f"{c['name']} ({c['type']})" if c['type'] else c['name'] for c in info['columns']]
            print(f"  Таблица '{t}' [{info['rows']} записей]: {', '.join(cols)}")

    print(f"[OK] Схема успешно сохранена в {out_file}")

def cmd_logs(n=20, errors_only=False):
    """Просмотр последних строк лога сервера."""
    for lp in [os.path.join(PATH_E, "server_run.log"), os.path.join(PATH_C, "server_run.log")]:
        if os.path.exists(lp):
            print(f"=== [LOGS] {lp} (последние {n} строк) ===")
            with open(lp, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            if errors_only:
                lines = [l for l in lines if "err" in l.lower() or "exception" in l.lower()]
            for l in lines[-int(n):]:
                print("  " + l.rstrip())
            return
    print("[LOGS] server_run.log не найден")

def cmd_restart():
    """Безопасный перезапуск сервера на порту 8080."""
    print("=== [RESTART] Перезапуск сервера SkyBase ===")
    cmd_sync("e2c")
    if not cmd_check():
        print("[ABORT] Перезапуск отменен из-за ошибок синтаксиса!")
        return False

    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:8080/api/server/shutdown", headers={"User-Agent": "dev.py"})
        urllib.request.urlopen(req, timeout=1.5)
        time.sleep(0.6)
    except Exception:
        pass

    pids_to_check = []
    for pf in [os.path.join(PATH_C, "server.pid"), os.path.join(PATH_E, "server.pid")]:
        if os.path.exists(pf):
            try:
                with open(pf, "r") as f:
                    v = f.read().strip()
                    if v and v.isdigit(): pids_to_check.append(v)
            except Exception:
                pass

    pids_str = ", ".join(pids_to_check)
    kill_script = (
        f"$pids = @({pids_str}); "
        f"Get-NetTCPConnection -LocalPort 8080 -ErrorAction SilentlyContinue | ForEach-Object {{ $pids += $_.OwningProcess }}; "
        f"Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {{ $_.CommandLine -like '*server.ps1*' }} | ForEach-Object {{ $pids += $_.ProcessId }}; "
        f"$pids = $pids | Where-Object {{ $_ -gt 4 }} | Select-Object -Unique; "
        f"foreach ($p in $pids) {{ "
        f"  try {{ Stop-Process -Id $p -Force -ErrorAction SilentlyContinue }} catch {{ "
        f"    Start-Process powershell -Verb RunAs -Wait -ArgumentList ('-NoProfile -Command taskkill /F /PID ' + $p) -ErrorAction SilentlyContinue "
        f"  }} "
        f"}}"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", kill_script], capture_output=True)
    time.sleep(1)

    srv_script = os.path.join(PATH_C, "server.ps1")
    flags = subprocess.CREATE_NEW_PROCESS_GROUP
    if hasattr(subprocess, "DETACHED_PROCESS"):
        flags |= subprocess.DETACHED_PROCESS
    subprocess.Popen(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", srv_script],
        cwd=PATH_C,
        creationflags=flags,
        close_fds=True
    )

    started = False
    for _ in range(12):
        time.sleep(0.5)
        try:
            req = urllib.request.Request("http://127.0.0.1:8080/api/server/network-info")
            with urllib.request.urlopen(req, timeout=1) as resp:
                if resp.status == 200:
                    started = True
                    break
        except Exception:
            pass

    if started:
        print("[SUCCESS] Сервер SkyBase успешно запущен на http://localhost:8080/!")
        return True
    else:
        print("[WARN] Сервер запущен, но пока не ответил на пинг. Проверьте server_run.log")
        return False

def cmd_test():
    """Экспресс-тест API эндпоинтов и статики."""
    print("=== [TEST] Экспресс-тестирование API и статики ===")
    t0 = time.time()

    # Считываем актуальные токены сессий из базы пользователей для тестов
    tokens = {}
    for base in [PATH_C, PATH_E]:
        p_users = os.path.join(base, "data", "users.json")
        if os.path.exists(p_users):
            try:
                with open(p_users, "r", encoding="utf-8-sig") as f:
                    for u in json.load(f):
                        tokens[u.get("username")] = u.get("session_token", "")
                break
            except Exception:
                pass

    tok_admin = tokens.get("skynet83", "")
    tok_sky = tokens.get("sky83", "")

    tests = [
        ("API me (admin)", f"http://127.0.0.1:8080/api/me?username=skynet83&token={tok_admin}", lambda d: d.get("user", {}).get("role") == "admin"),
        ("API me (sky83)", f"http://127.0.0.1:8080/api/me?username=sky83&token={tok_sky}", lambda d: "max_searches" in d.get("user", {}).get("permissions", {})),
        ("Static index.html", "http://127.0.0.1:8080/", lambda d: "<title>" in d),
        ("Logo", "http://127.0.0.1:8080/img/logo.png", lambda b: len(b) > 100),
        ("Avito Icon", "http://127.0.0.1:8080/img/avito_icon.png", lambda b: len(b) > 100),
        ("Shop Icon Avito", "http://127.0.0.1:8080/img/shop_avito.png", lambda b: len(b) > 100),
    ]

    passed = 0
    for name, url, validator in tests:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "DevTool/1.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                raw = resp.read()
                is_json = "application/json" in resp.headers.get("Content-Type", "")
                data = json.loads(raw.decode("utf-8")) if is_json else (raw.decode("utf-8", errors="ignore") if "text" in resp.headers.get("Content-Type", "") or "html" in resp.headers.get("Content-Type", "") else raw)
                if validator(data):
                    passed += 1
                else:
                    print(f"  [FAIL] {name}: валидация ответа не прошла")
        except Exception as ex:
            print(f"  [FAIL] {name}: {ex}")

    elapsed = int((time.time() - t0) * 1000)
    if passed == len(tests):
        print(f"[SUCCESS] Все {passed}/{len(tests)} проверок успешно пройдены за {elapsed}ms!")
    else:
        print(f"[WARN] Пройдено {passed}/{len(tests)} за {elapsed}ms")

def cmd_search(query, filename="all"):
    """Быстрый компактный поиск по коду без вывода лишних токенов."""
    print(f"=== [SEARCH] Поиск: '{query}' в {filename} ===")
    targets = CORE_FILES if filename == "all" else [filename]
    matches = 0

    for rel in targets:
        fpath = os.path.join(PATH_E, rel.replace("/", "\\"))
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            for idx, line in enumerate(lines, start=1):
                if re.search(query, line, re.IGNORECASE):
                    matches += 1
                    print(f"  {rel}:{idx}: {line.strip()[:100]}")
                    if matches >= 25:
                        print("  ... (показаны первые 25 совпадений)")
                        return
        except Exception as e:
            print(f"  Ошибка чтения {rel}: {e}")

    print(f"[DONE] Найдено совпадений: {matches}")

def cmd_func(func_name, filename="js/app.js", show=False):
    """Находит функцию, определяет её точные границы (start..end) по фигурным скобкам."""
    print(f"=== [FUNC] Поиск функции '{func_name}' в {filename} ===")
    fpath = os.path.join(PATH_E, filename.replace("/", "\\"))
    if not os.path.exists(fpath):
        print(f"[ERR] Файл {filename} не найден")
        return

    with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    pat = re.compile(r'\b(function\s+' + re.escape(func_name) + r'\b|async\s+function\s+' + re.escape(func_name) + r'\b|' + re.escape(func_name) + r'\s*[:=]\s*(?:async\s*)?\()')
    start_line = None
    for idx, line in enumerate(lines, start=1):
        if pat.search(line):
            start_line = idx
            break

    if not start_line:
        for idx, line in enumerate(lines, start=1):
            if func_name in line and ("(" in line or "{" in line):
                start_line = idx
                break

    if not start_line:
        print(f"[NOT FOUND] Функция '{func_name}' не найдена в {filename}")
        return

    brace_depth = 0
    found_first_brace = False
    end_line = start_line

    for idx in range(start_line - 1, len(lines)):
        line = lines[idx]
        for ch in line:
            if ch == '{':
                brace_depth += 1
                found_first_brace = True
            elif ch == '}':
                brace_depth -= 1
                if found_first_brace and brace_depth == 0:
                    end_line = idx + 1
                    break
        if found_first_brace and brace_depth == 0:
            break

    total_lines = end_line - start_line + 1
    print(f"[FOUND] Функция '{func_name}': строки {start_line}..{end_line} (всего {total_lines} строк)")
    
    if show:
        print("-" * 50)
        for i in range(start_line - 1, end_line):
            print(f"{i + 1:4d}: {lines[i].rstrip()}")
        print("-" * 50)

def cmd_backup():
    """Создает резервную копию рабочих файлов в .bak перед правками."""
    bak_dir = os.path.join(PATH_E, ".bak")
    os.makedirs(bak_dir, exist_ok=True)
    count = 0
    for rel in CORE_FILES:
        src = os.path.join(PATH_E, rel.replace("/", "\\"))
        dst = os.path.join(bak_dir, os.path.basename(rel))
        if os.path.exists(src):
            shutil.copy2(src, dst)
            count += 1
    print(f"[BACKUP] Создана резервная копия {count} файлов в .bak/")

def cmd_rollback():
    """Мгновенно откатывает файлы из .bak в обе директории."""
    bak_dir = os.path.join(PATH_E, ".bak")
    if not os.path.exists(bak_dir):
        print("[ERR] Папка .bak не найдена!")
        return
    count = 0
    for rel in CORE_FILES:
        bfile = os.path.join(bak_dir, os.path.basename(rel))
        if os.path.exists(bfile):
            for base in [PATH_E, PATH_C]:
                target = os.path.join(base, rel.replace("/", "\\"))
                shutil.copy2(bfile, target)
            count += 1
    print(f"[ROLLBACK] Успешно восстановлено {count} файлов в E:\\ и C:\\")
    cmd_check()

def cmd_diff(filename="all"):
    """Показывает только компактный diff изменений относительно .bak."""
    import difflib
    bak_dir = os.path.join(PATH_E, ".bak")
    if not os.path.exists(bak_dir):
        print("[ERR] Сначала создайте бэкап: python tools/dev.py backup")
        return
    targets = CORE_FILES if filename == "all" else [filename]
    has_diff = False
    for rel in targets:
        bfile = os.path.join(bak_dir, os.path.basename(rel))
        cfile = os.path.join(PATH_E, rel.replace("/", "\\"))
        if os.path.exists(bfile) and os.path.exists(cfile):
            with open(bfile, "r", encoding="utf-8", errors="ignore") as f1, open(cfile, "r", encoding="utf-8", errors="ignore") as f2:
                l1, l2 = f1.readlines(), f2.readlines()
            diff = list(difflib.unified_diff(l1, l2, fromfile=f"bak/{rel}", tofile=rel, n=2))
            if diff:
                has_diff = True
                print(f"--- Diff {rel} ---")
                for d in diff[:30]:
                    print(d.rstrip())
                if len(diff) > 30:
                    print(f"  ... (+еще {len(diff) - 30} строк изменений)")
    if not has_diff:
        print("[DIFF] Изменений нет (файлы идентичны .bak)")

def cmd_db_backup():
    """Создает безопасную горячую резервную копию SQLite баз и данных в data/backups/."""
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(PATH_E, "data", "backups", f"backup_{ts}")
    os.makedirs(backup_dir, exist_ok=True)

    db_candidates = [
        r"data\store.sqlite",
        r"База деталей\Base\store.sqlite",
        r"Base деталей\Base\store.sqlite",
        r"avito_bot\avito_bot.db",
        r"avito_bot\avito_monitor.db",
        r"avito_bot\bot_database.db",
        r"data\users.json",
        r"data\radio_components.json"
    ]

    backed_up = []
    for rel in db_candidates:
        src = os.path.join(PATH_E, rel)
        if not os.path.exists(src):
            src_c = os.path.join(PATH_C, rel)
            if os.path.exists(src_c):
                src = src_c
            else:
                continue

        target_name = os.path.basename(rel)
        if "avito_bot" in rel:
            target_name = "avito_" + target_name
        dst = os.path.join(backup_dir, target_name)

        if rel.endswith((".sqlite", ".db")):
            try:
                con_src = sqlite3.connect(src)
                con_dst = sqlite3.connect(dst)
                with con_dst:
                    con_src.backup(con_dst)
                con_dst.close()
                con_src.close()
                sz_kb = os.path.getsize(dst) / 1024
                backed_up.append((target_name, f"{sz_kb:.1f} KB (SQLite safe)"))
            except Exception as e:
                shutil.copy2(src, dst)
                sz_kb = os.path.getsize(dst) / 1024
                backed_up.append((target_name, f"{sz_kb:.1f} KB (copy)"))
        else:
            shutil.copy2(src, dst)
            sz_kb = os.path.getsize(dst) / 1024
            backed_up.append((target_name, f"{sz_kb:.1f} KB"))

    print("=== [DB-BACKUP] Резервное копирование завершено ===")
    print(f"Папка бэкапа: {backup_dir}")
    for name, sz in backed_up:
        print(f"  [OK] {name} ({sz})")

def cmd_api(endpoint, field=None):
    """Выполняет точечный запрос к локальному API и выводит только нужное поле."""
    url = f"http://127.0.0.1:8080{endpoint}" if endpoint.startswith("/") else f"http://127.0.0.1:8080/{endpoint}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "DevTool/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if field:
                parts = field.split(".")
                curr = data
                for p in parts:
                    if isinstance(curr, dict):
                        curr = curr.get(p)
                    else:
                        curr = None
                        break
                print(f"[API] {field} = {json.dumps(curr, ensure_ascii=False, indent=2)}")
            else:
                print(f"[API] {json.dumps(data, ensure_ascii=False, indent=2)[:300]}")
    except Exception as e:
        print(f"[API ERR] {e}")

def cmd_watch():
    """Запускает фоновое отслеживание изменений: авто-синхронизация при сохранении."""
    print("=== [WATCH] Авто-синхронизатор ElectroBase запущен ===")
    print("При любом сохранении в E:\\TEMP файлы автоматически копируются в C:\\ins")
    print("Нажмите Ctrl+C для остановки.")
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler

        class AutoSyncHandler(FileSystemEventHandler):
            def __init__(self):
                self.last_sync = 0

            def on_modified(self, event):
                if event.is_directory:
                    return
                fname = os.path.basename(event.src_path)
                if fname.endswith(('.ps1', '.js', '.html', '.json', '.css', '.png', '.jpg', '.md')):
                    now = time.time()
                    if now - self.last_sync > 0.5:
                        self.last_sync = now
                        print(f"  [CHANGE] Изменен {fname} -> синхронизируем...")
                        cmd_sync("e2c")

        event_handler = AutoSyncHandler()
        observer = Observer()
        observer.schedule(event_handler, PATH_E, recursive=True)
        observer.start()
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            observer.stop()
        observer.join()
    except Exception as e:
        print(f"[WATCH ERR] {e}")

def cmd_snapshot(msg="Auto snapshot"):
    """Создает легковесный снимок репозитория через встроенный Python Git."""
    try:
        from dulwich import porcelain
        git_dir = os.path.join(PATH_E, ".git")
        if not os.path.exists(git_dir):
            porcelain.init(PATH_E)
            print("[GIT] Инициализирован локальный репозиторий Git в E:\\TEMP")
        porcelain.add(PATH_E, [r for r in CORE_FILES if os.path.exists(os.path.join(PATH_E, r))])
        c = porcelain.commit(PATH_E, message=msg.encode("utf-8"))
        print(f"[GIT] Создан снимок состояния (коммит: {c.decode('utf-8')[:8]}): {msg}")
    except Exception as e:
        print(f"[GIT ERR] {e}")

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    action = sys.argv[1].lower()
    if action == "sync":
        direction = sys.argv[2] if len(sys.argv) > 2 else "auto"
        cmd_sync(direction)
    elif action == "watch":
        cmd_watch()
    elif action == "snapshot":
        msg = sys.argv[2] if len(sys.argv) > 2 else "Checkpoint"
        cmd_snapshot(msg)
    elif action == "check":
        cmd_check()
    elif action == "restart":
        cmd_restart()
    elif action == "test":
        cmd_test()
    elif action == "routes":
        filt = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else None
        show = "--show" in sys.argv
        cmd_routes(filt, show)
    elif action == "funcs":
        filt = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].endswith((".js", ".py", ".ps1")) else None
        target = sys.argv[-1] if len(sys.argv) > 2 and sys.argv[-1].endswith((".js", ".py", ".ps1")) else "js/app.js"
        cmd_funcs(filt, target)
    elif action == "dom":
        filt = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_dom(filt)
    elif action == "trace":
        if len(sys.argv) < 3:
            print("Укажите запрос: python tools/dev.py trace <слово>")
            return
        cmd_trace(sys.argv[2])
    elif action == "slice":
        if len(sys.argv) < 4:
            print("Использование: python tools/dev.py slice <файл> <строка_начала> [кол-во]")
            return
        cnt = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].isdigit() else 30
        cmd_slice(sys.argv[2], sys.argv[3], cnt)
    elif action == "users":
        cmd_users()
    elif action == "db":
        if len(sys.argv) < 3:
            print("Укажите SQL запрос: python tools/dev.py db \"SELECT count(*) FROM elements\"")
            return
        cmd_db(sys.argv[2])
    elif action == "schema":
        cmd_schema()
    elif action == "logs":
        count = sys.argv[2] if len(sys.argv) > 2 else 20
        err_only = "--err" in sys.argv
        cmd_logs(count, err_only)
    elif action == "search":
        if len(sys.argv) < 3:
            print("Укажите поисковый запрос: python tools/dev.py search <запрос> [файл]")
            return
        fname = sys.argv[3] if len(sys.argv) > 3 else "all"
        cmd_search(sys.argv[2], fname)
    elif action == "func":
        if len(sys.argv) < 3:
            print("Укажите имя функции: python tools/dev.py func <имя> [файл] [--show]")
            return
        fname = "js/app.js"
        show = False
        for arg in sys.argv[3:]:
            if arg == "--show":
                show = True
            else:
                fname = arg
        cmd_func(sys.argv[2], fname, show)
    elif action == "backup":
        cmd_backup()
    elif action in ("db-backup", "db_backup"):
        cmd_db_backup()
    elif action == "rollback":
        cmd_rollback()
    elif action == "diff":
        fname = sys.argv[2] if len(sys.argv) > 2 else "all"
        cmd_diff(fname)
    elif action in ("lic", "lic-status", "license"):
        sys.path.insert(0, os.path.dirname(__file__))
        import lic_tool
        lic_tool.cmd_status()
    elif action in ("lic-reset", "reset-license"):
        sys.path.insert(0, os.path.dirname(__file__))
        import lic_tool
        lic_tool.cmd_reset()
    elif action in ("lic-test", "test-flow"):
        sys.path.insert(0, os.path.dirname(__file__))
        import lic_tool
        lic_tool.cmd_test_flow()
    elif action in ("lic-chat-test", "chat-test", "lic-iso"):
        sys.path.insert(0, os.path.dirname(__file__))
        import lic_tool
        lic_tool.cmd_chat_test()
    elif action in ("lic-chat", "chat"):
        sys.path.insert(0, os.path.dirname(__file__))
        import lic_tool
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        lic_tool.cmd_chat(n)
    else:
        print(f"Неизвестная команда: {action}\n{__doc__}")

if __name__ == "__main__":
    main()
