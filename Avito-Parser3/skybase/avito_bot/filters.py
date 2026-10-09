# -*- coding: utf-8 -*-
"""
Модуль фильтрации объявлений Avito (релевантность, стоп-слова, ключевые токены модели, фильтр цен).
Используется как Telegram-ботом, так и веб-скриптом avito_api_helper.py.
"""
import re
import base64
import json
from typing import List, Optional, Tuple
from urllib.parse import urlparse, parse_qs, unquote

ACCESSORY_WORDS = [
    "коробк", "кулер", "вентилятор", "вертушк",
    "охлажден", "радиатор", "термопрокладк", "термопаст", "бэкплейт",
    "система охлажден", "системы охлажден"
]

SPAM_WORDS = [
    "скупка", "выкуп", "купим", "куплю",
    "чернил", "картридж", "тонер", "краска для", "для принтер"
]

# Общий список стоп-слов (без отсечения неисправных/ремонтных товаров)
STOP_WORDS = SPAM_WORDS + ACCESSORY_WORDS


def extract_price_range(url: str, name: str = "") -> Tuple[Optional[int], Optional[int]]:
    """Извлекает минимальную и максимальную цену из URL (?pmin, ?pmax, ?f=...) или названия поиска."""
    pmin = None
    pmax = None

    # 1. Из URL параметров pmin / pmax
    try:
        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query)
        if "pmin" in query_dict and query_dict["pmin"]:
            try:
                pmin = int(query_dict["pmin"][0])
            except Exception:
                pass
        if "pmax" in query_dict and query_dict["pmax"]:
            try:
                pmax = int(query_dict["pmax"][0])
            except Exception:
                pass

        # 2. Из base64-фильтра Avito (f=...)
        if "f" in query_dict and query_dict["f"] and (pmin is None or pmax is None):
            f_val = query_dict["f"][0]
            try:
                padded = f_val.replace('-', '+').replace('~', '/')
                padded += '=' * ((4 - len(padded) % 4) % 4)
                raw = base64.b64decode(padded)
                m = re.search(rb'\{[^{}]*(?:from|to)[^{}]*\}', raw)
                if m:
                    data = json.loads(m.group(0).decode('utf-8', errors='ignore'))
                    if "from" in data and pmin is None:
                        pmin = int(data["from"])
                    if "to" in data and pmax is None:
                        pmax = int(data["to"])
            except Exception:
                pass
    except Exception:
        pass

    # 3. Из названия поиска, например "RX470 (500-2500)", "RX470 (500 - 2500 ₽)", "(от 500)", "(до 2500)"
    if (pmin is None or pmax is None) and name:
        m_range = re.search(r'\(\s*(\d+)\s*(?:-|–|до)\s*(\d+)\s*(?:₽|руб)?\s*\)', name, re.IGNORECASE)
        if m_range:
            if pmin is None:
                pmin = int(m_range.group(1))
            if pmax is None:
                pmax = int(m_range.group(2))
        else:
            m_from = re.search(r'\(\s*от\s*(\d+)\s*(?:₽|руб)?\s*\)', name, re.IGNORECASE)
            if m_from and pmin is None:
                pmin = int(m_from.group(1))
            m_to = re.search(r'\(\s*до\s*(\d+)\s*(?:₽|руб)?\s*\)', name, re.IGNORECASE)
            if m_to and pmax is None:
                pmax = int(m_to.group(1))

    return pmin, pmax


def parse_price_value(price_str: Optional[object]) -> Optional[int]:
    """Преобразует строку цены ('2 500 ₽', '2500', 'Бесплатно') или число в целое число."""
    if price_str is None or price_str == "":
        return None
    if isinstance(price_str, (int, float)):
        return int(price_str)
    s = str(price_str).strip().lower()
    if "бесплатно" in s or "даром" in s:
        return 0
    digits = re.sub(r'[^\d]', '', s)
    if digits:
        try:
            return int(digits)
        except Exception:
            return None
    return None


def is_ad_in_price_range(price_str: Optional[str], url: str, search_name: str = "") -> bool:
    """Проверяет, входит ли цена объявления в заданный диапазон поиска."""
    pmin, pmax = extract_price_range(url, search_name)
    if pmin is None and pmax is None:
        return True  # Нет фильтра по цене

    num_price = parse_price_value(price_str)
    if num_price is None:
        # Если цена не указана вообще, но фильтр строгий — отсекаем
        return False

    if pmin is not None and num_price < pmin:
        return False
    if pmax is not None and num_price > pmax:
        return False

    return True


def format_price_suffix(pmin: Optional[int], pmax: Optional[int]) -> str:
    """Форматирует диапазон цен в виде суффикса для карточки/поиска, например (500-2500)."""
    if pmin is not None and pmax is not None:
        return f"({pmin}-{pmax})"
    if pmin is not None:
        return f"(от {pmin})"
    if pmax is not None:
        return f"(до {pmax})"
    return ""


def attach_price_suffix_to_name(name: str, url: str) -> str:
    """Добавляет к имени поиска приписку фильтра цен, если её ещё нет."""
    clean_name = (name or "").strip()
    pmin, pmax = extract_price_range(url, clean_name)
    suffix = format_price_suffix(pmin, pmax)
    if not suffix:
        return clean_name or "Поиск Avito"

    # Если уже есть суффикс вида (500-2500) или (от 500)
    if re.search(r'\(\s*(?:от|до|\d+)\s*[\d\-–\s]*\)', clean_name, re.IGNORECASE):
        return clean_name

    if not clean_name:
        parsed = urlparse(url)
        qs = parse_qs(parsed.query)
        if "q" in qs and qs["q"]:
            q_val = unquote(qs["q"][0]).replace("+", " ").strip()
            clean_name = q_val
        elif "videokarty" in url:
            clean_name = "Видеокарты"
        elif "protsessory" in url:
            clean_name = "Процессоры"
        elif "telefony" in url:
            clean_name = "Телефоны"
        elif "noutbuki" in url:
            clean_name = "Ноутбуки"
        elif "komplektuyuschie" in url:
            clean_name = "Комплектующие"
        else:
            clean_name = "Поиск Avito"

    return f"{clean_name} {suffix}"


def extract_keywords_from_url_or_name(url: str, name: str) -> List[str]:
    """Извлекает ключевые слова из поискового запроса URL (?q=...) или названия поиска."""
    raw_text = ""
    try:
        parsed = urlparse(url)
        query_dict = parse_qs(parsed.query)
        if "q" in query_dict and query_dict["q"]:
            raw_text = unquote(query_dict["q"][0]).strip().lower()
    except Exception:
        pass

    # Если в URL нет поискового параметра ?q= (например, общая ссылка на категорию),
    # произвольное имя задачи (например, «Тест», «Ссылка 1», «Компьютеры») НЕ должно отсекать объявления!
    if not raw_text and name:
        # Проверяем, есть ли в названии конкретная модель с цифрами (например rx580, rtx 3060, i5 12400)
        has_model_pattern = bool(re.search(r'\b(rtx|gtx|rx|gt|intel|ryzen|core|i[3579]|r[3579]|ps[45]|iphone)\b|\d{3,4}', name, re.IGNORECASE))
        if has_model_pattern:
            raw_text = re.sub(r"\(.*?\)", "", name).lower()

    if not raw_text:
        return []

    # Разбиваем слитые обозначения, например 'rx580' -> 'rx', '580', 'rtx3060' -> 'rtx', '3060'
    normalized = re.sub(r"([a-zа-яё]+)(\d+)", r"\1 \2", raw_text)
    normalized = re.sub(r"(\d+)([a-zа-яё]+)", r"\1 \2", normalized)

    words = [w for w in re.split(r"[\s\-_/,+]+", normalized) if len(w) >= 2]
    return words


def is_relevant_ad(title: str, url: str, search_name: str, price: Optional[str] = None) -> bool:
    """
    Умный фильтр релевантности:
    1. Отсекает спам по стоп-словам (коробка, кулер, на запчасти, нерабочая и т.д.)
    2. Проверяет фильтр цен (если передан price)
    3. Если в поиске указана конкретная модель (например, rx 580),
       проверяет, что ключевые токены присутствуют в названии товара,
       чтобы отсечь левые объявления из-за спам-тегов в описании.
    """
    if not title:
        return False

    # 1. Проверка диапазона цен (если передан price)
    if price is not None and not is_ad_in_price_range(price, url, search_name):
        return False

    title_lower = title.lower()
    # Нормализуем заголовок ('rx580' -> 'rx 580')
    normalized_title = re.sub(r"([a-zа-яё]+)(\d+)", r"\1 \2", title_lower)
    normalized_title = re.sub(r"(\d+)([a-zа-яё]+)", r"\1 \2", normalized_title)

    # 2. Проверка на спам-объявления (скупка, картриджи)
    for spam_word in SPAM_WORDS:
        if spam_word in title_lower:
            return False

    # 3. Отсекаем отдельные аксессуары (коробки, кулеры, радиаторы), но НЕ отсекаем видеокарты с дефектами
    for acc in ACCESSORY_WORDS:
        if title_lower.startswith(acc):
            if not any(w in title_lower for w in ["не крут", "шумит", "гудит", "трещит", "нет кулер", "без кулер", "под замену"]):
                return False
        if f" {acc} для" in title_lower or f" {acc} от" in title_lower or f" {acc} на " in title_lower:
            if not any(w in title_lower for w in ["не крут", "шумит", "гудит", "трещит", "нет кулер", "без кулер", "под замену"]):
                return False

    # 4. Проверка видеокарт/GPU и отсечение аксессуаров и чипов
    url_lower = url.lower()
    search_lower = search_name.lower()
    keywords = extract_keywords_from_url_or_name(url, search_name)

    is_gpu_query = (
        any(k in ["rx", "rtx", "gtx", "radeon", "geforce", "gpu"] for k in keywords)
        or "videokart" in url_lower
        or "видеокарт" in search_lower
        or "видеокарт" in url_lower
    )
    if is_gpu_query:
        if re.search(r'\b(мышь|мышка|mouse|коврик|чехол|брелок|наклейка)\b', normalized_title):
            return False

        # Отсекаем отдельные компоненты GPU (видеочипы, BGA чипы, трафареты, чипы памяти),
        # но оставляем целые видеокарты под ремонт / на запчасти / с дефектами.
        gpu_comp_patterns = [
            r'\bвидеочип[а-я]*\b',
            r'\bвидео-чип[а-я]*\b',
            r'\bвидео\s+чип[а-я]*\b',
            r'\bbga\s*чип[а-я]*\b',
            r'\bчип[а-я]*\s*bga\b',
            r'\bbga\s*трафарет[а-я]*\b',
            r'\bтрафарет[а-я]*\b',
            r'\bчип[ыа]?\s+памяти\b',
            r'\bбанк[иа]\s+памяти\b',
            r'^(?:новый\s+|оригинальный\s+|рабочий\s+|б/?у\s+|комплект\s+)?чип[а-я]*\b',
            r'\bчип[а-я]*\s+(?:для|от|на)\b',
        ]
        if any(re.search(pat, title_lower) for pat in gpu_comp_patterns):
            defect_indicators = [
                "отвал", "без ", "снят", "прогрет", "прогрев", "замен", "неисправ",
                "артефакт", "донор", "на запчаст", "мертв", "сгорев", "горел",
                "не рабоч", "нерабоч", "под ремонт", "под восстановл", "восстановлен",
                "скол", "реболл", "нет чип"
            ]
            is_defective_card = any(d in title_lower for d in defect_indicators)
            # Если есть признаки дефекта целой карты (например "Sapphire RX 570 (отвал чипа)" или "RX 570 без видеочипа"),
            # но объявление НЕ о продаже самого чипа/трафарета (заголовок не начинается с чип/видеочип/трафарет)
            if is_defective_card and not re.match(r'^(?:новый\s+|оригинальный\s+|рабочий\s+|б/?у\s+|комплект\s+)?(видеочип|чип|трафарет)', title_lower):
                pass
            else:
                return False

    # 5. Проверка ключевых слов модели
    if keywords:
        for kw in keywords:
            # Числа (580, 570, 1060, 3060) ищем строго как отдельное число/слово
            if kw.isdigit():
                if not re.search(rf"\b{re.escape(kw)}\b", normalized_title):
                    return False
            else:
                # Префиксы моделей (rx, rtx, gtx, radeon)
                if len(kw) >= 2 and kw not in normalized_title:
                    return False

    return True
