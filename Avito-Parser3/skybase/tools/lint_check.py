#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Комплексный линтер и анализатор проекта ElectroBase.
Проверяет:
1. Синтаксическую корректность всех Python-файлов (py_compile).
2. Синтаксическую корректность PowerShell-скриптов (server.ps1).
3. Валидность всех JSON-файлов (users.json, manifest.json, monitor_state.json).
4. Отсутствие недопустимых абсолютных путей-хардкодов (диски E:, D:, C:\ins\...).
5. Целостность SQLite баз данных (PRAGMA integrity_check).
"""

import os
import sys
import py_compile
import json
import sqlite3
import subprocess
import re

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_DIR = os.path.dirname(TOOLS_DIR)

if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

def check_python_syntax() -> list:
    """Проверяет синтаксис всех Python-файлов."""
    errors = []
    for root, dirs, files in os.walk(SITE_DIR):
        dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", ".ruff_cache", "installer", ".bak", "scratch"]]
        for f in files:
            if f.endswith(".py"):
                fp = os.path.join(root, f)
                try:
                    py_compile.compile(fp, doraise=True)
                except py_compile.PyCompileError as e:
                    rel = os.path.relpath(fp, SITE_DIR)
                    errors.append(f"[Python] Ошибка компиляции {rel}: {e}")
    return errors

def check_json_validity() -> list:
    """Проверяет валидность всех конфигурационных JSON-файлов."""
    errors = []
    for root, dirs, files in os.walk(SITE_DIR):
        dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", ".ruff_cache", "installer", ".bak", "scratch"]]
        for f in files:
            if f.endswith(".json"):
                fp = os.path.join(root, f)
                try:
                    with open(fp, "r", encoding="utf-8-sig") as jf:
                        json.load(jf)
                except Exception as e:
                    rel = os.path.relpath(fp, SITE_DIR)
                    errors.append(f"[JSON] Некорректный JSON в {rel}: {e}")
    return errors

def check_hardcoded_paths() -> list:
    """Проверяет отсутствие жестко зашитых путей к дискам E:, D: и C:\ins."""
    warnings = []
    suspicious_patterns = [
        re.compile(r'e:\\\\temp', re.I),
        re.compile(r'd:\\\\temp', re.I),
        re.compile(r'c:\\\\ins\\\\exp', re.I)
    ]
    scan_exts = (".py", ".ps1", ".json", ".bat", ".sh")
    for root, dirs, files in os.walk(SITE_DIR):
        dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", ".ruff_cache", "installer", ".bak", "tools"]]
        for f in files:
            if f.endswith(scan_exts):
                fp = os.path.join(root, f)
                try:
                    with open(fp, "r", encoding="utf-8", errors="ignore") as fl:
                        for num, line in enumerate(fl, 1):
                            for pat in suspicious_patterns:
                                if pat.search(line):
                                    rel = os.path.relpath(fp, SITE_DIR)
                                    warnings.append(f"[Хардкод пути] {rel}:{num} -> {line.strip()[:80]}")
                except Exception:
                    pass
    return warnings

def check_sqlite_integrity() -> list:
    """Проверяет целостность SQLite баз данных."""
    errors = []
    db_candidates = [
        os.path.join(SITE_DIR, "avito_bot", "avito_bot.db"),
        os.path.join(SITE_DIR, "data", "database.db")
    ]
    for db in db_candidates:
        if os.path.exists(db):
            try:
                con = sqlite3.connect(db)
                cur = con.cursor()
                cur.execute("PRAGMA integrity_check;")
                res = cur.fetchone()[0]
                con.close()
                if res.lower() != "ok":
                    rel = os.path.relpath(db, SITE_DIR)
                    errors.append(f"[SQLite] Нарушена целостность базы {rel}: {res}")
            except Exception as e:
                rel = os.path.relpath(db, SITE_DIR)
                errors.append(f"[SQLite] Ошибка подключения к базе {rel}: {e}")
    return errors

def check_powershell_syntax() -> list:
    """Проверяет наличие UTF-8 BOM и синтаксис PowerShell-скриптов."""
    errors = []
    for root, dirs, files in os.walk(SITE_DIR):
        dirs[:] = [d for d in dirs if d not in [".git", "__pycache__", ".ruff_cache", "installer", ".bak", "tools"]]
        for f in files:
            if f == "server.ps1":
                fp = os.path.join(root, f)
                rel = os.path.relpath(fp, SITE_DIR)
                # 1. Проверка UTF-8 BOM
                try:
                    with open(fp, "rb") as pf:
                        hdr = pf.read(3)
                    if hdr != b"\xef\xbb\xbf":
                        with open(fp, "rb") as pf:
                            data = pf.read()
                        with open(fp, "wb") as pf:
                            pf.write(b"\xef\xbb\xbf" + data)
                except Exception as e:
                    errors.append(f"[PowerShell] Ошибка проверки BOM {rel}: {e}")
                
                # 2. Проверка синтаксиса через Parser
                try:
                    ps_cmd = f"$errs = $null; $toks = $null; $ast = [System.Management.Automation.Language.Parser]::ParseFile('{fp}', [ref]$toks, [ref]$errs); if ($errs) {{ $errs | ForEach-Object {{ Write-Output ('ERR:' + $_.Extent.StartLineNumber + ':' + $_.Message) }} }}"
                    res = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15)
                    for line in res.stdout.splitlines():
                        if line.startswith("ERR:"):
                            errors.append(f"[PowerShell] {rel} {line}")
                except Exception as e:
                    errors.append(f"[PowerShell] Ошибка синтаксического анализа {rel}: {e}")
    return errors

def run_all_checks():
    """Запускает полную проверку проекта."""
    print("=" * 60)
    print("        SkyBase Code & System Integrity Checker")
    print("=" * 60)

    py_errs = check_python_syntax()
    if py_errs:
        print(f"\n[!] Ошибки синтаксиса Python ({len(py_errs)}):")
        for e in py_errs:
            print("  ", e)
    else:
        print("[+] Все Python-скрипты синтаксически корректны.")

    json_errs = check_json_validity()
    if json_errs:
        print(f"\n[!] Ошибки валидации JSON ({len(json_errs)}):")
        for e in json_errs:
            print("  ", e)
    else:
        print("[+] Все JSON-файлы корректны.")

    hard_warns = check_hardcoded_paths()
    if hard_warns:
        print(f"\n[!] Найдены остаточные хардкоды путей ({len(hard_warns)}):")
        for w in hard_warns:
            print("  ", w)
    else:
        print("[+] Абсолютные хардкоды путей в рабочем коде отсутствуют.")

    db_errs = check_sqlite_integrity()
    if db_errs:
        print(f"\n[!] Ошибки баз данных ({len(db_errs)}):")
        for e in db_errs:
            print("  ", e)
    else:
        print("[+] Базы данных SQLite проверены: статус OK.")

    ps_errs = check_powershell_syntax()
    if ps_errs:
        print(f"\n[!] Ошибки синтаксиса PowerShell ({len(ps_errs)}):")
        for e in ps_errs:
            print("  ", e)
    else:
        print("[+] PowerShell-скрипты проверены (BOM + синтаксис): статус OK.")

    print("\n" + "=" * 60)
    total_issues = len(py_errs) + len(json_errs) + len(hard_warns) + len(db_errs) + len(ps_errs)
    if total_issues == 0:
        print("[OK] Все проверки успешно пройдены! Проект готов к работе.")
    else:
        print(f"[!] Обнаружено замечаний: {total_issues}")
    print("=" * 60)

if __name__ == "__main__":
    run_all_checks()