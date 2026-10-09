# -*- coding: utf-8 -*-
"""
Утилита администратора для управления и выдачи лицензионных ключей SkyBase.
Поддерживает:
1. Базу данных устройств и закрепленных паролей (Device & Password Registry):
   - Хранение всех клиентских компьютеров и истории всех паролей для каждого ПК.
   - Сверка при переустановке Windows: распознавание устройства по ID/MAC,
     выдача второго/следующего пароля и закрепление его за данным устройством.
2. Аппаратную привязку лицензий (Challenge-Response / Запрос-Ответ):
   - Клиент копирует на сайте ID код оборудования (EBID-XXXX-XXXX-XXXX-XXXX-XXXX).
   - Администратор вставляет ID код в KeyManager, программа производит сверку с базой.
   - Генерирует уникальный ответный ключ (EB30-... или VIPX-...), закрепляемый за устройством.
   - Этот ключ активируется ТОЛЬКО на компьютере с данным ID и не работает на чужих ПК.
3. Традиционную выдачу 20-значных ключей из базы (10 000 шт).
4. Полный реестр выданных лицензий и мониторинг их статуса на сайте.
"""
from __future__ import annotations
import os
import sys
import json
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
import datetime
import re
import typing
from typing import Optional, Dict, Any, Tuple, List, Union

# Кодировка
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Определение директории (работает и как .py, и как скомпилированный standalone .exe)
if getattr(sys, 'frozen', False):
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

import ctypes

# Регистрация отдельного AppUserModelID в Windows, чтобы таскбар использовал наш значок вместо пера Tkinter
try:
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('skybase.keymanager.admin.v1')
except Exception:
    pass

def ensure_single_instance():
    """Защита от повторного запуска: предотвращает открытие дубликатов KeyManager."""
    if sys.platform == "win32":
        try:
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32
            mutex_name = "Global\\SkyBaseKeyManagerSingleInstanceMutex"
            mutex = kernel32.CreateMutexW(None, False, mutex_name)
            last_error = kernel32.GetLastError()
            ERROR_ALREADY_EXISTS = 183
            if last_error == ERROR_ALREADY_EXISTS:
                # Находим уже открытое окно и разворачиваем его на передний план
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
                    user32.ShowWindow(target_hwnd[0], 9)  # SW_RESTORE
                    user32.SetForegroundWindow(target_hwnd[0])
                    user32.BringWindowToTop(target_hwnd[0])
                    user32.AttachThreadInput(current_tid, target_tid, False)
                sys.exit(0)
            return mutex
        except Exception:
            pass
    return None

def get_resource_path(relative_path):
    """Находит ресурс как при обычном запуске, так и внутри скомпилированного .exe."""
    if hasattr(sys, '_MEIPASS'):
        p = os.path.join(sys._MEIPASS, relative_path)
        if os.path.exists(p):
            return p
    p = os.path.join(SCRIPT_DIR, relative_path)
    if os.path.exists(p):
        return p
    site_p = os.path.join(SCRIPT_DIR, "SITE", relative_path)
    if os.path.exists(site_p):
        return site_p
    parent_p = os.path.join(os.path.dirname(SCRIPT_DIR), relative_path)
    if os.path.exists(parent_p):
        return parent_p
    return relative_path

if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)
parent_script_dir = os.path.dirname(SCRIPT_DIR)
if parent_script_dir not in sys.path:
    sys.path.append(parent_script_dir)

try:
    import hwid_security
except Exception:
    hwid_security = None

try:
    import devices_db
except Exception:
    devices_db = None

def find_data_dir() -> str:
    candidates = []
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        candidates.extend([
            os.path.join(exe_dir, "data"),
            os.path.join(exe_dir, "SITE", "data"),
            os.path.join(os.path.dirname(exe_dir), "SITE", "data"),
            os.path.join(os.path.dirname(exe_dir), "data"),
        ])

    file_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.extend([
        os.path.join(file_dir, "data"),
        os.path.join(file_dir, "SITE", "data"),
        os.path.join(os.path.dirname(file_dir), "SITE", "data"),
        os.path.join(os.path.dirname(file_dir), "data"),
    ])

    for c in candidates:
        if os.path.exists(c) and (
            os.path.exists(os.path.join(c, "devices.json")) or 
            os.path.exists(os.path.join(c, "dispensed_keys.json")) or 
            os.path.exists(os.path.join(c, "users.json")) or 
            os.path.exists(os.path.join(c, "license_keys.json"))
        ):
            return c

    for c in candidates:
        if os.path.exists(c):
            return c

    fallback = os.path.join(file_dir, "data")
    os.makedirs(fallback, exist_ok=True)
    return fallback

DATA_DIR = find_data_dir()
KEYS_LIST_PATH = os.path.join(DATA_DIR, "license_keys_10000_list.txt")
VIP_KEYS_LIST_PATH = os.path.join(DATA_DIR, "license_keys_unlimited_vip_100.txt")
KEYS_JSON_PATH = os.path.join(DATA_DIR, "license_keys.json")
DISPENSED_PATH = os.path.join(DATA_DIR, "dispensed_keys.json")
DEVICES_JSON_PATH = os.path.join(DATA_DIR, "devices.json")

# Встроенные криптографические функции на случай автономной работы .exe без внешних файлов (SkyBase)
MASTER_LICENSE_SECRET = "SkyBase_HWID_v3_2026_KeyShield_@AvitoSecure"

def fallback_parse_request_id(req_id_str: str):
    s = str(req_id_str).strip().upper()
    if s.startswith("EBID"):
        s = s[4:].lstrip("-: ").strip()
    clean = re.sub(r"[^0-9A-Fa-f]", "", s)
    if len(clean) != 20:
        return {"valid": False, "error": f"Длина ID кода {len(clean)} вместо 20 символов"}
    mac_tail = clean[0:4]
    hw_sig = clean[4:10]
    part1 = clean[10:16]
    chk = clean[16:20]
    exp_chk = hashlib.sha256(f"CHK:{mac_tail}:{hw_sig}:{part1}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:4]
    if chk != exp_chk:
        return {"valid": False, "error": "Неверная контрольная сумма ID кода"}
    exp_part1 = hashlib.sha256(f"P1:{hw_sig}:{mac_tail}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:6]
    if part1 != exp_part1:
        return {"valid": False, "error": "Недействительная сигнатура железа"}
    return {
        "valid": True,
        "mac_tail": mac_tail,
        "hw_sig": hw_sig,
        "part1": part1,
        "chk": chk,
        "request_id": f"EBID-{clean[0:4]}-{clean[4:8]}-{clean[8:12]}-{clean[12:16]}-{clean[16:20]}"
    }

def fallback_gen_response_key(parsed: dict, tier: str = "30_days"):
    hw_sig = parsed["hw_sig"]
    part1 = parsed["part1"]
    is_vip = tier.lower() in ("unlimited", "vip", "vipx", "бессрочный", "безлимит")
    tier_code = "VIPX" if is_vip else "EB30"
    tier_id = "VIP" if is_vip else "STD"
    part2 = hashlib.sha256(f"P2:{hw_sig}:{part1}:{tier_id}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:12]
    r_chk = hashlib.sha256(f"RCHK:{tier_code}:{hw_sig}:{part2}:{MASTER_LICENSE_SECRET}".encode("utf-8")).hexdigest().upper()[:4]
    raw_resp = f"{tier_code}{part2}{r_chk}"
    return f"{raw_resp[0:4]}-{raw_resp[4:8]}-{raw_resp[8:12]}-{raw_resp[12:16]}-{raw_resp[16:20]}"

def load_json_file(path: str) -> dict:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading {path}: {e}")
    return {}

def save_json_file(path: str, data: dict):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {path}: {e}")

def parse_keys_list(key_type: str = "all"):
    """Читает ключи: стандартные 30 дней и VIP бессрочные."""
    standard_keys = []
    vip_keys = []

    if os.path.exists(KEYS_LIST_PATH):
        with open(KEYS_LIST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("="):
                    continue
                if "." in line:
                    parts = line.split(".", 1)
                    num_str = parts[0].strip()
                    key_str = parts[1].strip()
                    if len(key_str.replace("-", "")) == 20:
                        standard_keys.append((num_str, key_str, "30_days"))

    if os.path.exists(VIP_KEYS_LIST_PATH):
        with open(VIP_KEYS_LIST_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("="):
                    continue
                if "." in line:
                    parts = line.split(".", 1)
                    num_str = parts[0].strip()
                    key_str = parts[1].strip()
                    if len(key_str.replace("-", "")) == 20:
                        vip_keys.append((num_str, key_str, "unlimited"))

    if key_type == "standard":
        return standard_keys
    elif key_type == "vip":
        return vip_keys
    return vip_keys + standard_keys

class KeyManagerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("🔑 Генератор & Менеджер Лицензий — SkyBase (База устройств и HWID)")
        self.root.geometry("980x760")
        self.root.minsize(860, 600)
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

        self.all_keys = parse_keys_list()
        self.db_hashes = load_json_file(KEYS_JSON_PATH)
        self.dispensed = load_json_file(DISPENSED_PATH)
        self.current_matched_device = None

        self.setup_ui()
        self.refresh_stats()
        self.refresh_devices_table()

    def setup_ui(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background="#0f172a", foreground="#f8fafc", font=("Segoe UI", 10))
        style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground="#fbbf24")
        style.configure("Stat.TLabel", font=("Segoe UI", 11, "bold"), foreground="#38bdf8")

        style.configure("TNotebook", background="#0f172a", borderwidth=0)
        style.configure("TNotebook.Tab", background="#1e293b", foreground="#94a3b8", font=("Segoe UI", 10, "bold"), padding=[14, 6])
        style.map("TNotebook.Tab", background=[("selected", "#0284c7")], foreground=[("selected", "#ffffff")])

        # Стили таблиц
        style.configure("Treeview", background="#1e293b", foreground="#f8fafc", fieldbackground="#1e293b", 
                        rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#0f172a", foreground="#38bdf8", font=("Segoe UI", 9, "bold"))
        style.map("Treeview", background=[("selected", "#0369a1")])

        # Верхняя панель: Шапка и Статистика
        header_frame = tk.Frame(self.root, bg="#1e293b", padx=16, pady=10, relief="ridge", bd=1)
        header_frame.pack(fill="x", padx=12, pady=(10, 6))

        title_row = tk.Frame(header_frame, bg="#1e293b")
        title_row.pack(fill="x")

        # Логотип в шапке
        logo_file = get_resource_path(os.path.join("img", "skybase_header_logo.png"))
        self._header_logo_img = None
        if os.path.exists(logo_file):
            try:
                from PIL import Image, ImageTk
                self._header_logo_img = ImageTk.PhotoImage(Image.open(logo_file))
                lbl_icon = tk.Label(title_row, image=self._header_logo_img, bg="#1e293b")
                lbl_icon.pack(side="left", padx=(0, 10))
            except Exception:
                pass

        title_lbl = tk.Label(title_row, text="Менеджер Лицензий SkyBase — База устройств и защита железа ПК", 
                             font=("Segoe UI", 12, "bold"), bg="#1e293b", fg="#fbbf24")
        title_lbl.pack(side="left")

        stats_row = tk.Frame(header_frame, bg="#1e293b")
        stats_row.pack(fill="x", pady=(6, 0))

        self.lbl_stat_devices = tk.Label(stats_row, text="🖥️ Устройств в базе: 0", bg="#1e293b", fg="#38bdf8", font=("Segoe UI", 9, "bold"))
        self.lbl_stat_devices.pack(side="left", padx=(0, 14))

        self.lbl_stat_dispensed = tk.Label(stats_row, text="📤 Выдано паролей: 0", bg="#1e293b", fg="#facc15", font=("Segoe UI", 9, "bold"))
        self.lbl_stat_dispensed.pack(side="left", padx=(0, 14))

        self.lbl_stat_activated = tk.Label(stats_row, text="✅ Активировано: 0", bg="#1e293b", fg="#34d399", font=("Segoe UI", 9, "bold"))
        self.lbl_stat_activated.pack(side="left", padx=(0, 14))

        self.lbl_stat_vip = tk.Label(stats_row, text="👑 VIP: 100", bg="#1e293b", fg="#c084fc", font=("Segoe UI", 9, "bold"))
        self.lbl_stat_vip.pack(side="left", padx=(0, 14))

        self.lbl_stat_available = tk.Label(stats_row, text="🟢 Свободно в пуле: 0", bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9, "bold"))
        self.lbl_stat_available.pack(side="left")

        # Вкладки: 1) Аппаратная привязка и сверка  2) База устройств и история паролей  3) Выдача из пула 10 000
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="x", padx=12, pady=4)

        # =========================================================================
        # TAB 1: Аппаратная привязка и СВЕРКА УСТРОЙСТВА
        # =========================================================================
        tab_hw = tk.Frame(self.notebook, bg="#0f172a", padx=14, pady=10)
        self.notebook.add(tab_hw, text=" 🔐 Привязка к ПК & Сверка устройств ")

        # Описание работы
        tk.Label(tab_hw, 
                 text="Вставьте ID код компьютера от клиента. Программа моментально выполнит сверку с базой устройств:\n"
                      "• Если устройство новое — будет зарегистрирована новая карточка ПК и выдан Пароль №1.\n"
                      "• Если Windows переустановлена или продлевается тариф — программа закрепит Пароль №2 (или следующий) за этим же ПК.",
                 bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 9), justify="left").pack(anchor="w", pady=(0, 6))

        # Поле ввода ID кода клиента
        req_id_row = tk.Frame(tab_hw, bg="#0f172a")
        req_id_row.pack(fill="x", pady=2)

        tk.Label(req_id_row, text="1. ID код от клиента:", font=("Segoe UI", 10, "bold"), 
                 bg="#0f172a", fg="#fbbf24").pack(side="left", padx=(0, 10))

        self.entry_client_req_id = tk.Entry(req_id_row, font=("Consolas", 13, "bold"), 
                                            bg="#1e293b", fg="#38bdf8", relief="flat", bd=3)
        self.entry_client_req_id.pack(side="left", fill="x", expand=True, ipady=4)
        self.entry_client_req_id.bind("<KeyRelease>", self.on_client_req_id_change)

        btn_paste_id = tk.Button(req_id_row, text="📋 Вставить", font=("Segoe UI", 9, "bold"),
                                 bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=10,
                                 command=self.action_paste_req_id)
        btn_paste_id.pack(side="left", padx=(8, 0))

        btn_clear_id = tk.Button(req_id_row, text="✖", font=("Segoe UI", 9),
                                 bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=8,
                                 command=self.action_clear_req_id)
        btn_clear_id.pack(side="left", padx=(4, 0))

        # Статус распознавания и СВЕРКИ с базой устройств
        self.frame_match_box = tk.Frame(tab_hw, bg="#1e293b", relief="groove", bd=1, padx=10, pady=6)
        self.frame_match_box.pack(fill="x", pady=(4, 6))

        self.lbl_hw_detect = tk.Label(self.frame_match_box, 
                                      text="⚪ Вставьте ID код клиента (например: EBID-1AEC-084C-7AB8-8CF5-88B7)", 
                                      bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9), justify="left")
        self.lbl_hw_detect.pack(anchor="w")

        # Параметры закрепления: Назначение / Заметка
        fields_row = tk.Frame(tab_hw, bg="#0f172a")
        fields_row.pack(fill="x", pady=4)

        tk.Label(fields_row, text="2. Назначение / Событие:", font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#fbbf24").pack(side="left", padx=(0, 8))
        self.combo_hw_reason = ttk.Combobox(fields_row, values=[
            "Продление тарифа",
            "Первичная выдача ключа",
            "Переустановка Windows (пароль #2)",
            "Замена накопителя / оборудования",
            "Восстановление доступа"
        ], font=("Segoe UI", 9), width=35)
        self.combo_hw_reason.pack(side="left", fill="x", expand=True)
        self.combo_hw_reason.set("Первичная выдача ключа")
        self.combo_hw_reason.bind("<<ComboboxSelected>>", self.on_reason_changed)
        self.combo_hw_reason.bind("<KeyRelease>", self.on_reason_changed)

        # Скрытое поле для совместимости с кодом
        self.client_name = "skynet83"

        # Выбор тарифа / Срок действия ключа (ручной ввод + быстрые пресеты)
        time_box = tk.LabelFrame(tab_hw, text=" 3. Срок действия ключа (ручной ввод / пресеты) ", 
                                 bg="#0f172a", fg="#fbbf24", font=("Segoe UI", 9, "bold"), padx=10, pady=6)
        time_box.pack(fill="x", pady=4)

        # Выбор режима: По сроку vs VIP
        opts_row = tk.Frame(time_box, bg="#0f172a")
        opts_row.pack(fill="x", pady=(0, 4))

        self.hw_tier_mode = tk.StringVar(value="timed")
        rb_hw_timed = tk.Radiobutton(opts_row, text="⏱️ По сроку (дни / точная дата и время)", variable=self.hw_tier_mode, value="timed",
                                     bg="#0f172a", fg="#f8fafc", selectcolor="#1e293b", activebackground="#0f172a",
                                     font=("Segoe UI", 9, "bold"), command=self.on_hw_tier_changed)
        rb_hw_timed.pack(side="left", padx=(0, 16))

        rb_hw_vip = tk.Radiobutton(opts_row, text="👑 VIP Бессрочная (Безлимит / навсегда)", variable=self.hw_tier_mode, value="unlimited",
                                   bg="#0f172a", fg="#c084fc", selectcolor="#1e293b", activebackground="#0f172a",
                                   font=("Segoe UI", 9, "bold"), command=self.on_hw_tier_changed)
        rb_hw_vip.pack(side="left", padx=(0, 16))

        # Информационная плашка режима продления
        self.frame_renewal_notice = tk.Frame(time_box, bg="#0c2a44", padx=10, pady=5)
        self.lbl_renewal_title = tk.Label(self.frame_renewal_notice, text="", font=("Segoe UI", 9, "bold"), bg="#0c2a44", fg="#38bdf8", justify="left")
        self.lbl_renewal_title.pack(anchor="w")
        self.lbl_renewal_sub = tk.Label(self.frame_renewal_notice, text="", font=("Segoe UI", 8), bg="#0c2a44", fg="#bae6fd", justify="left")
        self.lbl_renewal_sub.pack(anchor="w")

        # Пресеты быстрых сроков
        self.presets_row = tk.Frame(time_box, bg="#0f172a")
        self.presets_row.pack(fill="x", pady=2)

        tk.Label(self.presets_row, text="Быстрый выбор:", font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#94a3b8").pack(side="left", padx=(0, 6))

        preset_list = [
            ("7 дн.", 7),
            ("14 дн.", 14),
            ("30 дн. (1 мес)", 30),
            ("60 дн. (2 мес)", 60),
            ("90 дн. (3 мес)", 90),
            ("180 дн. (полгода)", 180),
            ("365 дн. (1 год)", 365),
        ]
        self.preset_buttons = []
        for p_label, p_days in preset_list:
            btn_p = tk.Button(self.presets_row, text=p_label, font=("Segoe UI", 8, "bold"),
                              bg="#1e293b", fg="#38bdf8", activebackground="#0284c7", activeforeground="#ffffff",
                              relief="flat", cursor="hand2", padx=6, pady=2,
                              command=lambda d=p_days: self.set_preset_days(d))
            btn_p.pack(side="left", padx=2)
            self.preset_buttons.append((btn_p, p_label, p_days))
        self.selected_preset_days = 30
        self.highlight_preset(30)

        # Ручной ввод дней, точной даты и времени (с точностью до минут)
        self.manual_row = tk.Frame(time_box, bg="#0f172a")
        self.manual_row.pack(fill="x", pady=(4, 2))

        tk.Label(self.manual_row, text="Срок (дней):", font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#f8fafc").pack(side="left", padx=(0, 4))
        self.entry_custom_days = tk.Entry(self.manual_row, font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#38bdf8", 
                                          justify="center", relief="flat", bd=2, width=5)
        self.entry_custom_days.pack(side="left", padx=(0, 8))
        self.entry_custom_days.insert(0, "30")
        self.entry_custom_days.bind("<KeyRelease>", self.on_custom_days_change)

        tk.Label(self.manual_row, text="Дата окончания:", font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#f8fafc").pack(side="left", padx=(0, 4))
        self.entry_custom_date = tk.Entry(self.manual_row, font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#38bdf8", 
                                          justify="center", relief="flat", bd=2, width=11)
        self.entry_custom_date.pack(side="left", padx=(0, 8))
        default_target = datetime.date.today() + datetime.timedelta(days=30)
        self.entry_custom_date.insert(0, default_target.strftime("%d.%m.%Y"))
        self.entry_custom_date.bind("<KeyRelease>", self.on_custom_date_change)

        tk.Label(self.manual_row, text="Время (ЧЧ:ММ):", font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#f8fafc").pack(side="left", padx=(0, 4))
        self.entry_custom_time = tk.Entry(self.manual_row, font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#38bdf8", 
                                          justify="center", relief="flat", bd=2, width=7)
        self.entry_custom_time.pack(side="left", padx=(0, 6))
        self.entry_custom_time.insert(0, "23:59")
        self.entry_custom_time.bind("<KeyRelease>", self.on_custom_time_change)

        btn_t_end = tk.Button(self.manual_row, text="23:59", font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8",
                              relief="flat", cursor="hand2", padx=4, pady=1, command=lambda: self.set_preset_time("23:59"))
        btn_t_end.pack(side="left", padx=2)

        btn_t_now = tk.Button(self.manual_row, text="Сейчас", font=("Segoe UI", 8), bg="#1e293b", fg="#94a3b8",
                              relief="flat", cursor="hand2", padx=4, pady=1, command=self.set_current_time_preset)
        btn_t_now.pack(side="left", padx=2)

        # Итог / расчетная строка
        self.lbl_calculated_time = tk.Label(time_box, font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#34d399")
        self.lbl_calculated_time.pack(anchor="w", pady=(2, 0))
        self.update_calculated_label()

        # Генерация и результат
        gen_action_row = tk.Frame(tab_hw, bg="#0f172a")
        gen_action_row.pack(fill="x", pady=(8, 4))

        self.btn_gen_hw = tk.Button(gen_action_row, text="🚀 Сгенерировать и закрепить ключ", font=("Segoe UI", 10, "bold"),
                                    bg="#059669", fg="#ffffff", activebackground="#047857", activeforeground="#ffffff",
                                    relief="flat", cursor="hand2", padx=14, pady=5, command=self.action_gen_response_key)
        self.btn_gen_hw.pack(side="left")

        self.entry_resp_key = tk.Entry(gen_action_row, font=("Consolas", 14, "bold"), 
                                       bg="#1e293b", fg="#38bdf8", justify="center", relief="flat", bd=3)
        self.entry_resp_key.pack(side="left", fill="x", expand=True, padx=10, ipady=4)

        btn_copy_resp = tk.Button(gen_action_row, text="📋 Скопировать", font=("Segoe UI", 10, "bold"),
                                  bg="#2563eb", fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff",
                                  relief="flat", cursor="hand2", padx=14, pady=5, command=self.action_copy_response_key)
        btn_copy_resp.pack(side="left")

        # Панель "Ключи пользователя" прямо под кнопкой генерации пароля
        user_keys_row = tk.Frame(tab_hw, bg="#0f172a")
        user_keys_row.pack(fill="x", pady=(4, 4))

        self.btn_user_keys = tk.Button(
            user_keys_row,
            text="🔑 Ключи пользователя",
            font=("Segoe UI", 10, "bold"),
            bg="#334155",
            fg="#f8fafc",
            activebackground="#475569",
            activeforeground="#ffffff",
            relief="flat",
            cursor="hand2",
            padx=14,
            pady=4,
            command=self.action_show_user_keys
        )
        self.btn_user_keys.pack(side="left")

        self.lbl_user_keys_badge = tk.Label(
            user_keys_row,
            text="⚪ Вставьте ID клиента для мгновенной сверки ключей",
            font=("Segoe UI", 9, "bold"),
            bg="#1e293b",
            fg="#94a3b8",
            padx=8,
            pady=3,
            relief="groove",
            bd=1
        )
        self.lbl_user_keys_badge.pack(side="left", padx=(10, 0))

        self.lbl_hw_status = tk.Label(tab_hw, text="", bg="#0f172a", fg="#34d399", font=("Segoe UI", 9, "bold"))
        self.lbl_hw_status.pack(anchor="w", pady=(3, 0))

        # =========================================================================
        # TAB 2: БАЗА УСТРОЙСТВ И ЗАКРЕПЛЕННЫЕ ПАРОЛИ
        # =========================================================================
        tab_devs = tk.Frame(self.notebook, bg="#0f172a", padx=12, pady=8)
        self.notebook.add(tab_devs, text=" 🖥️ База устройств & Закрепленные пароли ")

        # Верхняя панель поиска устройств
        dev_search_row = tk.Frame(tab_devs, bg="#0f172a")
        dev_search_row.pack(fill="x", pady=(0, 6))

        tk.Label(dev_search_row, text="🔍 Поиск устройства:", font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#fbbf24").pack(side="left", padx=(0, 6))
        self.entry_dev_search = tk.Entry(dev_search_row, font=("Segoe UI", 9), bg="#1e293b", fg="#38bdf8", relief="flat", bd=2)
        self.entry_dev_search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_dev_search.bind("<KeyRelease>", lambda e: self.refresh_devices_table())

        btn_refresh_devs = tk.Button(dev_search_row, text="🔄 Обновить", font=("Segoe UI", 9, "bold"),
                                     bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=10,
                                     command=self.refresh_devices_table)
        btn_refresh_devs.pack(side="left")

        # Split frame: слева устройства, справа закрепленные пароли
        dev_split = tk.Frame(tab_devs, bg="#0f172a")
        dev_split.pack(fill="both", expand=True)

        # Левая часть: Таблица устройств
        left_box = tk.LabelFrame(dev_split, text=" Реестр устройств клиентов ", bg="#0f172a", fg="#f8fafc", font=("Segoe UI", 9, "bold"))
        left_box.pack(side="left", fill="both", expand=True, padx=(0, 6))

        dev_cols = ("dev_id", "dev_type", "mac", "count", "active_key", "tier", "updated")
        self.tree_devs = ttk.Treeview(left_box, columns=dev_cols, show="headings", selectmode="browse", height=7)
        self.tree_devs.heading("dev_id", text="Код устройства")
        self.tree_devs.heading("dev_type", text="Тип")
        self.tree_devs.heading("mac", text="MAC / Идентификатор")
        self.tree_devs.heading("count", text="Паролей")
        self.tree_devs.heading("active_key", text="Активный пароль")
        self.tree_devs.heading("tier", text="Тариф")
        self.tree_devs.heading("updated", text="Дата обновления")

        self.tree_devs.column("dev_id", width=115, anchor="center")
        self.tree_devs.column("dev_type", width=95, anchor="center")
        self.tree_devs.column("mac", width=125, anchor="center")
        self.tree_devs.column("count", width=65, anchor="center")
        self.tree_devs.column("active_key", width=195, anchor="center")
        self.tree_devs.column("tier", width=85, anchor="center")
        self.tree_devs.column("updated", width=120, anchor="center")

        sb_dev = ttk.Scrollbar(left_box, orient="vertical", command=self.tree_devs.yview)
        self.tree_devs.configure(yscrollcommand=sb_dev.set)
        self.tree_devs.pack(side="left", fill="both", expand=True)
        sb_dev.pack(side="right", fill="y")
        self.tree_devs.bind("<<TreeviewSelect>>", self.on_device_selected)
        self.tree_devs.bind("<Double-1>", lambda e: self.copy_selected_device_password())
        self.tree_devs.bind("<Control-c>", lambda e: self.copy_selected_device_password())
        self.tree_devs.bind("<Button-3>", self.show_tree_devs_context_menu)

        # Нижняя часть Tab 2: История паролей выбранного устройства
        self.detail_frame = tk.LabelFrame(tab_devs, text=" 📜 История всех паролей, закрепленных за данным устройством ", 
                                          bg="#0f172a", fg="#fbbf24", font=("Segoe UI", 9, "bold"), padx=6, pady=4)
        self.detail_frame.pack(fill="x", pady=(6, 0))

        pwd_cols = ("index", "key", "tier", "issued_at", "valid_until", "status", "reason", "activated")
        self.tree_pwds = ttk.Treeview(self.detail_frame, columns=pwd_cols, show="headings", selectmode="browse", height=4)
        self.tree_pwds.heading("index", text="№")
        self.tree_pwds.heading("key", text="Закрепленный пароль/ключ")
        self.tree_pwds.heading("tier", text="Тариф")
        self.tree_pwds.heading("issued_at", text="Время выдачи")
        self.tree_pwds.heading("valid_until", text="Действует до (вшито)")
        self.tree_pwds.heading("status", text="Статус")
        self.tree_pwds.heading("reason", text="Событие / Причина")
        self.tree_pwds.heading("activated", text="Активирован на сайте")

        self.tree_pwds.column("index", width=35, anchor="center")
        self.tree_pwds.column("key", width=210, anchor="center")
        self.tree_pwds.column("tier", width=95, anchor="center")
        self.tree_pwds.column("issued_at", width=140, anchor="center")
        self.tree_pwds.column("valid_until", width=140, anchor="center")
        self.tree_pwds.column("status", width=95, anchor="center")
        self.tree_pwds.column("reason", width=190, anchor="w")
        self.tree_pwds.column("activated", width=120, anchor="center")

        self.tree_pwds.pack(side="left", fill="x", expand=True)
        sb_pwds = ttk.Scrollbar(self.detail_frame, orient="vertical", command=self.tree_pwds.yview)
        self.tree_pwds.configure(yscrollcommand=sb_pwds.set)
        sb_pwds.pack(side="right", fill="y")
        self.tree_pwds.bind("<Double-1>", lambda e: self.copy_selected_device_password())
        self.tree_pwds.bind("<Control-c>", lambda e: self.copy_selected_device_password())
        self.tree_pwds.bind("<Button-3>", self.show_tree_pwds_context_menu)

        # Кнопки действий над выбранным устройством
        dev_actions_bar = tk.Frame(tab_devs, bg="#0f172a")
        dev_actions_bar.pack(fill="x", pady=(4, 0))

        btn_copy_pwd = tk.Button(dev_actions_bar, text="📋 Скопировать ключ (Ctrl+C / 2x клик)", font=("Segoe UI", 9, "bold"),
                                 bg="#2563eb", fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff",
                                 relief="flat", cursor="hand2", padx=12,
                                 command=self.copy_selected_device_password)
        btn_copy_pwd.pack(side="left", padx=(0, 6))

        btn_issue_next = tk.Button(dev_actions_bar, text="🔁 Выдать следующий пароль этому ПК", font=("Segoe UI", 9, "bold"),
                                   bg="#059669", fg="#ffffff", relief="flat", cursor="hand2", padx=10,
                                   command=self.jump_to_issue_next_password)
        btn_issue_next.pack(side="left", padx=(0, 6))

        btn_edit_dev = tk.Button(dev_actions_bar, text="✏️ Изменить заметку", font=("Segoe UI", 9),
                                 bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=10,
                                 command=self.edit_selected_device)
        btn_edit_dev.pack(side="left", padx=(0, 6))

        btn_del_dev = tk.Button(dev_actions_bar, text="🗑️ Удалить", font=("Segoe UI", 9),
                                bg="#7f1d1d", fg="#fca5a5", relief="flat", cursor="hand2", padx=8,
                                command=self.delete_selected_device)
        btn_del_dev.pack(side="right")

        # =========================================================================
        # TAB 3: Выдача из пула 10 000 ключей
        # =========================================================================
        tab_pool = tk.Frame(self.notebook, bg="#0f172a", padx=14, pady=10)
        self.notebook.add(tab_pool, text=" ⚡ Выдача из готовой базы (10 000 ключей) ")

        pool_type_frame = tk.Frame(tab_pool, bg="#0f172a")
        pool_type_frame.pack(fill="x", pady=(0, 6))

        self.key_dispense_mode = tk.StringVar(value="standard")
        rb_std = tk.Radiobutton(pool_type_frame, text="📦 Стандартный ключ (+30 дней)", 
                                variable=self.key_dispense_mode, value="standard",
                                bg="#0f172a", fg="#f8fafc", selectcolor="#1e293b", activebackground="#0f172a",
                                font=("Segoe UI", 9, "bold"), command=self.on_mode_changed)
        rb_std.pack(side="left", padx=(0, 20))

        rb_vip = tk.Radiobutton(pool_type_frame, text="👑 VIP Бессрочный ключ (Безлимит навсегда)", 
                                variable=self.key_dispense_mode, value="vip",
                                bg="#0f172a", fg="#a855f7", selectcolor="#1e293b", activebackground="#0f172a",
                                font=("Segoe UI", 9, "bold"), command=self.on_mode_changed)
        rb_vip.pack(side="left")

        pool_key_row = tk.Frame(tab_pool, bg="#0f172a")
        pool_key_row.pack(fill="x", pady=4)

        self.entry_current_key = tk.Entry(pool_key_row, font=("Consolas", 14, "bold"), 
                                          bg="#1e293b", fg="#38bdf8", justify="center", relief="flat", bd=3)
        self.entry_current_key.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 10))

        btn_copy_pool = tk.Button(pool_key_row, text="📋 Копировать и выдать", font=("Segoe UI", 10, "bold"),
                                  bg="#2563eb", fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff",
                                  relief="flat", cursor="hand2", padx=14, command=self.action_dispense_key)
        btn_copy_pool.pack(side="left", ipady=3)

        pool_client_frame = tk.Frame(tab_pool, bg="#0f172a")
        pool_client_frame.pack(fill="x", pady=(8, 0))

        tk.Label(pool_client_frame, text="Заметка к ключу:", bg="#0f172a", fg="#94a3b8", font=("Segoe UI", 9)).pack(side="left")
        self.entry_client_note = tk.Entry(pool_client_frame, font=("Segoe UI", 9), bg="#1e293b", fg="#f8fafc", relief="flat", bd=2)
        self.entry_client_note.pack(side="left", fill="x", expand=True, padx=8)
        self.entry_client_note.insert(0, "Оплата тарифа (30 дней)")

        self.lbl_dispense_status = tk.Label(tab_pool, text="💡 Ключ копируется в буфер обмена, в базе фиксируется выдача.", 
                                            bg="#0f172a", fg="#64748b", font=("Segoe UI", 8, "italic"))
        self.lbl_dispense_status.pack(anchor="w", pady=(4, 0))

        # =========================================================================
        # Нижняя секция: Общий журнал выданных ключей и статусов
        # =========================================================================
        log_frame = tk.LabelFrame(self.root, text=" 📜 Общий реестр выданных лицензий и активаций на сайте ", 
                                  bg="#0f172a", fg="#f8fafc", font=("Segoe UI", 10, "bold"), padx=8, pady=6)
        log_frame.pack(fill="both", expand=True, padx=12, pady=6)

        # Панель мгновенного поиска по общему реестру
        reg_search_row = tk.Frame(log_frame, bg="#0f172a")
        reg_search_row.pack(fill="x", pady=(0, 6))

        tk.Label(reg_search_row, text="🔍 Поиск в реестре:", font=("Segoe UI", 9, "bold"), bg="#0f172a", fg="#fbbf24").pack(side="left", padx=(0, 6))
        self.entry_registry_search = tk.Entry(reg_search_row, font=("Segoe UI", 9), bg="#1e293b", fg="#38bdf8", relief="flat", bd=2)
        self.entry_registry_search.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.entry_registry_search.bind("<KeyRelease>", lambda e: self.populate_tree())

        btn_clear_reg_search = tk.Button(reg_search_row, text="❌ Очистить", font=("Segoe UI", 8),
                                         bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=8,
                                         command=self.clear_registry_search)
        btn_clear_reg_search.pack(side="left")

        columns = ("id", "req_id", "type", "key", "client", "dispensed_at", "status", "used_at")
        self.tree = ttk.Treeview(log_frame, columns=columns, show="headings", selectmode="browse")
        self.tree.heading("id", text="№")
        self.tree.heading("req_id", text="Код устройства (ID клиента)")
        self.tree.heading("type", text="Тариф")
        self.tree.heading("key", text="Лицензионный / Ответный ключ")
        self.tree.heading("client", text="Заметка / Привязка")
        self.tree.heading("dispensed_at", text="Дата выдачи")
        self.tree.heading("status", text="Статус на сайте")
        self.tree.heading("used_at", text="Время активации")

        self.tree.column("id", width=35, anchor="center")
        self.tree.column("req_id", width=240, anchor="center")
        self.tree.column("type", width=95, anchor="center")
        self.tree.column("key", width=215, anchor="center")
        self.tree.column("client", width=160, anchor="w")
        self.tree.column("dispensed_at", width=125, anchor="center")
        self.tree.column("status", width=110, anchor="center")
        self.tree.column("used_at", width=125, anchor="center")

        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.tree.yview)
        xscrollbar = ttk.Scrollbar(log_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=xscrollbar.set)
        scrollbar.pack(side="right", fill="y")
        xscrollbar.pack(side="bottom", fill="x")
        self.tree.pack(side="left", fill="both", expand=True)

        self.tree.bind("<Double-1>", lambda e: self.copy_selected_key())
        self.tree.bind("<Control-c>", lambda e: self.copy_selected_key())
        self.tree.bind("<Button-3>", self.show_registry_context_menu)

        # Нижние кнопки
        bottom_bar = tk.Frame(self.root, bg="#0f172a")
        bottom_bar.pack(fill="x", padx=12, pady=(0, 8))

        btn_refresh = tk.Button(bottom_bar, text="🔄 Обновить всё", font=("Segoe UI", 9, "bold"),
                                bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=10, pady=4,
                                command=self.refresh_all)
        btn_refresh.pack(side="left", padx=(0, 8))

        btn_copy_sel = tk.Button(bottom_bar, text="📋 Скопировать ключ (Ctrl+C / 2x клик)", font=("Segoe UI", 9, "bold"),
                                 bg="#0284c7", fg="#ffffff", activebackground="#0369a1", activeforeground="#ffffff",
                                 relief="flat", cursor="hand2", padx=12, pady=4,
                                 command=self.copy_selected_key)
        btn_copy_sel.pack(side="left", padx=(0, 8))

        btn_copy_req = tk.Button(bottom_bar, text="🖥️ Скопировать код устройства", font=("Segoe UI", 9),
                                 bg="#334155", fg="#f8fafc", relief="flat", cursor="hand2", padx=10, pady=4,
                                 command=self.copy_selected_req_id)
        btn_copy_req.pack(side="left", padx=(0, 8))

        self.lbl_global_status = tk.Label(bottom_bar, text="", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#34d399")
        self.lbl_global_status.pack(side="left", padx=10)

        btn_gen_more = tk.Button(bottom_bar, text="➕ Сгенерировать пачку ключей", font=("Segoe UI", 9, "bold"),
                                 bg="#059669", fg="#ffffff", activebackground="#047857", activeforeground="#ffffff",
                                 relief="flat", cursor="hand2", padx=12, pady=4,
                                 command=self.open_generate_dialog)
        btn_gen_more.pack(side="right")

        self.show_next_available_key()

    def get_hash(self, formatted_key: str) -> str:
        raw = formatted_key.replace("-", "").strip().upper()
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def on_client_req_id_change(self, event=None, keep_resp_key: bool = False):
        """Реакция на ввод или вставку ID кода: моментальная сверка с базой устройств."""
        val = self.entry_client_req_id.get().strip()
        if not val:
            self.current_matched_device = None
            self.lbl_hw_detect.config(text="⚪ Вставьте ID код клиента (например: EBID-1AEC-084C-7AB8-8CF5-88B7)", fg="#94a3b8")
            self.btn_gen_hw.config(text="🚀 Сгенерировать и закрепить ключ", bg="#059669")
            self.update_trial_button_state("")
            self.update_user_keys_ui_state("", None)
            return
        
        parsed = hwid_security.parse_request_id(val) if hwid_security else fallback_parse_request_id(val)
        if not parsed.get("valid"):
            self.current_matched_device = None
            err = parsed.get("error", "Неверный формат")
            self.lbl_hw_detect.config(text=f"🔴 {err}", fg="#f87171")
            self.btn_gen_hw.config(text="🚀 Сгенерировать и закрепить ключ", bg="#059669")
            self.update_trial_button_state(val)
            self.update_user_keys_ui_state(val, None)
            return

        mac_t = parsed.get("mac_tail", "????")
        sig = parsed.get("hw_sig", "??????")

        # Поиск в базе устройств
        matched_dev = None
        if devices_db:
            matched_dev = devices_db.find_device_by_req_id(val)

        self.current_matched_device = matched_dev

        if matched_dev:
            # Устройство уже есть в базе!
            dev_id = matched_dev.get("device_id")
            client = matched_dev.get("client_name", "Клиент")
            notes = matched_dev.get("notes", "")
            pwds = matched_dev.get("passwords", [])
            p_count = len(pwds)
            last_key = matched_dev.get("active_key")
            if not last_key or last_key == "—":
                if pwds:
                    last_key = pwds[-1].get("key", "—")
                else:
                    last_key = "—"
            next_p_num = p_count + 1

            if hasattr(self, 'entry_hw_client'):
                self.entry_hw_client.delete(0, tk.END)
                self.entry_hw_client.insert(0, client)
            
            if not keep_resp_key:
                # Если устройство уже есть в базе, по умолчанию предлагаем «Продление тарифа»
                self.combo_hw_reason.set("Продление тарифа")

                if last_key and last_key != "—":
                    self.entry_resp_key.delete(0, tk.END)
                    self.entry_resp_key.insert(0, last_key)
                    self.entry_resp_key.config(fg="#38bdf8")
                    self.lbl_hw_status.config(
                        text=f"ℹ️ Ключ для выдачи: {last_key} (скопируйте кнопкой «Скопировать» или выдайте новый #{next_p_num})",
                        fg="#38bdf8"
                    )

            is_phone = val.upper().startswith("EBMOB") or mac_t.startswith("MO") or (matched_dev and matched_dev.get("device_type") == "phone")
            dev_icon = "📱" if is_phone else "💻"
            dev_title = "Мобильное устройство" if is_phone else "Компьютер"

            curr_exp, is_exp, exp_desc = self.get_matched_device_current_expiration()
            exp_status_line = f" | {exp_desc}" if exp_desc else ""

            # Проверка, использовало ли устройство пробный период (3 дня)
            used_trial = False
            if devices_db and hasattr(devices_db, 'has_device_used_trial'):
                used_trial = devices_db.has_device_used_trial(val)
            if not used_trial and matched_dev:
                used_trial = matched_dev.get("trial_used") or any(
                    p.get("is_trial") or "триал" in (p.get("tier_name") or "").lower() or "пробн" in (p.get("tier_name") or "").lower() or "триал" in (p.get("reason") or "").lower() or "пробн" in (p.get("reason") or "").lower()
                    for p in matched_dev.get("passwords", [])
                )

            trial_warn = "\n⛔ ВНИМАНИЕ: Пробный период (3 дня) уже ИСПОЛЬЗОВАН! Повторный триал заблокирован." if used_trial else ""

            self.lbl_hw_detect.config(
                text=f"{dev_icon} Устройство НАЙДЕНО в базе! [{dev_id}] ({dev_title}) | Заметка: {notes}\n"
                     f"Ранее закреплено ключей: {p_count}. Текущий ключ: {last_key}{exp_status_line}.{trial_warn}\n"
                     f"👉 Выберите срок продления ниже или нажмите «Выдать ключ #{next_p_num}».",
                fg="#f43f5e" if used_trial else "#f59e0b"
            )
            self.btn_gen_hw.config(
                text=f"🔁 Выдать ключ #{next_p_num} и закрепить за {dev_icon} {dev_title}",
                bg="#d97706"
            )
            self.update_renewal_ui()
            if not keep_resp_key:
                self.set_preset_days(30)
        else:
            # Новое устройство
            is_phone = val.upper().startswith("EBMOB") or mac_t.startswith("MO")
            dev_icon = "📱" if is_phone else "💻"
            dev_title = "Мобильный телефон (Смартфон)" if is_phone else "Персональный компьютер (ПК)"
            dev_id = f"MOB-{mac_t}-{sig[:4]}" if is_phone else f"DEV-{mac_t}-{sig[:4]}"
            if not keep_resp_key:
                self.combo_hw_reason.set("Первичная выдача ключа")
            id_info = f"Идентификатор: {mac_t}" if is_phone else f"Хвост MAC: **:**:**:**:{mac_t[:2]}:{mac_t[2:]}"
            self.lbl_hw_detect.config(
                text=f"🟢 НОВОЕ УСТРОЙСТВО: {dev_icon} {dev_title} [{dev_id}] | {id_info} | Сигнатура: #{sig}\n"
                     f"Устройство не найдено в базе. Будет зарегистрировано с первичным ключом #1.",
                fg="#34d399"
            )
            self.btn_gen_hw.config(
                text=f"🚀 Зарегистрировать {dev_icon} {dev_title} и выдать ключ #1",
                bg="#059669"
            )
            self.update_renewal_ui()
            if not keep_resp_key:
                self.set_preset_days(30)
        
        self.update_trial_button_state(val)
        self.update_user_keys_ui_state(val, matched_dev)

    def action_paste_req_id(self):
        try:
            val = self.root.clipboard_get().strip()
            self.entry_client_req_id.delete(0, tk.END)
            self.entry_client_req_id.insert(0, val)
            self.on_client_req_id_change()
        except Exception:
            pass

    def action_clear_req_id(self):
        self.entry_client_req_id.delete(0, tk.END)
        self.entry_resp_key.delete(0, tk.END)
        self.lbl_hw_status.config(text="")
        self.combo_hw_reason.set("Первичная выдача ключа")
        self.on_client_req_id_change()
        self.update_trial_button_state("")
        self.update_user_keys_ui_state("", None)

    def update_trial_button_state(self, req_id: str = ""):
        """Метод оставлен для совместимости; кнопка триала удалена из интерфейса."""
        return

    def action_quick_issue_trial(self):
        """Ручная выдача триал-ключей в Кей-менеджере отключена."""
        messagebox.showinfo(
            "Выдача триала отключена",
            "Ручная выдача бесплатных триал-ключей в Кей-Менеджере отключена.\n\n"
            "Выдачей пробных периодов занимается Telegram-бот @avvvskybot автоматически.",
            parent=self.root
        )

    def get_client_keys_info(self, req_id_str: str) -> Dict[str, Any]:
        """
        Возвращает детальную информацию обо всех ключах клиента из общего реестра (devices_db):
        - active_keys: список действующих (непросроченных) ключей (зелёные)
        - expired_keys: список просроченных или архивных ключей (серые)
        - all_keys: полный список всех найденных ключей
        - active_key_item: актуальный действующий ключ
        - device: карточка устройства из devices_db
        """
        req_id = (req_id_str or "").strip()
        result = {
            "valid_id": False,
            "device": None,
            "active_keys": [],
            "expired_keys": [],
            "all_keys": [],
            "active_key_item": None,
            "client_name": "skynet83",
            "device_id": "—",
            "device_title": "Устройство",
            "mac": "—",
            "notes": ""
        }
        if not req_id:
            return result

        parsed = hwid_security.parse_request_id(req_id) if hwid_security else fallback_parse_request_id(req_id)
        if not parsed.get("valid"):
            return result

        result["valid_id"] = True
        mac_t = parsed.get("mac_tail", "????")
        sig = parsed.get("hw_sig", "????")
        is_phone = req_id.upper().startswith("EBMOB") or mac_t.startswith("MO")
        result["device_title"] = "📱 Смартфон (Android)" if is_phone else "💻 Компьютер (ПК)"
        result["device_id"] = f"MOB-{mac_t}-{sig[:4]}" if is_phone else f"DEV-{mac_t}-{sig[:4]}"
        result["mac"] = f"MOB-ID:{mac_t}" if is_phone else f"**:**:**:**:{mac_t[:2]}:{mac_t[2:]}"

        # 1. Поиск в базе устройств devices_db (общий реестр)
        matched_dev = None
        if devices_db:
            matched_dev = devices_db.find_device_by_req_id(req_id)

        if matched_dev:
            result["device"] = matched_dev
            result["client_name"] = matched_dev.get("client_name", "skynet83")
            result["notes"] = matched_dev.get("notes", "")
            result["device_id"] = matched_dev.get("device_id", result["device_id"])
            if matched_dev.get("mac"):
                result["mac"] = matched_dev.get("mac")

        # 2. Сбор ключей из карточки устройства
        keys_dict: Dict[str, Dict[str, Any]] = {}
        now = datetime.datetime.now()

        if matched_dev:
            for p in matched_dev.get("passwords", []):
                k = p.get("key", "").strip()
                if not k or k == "—":
                    continue
                k_norm = devices_db.normalize_key(k) if devices_db else k
                keys_dict[k_norm] = {
                    "key": k_norm,
                    "index": p.get("index", len(keys_dict) + 1),
                    "tier": p.get("tier", "30_days"),
                    "tier_name": p.get("tier_name") or ("👑 VIP Бессрочно" if p.get("tier") in ("unlimited", "vip", "vipx") else "+30 дней"),
                    "issued_at": p.get("issued_at", "—"),
                    "valid_until": p.get("valid_until", "—"),
                    "status": p.get("status", "active"),
                    "reason": p.get("reason", "Выдача ключа"),
                    "activated": bool(p.get("activated")),
                    "activated_at": p.get("activated_at", ""),
                    "activated_by": p.get("activated_by", ""),
                    "is_trial": bool(p.get("is_trial")),
                    "source": "devices_db"
                }

        # 3. Дополнительная сверка с self.dispensed / dispensed_keys.json для 100% покрытия
        norm_req = devices_db.normalize_req_id(req_id) if devices_db else req_id.upper()
        if hasattr(self, 'dispensed') and isinstance(self.dispensed, dict):
            for k_str, disp_item in self.dispensed.items():
                d_req = disp_item.get("request_id") or ""
                d_dev_id = disp_item.get("device_id") or ""
                norm_d_req = devices_db.normalize_req_id(d_req) if devices_db else d_req.upper()
                if (norm_d_req and norm_d_req == norm_req) or (result["device_id"] and d_dev_id == result["device_id"]):
                    k_norm = devices_db.normalize_key(k_str) if devices_db else k_str
                    if k_norm not in keys_dict:
                        vu = disp_item.get("valid_until", "")
                        tier = disp_item.get("tier", "30_days")
                        is_vip = (tier in ("unlimited", "vip", "vipx") or k_norm.startswith("VIPX-"))
                        if not vu or vu == "—":
                            if devices_db:
                                vu, _ = devices_db.decode_key_valid_until(k_norm)
                        keys_dict[k_norm] = {
                            "key": k_norm,
                            "index": len(keys_dict) + 1,
                            "tier": "unlimited" if is_vip else tier,
                            "tier_name": "👑 VIP Бессрочно" if is_vip else (disp_item.get("client_note") or "+30 дней"),
                            "issued_at": disp_item.get("dispensed_at", "—"),
                            "valid_until": vu or "—",
                            "status": "active",
                            "reason": disp_item.get("client_note", "Выдача из реестра"),
                            "activated": bool(disp_item.get("activated_by")),
                            "activated_at": disp_item.get("used_at", ""),
                            "activated_by": disp_item.get("activated_by", ""),
                            "is_trial": bool(disp_item.get("is_trial")),
                            "source": "dispensed_keys"
                        }

        # 4. Классификация ключей: Активный (Зелёный) vs Просроченный (Серый)
        keys_list = list(keys_dict.values())
        for item in keys_list:
            k_val = item["key"]
            tier = item.get("tier", "")
            tier_name = item.get("tier_name", "")
            vu_str = item.get("valid_until", "")

            # Проверка VIP
            if tier in ("unlimited", "vip", "vipx") or "VIP" in tier_name.upper() or vu_str == "Бессрочно (VIP)":
                item["is_vip"] = True
                item["is_expired"] = False
                item["exp_dt"] = None
                item["exp_display"] = "👑 VIP Бессрочно (Безлимит)"
                item["time_left_str"] = "Не ограничен"
                continue

            item["is_vip"] = False
            if not vu_str or vu_str == "—":
                if devices_db:
                    vu_str, _ = devices_db.decode_key_valid_until(k_val)
                    item["valid_until"] = vu_str

            exp_dt = None
            if vu_str and vu_str != "—":
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
                    try:
                        exp_dt = datetime.datetime.strptime(vu_str.strip(), fmt)
                        break
                    except Exception:
                        pass

            item["exp_dt"] = exp_dt
            if exp_dt:
                diff = (exp_dt - now).total_seconds()
                if diff <= 0:
                    item["is_expired"] = True
                    item["exp_display"] = f"Истёк {exp_dt.strftime('%d.%m.%Y в %H:%M')}"
                    item["time_left_str"] = "Срок действия истёк"
                else:
                    item["is_expired"] = False
                    d_days = int(diff // 86400)
                    d_hours = int((diff % 86400) // 3600)
                    d_mins = int((diff % 3600) // 60)
                    if d_days > 0:
                        left_str = f"осталось {d_days} дн. {d_hours} ч."
                    else:
                        left_str = f"осталось {d_hours} ч. {d_mins} мин."
                    item["exp_display"] = f"до {exp_dt.strftime('%d.%m.%Y в %H:%M')}"
                    item["time_left_str"] = left_str
            else:
                item["is_expired"] = False
                item["exp_display"] = vu_str or "Срок не указан"
                item["time_left_str"] = "—"

        active_list = []
        expired_list = []
        for item in keys_list:
            if item.get("status") in ("replaced", "archived", "revoked"):
                item["is_expired"] = True
                expired_list.append(item)
            elif item["is_expired"]:
                expired_list.append(item)
            else:
                active_list.append(item)

        # Выбираем актуальный активный ключ (приоритет - активированный)
        active_target = None
        for item in reversed(active_list):
            if item.get("activated"):
                active_target = item
                break
        if not active_target and active_list:
            active_target = active_list[-1]

        result["active_keys"] = active_list
        result["expired_keys"] = expired_list
        result["all_keys"] = keys_list
        result["active_key_item"] = active_target
        return result

    def update_user_keys_ui_state(self, req_id: str = "", matched_dev: Optional[Dict[str, Any]] = None):
        """Обновляет состояние кнопки «🔑 Ключи пользователя» и бейджа статуса при любом изменении ID."""
        if not hasattr(self, 'btn_user_keys') or not hasattr(self, 'lbl_user_keys_badge'):
            return

        val = (req_id or self.entry_client_req_id.get()).strip()
        if not val:
            self.btn_user_keys.config(
                text="🔑 Ключи пользователя",
                bg="#334155",
                fg="#94a3b8",
                activebackground="#475569",
                activeforeground="#ffffff"
            )
            self.lbl_user_keys_badge.config(
                text="⚪ Вставьте ID клиента для мгновенной сверки ключей",
                bg="#1e293b",
                fg="#94a3b8"
            )
            return

        parsed = hwid_security.parse_request_id(val) if hwid_security else fallback_parse_request_id(val)
        if not parsed.get("valid"):
            self.btn_user_keys.config(
                text="🔑 Ключи пользователя",
                bg="#334155",
                fg="#94a3b8",
                activebackground="#475569",
                activeforeground="#ffffff"
            )
            self.lbl_user_keys_badge.config(
                text="⚠️ Недействительный формат ID кода",
                bg="#2d1519",
                fg="#f87171"
            )
            return

        info = self.get_client_keys_info(val)
        total_keys = len(info["all_keys"])
        active_keys = info["active_keys"]
        expired_keys = info["expired_keys"]
        active_item = info["active_key_item"]

        if total_keys == 0:
            self.btn_user_keys.config(
                text="🔑 Ключи пользователя (0)",
                bg="#334155",
                fg="#cbd5e1",
                activebackground="#475569",
                activeforeground="#ffffff"
            )
            self.lbl_user_keys_badge.config(
                text="🆕 Первичное обращение (ключи ещё не выдавались)",
                bg="#0c2340",
                fg="#38bdf8"
            )
        elif active_item:
            # Есть действующий зелёный ключ!
            exp_short = active_item.get("exp_display", "")
            if active_item.get("is_vip"):
                badge_desc = "🟢 VIP Бессрочно"
            else:
                badge_desc = f"🟢 {exp_short} ({active_item.get('time_left_str', '')})"
            
            archive_info = f" | Архив: {len(expired_keys)} шт." if expired_keys else ""

            self.btn_user_keys.config(
                text=f"🔑 Ключи пользователя ({total_keys})",
                bg="#059669",
                fg="#ffffff",
                activebackground="#047857",
                activeforeground="#ffffff"
            )
            self.lbl_user_keys_badge.config(
                text=f"{badge_desc}{archive_info}",
                bg="#064e3b",
                fg="#a7f3d0"
            )
        else:
            # Все выданные ключи истекли / в архиве (серая индикация)
            self.btn_user_keys.config(
                text=f"🔑 Ключи пользователя ({total_keys})",
                bg="#64748b",
                fg="#f8fafc",
                activebackground="#475569",
                activeforeground="#ffffff"
            )
            self.lbl_user_keys_badge.config(
                text=f"⚪ Все ключи истекли ({len(expired_keys)} шт.) — требуется продление",
                bg="#331518",
                fg="#fca5a5"
            )

    def action_show_user_keys(self):
        """Открывает детальное окно просмотра ключей пользователя."""
        val = self.entry_client_req_id.get().strip()
        if not val:
            try:
                clip_val = self.root.clipboard_get().strip()
                if clip_val and (clip_val.upper().startswith("EBID") or clip_val.upper().startswith("EBMOB")):
                    self.entry_client_req_id.delete(0, tk.END)
                    self.entry_client_req_id.insert(0, clip_val)
                    self.on_client_req_id_change()
                    val = clip_val
            except Exception:
                pass

        if not val:
            messagebox.showinfo(
                "Ключи пользователя",
                "Сначала вставьте ID код клиента в поле ввода (кнопка «📋 Вставить»),\n"
                "чтобы загрузить историю ключей из общего реестра.",
                parent=self.root
            )
            return

        self._open_user_keys_dialog(val)

    def _open_user_keys_dialog(self, req_id_str: str):
        """Создает и отображает диалоговое окно «Ключи пользователя» с зеленым активным ключом и серыми архивными."""
        val = req_id_str.strip()
        dialog = tk.Toplevel(self.root)
        dialog.title("🔑 Ключи пользователя — Реестр лицензий")
        dialog.configure(bg="#0f172a")
        dialog.minsize(780, 520)
        dialog.transient(self.root)

        if hasattr(self, '_app_icon_img') and self._app_icon_img:
            try:
                dialog.iconphoto(False, self._app_icon_img)
            except Exception:
                pass

        # Центрирование окна относительно главного
        self.root.update_idletasks()
        dlg_w = 880
        dlg_h = 640
        rx = self.root.winfo_x()
        ry = self.root.winfo_y()
        rw = self.root.winfo_width()
        rh = self.root.winfo_height()
        pos_x = max(0, rx + (rw - dlg_w) // 2)
        pos_y = max(0, ry + (rh - dlg_h) // 2)
        dialog.geometry(f"{dlg_w}x{dlg_h}+{pos_x}+{pos_y}")

        # Верхняя панель: Данные устройства и ID клиента
        header_frame = tk.Frame(dialog, bg="#1e293b", padx=16, pady=12, relief="groove", bd=1)
        header_frame.pack(fill="x", padx=14, pady=(12, 6))

        hdr_left = tk.Frame(header_frame, bg="#1e293b")
        hdr_left.pack(side="left", fill="both", expand=True)

        lbl_dev_title = tk.Label(hdr_left, text="", font=("Segoe UI", 12, "bold"), bg="#1e293b", fg="#fbbf24")
        lbl_dev_title.pack(anchor="w")

        lbl_dev_meta = tk.Label(hdr_left, text="", font=("Segoe UI", 9), bg="#1e293b", fg="#94a3b8")
        lbl_dev_meta.pack(anchor="w", pady=(2, 4))

        id_box = tk.Frame(hdr_left, bg="#1e293b")
        id_box.pack(anchor="w")

        tk.Label(id_box, text="ID запроса:", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#94a3b8").pack(side="left", padx=(0, 6))
        lbl_req_val = tk.Label(id_box, text=val, font=("Consolas", 10, "bold"), bg="#0f172a", fg="#38bdf8", padx=8, pady=2, relief="flat")
        lbl_req_val.pack(side="left", padx=(0, 8))

        def copy_id_action():
            self.root.clipboard_clear()
            self.root.clipboard_append(val)
            self.root.update()
            btn_copy_id.config(text="✅ Скопирован", bg="#047857")
            dialog.after(1800, lambda: btn_copy_id.config(text="📋 Скопировать ID", bg="#334155") if btn_copy_id.winfo_exists() else None)
            self.notify_copied(f"ID код скопирован: {val}")

        btn_copy_id = tk.Button(id_box, text="📋 Скопировать ID", font=("Segoe UI", 8, "bold"),
                                bg="#334155", fg="#f8fafc", activebackground="#475569", activeforeground="#ffffff",
                                relief="flat", cursor="hand2", padx=8, pady=2, command=copy_id_action)
        btn_copy_id.pack(side="left")

        # Правая колонка шапки: общий бейдж статуса лицензии
        hdr_right = tk.Frame(header_frame, bg="#1e293b")
        hdr_right.pack(side="right", padx=(12, 0))

        lbl_status_pill = tk.Label(hdr_right, text="", font=("Segoe UI", 10, "bold"), padx=12, pady=8, relief="groove", bd=1)
        lbl_status_pill.pack()

        # Центральная скроллируемая область для карточек ключей
        container = tk.Frame(dialog, bg="#0f172a")
        container.pack(fill="both", expand=True, padx=14, pady=6)

        canvas = tk.Canvas(container, bg="#0f172a", highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_content = tk.Frame(canvas, bg="#0f172a")

        scroll_content.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas_window = canvas.create_window((0, 0), window=scroll_content, anchor="nw")

        def _on_canvas_resize(event):
            canvas.itemconfig(canvas_window, width=event.width)
        canvas.bind("<Configure>", _on_canvas_resize)
        canvas.configure(yscrollcommand=scrollbar.set)

        def _on_dlg_mousewheel(event):
            try:
                if canvas.winfo_exists():
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass
        dialog.bind("<MouseWheel>", _on_dlg_mousewheel)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Нижняя панель действий
        bottom_bar = tk.Frame(dialog, bg="#1e293b", padx=16, pady=10, relief="groove", bd=1)
        bottom_bar.pack(fill="x", padx=14, pady=(6, 12))

        lbl_dlg_feedback = tk.Label(bottom_bar, text="", font=("Segoe UI", 9, "bold"), bg="#1e293b", fg="#34d399")

        def set_dlg_status(text: str, color: str = "#34d399"):
            lbl_dlg_feedback.config(text=text, fg=color)
            dialog.after(3500, lambda: lbl_dlg_feedback.config(text="") if lbl_dlg_feedback.winfo_exists() else None)

        def copy_key_to_clipboard(key_val: str, button_widget=None):
            self.root.clipboard_clear()
            self.root.clipboard_append(key_val)
            self.root.update()
            if button_widget and button_widget.winfo_exists():
                old_text = button_widget.cget("text")
                old_bg = button_widget.cget("bg")
                button_widget.config(text="✅ Скопировано!", bg="#047857")
                dialog.after(2000, lambda: button_widget.config(text=old_text, bg=old_bg) if button_widget.winfo_exists() else None)
            self.notify_copied(f"Ключ скопирован в буфер: {key_val}")
            set_dlg_status(f"📋 Ключ {key_val} скопирован в буфер обмена!")

        def apply_key_to_main_window(key_val: str):
            self.entry_resp_key.delete(0, tk.END)
            self.entry_resp_key.insert(0, key_val)
            set_dlg_status(f"🚀 Ключ {key_val} подставлен в поле ответа в главном окне!", "#38bdf8")

        def do_renew_for_user():
            dialog.destroy()
            self.notebook.select(0)
            self.combo_hw_reason.set("Продление тарифа")
            self.hw_tier_mode.set("timed")
            self.on_hw_tier_changed()
            self.set_preset_days(30)
            self.on_client_req_id_change(keep_resp_key=True)
            if hasattr(self, 'entry_custom_days'):
                self.entry_custom_days.focus_set()

        def render_all_cards():
            # Очистка контейнера
            for ch in scroll_content.winfo_children():
                ch.destroy()

            # Получаем свежие данные из общего реестра
            info = self.get_client_keys_info(val)
            dev_id = info["device_id"]
            client = info["client_name"]
            notes = info["notes"] or "Основное устройство"
            mac = info["mac"]

            lbl_dev_title.config(text=f"{info['device_title']}: [{dev_id}]")
            lbl_dev_meta.config(text=f"👤 Клиент: {client}   |   📝 Заметка: {notes}   |   🌐 Идентификатор: {mac}")

            active_keys = info["active_keys"]
            expired_keys = info["expired_keys"]
            total_keys = len(info["all_keys"])
            active_item = info["active_key_item"]

            if total_keys == 0:
                lbl_status_pill.config(
                    text="🆕 НОВОЕ УСТРОЙСТВО\n(ключи ещё не выдавались)",
                    bg="#0c2340",
                    fg="#38bdf8"
                )
            elif active_item:
                exp_s = "VIP БЕССРОЧНО" if active_item.get("is_vip") else active_item.get("exp_display", "")
                lbl_status_pill.config(
                    text=f"🟢 ЛИЦЕНЗИЯ АКТИВНА\n{exp_s}",
                    bg="#064e3b",
                    fg="#34d399"
                )
            else:
                lbl_status_pill.config(
                    text="🔴 ЛИЦЕНЗИЯ ИСТЕКЛА\n(требуется продление)",
                    bg="#331518",
                    fg="#fca5a5"
                )

            # =========================================================================
            # СЕКЦИЯ 1: ДЕЙСТВУЮЩИЙ КЛЮЧ (ЗЕЛЁНЫЙ)
            # =========================================================================
            if active_keys:
                sec_active_hdr = tk.Frame(scroll_content, bg="#0f172a")
                sec_active_hdr.pack(fill="x", pady=(4, 6))

                tk.Label(sec_active_hdr, text=f"🟢 ДЕЙСТВУЮЩИЙ ЛИЦЕНЗИОННЫЙ КЛЮЧ ({len(active_keys)} шт.):", 
                         font=("Segoe UI", 11, "bold"), bg="#0f172a", fg="#34d399").pack(side="left")

                for act_k in active_keys:
                    # Зелёная карточка действующего ключа
                    card = tk.Frame(scroll_content, bg="#064e3b", highlightbackground="#10b981", highlightthickness=2, padx=14, pady=12)
                    card.pack(fill="x", pady=(0, 10))

                    # Верхний ряд карточки: бейджи
                    row_top = tk.Frame(card, bg="#064e3b")
                    row_top.pack(fill="x", pady=(0, 8))

                    lbl_badge_act = tk.Label(row_top, text="🟢 ДЕЙСТВУЕТ (АКТИВЕН)", font=("Segoe UI", 9, "bold"),
                                             bg="#047857", fg="#ffffff", padx=8, pady=3)
                    lbl_badge_act.pack(side="left", padx=(0, 8))

                    tier_badge_bg = "#581c87" if act_k.get("is_vip") else "#065f46"
                    tier_badge_fg = "#e9d5ff" if act_k.get("is_vip") else "#a7f3d0"
                    lbl_badge_tier = tk.Label(row_top, text=f"👑 {act_k['tier_name']}" if act_k.get("is_vip") else f"⚡ {act_k['tier_name']}",
                                              font=("Segoe UI", 9, "bold"), bg=tier_badge_bg, fg=tier_badge_fg, padx=8, pady=3)
                    lbl_badge_tier.pack(side="left", padx=(0, 8))

                    lbl_p_num = tk.Label(row_top, text=f"Пароль #{act_k['index']}", font=("Segoe UI", 9),
                                         bg="#022c22", fg="#a7f3d0", padx=6, pady=3)
                    lbl_p_num.pack(side="left")

                    # Статус активации: ключ активирован сразу при выдаче
                    act_time = act_k.get("activated_at") or act_k.get("issued_at") or ""
                    act_by = act_k.get("activated_by") or client or "Администратор"
                    act_lbl_txt = f"✅ Активирован ({act_time})" if act_time else "✅ Активирован"
                    act_fg = "#a7f3d0"

                    lbl_act_site = tk.Label(row_top, text=act_lbl_txt, font=("Segoe UI", 9, "bold"),
                                            bg="#064e3b", fg=act_fg)
                    lbl_act_site.pack(side="right")

                    # Ряд ключа: крупный моноширинный код + кнопки действий
                    row_key = tk.Frame(card, bg="#064e3b")
                    row_key.pack(fill="x", pady=4)

                    ent_k = tk.Entry(row_key, font=("Consolas", 15, "bold"), fg="#6ee7b7", bg="#022c22",
                                     relief="flat", bd=3, justify="center")
                    ent_k.insert(0, act_k["key"])
                    ent_k.config(state="readonly")
                    ent_k.pack(side="left", fill="x", expand=True, padx=(0, 10), ipady=4)

                    b_copy = tk.Button(row_key, text="📋 Скопировать ключ", font=("Segoe UI", 10, "bold"),
                                       bg="#10b981", fg="#ffffff", activebackground="#059669", activeforeground="#ffffff",
                                       relief="flat", cursor="hand2", padx=14, pady=5)
                    b_copy.config(command=lambda k=act_k["key"], btn=b_copy: copy_key_to_clipboard(k, btn))
                    b_copy.pack(side="left", padx=(0, 8))

                    b_apply = tk.Button(row_key, text="🚀 В ответный ключ", font=("Segoe UI", 9, "bold"),
                                        bg="#2563eb", fg="#ffffff", activebackground="#1d4ed8", activeforeground="#ffffff",
                                        relief="flat", cursor="hand2", padx=12, pady=5,
                                        command=lambda k=act_k["key"]: apply_key_to_main_window(k))
                    b_apply.pack(side="left")

                    # Нижний ряд карточки: детальные сроки и примечание
                    row_meta = tk.Frame(card, bg="#064e3b")
                    row_meta.pack(fill="x", pady=(6, 0))

                    if act_k.get("is_vip"):
                        exp_desc_text = "⏳ Срок: Бессрочно (VIP Безлимит навсегда)"
                    else:
                        exp_desc_text = f"⏳ Действует до: {act_k.get('valid_until', '—')} ({act_k.get('time_left_str', '')})"

                    tk.Label(row_meta, text=f"📅 Выдан: {act_k.get('issued_at', '—')}   |   {exp_desc_text}",
                             font=("Segoe UI", 9, "bold"), bg="#064e3b", fg="#ecfdf5").pack(anchor="w")

                    reason_val = act_k.get("reason") or "Выдача лицензии"
                    tk.Label(row_meta, text=f"📝 Причина / Назначение: {reason_val}",
                             font=("Segoe UI", 8), bg="#064e3b", fg="#a7f3d0").pack(anchor="w", pady=(2, 0))

            # =========================================================================
            # СЕКЦИЯ 2: АРХИВНЫЕ И ПРОСРОЧЕННЫЕ КЛЮЧИ (СЕРЫЕ)
            # =========================================================================
            if expired_keys:
                sec_exp_hdr = tk.Frame(scroll_content, bg="#0f172a")
                sec_exp_hdr.pack(fill="x", pady=(10, 6))

                tk.Label(sec_exp_hdr, text=f"📁 АРХИВ ПРЕДЫДУЩИХ КЛЮЧЕЙ (ПРОСРОЧЕННЫЕ ИЛИ ЗАМЕНЁННЫЕ) — {len(expired_keys)} шт.:", 
                         font=("Segoe UI", 10, "bold"), bg="#0f172a", fg="#94a3b8").pack(side="left")

                for exp_k in expired_keys:
                    # Серая карточка архивного / просроченного ключа
                    card_grey = tk.Frame(scroll_content, bg="#1e293b", highlightbackground="#475569", highlightthickness=1, padx=12, pady=10)
                    card_grey.pack(fill="x", pady=(0, 8))

                    row_g_top = tk.Frame(card_grey, bg="#1e293b")
                    row_g_top.pack(fill="x", pady=(0, 6))

                    lbl_badge_exp = tk.Label(row_g_top, text="⚪ ИСТЁК / В АРХИВЕ", font=("Segoe UI", 9, "bold"),
                                             bg="#334155", fg="#94a3b8", padx=8, pady=2)
                    lbl_badge_exp.pack(side="left", padx=(0, 8))

                    lbl_g_pnum = tk.Label(row_g_top, text=f"Пароль #{exp_k['index']}", font=("Segoe UI", 9),
                                          bg="#0f172a", fg="#94a3b8", padx=6, pady=2)
                    lbl_g_pnum.pack(side="left", padx=(0, 8))

                    g_reason = exp_k.get("reason") or "Выдача ключа"
                    tk.Label(row_g_top, text=f"📝 {g_reason} ({exp_k.get('tier_name', '')})", font=("Segoe UI", 9),
                             bg="#1e293b", fg="#cbd5e1").pack(side="left")

                    g_status_note = "🔄 Заменён новым ключом" if exp_k.get("status") == "replaced" else "⏳ Срок действия истёк"
                    tk.Label(row_g_top, text=g_status_note, font=("Segoe UI", 8, "italic"),
                             bg="#1e293b", fg="#94a3b8").pack(side="right")

                    # Ряд архивного ключа
                    row_g_key = tk.Frame(card_grey, bg="#1e293b")
                    row_g_key.pack(fill="x", pady=2)

                    ent_gk = tk.Entry(row_g_key, font=("Consolas", 12, "bold"), fg="#94a3b8", bg="#0f172a",
                                      relief="flat", bd=2, justify="center")
                    ent_gk.insert(0, exp_k["key"])
                    ent_gk.config(state="readonly")
                    ent_gk.pack(side="left", fill="x", expand=True, padx=(0, 8), ipady=3)

                    b_g_copy = tk.Button(row_g_key, text="📋 Скопировать", font=("Segoe UI", 9),
                                         bg="#334155", fg="#cbd5e1", activebackground="#475569", activeforeground="#ffffff",
                                         relief="flat", cursor="hand2", padx=12, pady=3)
                    b_g_copy.config(command=lambda k=exp_k["key"], btn=b_g_copy: copy_key_to_clipboard(k, btn))
                    b_g_copy.pack(side="left")

                    # Нижний ряд серой карточки
                    row_g_meta = tk.Frame(card_grey, bg="#1e293b")
                    row_g_meta.pack(fill="x", pady=(4, 0))

                    site_act_str = f"Активировался ({exp_k.get('activated_at') or 'ранее'})" if exp_k.get("activated") else "Не активировался"
                    tk.Label(row_g_meta, text=f"📅 Выдан: {exp_k.get('issued_at', '—')}   |   ⏳ Истёк: {exp_k.get('valid_until', '—')}   |   Сайт: {site_act_str}",
                             font=("Segoe UI", 8), bg="#1e293b", fg="#64748b").pack(anchor="w")

            # =========================================================================
            # СЕКЦИЯ 3: ЕСЛИ КЛЮЧЕЙ НЕТ (НОВЫЙ КЛИЕНТ)
            # =========================================================================
            if not active_keys and not expired_keys:
                box_empty = tk.Frame(scroll_content, bg="#1e293b", highlightbackground="#0284c7", highlightthickness=1, padx=24, pady=24)
                box_empty.pack(fill="x", pady=20)

                tk.Label(box_empty, text="🆕 Для данного клиента ещё нет выданных лицензий", 
                         font=("Segoe UI", 13, "bold"), bg="#1e293b", fg="#38bdf8").pack(anchor="w")

                tk.Label(box_empty, text="Устройство распознано как новое. История ранее выданных ключей пуста.\n\n"
                                         "Чтобы зарегистрировать устройство и выдать первый лицензионный ключ:\n"
                                         "1. Выберите нужный срок в главном окне (3 дня, 30 дней или VIP Безлимит, либо «Выдать триал»);\n"
                                         "2. Нажмите зелёную кнопку «🚀 Сгенерировать и закрепить ключ»;\n"
                                         "3. Ключ автоматически привяжется к данному клиенту и появится в этом реестре.",
                         font=("Segoe UI", 10), bg="#1e293b", fg="#e2e8f0", justify="left").pack(anchor="w", pady=(8, 14))

                btn_gen_first = tk.Button(box_empty, text="🚀 Перейти к выдаче первого ключа", font=("Segoe UI", 10, "bold"),
                                          bg="#059669", fg="#ffffff", activebackground="#047857", activeforeground="#ffffff",
                                          relief="flat", cursor="hand2", padx=16, pady=6,
                                          command=do_renew_for_user)
                btn_gen_first.pack(anchor="w")

            # Синхронизируем состояние кнопки в главном окне
            self.update_user_keys_ui_state(val, info.get("device"))

        # Кнопки нижней панели диалога
        btn_refresh_dlg = tk.Button(bottom_bar, text="🔄 Обновить из реестра", font=("Segoe UI", 9, "bold"),
                                    bg="#334155", fg="#f8fafc", activebackground="#475569", activeforeground="#ffffff",
                                    relief="flat", cursor="hand2", padx=12, pady=4,
                                    command=lambda: [render_all_cards(), set_dlg_status("🔄 Данные успешно обновлены из общего реестра!")])
        btn_refresh_dlg.pack(side="left", padx=(0, 10))

        lbl_dlg_feedback.pack(side="left", padx=10)

        btn_close_dlg = tk.Button(bottom_bar, text="✖ Закрыть", font=("Segoe UI", 9),
                                  bg="#475569", fg="#ffffff", activebackground="#64748b", activeforeground="#ffffff",
                                  relief="flat", cursor="hand2", padx=14, pady=4,
                                  command=dialog.destroy)
        btn_close_dlg.pack(side="right")

        btn_renew_dlg = tk.Button(bottom_bar, text="➕ Продлить / Выдать новый ключ", font=("Segoe UI", 10, "bold"),
                                  bg="#059669", fg="#ffffff", activebackground="#047857", activeforeground="#ffffff",
                                  relief="flat", cursor="hand2", padx=14, pady=4,
                                  command=do_renew_for_user)
        btn_renew_dlg.pack(side="right", padx=(0, 10))

        # Первичная отрисовка содержимого диалога
        render_all_cards()

    def get_matched_device_current_expiration(self):
        """
        Определяет дату окончания текущего ключа для найденного устройства.
        Возвращает (exp_dt, is_expired, desc).
        """
        if not self.current_matched_device:
            return None, False, "Устройство не найдено"

        dev = self.current_matched_device
        pwds = dev.get("passwords", [])
        now = datetime.datetime.now()

        # 1. Ищем активированный пароль
        target_p = None
        for p in reversed(pwds):
            if p.get("activated") and p.get("status") == "active":
                target_p = p
                break
        if not target_p:
            for p in reversed(pwds):
                if p.get("activated"):
                    target_p = p
                    break
        if not target_p and pwds:
            target_p = pwds[-1]

        if not target_p:
            return None, False, "Пароли отсутствуют"

        if target_p.get("tier") in ("unlimited", "vip", "vipx") or dev.get("active_tier") in ("unlimited", "vip", "vipx"):
            return None, False, "👑 VIP Бессрочный (Безлимит)"

        vu_str = target_p.get("valid_until") or dev.get("active_valid_until") or ""
        if not vu_str or vu_str == "—":
            if devices_db:
                vu_str, _ = devices_db.decode_key_valid_until(target_p.get("key", ""))

        if not vu_str or vu_str == "—" or "VIP" in vu_str:
            return None, False, "👑 VIP Бессрочный (Безлимит)"

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                exp_dt = datetime.datetime.strptime(vu_str.strip(), fmt)
                diff = (exp_dt - now).total_seconds()
                if diff <= 0:
                    return exp_dt, True, f"Истёк {exp_dt.strftime('%d.%m.%Y в %H:%M')}"
                else:
                    d_days = int(diff // 86400)
                    d_hours = int((diff % 86400) // 3600)
                    return exp_dt, False, f"Активен до {exp_dt.strftime('%d.%m.%Y в %H:%M')} (осталось {d_days} дн. {d_hours} ч.)"
            except Exception:
                pass

        return None, False, f"Не распознана дата: {vu_str}"

    def get_calculation_base_datetime(self):
        """
        Возвращает (base_dt, is_extension, info_text):
        - Если 'Продление тарифа' и у устройства есть активный непросроченный ключ:
          base_dt = дата окончания действующего ключа (is_extension = True).
        - Если ключ просрочен, либо новое устройство / первое подключение:
          base_dt = datetime.datetime.now() (is_extension = False).
        """
        reason = self.combo_hw_reason.get().strip() if hasattr(self, 'combo_hw_reason') else ""
        is_renewal_reason = ("продлен" in reason.lower())

        if is_renewal_reason and self.current_matched_device:
            curr_exp, is_exp, desc = self.get_matched_device_current_expiration()
            if curr_exp and not is_exp:
                return curr_exp, True, desc
            elif curr_exp and is_exp:
                return datetime.datetime.now(), False, f"Предыдущий ключ истёк ({curr_exp.strftime('%d.%m.%Y %H:%M')}). Отсчёт от текущего момента."
            else:
                return datetime.datetime.now(), False, "Ключ ранее не был активирован. Отсчёт от текущего момента."

        return datetime.datetime.now(), False, "Отсчёт от текущего момента."

    def update_renewal_ui(self):
        """Динамически обновляет интерфейс блока срока действия при выборе продления."""
        if not hasattr(self, 'frame_renewal_notice'):
            return

        reason = self.combo_hw_reason.get().strip() if hasattr(self, 'combo_hw_reason') else ""
        is_renewal = ("продлен" in reason.lower())

        if is_renewal:
            curr_exp, is_exp, desc = self.get_matched_device_current_expiration()
            if curr_exp and not is_exp:
                # Действующий ключ — срок прибавляется к дате окончания
                self.frame_renewal_notice.config(bg="#0c2a44", bd=1, relief="solid")
                self.lbl_renewal_title.config(
                    text=f"🔄 РЕЖИМ ПРОДЛЕНИЯ: Текущий ключ активен до {curr_exp.strftime('%d.%m.%Y в %H:%M')}",
                    fg="#38bdf8", bg="#0c2a44"
                )
                self.lbl_renewal_sub.config(
                    text=f"➕ Добавляемый срок прибавится к дате {curr_exp.strftime('%d.%m.%Y %H:%M')} (остаток не сгорает!)",
                    fg="#bae6fd", bg="#0c2a44"
                )
                self.frame_renewal_notice.pack(fill="x", pady=(2, 4), before=self.presets_row)

                if hasattr(self, 'preset_buttons'):
                    for btn_p, _, p_days in self.preset_buttons:
                        btn_p.config(text=f"+{p_days} дн.")
            elif curr_exp and is_exp:
                # Ключ просрочен — отсчет начинается от текущего момента
                self.frame_renewal_notice.config(bg="#2d1c03", bd=1, relief="solid")
                self.lbl_renewal_title.config(
                    text=f"⚠️ Предыдущий ключ истёк ({curr_exp.strftime('%d.%m.%Y в %H:%M')})",
                    fg="#fbbf24", bg="#2d1c03"
                )
                self.lbl_renewal_sub.config(
                    text="⏱️ Отсчёт продления начнётся от текущего времени (сегодня), а не от просроченной даты.",
                    fg="#fde68a", bg="#2d1c03"
                )
                self.frame_renewal_notice.pack(fill="x", pady=(2, 4), before=self.presets_row)

                if hasattr(self, 'preset_buttons'):
                    for btn_p, p_label, _ in self.preset_buttons:
                        btn_p.config(text=p_label)
            else:
                # Первичный пользователь или не активировал — отсчет от текущего момента
                self.frame_renewal_notice.config(bg="#062d1f", bd=1, relief="solid")
                self.lbl_renewal_title.config(
                    text="🟢 Первичная выдача / устройство ранее не активировало ключ",
                    fg="#34d399", bg="#062d1f"
                )
                self.lbl_renewal_sub.config(
                    text="⏱️ Отсчёт срока действия начнётся от текущего момента.",
                    fg="#a7f3d0", bg="#062d1f"
                )
                self.frame_renewal_notice.pack(fill="x", pady=(2, 4), before=self.presets_row)

                if hasattr(self, 'preset_buttons'):
                    for btn_p, p_label, _ in self.preset_buttons:
                        btn_p.config(text=p_label)
        else:
            # Назначение не "Продление тарифа"
            self.frame_renewal_notice.pack_forget()
            if hasattr(self, 'preset_buttons'):
                for btn_p, p_label, _ in self.preset_buttons:
                    btn_p.config(text=p_label)

    def on_reason_changed(self, event=None):
        """Реакция на смену назначения (Продление, Первичная выдача и т.д.)"""
        self.update_renewal_ui()
        days_str = self.entry_custom_days.get().strip() if hasattr(self, 'entry_custom_days') else "30"
        try:
            d = int(days_str) if days_str else 30
        except ValueError:
            d = 30
        self.set_preset_days(d)

    def on_hw_tier_changed(self):
        """Переключение между ограниченным по времени и VIP режимом."""
        mode = self.hw_tier_mode.get()
        if mode == "unlimited":
            self.entry_custom_days.config(state="disabled")
            self.entry_custom_date.config(state="disabled")
            if hasattr(self, 'entry_custom_time'):
                self.entry_custom_time.config(state="disabled")
            if hasattr(self, 'frame_renewal_notice'):
                self.frame_renewal_notice.pack_forget()
            self.lbl_calculated_time.config(
                text="👑 Итог: Бессрочная лицензия VIP (без ограничений по времени)",
                fg="#c084fc"
            )
            self.selected_preset_days = None
            self.highlight_preset(None)
        else:
            self.entry_custom_days.config(state="normal")
            self.entry_custom_date.config(state="normal")
            if hasattr(self, 'entry_custom_time'):
                self.entry_custom_time.config(state="normal")
            self.update_renewal_ui()
            self.update_calculated_label()

    def highlight_preset(self, days):
        """Подсвечивает выбранный пресет срока и фиксирует визуальное состояние."""
        if hasattr(self, 'preset_buttons'):
            for btn_p, p_label, p_days in self.preset_buttons:
                try:
                    if days is not None and p_days == days:
                        btn_p.config(bg="#0284c7", fg="#ffffff", relief="sunken")
                    else:
                        btn_p.config(bg="#1e293b", fg="#38bdf8", relief="flat")
                except Exception:
                    pass

    def check_preset_selection(self, days):
        """Если срок дней меньше чем в выбранном пресете (например, < 3 или < 7), снимает выделение с пресета."""
        curr_preset = getattr(self, 'selected_preset_days', None)
        if curr_preset is not None:
            if days is None or days < curr_preset:
                self.selected_preset_days = None
                self.highlight_preset(None)
            elif days == curr_preset:
                self.highlight_preset(days)
            else:
                matched = None
                if hasattr(self, 'preset_buttons'):
                    for _, _, p_days in self.preset_buttons:
                        if p_days == days:
                            matched = p_days
                            break
                self.selected_preset_days = matched
                self.highlight_preset(matched)
        else:
            matched = None
            if days is not None and hasattr(self, 'preset_buttons'):
                for _, _, p_days in self.preset_buttons:
                    if p_days == days:
                        matched = p_days
                        break
            self.selected_preset_days = matched
            self.highlight_preset(matched)

    def set_preset_days(self, days: int):
        """Выбор количества дней с учётом базовой даты (продление vs текущее время)."""
        self.hw_tier_mode.set("timed")
        self.entry_custom_days.config(state="normal")
        self.entry_custom_date.config(state="normal")
        if hasattr(self, 'entry_custom_time'):
            self.entry_custom_time.config(state="normal")

        is_preset = any(p_days == days for _, _, p_days in getattr(self, 'preset_buttons', []))
        self.selected_preset_days = days if is_preset else None

        self.entry_custom_days.delete(0, tk.END)
        self.entry_custom_days.insert(0, str(days))

        base_dt, is_ext, _ = self.get_calculation_base_datetime()
        target_dt = base_dt + datetime.timedelta(days=days)

        self.entry_custom_date.delete(0, tk.END)
        self.entry_custom_date.insert(0, target_dt.strftime("%d.%m.%Y"))

        if hasattr(self, 'entry_custom_time'):
            curr_t = self.entry_custom_time.get().strip()
            if not curr_t:
                self.entry_custom_time.insert(0, target_dt.strftime("%H:%M") if is_ext else "23:59")

        self.update_calculated_label()
        self.highlight_preset(days)

    def set_preset_time(self, time_str: str):
        if hasattr(self, 'entry_custom_time'):
            self.entry_custom_time.delete(0, tk.END)
            self.entry_custom_time.insert(0, time_str)
        self.update_calculated_label()

    def set_current_time_preset(self):
        if hasattr(self, 'entry_custom_time'):
            now_str = datetime.datetime.now().strftime("%H:%M")
            self.entry_custom_time.delete(0, tk.END)
            self.entry_custom_time.insert(0, now_str)
        self.update_calculated_label()

    def on_custom_time_change(self, event=None):
        self.update_calculated_label()

    def on_custom_days_change(self, event=None):
        """Реакция на изменение поля дней: пересчитывает дату от базовой точки."""
        if self.hw_tier_mode.get() == "unlimited":
            return
        val = self.entry_custom_days.get().strip()
        if not val:
            self.lbl_calculated_time.config(text="⚠️ Укажите количество дней или дату", fg="#f59e0b")
            self.check_preset_selection(None)
            return
        try:
            days = int(val)
            if days < 0:
                self.lbl_calculated_time.config(text="⚠️ Количество дней должно быть >= 0", fg="#f87171")
                self.check_preset_selection(None)
                return
            base_dt, is_ext, _ = self.get_calculation_base_datetime()
            target_dt = base_dt + datetime.timedelta(days=days)
            self.entry_custom_date.delete(0, tk.END)
            self.entry_custom_date.insert(0, target_dt.strftime("%d.%m.%Y"))
            self.update_calculated_label()
            self.check_preset_selection(days)
        except ValueError:
            self.lbl_calculated_time.config(text="⚠️ Введите целое число дней", fg="#f87171")
            self.check_preset_selection(None)

    def on_custom_date_change(self, event=None):
        """Реакция на ручной ввод даты: пересчитывает количество дней от базовой точки."""
        if self.hw_tier_mode.get() == "unlimited":
            return
        val = self.entry_custom_date.get().strip()
        if not val or len(val) < 8:
            return
        for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
            try:
                target_date = datetime.datetime.strptime(val, fmt).date()
                base_dt, is_ext, _ = self.get_calculation_base_datetime()
                diff = (target_date - base_dt.date()).days
                if diff < 0:
                    self.lbl_calculated_time.config(
                        text=f"⚠️ Дата {target_date.strftime('%d.%m.%Y')} раньше точки отсчёта ({base_dt.strftime('%d.%m.%Y')})!", 
                        fg="#f87171"
                    )
                    self.check_preset_selection(None)
                    return
                self.entry_custom_days.delete(0, tk.END)
                self.entry_custom_days.insert(0, str(diff))
                self.update_calculated_label()
                self.check_preset_selection(diff)
                return
            except ValueError:
                pass

    def update_calculated_label(self):
        if self.hw_tier_mode.get() == "unlimited":
            self.lbl_calculated_time.config(
                text="👑 Итог: Бессрочная лицензия VIP (без ограничений по времени)",
                fg="#c084fc"
            )
            return
        try:
            exp_dt, label = self.get_selected_expiration()
            base_dt, is_ext, _ = self.get_calculation_base_datetime()
            days_val = self.entry_custom_days.get().strip()
            if is_ext:
                self.lbl_calculated_time.config(
                    text=f"➕ Продление: +{days_val} дн. к текущему тарифу ➔ Действует до {exp_dt.strftime('%d.%m.%Y в %H:%M:00')} ({label})",
                    fg="#38bdf8"
                )
            else:
                self.lbl_calculated_time.config(
                    text=f"📅 Итог: Ключ будет действовать до {exp_dt.strftime('%d.%m.%Y в %H:%M:00')} (срок: {label})",
                    fg="#34d399"
                )
        except ValueError as e:
            self.lbl_calculated_time.config(text=f"⚠️ {e}", fg="#f59e0b")
        except Exception:
            pass

    def get_selected_expiration(self):
        """Возвращает (exp_datetime, label) с точностью до минут или вызывает ValueError."""
        mode = self.hw_tier_mode.get()
        if mode == "unlimited":
            return None, "Бессрочно (VIP)"

        date_str = self.entry_custom_date.get().strip()
        time_str = self.entry_custom_time.get().strip() if hasattr(self, 'entry_custom_time') else "23:59"
        if not time_str:
            time_str = "23:59"

        parsed_time = None
        for t_fmt in ("%H:%M", "%H:%M:%S", "%H-%M", "%H"):
            try:
                t_dt = datetime.datetime.strptime(time_str, t_fmt)
                parsed_time = t_dt.time()
                break
            except ValueError:
                pass
        if not parsed_time:
            parsed_time = datetime.time(23, 59, 0)

        exp_date = None
        if date_str:
            for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%y"):
                try:
                    exp_date = datetime.datetime.strptime(date_str, fmt).date()
                    break
                except ValueError:
                    pass

        base_dt, is_ext, _ = self.get_calculation_base_datetime()

        if not exp_date:
            days_str = self.entry_custom_days.get().strip()
            if days_str:
                try:
                    d = int(days_str)
                    if d < 0:
                        raise ValueError("Количество дней должно быть >= 0")
                    exp_date = (base_dt + datetime.timedelta(days=d)).date()
                except ValueError as ve:
                    if ">= 0" in str(ve):
                        raise
                    raise ValueError("Введите корректное число дней или дату ДД.ММ.ГГГГ")

        if not exp_date:
            raise ValueError("Укажите срок действия ключа (дней или дату)")

        exp_datetime = datetime.datetime.combine(exp_date, parsed_time)
        now_dt = datetime.datetime.now()
        if exp_datetime <= now_dt:
            raise ValueError(f"Указанная дата и время {exp_datetime.strftime('%d.%m.%Y %H:%M')} уже в прошлом! Выберите время в будущем.")

        diff_total = exp_datetime - now_dt
        diff_days = diff_total.days
        diff_hours = int(diff_total.seconds // 3600)
        diff_mins = int((diff_total.seconds % 3600) // 60)

        if is_ext:
            days_cnt = self.entry_custom_days.get().strip()
            dur_label = f"+{days_cnt} дн. (до {exp_datetime.strftime('%d.%m.%Y %H:%M')})"
        elif diff_days > 0:
            dur_label = f"{diff_days} дн. {diff_hours} ч. (до {exp_datetime.strftime('%d.%m.%Y %H:%M')})"
        else:
            dur_label = f"{diff_hours} ч. {diff_mins} мин. (до {exp_datetime.strftime('%d.%m.%Y %H:%M')})"

        return exp_datetime, dur_label

    def action_gen_response_key(self):
        """Генерация ключа с точно заданной датой окончания (до минут) и закрепление в базе устройств."""
        val = self.entry_client_req_id.get().strip()
        parsed = hwid_security.parse_request_id(val) if hwid_security else fallback_parse_request_id(val)
        if not parsed.get("valid"):
            messagebox.showerror("Ошибка", parsed.get("error", "Недействительный ID код клиента!"), parent=self.root)
            return

        mode = self.hw_tier_mode.get()
        exp_dt_obj = None
        if mode == "unlimited":
            tier_arg = "unlimited"
            tier_label = "Бессрочно (VIP)"
            valid_until_str = "Бессрочно (VIP)"
        else:
            tier_arg = "30_days"
            try:
                exp_dt_obj, tier_label = self.get_selected_expiration()
                valid_until_str = exp_dt_obj.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError as ve:
                messagebox.showerror("Ошибка срока действия", str(ve), parent=self.root)
                return

        # Проверка на попытку повторной выдачи пробного периода (триал 3 дня)
        days_val = None
        try:
            days_val = int(self.entry_custom_days.get().strip())
        except Exception:
            pass

        reason_str = self.combo_hw_reason.get().strip() if hasattr(self, 'combo_hw_reason') else ""
        is_trial_requested = bool(
            mode != "unlimited" and (
                "пробн" in reason_str.lower() or
                "триал" in reason_str.lower() or
                "триал" in (tier_label or "").lower() or
                "пробн" in (tier_label or "").lower()
            )
        )

        if is_trial_requested:
            messagebox.showinfo(
                "Выдача триала отключена",
                "Ручная выдача бесплатных триал-ключей в Кей-Менеджере отключена.\n\n"
                "Выдачей пробных периодов занимается Telegram-бот @avvvskybot автоматически.",
                parent=self.root
            )
            return

        try:
            if hwid_security:
                resp_key = hwid_security.generate_response_key(parsed, tier_arg, expires_date=exp_dt_obj)
            else:
                resp_key = fallback_gen_response_key(parsed, tier_arg)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сгенерировать ответный ключ: {e}", parent=self.root)
            return

        self.entry_resp_key.delete(0, tk.END)
        self.entry_resp_key.insert(0, resp_key)
        self.entry_resp_key.config(fg="#c084fc" if mode == "unlimited" else "#38bdf8")

        client_name = "skynet83"
        reason = self.combo_hw_reason.get().strip() or "Выдача пароля"

        # Закрепляем в базе устройств с точным сроком до минут
        is_phone = val.upper().startswith("EBMOB") or (parsed and parsed.get("is_mobile")) or (self.current_matched_device and self.current_matched_device.get("device_type") == "phone")
        dev_type_label = "Телефон" if is_phone else "ПК"
        p_index = 1
        dev_id = f"MOB-{parsed.get('mac_tail')}-{parsed.get('hw_sig')[:4]}" if is_phone else f"DEV-{parsed.get('mac_tail')}-{parsed.get('hw_sig')[:4]}"
        if devices_db:
            reg_res = devices_db.register_or_bind_password(
                req_id_str=val,
                new_key=resp_key,
                tier=tier_arg,
                client_name=client_name,
                notes=f"{dev_type_label} {dev_id} ({reason})",
                reason=reason,
                existing_dev_id=self.current_matched_device.get("device_id") if self.current_matched_device else None,
                tier_name=tier_label,
                exact_valid_until=valid_until_str
            )
            p_index = reg_res.get("password_index", 1)
            dev_id = reg_res.get("device", {}).get("device_id", dev_id)

        now_dt = datetime.datetime.now()
        issued_time_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

        mac_str = f"MOB-ID:{parsed.get('mac_tail')}" if is_phone else f"**:**:**:**:{parsed.get('mac_tail')[:2]}:{parsed.get('mac_tail')[2:]}"
        # Немедленно фиксируем в self.dispensed и сохраняем в dispensed_keys.json
        self.dispensed[resp_key] = {
            "client_note": f"{dev_type_label} [{dev_id}] {reason}",
            "dispensed_at": issued_time_str,
            "hash": self.get_hash(resp_key),
            "type": "hardware_bound",
            "tier": tier_arg,
            "mac": mac_str,
            "request_id": val,
            "device_id": dev_id,
            "password_index": p_index,
            "valid_until": valid_until_str,
            "activated_by": None,
            "activated_at": None,
            "activated": False,
            "status": "pending",
            "is_trial": is_trial_requested
        }
        save_json_file(DISPENSED_PATH, self.dispensed)
        # Двусторонняя синхронизация с сайтом skybase
        disp_sync_targets = [
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "skybase", "data", "dispensed_keys.json"),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "skybase", "data", "dispensed_keys.json"),
            r"C:\ins\Avito-Parser2\skybase\data\dispensed_keys.json",
            r"C:\ins\Avito-Parser\skybase\data\dispensed_keys.json",
            r"C:\ins\skybase\data\dispensed_keys.json"
        ]
        for alt_disp in disp_sync_targets:
            try:
                if os.path.exists(os.path.dirname(alt_disp)) and os.path.abspath(alt_disp).lower() != os.path.abspath(DISPENSED_PATH).lower():
                    save_json_file(alt_disp, self.dispensed)
            except Exception:
                pass

        # Автоматически копируем в буфер обмена
        self.root.clipboard_clear()
        self.root.clipboard_append(resp_key)
        self.root.update()

        self.lbl_hw_status.config(
            text=f"✅ Пароль #{p_index} ({tier_label}) успешно закреплен за устройством {dev_id}!\n"
                 f"🕒 Время выдачи: {issued_time_str}   |   ⏳ Действует до: {valid_until_str}\n"
                 f"🛡️ Защита: точная дата и время окончания (до минут) вшиты в крипто-код ключа.\n"
                 f"Ключ {resp_key} скопирован в буфер обмена.",
            fg="#34d399"
        )

        self.refresh_stats()
        self.refresh_devices_table()
        self.on_client_req_id_change(keep_resp_key=True)

    def notify_copied(self, message: str):
        """Информирует о копировании в буфер обмена без всплывающего модального окна."""
        if hasattr(self, "lbl_global_status") and self.lbl_global_status:
            self.lbl_global_status.config(text=f"📋 {message}", fg="#34d399")
            self.root.after(3500, lambda: self.lbl_global_status.config(text="") if hasattr(self, "lbl_global_status") else None)
        if hasattr(self, "lbl_hw_status") and self.lbl_hw_status:
            self.lbl_hw_status.config(text=f"📋 {message}", fg="#10b981")
        if hasattr(self, "lbl_dispense_status") and self.lbl_dispense_status:
            self.lbl_dispense_status.config(text=f"📋 {message}", fg="#10b981")

    def action_copy_response_key(self):
        val = self.entry_resp_key.get().strip()
        if not val or val == "ЗДЕСЬ_БУДЕТ_КЛЮЧ_АКТИВАЦИИ":
            if hasattr(self, "lbl_hw_status") and self.lbl_hw_status:
                self.lbl_hw_status.config(text="⚠️ Сначала сгенерируйте ответный ключ.", fg="#f59e0b")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(val)
        self.root.update()
        self.notify_copied(f"Ответный ключ скопирован в буфер: {val}")

    def refresh_devices_table(self):
        """Обновляет список устройств во вкладке База устройств."""
        for item in self.tree_devs.get_children():
            self.tree_devs.delete(item)

        if not devices_db:
            return

        q = self.entry_dev_search.get().strip() if hasattr(self, 'entry_dev_search') else ""
        devs = devices_db.search_devices(q)

        for dev in devs:
            dev_id = dev.get("device_id", "—")
            req_id = dev.get("request_id", "")
            is_phone = (dev.get("device_type") == "phone" or dev_id.startswith("MOB") or req_id.startswith("EBMOB") or dev.get("mac_tail", "").startswith("MO"))
            dev_type_str = "📱 Телефон" if is_phone else "💻 ПК"
            mac = dev.get("mac", "—")
            pwds = dev.get("passwords", [])
            p_count = len(pwds)
            active_k = dev.get("active_key")
            if not active_k or active_k == "—":
                if pwds:
                    active_k = f"⏳ {pwds[-1].get('key', '—')}"
                else:
                    active_k = "—"
            if dev.get("active_tier") == "unlimited":
                tier_str = "👑 VIP"
            else:
                vu = dev.get("active_valid_until", "")
                if vu:
                    tier_str = f"📅 до {vu[:10]}"
                else:
                    tier_str = dev.get("active_tier_name", "📦 Срок")
            updated = dev.get("last_updated_at", dev.get("first_registered_at", "—"))

            self.tree_devs.insert("", "end", values=(
                dev_id,
                dev_type_str,
                mac,
                f"{p_count} шт.",
                active_k,
                tier_str,
                updated
            ))

    def on_device_selected(self, event=None):
        """Отображение полной истории всех паролей выбранного устройства."""
        sel = self.tree_devs.selection()
        for item in self.tree_pwds.get_children():
            self.tree_pwds.delete(item)

        if not sel:
            self.detail_frame.config(text=" 📜 История всех паролей, закрепленных за данным устройством ")
            return

        vals = self.tree_devs.item(sel[0], "values")
        if not vals:
            return
        dev_id = vals[0]

        devs = devices_db.load_devices() if devices_db else {}
        dev = devs.get(dev_id)
        if not dev:
            return

        req_id = dev.get("request_id", "")
        is_phone = (dev.get("device_type") == "phone" or dev_id.startswith("MOB") or req_id.startswith("EBMOB") or dev.get("mac_tail", "").startswith("MO"))
        dev_label = "📱 Телефон" if is_phone else "💻 ПК"
        mac = dev.get("mac", "")
        self.detail_frame.config(text=f" 📜 История паролей устройства [{dev_id}] | {dev_label} | Идентификатор/MAC: {mac} ")

        pwds = dev.get("passwords", [])
        for p in pwds:
            idx = p.get("index", 1)
            k = p.get("key", "—")
            t_name = p.get("tier_name", "+30 дней")
            issued = p.get("issued_at", "—")
            status_val = p.get("status", "active")
            if status_val == "active":
                status_str = "🟢 Активен"
            elif status_val == "replaced":
                status_str = "🔄 Заменён"
            elif status_val in ("pending", "issued"):
                status_str = "⏳ Ожидает"
            else:
                status_str = status_val
            reason = p.get("reason", "—")
            act_str = f"✅ {p.get('activated_at')}" if p.get("activated") else "⏳ Ожидает"

            self.tree_pwds.insert("", "end", values=(
                f"#{idx}",
                k,
                t_name,
                issued,
                p.get("valid_until", "—"),
                status_str,
                reason,
                act_str
            ))

    def copy_selected_device_password(self):
        sel = self.tree_pwds.selection()
        if not sel:
            # Если в таблице паролей не выбрано, копируем активный из таблицы устройств
            sel_dev = self.tree_devs.selection()
            if sel_dev:
                vals = self.tree_devs.item(sel_dev[0], "values")
                k = vals[4]
                if k and k != "—":
                    clean_k = k.replace("⏳", "").strip()
                    self.root.clipboard_clear()
                    self.root.clipboard_append(clean_k)
                    self.root.update()
                    self.notify_copied(f"Ключ скопирован: {clean_k}")
                    return
            self.notify_copied("Выберите пароль или устройство для копирования.")
            return
        vals = self.tree_pwds.item(sel[0], "values")
        k = vals[1]
        self.root.clipboard_clear()
        self.root.clipboard_append(k)
        self.root.update()
        self.notify_copied(f"Ключ #{vals[0]} скопирован: {k}")

    def jump_to_issue_next_password(self):
        """Переключает на вкладку генератора с предзаполненными данными выбранного устройства."""
        sel_dev = self.tree_devs.selection()
        if not sel_dev:
            messagebox.showinfo("Инфо", "Выберите устройство из таблицы.")
            return
        vals = self.tree_devs.item(sel_dev[0], "values")
        dev_id = vals[0]
        devs = devices_db.load_devices() if devices_db else {}
        dev = devs.get(dev_id)
        if not dev:
            return

        req_id = dev.get("request_id", "")
        self.notebook.select(0)
        self.entry_client_req_id.delete(0, tk.END)
        self.entry_client_req_id.insert(0, req_id)
        if hasattr(self, 'entry_hw_client'):
            self.entry_hw_client.delete(0, tk.END)
            self.entry_hw_client.insert(0, dev.get("client_name", "skynet83"))
        self.combo_hw_reason.set("Переустановка Windows (пароль #2)")
        self.on_client_req_id_change()

    def edit_selected_device(self):
        sel_dev = self.tree_devs.selection()
        if not sel_dev:
            messagebox.showinfo("Инфо", "Выберите устройство для редактирования.")
            return
        vals = self.tree_devs.item(sel_dev[0], "values")
        dev_id = vals[0]
        devs = devices_db.load_devices() if devices_db else {}
        dev = devs.get(dev_id)
        if not dev:
            return

        new_notes = simpledialog.askstring("Заметка", f"Заметка по устройству {dev_id}:", 
                                           initialvalue=dev.get("notes", ""), parent=self.root)
        if new_notes is not None:
            dev["notes"] = new_notes.strip()
            devices_db.save_devices(devs)
            self.refresh_devices_table()
            messagebox.showinfo("Успешно", f"Заметка устройства {dev_id} обновлена!")

    def delete_selected_device(self):
        sel_dev = self.tree_devs.selection()
        if not sel_dev:
            messagebox.showinfo("Инфо", "Выберите устройство для удаления.")
            return
        vals = self.tree_devs.item(sel_dev[0], "values")
        dev_id = vals[0]
        if messagebox.askyesno("Подтверждение", f"Вы действительно хотите удалить устройство {dev_id} из базы?\nВсе привязанные пароли будут удалены из реестра устройств."):
            devs = devices_db.load_devices() if devices_db else {}
            if dev_id in devs:
                del devs[dev_id]
                devices_db.save_devices(devs)
                self.refresh_devices_table()
                self.on_device_selected()
                messagebox.showinfo("Удалено", f"Устройство {dev_id} удалено из базы.")

    def refresh_stats(self):
        if not self.all_keys:
            self.all_keys = parse_keys_list()

        self.db_hashes = load_json_file(KEYS_JSON_PATH)
        self.dispensed = load_json_file(DISPENSED_PATH)
        devs = devices_db.load_devices() if devices_db else {}

        # Синхронизация паролей из реестра устройств в dispensed_keys
        disp_changed = False
        for dev_id, dev in devs.items():
            for p in dev.get("passwords", []):
                pk = p.get("key")
                if pk:
                    if pk not in self.dispensed:
                        self.dispensed[pk] = {
                            "client_note": f"ПК [{dev_id}] {p.get('reason', '')}",
                            "dispensed_at": p.get("issued_at", ""),
                            "hash": self.get_hash(pk),
                            "type": "hardware_bound",
                            "tier": p.get("tier", "30_days"),
                            "mac": dev.get("mac", ""),
                            "request_id": p.get("request_id") or dev.get("request_id", ""),
                            "device_id": dev_id,
                            "valid_until": p.get("valid_until", ""),
                            "activated_by": p.get("activated_by") if p.get("activated") else None,
                            "used_at": p.get("activated_at") if p.get("activated") else None
                        }
                        disp_changed = True
                    else:
                        req = p.get("request_id") or dev.get("request_id", "")
                        if req and not self.dispensed[pk].get("request_id"):
                            self.dispensed[pk]["request_id"] = req
                            disp_changed = True
                        if p.get("activated") and not self.dispensed[pk].get("activated_by"):
                            self.dispensed[pk]["activated_by"] = p.get("activated_by") or "skynet83"
                            self.dispensed[pk]["used_at"] = p.get("activated_at") or self.dispensed[pk].get("dispensed_at")
                            disp_changed = True
                        disp_changed = True

        # Сверка с users.json (активный ключ на сайте)
        users_file = os.path.join(DATA_DIR, "users.json")
        if os.path.exists(users_file):
            try:
                u_list = load_json_file(users_file)
                if isinstance(u_list, list):
                    for u in u_list:
                        perms = u.get("permissions", {})
                        ak = perms.get("active_key")
                        if ak and ak in self.dispensed:
                            if not self.dispensed[ak].get("activated_by"):
                                self.dispensed[ak]["activated_by"] = u.get("username", "skynet83")
                                self.dispensed[ak]["used_at"] = self.dispensed[ak].get("dispensed_at") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                disp_changed = True
            except Exception:
                pass

        if disp_changed:
            save_json_file(DISPENSED_PATH, self.dispensed)

        total = len(self.all_keys)
        dispensed_count = len(self.dispensed)
        devices_count = len(devs)

        activated_count = 0
        for h, rec in self.db_hashes.items():
            if rec.get("used"):
                activated_count += 1
        for k, inf in self.dispensed.items():
            if inf.get("activated_by") or inf.get("used_by"):
                activated_count += 1

        vip_total = sum(1 for k in self.all_keys if k[2] == "unlimited")
        vip_dispensed = sum(1 for k, inf in self.dispensed.items() if inf.get("tier") == "unlimited" or any(item[1] == k and item[2] == "unlimited" for item in self.all_keys))
        vip_available = max(0, vip_total - vip_dispensed)
        available_count = max(0, total - dispensed_count)

        self.lbl_stat_devices.config(text=f"🖥️ Устройств в базе: {devices_count}")
        self.lbl_stat_dispensed.config(text=f"📤 Выдано: {dispensed_count:,}")
        self.lbl_stat_activated.config(text=f"✅ Активировано: {activated_count:,}")
        self.lbl_stat_vip.config(text=f"👑 VIP: {vip_available}/{vip_total}")
        self.lbl_stat_available.config(text=f"🟢 Свободно в пуле: {available_count:,}")

        self.populate_tree()

    def on_mode_changed(self):
        mode = self.key_dispense_mode.get()
        if mode == "vip":
            self.entry_client_note.delete(0, tk.END)
            self.entry_client_note.insert(0, "VIP Бессрочно (семья / друзья)")
            self.entry_current_key.config(fg="#c084fc")
        else:
            self.entry_client_note.delete(0, tk.END)
            self.entry_client_note.insert(0, "Оплата тарифа (30 дней)")
            self.entry_current_key.config(fg="#38bdf8")
        self.show_next_available_key()

    def show_next_available_key(self):
        target_mode = self.key_dispense_mode.get()
        for num_str, k_str, k_dur in self.all_keys:
            is_match = (
                (target_mode == "standard" and k_dur in ("standard", "30_days")) or
                (target_mode == "vip" and k_dur in ("vip", "unlimited"))
            )
            if is_match:
                if k_str not in self.dispensed:
                    self.entry_current_key.delete(0, tk.END)
                    self.entry_current_key.insert(0, k_str)
                    return
        self.entry_current_key.delete(0, tk.END)
        self.entry_current_key.insert(0, f"ВСЕ {target_mode.upper()} КЛЮЧИ ВЫДАНЫ!")

    def action_dispense_key(self):
        key_to_dispense = self.entry_current_key.get().strip()
        if not key_to_dispense or "ВСЕ" in key_to_dispense:
            messagebox.showwarning("Внимание", "Нет доступных ключей для выдачи!")
            return

        note = self.entry_client_note.get().strip() or "Без заметки"
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        self.dispensed[key_to_dispense] = {
            "client_note": note,
            "dispensed_at": now_str,
            "hash": self.get_hash(key_to_dispense),
            "tier": "unlimited" if self.key_dispense_mode.get() == "vip" else "30_days"
        }
        save_json_file(DISPENSED_PATH, self.dispensed)

        self.root.clipboard_clear()
        self.root.clipboard_append(key_to_dispense)
        self.root.update()

        self.lbl_dispense_status.config(
            text=f"✅ Ключ {key_to_dispense} скопирован в буфер обмена и выдан: {note}!",
            fg="#34d399"
        )
        self.refresh_stats()
        self.show_next_available_key()

    def populate_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Карта привязки ключей к коду устройства (ID клиента) из базы устройств
        dev_map = {}
        if devices_db:
            try:
                all_devs = devices_db.load_devices()
                for d_id, d_data in all_devs.items():
                    req = d_data.get("request_id")
                    for p in d_data.get("passwords", []):
                        if p.get("key") and req:
                            dev_map[p["key"]] = req
            except Exception:
                pass

        idx = 1
        items_rev = list(reversed(list(self.dispensed.items())))
        search_q = self.entry_registry_search.get().strip().lower() if hasattr(self, 'entry_registry_search') else ""

        for k_str, info in items_rev:
            h = info.get("hash") or self.get_hash(k_str)
            db_rec = self.db_hashes.get(h, {})
            is_used = db_rec.get("used", False) or bool(info.get("activated_by") or info.get("used_by"))
            used_status = "✅ Активирован" if is_used else "⏳ Ожидает ввода"
            used_at = db_rec.get("used_at") or info.get("used_at") or (info.get("dispensed_at") if info.get("activated_by") else "—")
            
            # Код устройства от клиента (request_id, например: EBID-1AEC-084C-7AB8-8CF5-88B7)
            raw_req = info.get("request_id") or dev_map.get(k_str) or info.get("device_id") or ""
            if raw_req and raw_req != "—":
                is_phone = raw_req.upper().startswith("EBMOB") or "MOB-" in raw_req.upper() or (info.get("device_type") == "phone")
                dev_icon = "📱" if is_phone else "💻"
                req_id_code = f"{dev_icon} {raw_req}"
            else:
                req_id_code = "—"
            client_note = info.get("client_note", "—")
            dispensed_at = info.get("dispensed_at", "—")

            is_vip = bool(info.get("tier") == "unlimited" or db_rec.get("is_unlimited") or any(item[1] == k_str and item[2] == "unlimited" for item in self.all_keys))
            is_hw = (info.get("type") == "hardware_bound" or k_str.startswith("EB30-") or k_str.startswith("VIPX-"))
            
            if is_hw:
                vu = info.get("valid_until", "")
                if is_vip:
                    type_label = "👑 VIP ПК"
                elif vu:
                    type_label = f"🔐 до {vu[:10]}"
                else:
                    type_label = "🔐 Срок ПК"
            else:
                type_label = "👑 VIP Пул" if is_vip else "📦 30 дн Пул"

            if search_q:
                match_blob = f"{k_str} {req_id_code} {client_note} {dispensed_at} {type_label} {used_status}".lower()
                if search_q not in match_blob:
                    continue

            self.tree.insert("", "end", values=(
                f"{idx}",
                req_id_code,
                type_label,
                k_str,
                client_note,
                dispensed_at,
                used_status,
                used_at
            ))
            idx += 1

    def clear_registry_search(self):
        if hasattr(self, 'entry_registry_search'):
            self.entry_registry_search.delete(0, tk.END)
            self.populate_tree()

    def show_registry_context_menu(self, event):
        row_id = self.tree.identify_row(event.y)
        if row_id:
            self.tree.selection_set(row_id)
        sel = self.tree.selection()
        if not sel:
            return
        menu = tk.Menu(self.root, tearoff=0, bg="#1e293b", fg="#f8fafc", activebackground="#0284c7", activeforeground="#ffffff")
        menu.add_command(label="📋 Скопировать ключ (Ctrl+C)", command=self.copy_selected_key)
        menu.add_command(label="🖥️ Скопировать код устройства", command=self.copy_selected_req_id)
        menu.add_separator()
        menu.add_command(label="🔍 Найти в базе устройств (Таб 2)", command=self.goto_device_from_registry)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def goto_device_from_registry(self):
        sel = self.tree.selection()
        if not sel:
            return
        vals = self.tree.item(sel[0], "values")
        if vals and len(vals) > 1:
            req_id = vals[1]
            key_val = vals[3] if len(vals) > 3 else ""
            self.notebook.select(1)
            if hasattr(self, 'entry_dev_search'):
                self.entry_dev_search.delete(0, tk.END)
                if req_id and req_id != "—":
                    self.entry_dev_search.insert(0, req_id)
                elif key_val:
                    self.entry_dev_search.insert(0, key_val)
                self.refresh_devices_table()

    def show_tree_devs_context_menu(self, event):
        row_id = self.tree_devs.identify_row(event.y)
        if row_id:
            self.tree_devs.selection_set(row_id)
            self.on_device_selected()
        sel = self.tree_devs.selection()
        if not sel:
            return
        menu = tk.Menu(self.root, tearoff=0, bg="#1e293b", fg="#f8fafc", activebackground="#0284c7", activeforeground="#ffffff")
        menu.add_command(label="📋 Скопировать активный ключ (Ctrl+C)", command=self.copy_selected_device_password)
        menu.add_command(label="🖥️ Скопировать код устройства", command=self.copy_selected_dev_code)
        menu.add_separator()
        menu.add_command(label="🔁 Выдать следующий пароль этому ПК", command=self.jump_to_issue_next_password)
        menu.add_command(label="✏️ Изменить заметку", command=self.edit_selected_device)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def show_tree_pwds_context_menu(self, event):
        row_id = self.tree_pwds.identify_row(event.y)
        if row_id:
            self.tree_pwds.selection_set(row_id)
        sel = self.tree_pwds.selection()
        if not sel:
            return
        menu = tk.Menu(self.root, tearoff=0, bg="#1e293b", fg="#f8fafc", activebackground="#0284c7", activeforeground="#ffffff")
        menu.add_command(label="📋 Скопировать этот ключ (Ctrl+C)", command=self.copy_selected_device_password)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def copy_selected_dev_code(self):
        sel = self.tree_devs.selection()
        if not sel:
            return
        vals = self.tree_devs.item(sel[0], "values")
        dev_id = vals[0]
        devs = devices_db.load_devices() if devices_db else {}
        dev = devs.get(dev_id, {})
        req_id = dev.get("request_id") or dev_id
        self.root.clipboard_clear()
        self.root.clipboard_append(req_id)
        self.root.update()
        self.notify_copied(f"Код устройства скопирован в буфер: {req_id}")

    def copy_selected_req_id(self):
        sel = self.tree.selection()
        if not sel:
            self.notify_copied("Выберите строку из таблицы.")
            return
        vals = self.tree.item(sel[0], "values")
        if vals and len(vals) > 1:
            req_val = vals[1]
            if req_val and req_val != "—":
                clean_req = re.sub(r'^[💻📱🖥️]\s*', '', req_val).strip()
                self.root.clipboard_clear()
                self.root.clipboard_append(clean_req)
                self.root.update()
                self.notify_copied(f"Код устройства скопирован в буфер: {clean_req}")
            else:
                self.notify_copied("Для выбранной записи код устройства не указан.")

    def copy_selected_key(self):
        sel = self.tree.selection()
        if not sel:
            self.notify_copied("Выберите строку из таблицы общего реестра.")
            return
        vals = self.tree.item(sel[0], "values")
        if vals and len(vals) > 3:
            key_val = vals[3]
            self.root.clipboard_clear()
            self.root.clipboard_append(key_val)
            self.root.update()
            self.notify_copied(f"Ключ скопирован в буфер: {key_val}")

    def open_generate_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("➕ Генерация новых лицензионных ключей")
        dialog.geometry("420x260")
        dialog.resizable(False, False)
        dialog.configure(bg="#1e293b")
        dialog.transient(self.root)
        dialog.grab_set()

        if hasattr(self, '_app_icon_img') and self._app_icon_img:
            try:
                dialog.iconphoto(False, self._app_icon_img)
            except Exception:
                pass

        tk.Label(dialog, text="Генерация новой партии лицензий", font=("Segoe UI", 12, "bold"),
                 bg="#1e293b", fg="#fbbf24").pack(pady=(16, 6))

        tk.Label(dialog, text="Сколько ключей сгенерировать?", font=("Segoe UI", 10),
                 bg="#1e293b", fg="#f8fafc").pack(pady=4)

        entry_count = tk.Entry(dialog, font=("Segoe UI", 12, "bold"), justify="center",
                               bg="#0f172a", fg="#38bdf8", relief="flat", bd=3)
        entry_count.pack(ipady=4, pady=6)
        entry_count.insert(0, "1000")

        lbl_status = tk.Label(dialog, text="Ключи сразу запишутся в файл и добавятся в базу сервера.",
                              bg="#1e293b", fg="#94a3b8", font=("Segoe UI", 9))
        lbl_status.pack(pady=4)

        def do_gen():
            val = entry_count.get().strip()
            if not val.isdigit() or int(val) <= 0:
                messagebox.showerror("Ошибка", "Введите положительное число ключей!", parent=dialog)
                return
            count_to_gen = int(val)
            if count_to_gen > 100000:
                messagebox.showerror("Ошибка", "Максимум 100 000 ключей за один раз!", parent=dialog)
                return

            import secrets
            CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
            new_hashes = load_json_file(KEYS_JSON_PATH)
            current_total = len(self.all_keys)

            added_count = 0
            with open(KEYS_LIST_PATH, "a", encoding="utf-8") as f_txt:
                while added_count < count_to_gen:
                    raw = "".join(secrets.choice(CHARS) for _ in range(20))
                    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                    if h in new_hashes:
                        continue
                    current_total += 1
                    formatted = f"{raw[0:4]}-{raw[4:8]}-{raw[8:12]}-{raw[12:16]}-{raw[16:20]}"
                    new_hashes[h] = {
                        "id": current_total,
                        "key_mask": f"{formatted[:9]}****-****-{formatted[-4:]}",
                        "duration_days": 30,
                        "used": False,
                        "used_by": None,
                        "used_at": None
                    }
                    f_txt.write(f"{current_total:05d}. {formatted}\n")
                    self.all_keys.append((f"{current_total:05d}", formatted, "30_days"))
                    added_count += 1

            save_json_file(KEYS_JSON_PATH, new_hashes)
            self.refresh_stats()
            self.show_next_available_key()
            dialog.destroy()
            messagebox.showinfo("Успешно", f"Сгенерировано и добавлено в базу {added_count} новых ключей!\nВсего ключей: {current_total}")

        btn_confirm = tk.Button(dialog, text="🚀 Сгенерировать и сохранить", font=("Segoe UI", 10, "bold"),
                                bg="#059669", fg="#ffffff", activebackground="#047857", activeforeground="#ffffff",
                                relief="flat", cursor="hand2", padx=16, pady=6, command=do_gen)
        btn_confirm.pack(pady=(12, 0))

    def refresh_all(self):
        self.refresh_stats()
        self.refresh_devices_table()
        self.show_next_available_key()
        self.update_user_keys_ui_state()
        messagebox.showinfo("Обновлено", "Данные базы устройств и ключей успешно актуализированы!")

if __name__ == "__main__":
    _single_instance_mutex = ensure_single_instance()
    root = tk.Tk()
    app = KeyManagerApp(root)
    root.mainloop()

