"""
build_skybot.py - Скрипт сборки SkyBotParser в нативные .exe файлы через Nuitka.

Запуск:
    python build_skybot.py

Результат: папка dist/ с готовыми .exe файлами и всеми нужными ресурсами.
"""

import os
import sys
import shutil
import subprocess
import re

# ──────────────────────────────────────────────
# Пути
# ──────────────────────────────────────────────
SRC_ROOT   = r"C:\G\ins\Avito-Parser3\skybase"   # исходник
BUILD_ROOT = r"C:\G\ins\skybotparser\build"       # временная сборка
DIST_ROOT  = r"C:\G\ins\skybotparser\dist"        # готовый дистрибутив
PYTHON     = sys.executable

# Файлы которые компилируем в нативный .exe (Nuitka)
COMPILE_TARGETS = [
    ("gateway.py",                     "gateway"),
    ("server.py",                      "server"),
    ("avito_api_helper.py",            "avito_api_helper"),
    ("avito_bot/bot.py",               "avito_bot/bot"),
    ("avito_bot/proxy_worker.py",      "avito_bot/proxy_worker"),
    ("app_launcher.py",                "app_launcher"),
    ("hwid_security.py",               "hwid_security"),
    ("devices_db.py",                  "devices_db"),
    ("avito_sniper.py",                "avito_sniper"),
]

# Папки/файлы которые копируются AS-IS (нужны для работы)
# (index.html, css, js, images, sound, etc.)
COPY_DIRS = [
    "css",
    "js",
    "sound",
    "img",
    "images",
    "fonts",
]

COPY_FILES_PATTERNS = [
    "*.html",
    "*.ico",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.svg",
    "*.mp3",
    "*.wav",
    "*.json",      # конфиг-шаблоны (не базы)
]

# Файлы/папки которые НЕ включаем в дистрибутив
EXCLUDE_DIRS = {
    "__pycache__", ".git", "data", "backups", "logs",
    "temp_chrome_profile", "bad_runtime_pkg", "profile",
    "build", "dist",
}
EXCLUDE_FILES = {
    "*.pyc", "*.pyo", "*.py",   # исходники Python - не включаем
    "test_*.py", "check_*.py",
    "*.log", "*.pid",
    "server_backend.log", "gateway.log", "bot.log",
    "backend.pid", "bot.pid", "proxy.pid",
}

# Папки для данных пользователя (создаём пустыми при первом запуске)
USER_DATA_DIRS = [
    "data",
    "data/backups",
    "avito_bot",   # для PID-файлов и логов бота
]


def run_nuitka(src_file: str, out_dir: str, module_name: str):
    """Компилирует один Python-файл через Nuitka в нативный .exe."""
    full_src = os.path.join(SRC_ROOT, src_file)
    if not os.path.exists(full_src):
        print(f"  [SKIP] Не найден: {full_src}")
        return False

    os.makedirs(out_dir, exist_ok=True)
    print(f"\n  [BUILD] Компиляция: {src_file} → {module_name}.exe")

    cmd = [
        PYTHON, "-m", "nuitka",
        "--onefile",                          # один .exe без папок
        "--standalone",                       # включить все зависимости
        "--windows-disable-console",          # без консоли (для GUI)
        # "--windows-console-mode=attach",    # раскомментить для консольных .exe
        f"--output-dir={out_dir}",
        f"--output-filename={os.path.basename(module_name)}.exe",
        "--assume-yes-for-downloads",         # автоматически скачать gcc если нужно
        "--remove-output",                    # убрать промежуточные файлы после сборки
        # Включаем нужные пакеты явно
        "--include-package=aiogram",
        "--include-package=aiohttp",
        "--include-package=aiosqlite",
        "--include-package=curl_cffi",
        "--include-package=cryptography",
        "--include-package=requests",
        "--include-package=sqlite3",
        full_src,
    ]

    result = subprocess.run(cmd, cwd=SRC_ROOT)
    if result.returncode == 0:
        print(f"  [OK] {module_name}.exe собран")
        return True
    else:
        print(f"  [ERR] Ошибка компиляции {src_file} (код: {result.returncode})")
        return False


def copy_resources():
    """Копирует статические ресурсы (HTML, CSS, JS, изображения, звуки)."""
    dest_skybase = os.path.join(DIST_ROOT, "skybase")

    # Папки
    for d in COPY_DIRS:
        src = os.path.join(SRC_ROOT, d)
        dst = os.path.join(dest_skybase, d)
        if os.path.exists(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            print(f"  [COPY] {d}/")

    # Файлы в корне skybase по шаблонам
    import glob
    for pat in COPY_FILES_PATTERNS:
        for f in glob.glob(os.path.join(SRC_ROOT, pat)):
            fn = os.path.basename(f)
            # Исключаем тестовые и лишние файлы
            if any(fn.startswith(x) for x in ("test_", "check_", "scratch_", "inspect_")):
                continue
            shutil.copy2(f, dest_skybase)
            print(f"  [COPY] {fn}")

    # Создаём пустые пользовательские папки
    for d in USER_DATA_DIRS:
        dp = os.path.join(dest_skybase, d)
        os.makedirs(dp, exist_ok=True)
        # Кладём .gitkeep чтобы папка не была пустой
        open(os.path.join(dp, ".keep"), "w").close()

    print("  [OK] Ресурсы скопированы")


def create_launcher_bat():
    """Создаёт launcher.bat для запуска (до компиляции app_launcher)."""
    bat = os.path.join(DIST_ROOT, "SkyBotParser.bat")
    content = (
        "@echo off\r\n"
        "cd /d \"%~dp0\"\r\n"
        "start \"\" skybase\\gateway.exe\r\n"
    )
    with open(bat, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [OK] Создан SkyBotParser.bat")


def main():
    print("=" * 60)
    print("  SkyBotParser — Nuitka Build Script")
    print("=" * 60)

    # Очистка
    if os.path.exists(BUILD_ROOT):
        shutil.rmtree(BUILD_ROOT)
    os.makedirs(BUILD_ROOT, exist_ok=True)
    os.makedirs(DIST_ROOT, exist_ok=True)
    os.makedirs(os.path.join(DIST_ROOT, "skybase"), exist_ok=True)

    # Шаг 1 — Компиляция Python → нативный .exe
    print("\n[1/3] Компиляция Python файлов в нативный .exe (Nuitka)...")
    ok_count = 0
    fail_count = 0
    for src, out_name in COMPILE_TARGETS:
        out_dir = os.path.join(DIST_ROOT, "skybase", os.path.dirname(out_name))
        os.makedirs(out_dir, exist_ok=True)
        if run_nuitka(src, out_dir, out_name):
            ok_count += 1
        else:
            fail_count += 1

    print(f"\n  Результат компиляции: {ok_count} OK / {fail_count} ошибок")

    # Шаг 2 — Копирование ресурсов
    print("\n[2/3] Копирование статических ресурсов...")
    copy_resources()

    # Шаг 3 — Лаунчер
    print("\n[3/3] Создание лаунчера...")
    create_launcher_bat()

    print("\n" + "=" * 60)
    print(f"  Готово! Дистрибутив: {DIST_ROOT}")
    print("=" * 60)


if __name__ == "__main__":
    main()
