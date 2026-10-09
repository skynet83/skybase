#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Модуль безопасных транзакционных обновлений SkyBase (tools/updater.py).
Обеспечивает:
1. Создание горячей точки восстановления (Snapshot & SQLite Hot Backup).
2. Валидацию файлов во временной карантинной зоне (Staging) до применения.
3. Атомарное обновление файлов.
4. Автоматический тест целостности (Post-Update Smoke Test).
5. АВТОМАТИЧЕСКИЙ ОТКАТ (Auto-Rollback) на рабочую версию в случае любой ошибки.
6. Ненавязчивую фоновую проверку обновлений без блокировки запуска сервера.
"""

import os
import sys
import json
import time
import shutil
import sqlite3
import zipfile
import py_compile
import threading
from typing import Dict, Any, Optional, Tuple, List

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_DIR = os.path.join(BASE_DIR, "lib")
if os.path.exists(LIB_DIR) and LIB_DIR not in sys.path:
    sys.path.insert(0, LIB_DIR)

VERSION_FILE = os.path.join(BASE_DIR, "version.json")
BACKUPS_DIR = os.path.join(BASE_DIR, "data", "backups")
STAGING_DIR = os.path.join(BASE_DIR, "scratch", "update_staging")
UPDATE_INFO_FILE = os.path.join(BASE_DIR, "data", "update_available.json")


def get_current_version() -> str:
    if os.path.exists(VERSION_FILE):
        try:
            with open(VERSION_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("version", "1.0.0")
        except Exception:
            pass
    return "1.0.0"


def create_recovery_snapshot(reason: str = "before_update") -> Tuple[bool, str]:
    """
    Создает полную горячую точку восстановления:
    - Базы данных SQLite через crash-safe Online Backup API (без блокировок)
    - Пользовательские конфигурации, токены, куки (папка data/)
    - Исполняемые файлы кода (.py)
    Возвращает (success, snapshot_dir)
    """
    ts = time.strftime("%Y%m%d_%H%M%S")
    snapshot_dir = os.path.join(BACKUPS_DIR, f"snapshot_{ts}_{reason}")
    os.makedirs(snapshot_dir, exist_ok=True)

    manifest = {
        "timestamp": ts,
        "reason": reason,
        "version": get_current_version(),
        "databases": [],
        "files": []
    }

    try:
        # 1. Горячий бэкап баз данных SQLite
        db_candidates = [
            os.path.join(BASE_DIR, "avito_bot", "avito_bot.db"),
            os.path.join(BASE_DIR, "avito_bot.db"),
            os.path.join(BASE_DIR, "data", "store.sqlite")
        ]
        db_dst_dir = os.path.join(snapshot_dir, "databases")
        os.makedirs(db_dst_dir, exist_ok=True)

        for src_db in db_candidates:
            if os.path.exists(src_db) and os.path.getsize(src_db) > 0:
                rel_name = os.path.basename(src_db)
                dst_db = os.path.join(db_dst_dir, rel_name)
                try:
                    con_src = sqlite3.connect(f"file:{src_db}?mode=ro", uri=True)
                    con_dst = sqlite3.connect(dst_db)
                    with con_dst:
                        con_src.backup(con_dst)
                    con_dst.close()
                    con_src.close()
                    manifest["databases"].append({"src": src_db, "backup": dst_db})
                except Exception:
                    shutil.copy2(src_db, dst_db)
                    manifest["databases"].append({"src": src_db, "backup": dst_db})

        # 2. Бэкап папки data/ (конфиги, авторизации, токены)
        data_src = os.path.join(BASE_DIR, "data")
        data_dst = os.path.join(snapshot_dir, "data_config")
        if os.path.exists(data_src):
            os.makedirs(data_dst, exist_ok=True)
            for item in os.listdir(data_src):
                if item == "backups":
                    continue
                s = os.path.join(data_src, item)
                d = os.path.join(data_dst, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                elif os.path.isfile(s):
                    shutil.copy2(s, d)

        # 3. Бэкап исполняемых Python-файлов корня и avito_bot
        code_dst = os.path.join(snapshot_dir, "code_files")
        os.makedirs(code_dst, exist_ok=True)

        for root, dirs, files in os.walk(BASE_DIR):
            if any(x in root for x in ["backups", "scratch", ".git", "browsers", "lib", "__pycache__"]):
                continue
            for f in files:
                if f.endswith((".py", ".html", ".js", ".css")):
                    full_p = os.path.join(root, f)
                    rel_p = os.path.relpath(full_p, BASE_DIR)
                    target_dst = os.path.join(code_dst, rel_p)
                    os.makedirs(os.path.dirname(target_dst), exist_ok=True)
                    shutil.copy2(full_p, target_dst)
                    manifest["files"].append(rel_p)

        # Запись манифеста
        with open(os.path.join(snapshot_dir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

        return True, snapshot_dir
    except Exception as e:
        return False, str(e)


def restore_snapshot(snapshot_dir: str) -> Tuple[bool, str]:
    """
    Мгновенно восстанавливает файлы и базу данных из указанного снимка.
    Используется для ручного и автоматического отката.
    """
    manifest_file = os.path.join(snapshot_dir, "manifest.json")
    if not os.path.exists(manifest_file):
        return False, "В папке снимка отсутствует manifest.json"

    try:
        with open(manifest_file, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        # 1. Восстановление баз данных
        for db_item in manifest.get("databases", []):
            src_orig = db_item["src"]
            b_src = db_item["backup"]
            if os.path.exists(b_src):
                os.makedirs(os.path.dirname(src_orig), exist_ok=True)
                shutil.copy2(b_src, src_orig)

        # 2. Восстановление конфигураций data/
        data_dst = os.path.join(snapshot_dir, "data_config")
        data_target = os.path.join(BASE_DIR, "data")
        if os.path.exists(data_dst):
            for item in os.listdir(data_dst):
                s = os.path.join(data_dst, item)
                d = os.path.join(data_target, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d, dirs_exist_ok=True)
                elif os.path.isfile(s):
                    shutil.copy2(s, d)

        # 3. Восстановление файлов кода
        code_src = os.path.join(snapshot_dir, "code_files")
        if os.path.exists(code_src):
            for rel_file in manifest.get("files", []):
                s = os.path.join(code_src, rel_file)
                d = os.path.join(BASE_DIR, rel_file)
                if os.path.exists(s):
                    os.makedirs(os.path.dirname(d), exist_ok=True)
                    shutil.copy2(s, d)

        # Восстановление версии
        old_ver = manifest.get("version", "1.0.0")
        if os.path.exists(VERSION_FILE):
            try:
                with open(VERSION_FILE, "r", encoding="utf-8") as f:
                    v_data = json.load(f)
                v_data["version"] = old_ver
                with open(VERSION_FILE, "w", encoding="utf-8") as f:
                    json.dump(v_data, f, ensure_ascii=False, indent=2)
            except Exception:
                pass

        return True, f"Успешно восстановлено из снимка от {manifest.get('timestamp')}"
    except Exception as e:
        return False, f"Ошибка восстановления из снимка: {e}"


def validate_python_files_in_dir(target_dir: str) -> Tuple[bool, List[str]]:
    """Проверяет синтаксическую корректность всех .py файлов в директории без их запуска."""
    errors = []
    for root, _, files in os.walk(target_dir):
        for f in files:
            if f.endswith(".py"):
                p = os.path.join(root, f)
                try:
                    py_compile.compile(p, doraise=True)
                except py_compile.PyCompileError as e:
                    errors.append(f"{f}: {e.msg}")
                except Exception as e:
                    errors.append(f"{f}: {str(e)}")
    return (len(errors) == 0), errors


def test_post_update_health() -> Tuple[bool, str]:
    """Быстрый проверочный тест (Smoke Test) после применения файлов."""
    try:
        # Проверяем компиляцию ключевых файлов
        for script in ["avito_sniper.py", "gateway.py", "avito_api_helper.py"]:
            sp = os.path.join(BASE_DIR, script)
            if os.path.exists(sp):
                py_compile.compile(sp, doraise=True)

        # Проверяем базовые импорты
        import avito_sniper
        import avito_api_helper
        return True, "Все тесты успешно пройдены"
    except Exception as e:
        return False, str(e)


def apply_update_package(source_path: str) -> Dict[str, Any]:
    """
    Транзакционная установка пакета обновления (ZIP-архив или папка):
    1. Создает точку восстановления (бэкап).
    2. Распаковывает в изолированную карантинную зону.
    3. Проверяет синтаксис всех скриптов в карантине.
    4. Применяет обновление.
    5. Проводит смоук-тест.
    6. При ЛЮБОЙ ошибке -> АВТОМАТИЧЕСКИЙ ОТКАТ на точку восстановления!
    """
    if not os.path.exists(source_path):
        return {"success": False, "error": f"Файл/папка обновления не найдена: {source_path}"}

    # ШАГ 1: Создание точки восстановления
    snap_ok, snap_res = create_recovery_snapshot(reason="auto_rollback_guard")
    if not snap_ok:
        return {"success": False, "error": f"Не удалось создать точку восстановления: {snap_res}"}
    snapshot_dir = snap_res

    # ШАГ 2: Распаковка в изолированный карантин (Staging)
    if os.path.exists(STAGING_DIR):
        shutil.rmtree(STAGING_DIR, ignore_errors=True)
    os.makedirs(STAGING_DIR, exist_ok=True)

    try:
        if zipfile.is_zipfile(source_path):
            with zipfile.ZipFile(source_path, "r") as z:
                z.extractall(STAGING_DIR)
        elif os.path.isdir(source_path):
            for item in os.listdir(source_path):
                s = os.path.join(source_path, item)
                d = os.path.join(STAGING_DIR, item)
                if os.path.isdir(s):
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
        else:
            return {"success": False, "error": "Пакет обновления должен быть ZIP-архивом или папкой"}

        # ШАГ 3: Предварительная валидация синтаксиса в карантине (до изменения рабочих файлов!)
        valid, compile_errors = validate_python_files_in_dir(STAGING_DIR)
        if not valid:
            shutil.rmtree(STAGING_DIR, ignore_errors=True)
            return {
                "success": False,
                "error": f"Пакет содержит синтаксические ошибки Python: {', '.join(compile_errors)}. Установка отменена, файлы не затронуты."
            }

        # ШАГ 4: Применение файлов из карантина
        for root, _, files in os.walk(STAGING_DIR):
            for f in files:
                s = os.path.join(root, f)
                rel = os.path.relpath(s, STAGING_DIR)
                target = os.path.join(BASE_DIR, rel)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                shutil.copy2(s, target)

        shutil.rmtree(STAGING_DIR, ignore_errors=True)

        # ШАГ 5: Проверочный тест работоспособности
        health_ok, health_err = test_post_update_health()
        if not health_ok:
            # АВТОМАТИЧЕСКИЙ ОТКАТ НАЗАД!
            roll_ok, roll_msg = restore_snapshot(snapshot_dir)
            return {
                "success": False,
                "rolled_back": True,
                "error": f"Обновление вызвало сбой ({health_err}). АВТОМАТИЧЕСКИЙ ОТКАТ ВЫПОЛНЕН: {roll_msg}"
            }

        # Обновление прошло успешно
        return {
            "success": True,
            "message": "Обновление успешно установлено и протестировано.",
            "snapshot": snapshot_dir
        }

    except Exception as e:
        # Аварийный откат при неожиданных исключениях
        roll_ok, roll_msg = restore_snapshot(snapshot_dir)
        return {
            "success": False,
            "rolled_back": True,
            "error": f"Непредвиденная ошибка обновления: {e}. АВТОМАТИЧЕСКИЙ ОТКАТ: {roll_msg}"
        }


def is_update_available() -> Tuple[bool, str]:
    """Быстрая проверка: готово ли обновление без сетевых задержек."""
    cur_v = get_current_version()
    if os.path.exists(UPDATE_INFO_FILE):
        try:
            with open(UPDATE_INFO_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            new_v = data.get("version", "")
            if new_v and new_v != cur_v:
                return True, new_v
        except Exception:
            pass
    return False, ""


def check_for_updates_quick(timeout: float = 1.0) -> Dict[str, Any]:
    """
    Быстрая предстартовая проверка обновлений (таймаут <= 1.0 сек).
    Ни при каких обстоятельствах не задерживает запуск более чем на 1 секунду.
    """
    cur_v = get_current_version()

    # 1. Проверяем локальный кэш / уведомление об обновлении
    if os.path.exists(UPDATE_INFO_FILE):
        try:
            with open(UPDATE_INFO_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            new_v = cached.get("version", "")
            if new_v and new_v != cur_v:
                return {"status": "available", "version": cur_v, "new_version": new_v, "notes": cached.get("notes", "")}
        except Exception:
            pass

    if not os.path.exists(VERSION_FILE):
        return {"status": "disabled", "version": cur_v}

    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        if not cfg.get("auto_check_enabled", True):
            return {"status": "disabled", "version": cur_v}

        remote_url = cfg.get("update_url")
        if not remote_url:
            return {"status": "up_to_date", "version": cur_v}

        import urllib.request
        req = urllib.request.Request(remote_url, headers={"User-Agent": "SkyBase-Updater"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        new_v = data.get("version", cur_v)
        if new_v != cur_v:
            os.makedirs(os.path.dirname(UPDATE_INFO_FILE), exist_ok=True)
            with open(UPDATE_INFO_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return {"status": "available", "version": cur_v, "new_version": new_v, "notes": data.get("notes", "")}
        else:
            return {"status": "up_to_date", "version": cur_v}

    except Exception:
        return {"status": "offline", "version": cur_v}



def check_for_updates_async():
    """
    Фоновая ненавязчивая проверка обновлений (без зависаний и блокировок запуска сайта).
    Если обнаружено обновление, сохраняет информацию в data/update_available.json.
    """
    def _worker():
        # Ждем 4 секунды после старта, чтобы сайт и сервер поднялись первыми
        time.sleep(4.0)
        try:
            # Здесь может быть ваш URL проверки версий (GitHub Releases / собственный сервер)
            # В данном демонстрационном релизе проверяется локальный манифест
            remote_url = None
            if os.path.exists(VERSION_FILE):
                with open(VERSION_FILE, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    remote_url = cfg.get("update_url")

            if not remote_url:
                return

            import urllib.request
            req = urllib.request.Request(remote_url, headers={"User-Agent": "SkyBase-Updater"})
            with urllib.request.urlopen(req, timeout=4.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            cur_v = get_current_version()
            new_v = data.get("version", cur_v)
            if new_v != cur_v:
                os.makedirs(os.path.dirname(UPDATE_INFO_FILE), exist_ok=True)
                with open(UPDATE_INFO_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="SkyBase Transactional Updater")
    parser.add_argument("--backup", action="store_true", help="Создать точку восстановления прямо сейчас")
    parser.add_argument("--restore", type=str, help="Откатиться на указанный снимок из data/backups/")
    parser.add_argument("--apply", type=str, help="Безопасно установить пакет обновления (zip или папка)")
    parser.add_argument("--version", action="store_true", help="Показать текущую версию")
    args = parser.parse_args()

    if args.version:
        print(f"SkyBase Version: {get_current_version()}")
    elif args.backup:
        ok, res = create_recovery_snapshot(reason="manual_user_backup")
        print(f"[{'OK' if ok else 'ERR'}] {res}")
    elif args.restore:
        ok, res = restore_snapshot(args.restore)
        print(f"[{'OK' if ok else 'ERR'}] {res}")
    elif args.apply:
        res = apply_update_package(args.apply)
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        parser.print_help()
