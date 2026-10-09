#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Утилита настройки и портативности Playwright для SkyBase (tools/setup_playwright_portable.py).
Позволяет:
1. Проверить статус Playwright и обнаруженных системных браузеров (Chrome, Edge, Portable).
2. Запустить экспресс-тест браузера.
3. Скопировать браузер внутрь папки проекта (browsers/) для 100% автономного переноса на любой ПК.
4. Скачать офлайн-пакеты (wheels) для установки pip без интернета.
"""

import os
import sys
import shutil
import glob
import asyncio
import subprocess

try:
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BROWSERS_DIR = os.path.join(BASE_DIR, "browsers")
INSTALLER_PACKAGES_DIR = os.path.join(BASE_DIR, "avito_bot", "installer", "packages")


def print_header(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def check_status():
    print_header("Диагностика Playwright и Браузеров для переноса")

    # 1. Проверка Python-библиотеки
    try:
        import playwright
        pw_ver = getattr(playwright, "__version__", "OK")
        print(f"[+] Библиотека Playwright (Python): Установлена (версия {pw_ver})")
    except ImportError:
        print("[-] Библиотека Playwright (Python): НЕ установлена")

    # 2. Обнаружение браузеров
    sys.path.insert(0, BASE_DIR)
    try:
        from avito_sniper import get_candidate_browsers
        candidates = get_candidate_browsers()
    except Exception as e:
        candidates = []
        print(f"[!] Ошибка вызова get_candidate_browsers: {e}")

    print("\n[+] Обнаруженные браузеры для работы снайпера (в порядке приоритета):")
    if candidates:
        for idx, path in enumerate(candidates, 1):
            tag = "Системный"
            if BROWSERS_DIR.lower() in path.lower():
                tag = "Портативный в проекте"
            elif "chrome.exe" in path.lower() and "google" in path.lower():
                tag = "Google Chrome"
            elif "msedge" in path.lower():
                tag = "Microsoft Edge"
            elif "ms-playwright" in path.lower():
                tag = "Кэш Playwright"
            print(f"   {idx}. [{tag}] {path}")
    else:
        print("   [-] Браузеры не обнаружены! (Рекомендуется установить Google Chrome или Edge)")

    # 3. Наличие локальной портативной папки
    has_local = os.path.isdir(BROWSERS_DIR) and len(os.listdir(BROWSERS_DIR)) > 0
    if has_local:
        print(f"\n[+] Локальная папка browsers/ в проекте: ПРИСУТСТВУЕТ ({BROWSERS_DIR})")
        print("    -> Проект можно переносить на другие ПК без скачивания браузеров!")
    else:
        print(f"\n[i] Локальная папка browsers/ в проекте: Отсутствует (используются системные Chrome/Edge)")
        print("    -> Если на целевом ПК есть Chrome или Edge, скачивать ничего не требуется!")

    # 4. Наличие офлайн-пакетов
    has_packages = os.path.isdir(INSTALLER_PACKAGES_DIR) and any(f.endswith(".whl") for f in os.listdir(INSTALLER_PACKAGES_DIR))
    if has_packages:
        print(f"[+] Офлайн-пакеты (wheels): Найдено {len(os.listdir(INSTALLER_PACKAGES_DIR))} файлов в avito_bot/installer/packages")
    else:
        print(f"[i] Офлайн-пакеты (wheels): Отсутствуют (автоустановка будет идти через интернет при первом запуске)")


async def test_launch():
    print_header("Тестирование запуска браузера")
    sys.path.insert(0, BASE_DIR)
    try:
        from avito_sniper import launch_sniper_browser, ensure_playwright_installed
        ensure_playwright_installed()
        from playwright.async_api import async_playwright

        print("[*] Инициализация Playwright...")
        async with async_playwright() as p:
            print("[*] Запуск браузера через launch_sniper_browser (headless)...")
            ctx = await launch_sniper_browser(p, headless=True)
            page = ctx.pages[0] if ctx.pages else await ctx.new_page()
            print("[*] Переход на тестовую страницу https://example.com...")
            await page.goto("https://example.com", timeout=15000)
            title = await page.title()
            print(f"[+] УСПЕХ! Страница успешно загружена, заголовок: '{title}'")
            await ctx.close()
            print("[+] Браузер корректно закрыт. Всё готово к работе!")
            return True
    except Exception as e:
        print(f"[ERR] Ошибка при тестировании: {e}")
        return False


def make_portable():
    """Копирует установленный Playwright Chromium в папку проекта browsers/."""
    print_header("Создание портативной сборки Chromium в папке проекта")
    local_app_pw = os.path.expandvars(r"%LOCALAPPDATA%\ms-playwright")
    if not os.path.exists(local_app_pw):
        print("[*] Стандартный кэш Playwright не найден. Выполняем 'playwright install chromium'...")
        try:
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        except Exception as e:
            print(f"[ERR] Не удалось скачать chromium: {e}")
            return False

    os.makedirs(BROWSERS_DIR, exist_ok=True)
    items = os.listdir(local_app_pw)
    copied = 0
    for item in items:
        src = os.path.join(local_app_pw, item)
        dst = os.path.join(BROWSERS_DIR, item)
        if os.path.isdir(src) and ("chromium" in item or "ffmpeg" in item):
            print(f"[*] Копирование {item} -> browsers/{item}...")
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            copied += 1

    if copied > 0:
        print(f"\n[+] Успешно скопировано {copied} папок в '{BROWSERS_DIR}'.")
        print("[+] Теперь при копировании SkyBase на другой ПК браузер переносится вместе с проектом!")
        return True
    else:
        print("[-] Не найдено папок chromium для копирования.")
        return False


def download_offline_wheels():
    """Скачивает .whl пакеты для полной офлайн-установки pip."""
    print_header("Загрузка офлайн-пакетов (wheels)")
    os.makedirs(INSTALLER_PACKAGES_DIR, exist_ok=True)
    req_file = os.path.join(BASE_DIR, "requirements.txt")
    print(f"[*] Скачивание зависимостей из {req_file} в {INSTALLER_PACKAGES_DIR}...")
    try:
        subprocess.run([
            sys.executable, "-m", "pip", "download",
            "-d", INSTALLER_PACKAGES_DIR,
            "-r", req_file
        ], check=True)
        print("\n[+] Офлайн-пакеты успешно сохранены!")
        print("[+] На новом ПК pip сможет установить их без интернета командой:")
        print(f"    pip install --no-index --find-links={INSTALLER_PACKAGES_DIR} -r requirements.txt")
        return True
    except Exception as e:
        print(f"[ERR] Ошибка при скачивании пакетов: {e}")
        return False


def main():
    if "--test" in sys.argv:
        asyncio.run(test_launch())
        return
    if "--copy-local" in sys.argv or "--portable" in sys.argv:
        make_portable()
        return
    if "--wheels" in sys.argv:
        download_offline_wheels()
        return

    check_status()

    print("\nВыберите действие:")
    print("  1. Протестировать запуск браузера прямо сейчас")
    print("  2. Скопировать браузер внутрь папки проекта (browsers/) для 100% офлайна")
    print("  3. Скачать офлайн-пакеты pip (wheels) для установки без интернета")
    print("  4. Сделать ВСЁ (Портативный браузер + Офлайн-пакеты + Тест)")
    print("  0. Выход")

    try:
        choice = input("\nВаш выбор [0-4]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return

    if choice == "1":
        asyncio.run(test_launch())
    elif choice == "2":
        make_portable()
    elif choice == "3":
        download_offline_wheels()
    elif choice == "4":
        make_portable()
        download_offline_wheels()
        asyncio.run(test_launch())
    else:
        print("Завершено.")


if __name__ == "__main__":
    main()
