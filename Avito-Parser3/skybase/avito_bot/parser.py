import os
import re
import json
import time
from datetime import datetime
import socket
import logging
import asyncio
import random
from typing import List, Optional, Dict, Callable, Any
from urllib.parse import urlparse
from dataclasses import dataclass
from bs4 import BeautifulSoup
import concurrent.futures
from curl_cffi.requests import AsyncSession, Session
try:
    from config import AVITO_PROXY as PROXY, PROXIES_FILE
except ImportError:
    PROXY = None
    PROXIES_FILE = None

logger = logging.getLogger(__name__)


class ProxyPool:
    """Пул прокси-серверов с приоритетом по наименьшему пингу и кулдауном 30 сек."""
    _MY_HOST_IP: Optional[str] = "62.183.2.72"

    @classmethod
    def get_my_host_ip(cls) -> Optional[str]:
        if cls._MY_HOST_IP:
            return cls._MY_HOST_IP
        for url in ["https://icanhazip.com", "https://api.ipify.org", "https://ifconfig.me/ip"]:
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    ip = resp.read().decode("utf-8").strip()
                    if ip and len(ip.split(".")) == 4:
                        cls._MY_HOST_IP = ip
                        return ip
            except Exception:
                pass
        return cls._MY_HOST_IP

    def __init__(self, single_proxy: Optional[str] = PROXY, proxies_file: Optional[str] = PROXIES_FILE):
        if not proxies_file:
            proxies_file = os.path.join(os.path.dirname(__file__), "proxies.txt")
        self.proxies_file = proxies_file
        self.proxies: List[str] = []
        self._last_used: Dict[str, float] = {}
        self.proxy_pings: Dict[str, float] = {}  # proxy -> latency in ms
        self._index = 0

        # 1. Загружаем список из proxies.txt (если файл существует)
        if proxies_file and os.path.exists(proxies_file):
            try:
                with open(proxies_file, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip().lstrip("\ufeff")
                        if line and not line.startswith("#"):
                            if line.startswith("http://socks"):
                                line = line[7:]
                            if not line.startswith("http://") and not line.startswith("https://") and not line.startswith("socks5://") and not line.startswith("socks5h://") and not line.startswith("socks4://"):
                                line = f"http://{line}"
                            if line.startswith("socks5://"):
                                line = "socks5h://" + line[9:]
                            self.proxies.append(line)
                if self.proxies:
                    logger.info(f"Загружено {len(self.proxies)} прокси для ротации из {proxies_file}")
            except Exception as e:
                logger.warning(f"Ошибка чтения proxies_file: {e}")

        # 2. Если файл пуст, но указан одиночный прокси в config.py
        if not self.proxies and single_proxy:
            sp = single_proxy
            if sp.startswith("socks5://"):
                sp = "socks5h://" + sp[9:]
            self.proxies.append(sp)

        # 3. Загружаем кешированные пинги с диска (если есть)
        pings_file = os.path.join(os.path.dirname(proxies_file), "proxy_pings.json")
        if os.path.exists(pings_file):
            try:
                with open(pings_file, "r", encoding="utf-8") as f:
                    self.proxy_pings = json.load(f)
            except Exception:
                pass

        # 4. Загружаем last_used с диска (если есть)
        lu_file = os.path.join(os.path.dirname(proxies_file), "proxy_last_used.json")
        if os.path.exists(lu_file):
            try:
                with open(lu_file, "r", encoding="utf-8") as f:
                    self._last_used = json.load(f)
            except Exception:
                pass

        self._stop_fetch_flag = False
        self.is_fetching = False


    def stop_fetching(self):
        """Останавливает текущий фоновый поиск бесплатных прокси."""
        self._stop_fetch_flag = True
        self.is_fetching = False

    def save_to_file(self, proxies_file: Optional[str] = PROXIES_FILE):
        """Сохраняет только живые прокси обратно в файл."""
        path = proxies_file or PROXIES_FILE
        if path:
            mirror_paths = [
                path,
                r"C:\ins\EXP\Arduino\Проект\База-бот\SITE\avito_bot\proxies.txt"
            ]
            for mp in set(mirror_paths):
                try:
                    if os.path.exists(os.path.dirname(mp)):
                        with open(mp, "w", encoding="utf-8") as f:
                            f.write("# Список рабочих прокси (автоматически очищенный)\n")
                            for p in self.proxies:
                                clean_p = p.strip()
                                if clean_p.startswith("socks5://"):
                                    clean_p = "socks5h://" + clean_p[9:]
                                f.write(f"{clean_p}\n")
                except Exception as e:
                    logger.warning(f"Ошибка сохранения proxies_file в {mp}: {e}")

    @staticmethod
    def measure_tcp_ping(proxy: str, timeout: float = 1.5) -> Optional[float]:
        """Быстрое измерение TCP пинга (ms) до прокси-сервера."""
        try:
            clean = proxy.split("://", 1)[1] if "://" in proxy else proxy
            if "@" in clean:
                clean = clean.split("@", 1)[1]
            host, port_str = clean.split(":", 1)
            port = int(port_str.split("/")[0])
            t0 = time.perf_counter()
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            t1 = time.perf_counter()
            return round((t1 - t0) * 1000.0, 1)
        except Exception:
            return None

    def record_ping(self, proxy: str, ping_ms: float):
        """Сохраняет или сглаживает (EMA) замеренный пинг для прокси и записывает на диск."""
        try:
            val = float(ping_ms)
            if val <= 0:
                return
            if proxy not in self.proxy_pings or self.proxy_pings[proxy] <= 0:
                self.proxy_pings[proxy] = round(val, 1)
            else:
                self.proxy_pings[proxy] = round(self.proxy_pings[proxy] * 0.7 + val * 0.3, 1)
            # Сохраняем на диск (throttle: не чаще раза в 5 сек)
            self._flush_pings_to_disk()
        except Exception:
            pass

    def _flush_pings_to_disk(self):
        """Записывает proxy_pings в файл (не чаще раза в 5 сек)."""
        try:
            now = time.time()
            if hasattr(self, "_last_pings_flush") and now - self._last_pings_flush < 5.0:
                return
            self._last_pings_flush = now
            pings_file = os.path.join(os.path.dirname(self.proxies_file), "proxy_pings.json")
            with open(pings_file, "w", encoding="utf-8") as f:
                json.dump(self.proxy_pings, f, ensure_ascii=False)
        except Exception:
            pass

    def _flush_last_used_to_disk(self):
        """Записывает _last_used в файл (не чаще раза в 3 сек)."""
        try:
            now = time.time()
            if hasattr(self, "_last_lu_flush") and now - self._last_lu_flush < 3.0:
                return
            self._last_lu_flush = now
            lu_file = os.path.join(os.path.dirname(self.proxies_file), "proxy_last_used.json")
            with open(lu_file, "w", encoding="utf-8") as f:
                json.dump(self._last_used, f, ensure_ascii=False)
        except Exception:
            pass


    def get_proxy_ping(self, proxy: str) -> float:
        """Возвращает замеренный пинг (мс). При первом обращении замеряет TCP RTT или возвращает 9999.0."""
        if proxy in self.proxy_pings and self.proxy_pings[proxy] > 0:
            return self.proxy_pings[proxy]
        measured = self.measure_tcp_ping(proxy, timeout=1.0)
        if measured is not None:
            self.proxy_pings[proxy] = measured
            return measured
        return 9999.0

    @staticmethod
    def is_socket_alive(proxy: str, timeout: float = 1.0) -> bool:
        """Быстрая проверка доступности сокета через TCP connect без тяжелых TLS-хэндшейков."""
        try:
            clean = proxy.split("://", 1)[1] if "://" in proxy else proxy
            if "@" in clean:
                clean = clean.split("@", 1)[1]
            host, port_str = clean.split(":", 1)
            port = int(port_str.split("/")[0])
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            s.connect((host, port))
            s.close()
            return True
        except Exception:
            return False

    @staticmethod
    def is_anonymous_proxy(proxy: str, timeout: float = 3.0) -> bool:
        """
        Проверяет анонимность прокси через внешний IP-сервис без обращения к Avito.
        Если прокси прозрачный (transparent) и раскрывает IP сервера, либо не работает — возвращает False.
        """
        if not proxy or not isinstance(proxy, str) or not proxy.strip() or proxy.strip() == "direct":
            return False
        clean = proxy.strip()
        if not any(clean.startswith(p) for p in ("http://", "https://", "socks5://", "socks5h://", "socks4://")):
            return False
        if clean.startswith("socks5://"):
            clean = "socks5h://" + clean[9:]
        my_ip = getattr(ProxyPool, "_MY_HOST_IP", None)
        if my_ip and my_ip in clean:
            return False
        try:
            with Session(impersonate="safari15_5", proxy=clean, timeout=timeout, verify=False) as s:
                r = s.get("http://icanhazip.com", timeout=timeout)
                if r.status_code == 200:
                    ret_text = r.text.strip()
                    if my_ip and my_ip in ret_text:
                        return False
                    return True
        except Exception:
            pass
        return False

    @staticmethod
    def check_proxy_sync(proxy: str, timeout: int = 4, pool: Optional['ProxyPool'] = None) -> bool:
        """Проверяет живучесть прокси синхронно через curl_cffi Session без асинхронного селектора.
        
        Критерий «живой»: прокси установил соединение и получил валидный ответ от Avito.
        """
        if not proxy or not isinstance(proxy, str) or not proxy.strip() or proxy.strip() == "direct":
            return False
        clean_proxy = proxy.strip()
        if not any(clean_proxy.startswith(p) for p in ("http://", "https://", "socks5://", "socks5h://", "socks4://")):
            return False
        if clean_proxy.startswith("socks5://"):
            clean_proxy = "socks5h://" + clean_proxy[9:]

        my_ip = getattr(ProxyPool, "_MY_HOST_IP", None)
        if my_ip and my_ip in clean_proxy:
            return False

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        t0 = time.perf_counter()
        try:
            with Session(impersonate="safari15_5", proxy=clean_proxy, timeout=timeout, verify=False) as s:
                resp = s.get("https://m.avito.ru", headers=headers)
                t1 = time.perf_counter()
                elapsed_ms = round((t1 - t0) * 1000.0, 1)
                code = resp.status_code
                if code == 200:
                    lower_t = resp.text.lower()
                    if "доступ ограничен" in lower_t or "проверка пользователя" in lower_t or "firewall" in lower_t or "qrator" in lower_t:
                        return False
                    if pool and hasattr(pool, "record_ping"):
                        pool.record_ping(clean_proxy, elapsed_ms)
                    return True
                if code in (301, 302):
                    loc = resp.headers.get("Location", "")
                    if "blocked" not in loc and "firewall" not in loc:
                        if pool and hasattr(pool, "record_ping"):
                            pool.record_ping(clean_proxy, elapsed_ms)
                        return True
                    return False
                if code in (403, 429, 439):
                    return False
                return False
        except Exception:
            return False

    async def check_proxy_alive(self, proxy: str, timeout: int = 4) -> bool:
        """Асинхронная обертка для проверки прокси через пул потоков."""
        return await asyncio.to_thread(self.check_proxy_sync, proxy, timeout, self)

    async def filter_and_clean_dead_proxies(self) -> int:
        """
        Проверяет все прокси в пуле на живучесть.
        Мертвые удаляются, в списке и файле остаются только актуальные.
        Возвращает количество оставшихся рабочих прокси.
        """
        if not self.proxies:
            return 0

        logger.info(f"Проверка {len(self.proxies)} прокси на живучесть...")
        def _check_pool(proxy_list):
            alive_list = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=min(25, len(proxy_list) or 1)) as ex:
                futures = {ex.submit(self.check_proxy_sync, p, 4, self): p for p in proxy_list}
                for f in concurrent.futures.as_completed(futures):
                    p = futures[f]
                    try:
                        if f.result():
                            alive_list.append(p)
                    except Exception:
                        pass
            return alive_list

        alive = await asyncio.to_thread(_check_pool, list(self.proxies))
        removed_count = len(self.proxies) - len(alive)
        self.proxies = alive
        self.save_to_file()

        if removed_count > 0:
            logger.info(f"Удалено {removed_count} мертвых прокси. Актуальных в пуле: {len(alive)}")
        return len(alive)

    async def fetch_free_proxies_and_verify(
        self,
        target_alive: int = 300,
        max_candidates: int = 5000,
        on_progress: Optional[Callable[[int, int], Any]] = None,
        replace_slower: bool = True
    ) -> int:
        """
        Многопоточный поиск бесплатных прокси для Avito с упором на РФ и СНГ:
        1. Сбор кандидатов с приоритетных российских/СНГ источников.
        2. Этап 1: Быстрый сокет-пинг (60 потоков) за секунды отсеивает 90% закрытых портов.
        3. Этап 2: Проверка живых адресов напрямую с m.avito.ru (25 потоков).
        4. Рабочие адреса мгновенно сохраняются и обновляют статус в интерфейсе.
        """
        priority_sources = [
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/RU/data.txt",
            "https://api.proxyscrape.com/v3/free-proxy-list/get?request=displayproxies&country=ru,by,kz,am,ge&proxy_format=protocolipport&format=text",
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/BY/data.txt",
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/KZ/data.txt",
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/AM/data.txt",
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/GE/data.txt",
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/MD/data.txt",
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/UZ/data.txt",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=all&timeout=8000&country=ru&ssl=all&anonymity=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=all&timeout=8000&country=by,kz&ssl=all&anonymity=all",
        ]

        general_sources = [
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
            "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
            "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/all/data.txt",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=5000&country=all",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
            "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
            "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
            "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/all.txt",
            "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/socks5_proxies.txt",
            "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/generated/http_proxies.txt",
            "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/socks5.txt",
            "https://raw.githubusercontent.com/vakhov/fresh-proxy-list/master/http.txt",
            "https://raw.githubusercontent.com/prxchk/proxy-list/main/all.txt",
        ]

        self._stop_fetch_flag = False
        priority_candidates = []
        general_candidates = []

        def _fetch_source(url):
            try:
                import urllib.request
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    return resp.read().decode("utf-8", errors="ignore")
            except Exception:
                return ""

        # Параллельная загрузка приоритетных источников (РФ / СНГ)
        def _download_all():
            results = {}
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
                futures = {ex.submit(_fetch_source, u): u for u in priority_sources}
                for f in concurrent.futures.as_completed(futures):
                    u = futures[f]
                    try:
                        results[u] = f.result()
                    except Exception:
                        results[u] = ""
            return results

        sources_data = await asyncio.to_thread(_download_all)

        # 1. Monosans JSON
        m_raw = await asyncio.to_thread(_fetch_source, "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies.json")
        if m_raw:
            try:
                m_data = json.loads(m_raw)
                for item in m_data:
                    proto = item.get("protocol", "http")
                    h = item.get("host")
                    p = item.get("port")
                    iso = item.get("geolocation", {}).get("country", {}).get("iso_code", "")
                    if h and p:
                        addr = f"{proto}://{h}:{p}"
                        if addr not in self.proxies:
                            if iso in ("RU", "BY", "KZ", "AM", "GE", "MD", "UZ", "TR"):
                                if addr not in priority_candidates:
                                    priority_candidates.append(addr)
                            else:
                                if addr not in general_candidates:
                                    general_candidates.append(addr)
                logger.info(f"База Monosans JSON OK: {len(priority_candidates)} RU/CIS кандидатов")
            except Exception as e:
                logger.warning(f"Ошибка парсинга Monosans JSON: {e}")

        # 2. Обработка скачанных RU/CIS источников
        for src, txt in sources_data.items():
            if not txt:
                continue
            is_socks = "socks5" in src or "socks" in src
            for l in txt.splitlines():
                l = l.strip()
                if l and ":" in l and not l.startswith("#"):
                    if not l.startswith("http") and not l.startswith("socks"):
                        l = f"socks5://{l}" if is_socks else f"http://{l}"
                    if l not in self.proxies and l not in priority_candidates:
                        priority_candidates.append(l)

        # 3. Общемировые (если RU мало)
        if len(priority_candidates) < 500:
            def _download_gen():
                res = []
                with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                    futs = [ex.submit(_fetch_source, u) for u in general_sources[:6]]
                    for f in concurrent.futures.as_completed(futs):
                        try:
                            t = f.result()
                            if t:
                                res.append(t)
                        except Exception:
                            pass
                return res

            gen_texts = await asyncio.to_thread(_download_gen)
            for txt in gen_texts:
                for l in txt.splitlines():
                    l = l.strip()
                    if l and ":" in l and not l.startswith("#"):
                        if not l.startswith("http") and not l.startswith("socks"):
                            l = f"http://{l}"
                        if l not in self.proxies and l not in priority_candidates and l not in general_candidates:
                            general_candidates.append(l)

        # Перемешиваем кандидатов
        random.shuffle(priority_candidates)
        random.shuffle(general_candidates)
        all_to_test = (priority_candidates + general_candidates)[:max_candidates]
        logger.info(f"Собрано {len(priority_candidates)} RU/CIS кандидатов. Начинаем проверку {len(all_to_test)} адресов...")

        found_working = []
        self.is_fetching = True
        try:
            # Проверяем кандидатов пачками по 100
            chunk_size = 100
            for i in range(0, len(all_to_test), chunk_size):
                if self._stop_fetch_flag or len(self.proxies) >= target_alive:
                    break
                chunk = all_to_test[i:i + chunk_size]

                # Шаг 1: быстрый сокет-пинг (60 потоков, ~2 сек на 100 штук)
                def _ping_chunk(candidates):
                    alive_ports = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=60) as ex:
                        futures = {ex.submit(self.is_socket_alive, p, 1.0): p for p in candidates}
                        for f in concurrent.futures.as_completed(futures):
                            if self._stop_fetch_flag:
                                break
                            p = futures[f]
                            try:
                                if f.result():
                                    alive_ports.append(p)
                            except Exception:
                                pass
                    return alive_ports

                alive_ports = await asyncio.to_thread(_ping_chunk, chunk)
                if not alive_ports or self._stop_fetch_flag:
                    continue
                if len(self.proxies) >= target_alive and not replace_slower:
                    continue

                # Шаг 2: проверка анонимности и фильтрация прозрачных прокси (без обращения к Avito!)
                def _check_anon_chunk(candidates):
                    anon_list = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(30, len(candidates))) as ex:
                        futures = {ex.submit(self.is_anonymous_proxy, p, 2.5): p for p in candidates}
                        for f in concurrent.futures.as_completed(futures):
                            if self._stop_fetch_flag:
                                break
                            p = futures[f]
                            try:
                                if f.result():
                                    anon_list.append(p)
                            except Exception:
                                pass
                    return anon_list

                anon_ports = await asyncio.to_thread(_check_anon_chunk, alive_ports)
                if not anon_ports or self._stop_fetch_flag:
                    continue

                # Шаг 3: проверка проверенных анонимных адресов через Avito (20 потоков)
                def _check_avito_chunk(candidates):
                    ok_proxies = []
                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(20, len(candidates))) as ex:
                        futures = {ex.submit(self.check_proxy_sync, p, 4, self): p for p in candidates}
                        for f in concurrent.futures.as_completed(futures):
                            if self._stop_fetch_flag:
                                break
                            p = futures[f]
                            try:
                                if f.result():
                                    ok_proxies.append(p)
                            except Exception:
                                pass
                    return ok_proxies

                verified = await asyncio.to_thread(_check_avito_chunk, anon_ports)
                for p in verified:
                    if self._stop_fetch_flag:
                        break
                    if p not in self.proxies:
                        if len(self.proxies) < target_alive:
                            self.proxies.append(p)
                            found_working.append(p)
                            self.save_to_file()
                            p_ping = self.get_proxy_ping(p)
                            logger.info(f"Найдена рабочая прокси ({len(self.proxies)}/{target_alive}): {p} (ping {p_ping:.0f}ms)")
                        elif replace_slower:
                            # Пул укомплектован (достигнута цель с резервом). Режим "Царь горы":
                            # проверяем, быстрее ли новый кандидат, чем самый медленный прокси в текущем пуле.
                            cand_ping = self.get_proxy_ping(p)
                            if cand_ping > 0 and cand_ping < 4000.0 and self.proxies:
                                worst_p = max(self.proxies, key=lambda px: self.get_proxy_ping(px))
                                worst_ping = self.get_proxy_ping(worst_p)
                                # Если у кандидата пинг лучше хотя бы на 15 мс — заменяем медленного
                                if cand_ping < worst_ping and (worst_ping - cand_ping) >= 15.0:
                                    self.proxies.remove(worst_p)
                                    self.proxies.append(p)
                                    found_working.append(p)
                                    self.save_to_file()
                                    logger.info(
                                        f"⚡ [Царь горы] Заменен медленный прокси ({worst_p}, ping {worst_ping:.0f}ms) "
                                        f"на более быстрый ({p}, ping {cand_ping:.0f}ms). Пул: {len(self.proxies)}/{target_alive}"
                                    )
                        if on_progress:
                            try:
                                res = on_progress(len(self.proxies), target_alive)
                                if asyncio.iscoroutine(res):
                                    await res
                            except Exception:
                                pass
                await asyncio.sleep(0.01)
        finally:
            self.is_fetching = False

        self.save_to_file()
        logger.info(f"Поиск прокси завершен. Найдено новых: {len(found_working)}, всего в пуле: {len(self.proxies)}")
        return len(self.proxies)

    def get_proxy_count(self) -> int:
        """Возвращает количество активных прокси в пуле."""
        return len(self.proxies)

    def reload(self, proxies_file: Optional[str] = PROXIES_FILE):
        """Перечитывает список прокси из файла на лету."""
        new_proxies = []
        path = proxies_file or PROXIES_FILE
        if path and os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    for line in f:
                        line = line.strip().lstrip("\ufeff")
                        if line and not line.startswith("#"):
                            if line.startswith("http://socks"):
                                line = line[7:]
                            if not line.startswith("http://") and not line.startswith("https://") and not line.startswith("socks5://") and not line.startswith("socks5h://") and not line.startswith("socks4://"):
                                line = f"http://{line}"
                            if line.startswith("socks5://"):
                                line = "socks5h://" + line[9:]
                            new_proxies.append(line)
                self.proxies = new_proxies
            except Exception as e:
                logger.warning(f"Ошибка перезагрузки proxies_file: {e}")

    def remove_proxy(self, proxy: str):
        """Мгновенно удаляет прокси из активного пула в памяти и сохраняет файл."""
        clean = re.sub(r"^(http|https|socks5h|socks5|socks4)://", "", proxy).strip().lower().rstrip("/")
        self.proxies = [p for p in self.proxies if re.sub(r"^(http|https|socks5h|socks5)://", "", p).strip().lower().rstrip("/") != clean]
        self.save_to_file()

    def get_next_proxy(self, exclude: Optional[set] = None) -> Optional[str]:
        """
        Возвращает лучший доступный рабочий прокси с наименьшим пингом.
        Приоритет: прокси с минимальным пингом среди отдохнувших (не менее 14 сек).
        Если все недавно использовались — кандидат с минимальным пингом и давним временем использования.
        Поддерживает exclude (множество адресов, уже занятых параллельными задачами).
        ВАЖНО: использует только закешированные пинги — без TCP-замеров на лету.
        """
        if not self.proxies:
            return None

        now = time.time()
        # Прокси, не занятые в текущей пачке
        candidates = [p for p in self.proxies if not exclude or p not in exclude]
        if not candidates:
            candidates = list(self.proxies)

        # Получаем пинг только из кеша (без TCP); если нет — 0 (отдаём первыми как «неизвестные»)
        def _cached_ping(px):
            v = self.proxy_pings.get(px, 0)
            return v if v > 0 else 0

        # Прокси, отдохнувшие не менее 14 секунд с момента прошлого использования (цикл ротации)
        eligible = [p for p in candidates if (now - self._last_used.get(p, 0)) >= 14.0]
        if eligible:
            # Сортируем по минимальному пингу (мс), при равенстве - по давности использования
            eligible.sort(key=lambda p: (_cached_ping(p), self._last_used.get(p, 0)))
            proxy = eligible[0]
        else:
            candidates.sort(key=lambda p: (_cached_ping(p), self._last_used.get(p, 0)))
            proxy = candidates[0]

        self._last_used[proxy] = now
        self._flush_last_used_to_disk()
        return proxy



    def mark_failed(self, proxy: str):
        """Если прокси вернул ошибку, логируем её и удаляем из активного пула."""
        logger.warning(f"Прокси {proxy} вернул ошибку или таймаут. Удаление из пула.")
        if proxy in self.proxies:
            self.proxies.remove(proxy)
            self._last_used.pop(proxy, None)
            self.save_to_file()


def deduplicate_avito_photos(urls: Optional[List[str]]) -> List[str]:
    """Исключает дубликаты одного и того же фото в разных разрешениях (превью vs оригинал)."""
    if not urls:
        return []
    result = []
    seen_hashes = {}
    for raw in urls:
        if not raw or not isinstance(raw, str):
            continue
        u = raw.strip().rstrip('\\/.,;\'\" ').replace('\\/', '/')
        if u.startswith('//'):
            u = f"https:{u}"
        elif not u.startswith('http'):
            continue
        
        # Извлекаем базовый хеш картинки Avito:
        # e.g. https://c60.img.avito.st/image/1/1.he565ba1KQdgRPc... -> he565ba
        m = re.search(r'img\.avito\.st/image/\d+/(?:[0-9]+x[0-9]+/)?(?:1\.)?([a-zA-Z0-9_\-]{6,12})', u)
        if m:
            h = m.group(1)[:7].lower()
            m_v = re.search(r'img\.avito\.st/image/\d+/(?:[0-9]+x[0-9]+/)?(?:1\.)?[a-zA-Z0-9_\-]{7}([0-9a-zA-Z])', u)
            v = m_v.group(1) if m_v else ''
            is_hires = v in ['4', '5', '6'] or any(d in u for d in ['1280x960', '1024x768', '864x648'])
            is_thumb = v in ['1', '2', '3'] or any(dim in u for dim in ["/150x110/", "/140x105/", "/120x90/", "/80x60/", "150x110", "140x105"])
            if h not in seen_hashes:
                seen_hashes[h] = len(result)
                result.append(u)
            elif is_hires or not is_thumb:
                idx = seen_hashes[h]
                result[idx] = u
        else:
            if u not in result:
                result.append(u)
    return result


@dataclass
class AvitoAd:
    id: str
    title: str
    price: str
    url: str
    photo: Optional[str] = None
    seller: Optional[str] = None
    address: Optional[str] = None
    has_delivery: bool = False
    has_chat: bool = True
    is_company: bool = False
    seller_type: str = "Частное лицо"
    is_reserved: bool = False
    item_date: Optional[str] = None
    seller_rating: Optional[str] = None
    photos: Optional[List[str]] = None
    description: Optional[str] = None


class AvitoParser:
    def __init__(self, proxy: Optional[str] = PROXY):
        self.proxy_pool = ProxyPool(single_proxy=proxy)
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",
        }

    def _normalize_url(self, url: str) -> str:
        """Переводит десктопный URL в мобильный вид (m.avito.ru) для обхода WAF и гарантирует сортировку по дате."""
        clean_url = url.strip()
        if clean_url.startswith("https://www.avito.ru/"):
            clean_url = clean_url.replace("https://www.avito.ru/", "https://m.avito.ru/", 1)
        elif clean_url.startswith("http://www.avito.ru/"):
            clean_url = clean_url.replace("http://www.avito.ru/", "https://m.avito.ru/", 1)
        elif clean_url.startswith("https://avito.ru/"):
            clean_url = clean_url.replace("https://avito.ru/", "https://m.avito.ru/", 1)

        # Гарантируем сортировку по дате (s=104) для хронологического поиска свежих объявлений
        if "s=" not in clean_url:
            delim = '&' if '?' in clean_url else '?'
            clean_url = f"{clean_url}{delim}s=104"

        return clean_url

    def _extract_id(self, item_tag, full_url: str) -> Optional[str]:
        """Извлекает цифровой ID объявления."""
        # 1. Из атрибута data-item-id
        item_id = item_tag.get("data-item-id")
        if item_id:
            return str(item_id)

        # 2. Из ссылки вида /..._8374875293?...
        match = re.search(r"_(\d{8,15})(?:\?|$)", full_url)
        if match:
            return match.group(1)

        # 3. Из атрибута id
        tag_id = item_tag.get("id")
        if tag_id:
            num_match = re.search(r"(\d{8,15})", tag_id)
            if num_match:
                return num_match.group(1)

        return None

    def _get_page_url(self, base_url: str, page_num: int) -> str:
        """Формирует URL для запроса конкретной страницы поиска Avito (p=1, 2, ...)."""
        if page_num <= 1:
            return base_url
        if re.search(r'([?&])p=\d+', base_url):
            return re.sub(r'([?&])p=\d+', r'\g<1>p=' + str(page_num), base_url)
        delim = '&' if '?' in base_url else '?'
        return f"{base_url}{delim}p={page_num}"

    async def fetch_single_page(self, page_url: str, proxy: Optional[str] = None, allow_direct: bool = False) -> List[AvitoAd]:
        """
        Асинхронно скачивает одну страницу поиска Avito.
        СТРОГО ЧЕРЕЗ ПРОКСИ. Прямое подключение к Авито для парсинга/поиска категорически запрещено!
        Прямое подключение зарезервировано исключительно для действий пользователя:
        написание сообщений продавцу, оформление заказов и оставление отзывов.
        """
        target_url = self._normalize_url(page_url)
        # Исключаем 'direct' и требуем только реальный прокси
        current_proxy = proxy if (proxy and proxy != "direct") else None

        max_attempts = min(5, max(3, len(self.proxy_pool.proxies) if (hasattr(self, "proxy_pool") and self.proxy_pool and self.proxy_pool.proxies) else 3))
        for attempt in range(max_attempts):
            if not current_proxy:
                if hasattr(self, "proxy_pool") and self.proxy_pool and self.proxy_pool.proxies:
                    current_proxy = self.proxy_pool.get_next_proxy()
                if not current_proxy:
                    logger.warning("🛡️ Защита IP: Все подключения к Авито для мониторинга/парсинга должны быть через прокси. Прямое подключение заблокировано.")
                    return []

            if not isinstance(current_proxy, str) or not any(current_proxy.startswith(p) for p in ("http://", "https://", "socks5://", "socks5h://", "socks4://")):
                logger.warning(f"🛡️ Защита IP: Недопустимый адрес прокси '{current_proxy}'. Прямое подключение заблокировано.")
                return []

            # Удаленный DNS для socks5 (исключение DNS-утечек через провайдера)
            if current_proxy.startswith("socks5://"):
                current_proxy = "socks5h://" + current_proxy[9:]

            # Защита от случайного указания собственного IP сервера
            my_ip = getattr(ProxyPool, "_MY_HOST_IP", None)
            if my_ip and my_ip in current_proxy:
                logger.warning(f"🛡️ Защита IP: Прокси содержит реальный IP хоста ({my_ip}). Использование заблокировано.")
                return []

            proxy_info = f" через {current_proxy}"
            t_req_start = time.perf_counter()
            try:
                async with AsyncSession(impersonate="safari15_5", proxy=current_proxy) as session:
                    response = await session.get(
                        target_url,
                        headers=self.headers,
                        timeout=10
                    )
                    t_req_end = time.perf_counter()
                    req_elapsed_ms = round((t_req_end - t_req_start) * 1000.0, 1)

                    if response.status_code == 200:
                        html = response.text
                        lower_html = html.lower()
                        if "доступ ограничен" not in lower_html and "проверка пользователя" not in lower_html and "firewall" not in lower_html:
                            if current_proxy and hasattr(self, "proxy_pool") and self.proxy_pool:
                                self.proxy_pool.record_ping(current_proxy, req_elapsed_ms)
                            ads = self._parse_html(html)
                            return ads or []

                    # Если вернул 403, 429, 502 или капчу — помечаем прокси сбойным и пробуем следующий
                    if current_proxy and hasattr(self, "proxy_pool") and self.proxy_pool:
                        self.proxy_pool.mark_failed(current_proxy)
            except Exception as e:
                logger.debug(f"Попытка #{attempt + 1} ({proxy_info}) не удалась: {e}")
                if current_proxy and hasattr(self, "proxy_pool") and self.proxy_pool:
                    self.proxy_pool.mark_failed(current_proxy)

            # Выбираем следующий прокси для следующей попытки (НИКОГДА не переходим на прямое подключение)
            if attempt < max_attempts - 1 and hasattr(self, "proxy_pool") and self.proxy_pool:
                current_proxy = self.proxy_pool.get_next_proxy()

        return []

    async def fetch_ads(
        self,
        search_url: str,
        proxy: Optional[str] = None,
        allow_direct: bool = False,
        max_pages: int = 10,
        stop_on_seen_callback: Optional[Any] = None,
        total_timeout: float = 35.0
    ) -> List[AvitoAd]:
        """
        Асинхронно скачивает объявления по страницам поиска Avito (пагинация p=1, 2, 3...).
        Гарантирует возврат всех уже скачанных объявлений даже при прерывании или таймауте.
        """
        all_ads: List[AvitoAd] = []
        seen_item_ids: set = set()
        is_unlimited = (max_pages == 0)
        max_p = 100 if is_unlimited else max(1, int(max_pages or 1))
        start_t = time.time()

        try:
            for page_num in range(1, max_p + 1):
                # Если общее отведенное время на исходе — возвращаем уже собранные объявления
                timeout_limit = 180.0 if is_unlimited else max(5.0, total_timeout - 3.5)
                if (time.time() - start_t) >= timeout_limit:
                    logger.debug(f"fetch_ads: лимит времени {timeout_limit}с достигнут на странице {page_num}, возвращаем {len(all_ads)} собранных объявлений")
                    break

                p_url = self._get_page_url(search_url, page_num)
                page_ads = await self.fetch_single_page(p_url, proxy=proxy, allow_direct=allow_direct)
                if not page_ads:
                    break

                new_page_ads = []
                for ad in page_ads:
                    if ad.id not in seen_item_ids:
                        seen_item_ids.add(ad.id)
                        new_page_ads.append(ad)
                        all_ads.append(ad)

                if not new_page_ads:
                    break

                if stop_on_seen_callback and stop_on_seen_callback(new_page_ads):
                    break

                if page_num < max_p:
                    await asyncio.sleep(0.1)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            logger.debug(f"fetch_ads: прервано по таймауту/отмене, сохраняем {len(all_ads)} уже собранных объявлений")
        except Exception as e:
            logger.debug(f"fetch_ads: ошибка при сборе страниц: {e}")

        return all_ads

    def _parse_html(self, html: str) -> List[AvitoAd]:
        """Парсит HTML-разметку страницы и возвращает структурированный список."""
        # 1. Извлекаем карту данных и изображений по ID объявлений из встроенного состояния window.__initialData__
        state_images_map: Dict[str, str] = {}
        state_items_map: Dict[str, Dict[str, Any]] = {}
        try:
            init_idx = html.find("__initialData__")
            if init_idx != -1:
                eq_idx = html.find("=", init_idx)
                start_pos = -1
                for pos in range(eq_idx + 1, min(eq_idx + 50, len(html))):
                    if not html[pos].isspace():
                        start_pos = pos
                        break

                if start_pos != -1:
                    decoder = json.JSONDecoder()
                    decoded_obj, _ = decoder.raw_decode(html[start_pos:])
                    if isinstance(decoded_obj, str):
                        data = json.loads(decoded_obj)
                    else:
                        data = decoded_obj

                    all_items = {}
                    s_items = data.get("search", {}).get("allItems")
                    if isinstance(s_items, dict):
                        all_items.update(s_items)
                    cat_items = data.get("catalog", {}).get("items") or data.get("items")
                    if isinstance(cat_items, list):
                        for ci in cat_items:
                            if isinstance(ci, dict) and ci.get("id"):
                                all_items[str(ci["id"])] = {"value": ci}
                    elif isinstance(cat_items, dict):
                        all_items.update(cat_items)

                    if isinstance(all_items, dict):
                        for it_id, it_info in all_items.items():
                            it_val = it_info.get("value", {}) if isinstance(it_info, dict) else {}
                            gallery = it_val.get("galleryItems") or it_val.get("gallery") or it_val.get("images") or it_val.get("photos") or []
                            chosen_url = None
                            item_photos = []
                            if gallery and isinstance(gallery, list):
                                for g in gallery:
                                    g_val = g.get("value", {}) if isinstance(g, dict) else (g if isinstance(g, dict) else {})
                                    if isinstance(g_val, dict) and g_val:
                                        u = (
                                            g_val.get("1280x960") or
                                            g_val.get("1024x768") or
                                            g_val.get("864x648") or
                                            g_val.get("678x678") or
                                            g_val.get("558x558") or
                                            g_val.get("507x507") or
                                            g_val.get("372x372") or
                                            g_val.get("url") or
                                            g_val.get("src") or
                                            next((v for v in g_val.values() if isinstance(v, str) and v.startswith("http")), None)
                                        )
                                        if u and u not in item_photos:
                                            item_photos.append(u)
                                    elif isinstance(g, str) and "img.avito.st/image/" in g:
                                        if g not in item_photos:
                                            item_photos.append(g)
                                if item_photos:
                                    chosen_url = item_photos[0]
                                    state_images_map[str(it_id)] = chosen_url

                            seller_inf = it_val.get("sellerInfo", {}) if isinstance(it_val.get("sellerInfo"), dict) else {}
                            s_name = seller_inf.get("name")
                            s_type = seller_inf.get("sellerTypeName")
                            if not s_type:
                                s_type = "Компания" if seller_inf.get("isShop") else "Частное лицо"
                            s_addr = seller_inf.get("logoImageAlt")

                            def _format_ts_to_ru_date_p(ts):
                                try:
                                    ts_fl = float(ts)
                                    if ts_fl > 1e11:
                                        ts_fl /= 1000.0
                                    if 1e9 <= ts_fl <= 2e10:
                                        dt = datetime.fromtimestamp(ts_fl)
                                        now_dt = datetime.now()
                                        ru_m = {
                                            1: "января", 2: "февраля", 3: "марта", 4: "апреля", 5: "мая", 6: "июня",
                                            7: "июля", 8: "августа", 9: "сентября", 10: "октября", 11: "ноября", 12: "декабря"
                                        }
                                        m_name = ru_m.get(dt.month, "")
                                        if dt.year == now_dt.year:
                                            return f"{dt.day} {m_name} в {dt.strftime('%H:%M')}".strip()
                                        else:
                                            return f"{dt.day} {m_name} {dt.year} в {dt.strftime('%H:%M')}".strip()
                                except Exception:
                                    pass
                                return None

                            def _extract_item_date_from_val(val_dict):
                                if not isinstance(val_dict, dict):
                                    return None
                                # 1. Прямые поля unix timestamp
                                for ts_k in ["sortTimeStamp", "sortTimestamp", "timestamp", "publishTime", "createdTime", "createTime"]:
                                    t_val = val_dict.get(ts_k)
                                    if t_val is not None:
                                        ru_d = _format_ts_to_ru_date_p(t_val)
                                        if ru_d:
                                            return ru_d
                                # 2. Прямые строковые / числовые поля
                                for k in ["sortTime", "itemDate", "ivaItemDate", "publishedAt", "createdDate", "time", "displayDate"]:
                                    f_val = val_dict.get(k)
                                    if f_val and isinstance(f_val, (int, float)):
                                        ru_d = _format_ts_to_ru_date_p(f_val)
                                        if ru_d:
                                            return ru_d
                                    if f_val and isinstance(f_val, str) and f_val.strip():
                                        s_f = f_val.strip()
                                        if any(w in s_f.lower() for w in ["сегодня", "вчера", "назад", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек", ":"]):
                                            return s_f
                                # 3. Рекурсивный поиск во вложенных структурах (freeForm, iva и др.)
                                def _search_rec(node, depth=0):
                                    if depth > 6:
                                        return None
                                    if isinstance(node, dict):
                                        t = node.get("text")
                                        if t and isinstance(t, str) and t.strip():
                                            s_t = t.strip()
                                            if any(w in s_t.lower() for w in ["сегодня", "вчера", "назад", "янв", "фев", "мар", "апр", "май", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]):
                                                return s_t
                                        nid = str(node.get("id", "")).lower()
                                        if "sorttime" in nid or "date" in nid:
                                            if t and isinstance(t, str) and t.strip():
                                                return t.strip()
                                        for v in node.values():
                                            res = _search_rec(v, depth + 1)
                                            if res:
                                                return res
                                    elif isinstance(node, list):
                                        for x in node:
                                            res = _search_rec(x, depth + 1)
                                            if res:
                                                return res
                                    return None

                                return _search_rec(val_dict.get("freeForm", [])) or _search_rec(val_dict.get("iva", {}))

                            s_date = _extract_item_date_from_val(it_val)

                            raw_badges = it_val.get("badges", [])
                            badge_text = ""
                            if isinstance(raw_badges, list):
                                for b in raw_badges:
                                    if isinstance(b, dict):
                                        badge_text += " " + str(b.get("title", "")) + " " + str(b.get("text", ""))
                            elif isinstance(raw_badges, dict):
                                badge_text = str(raw_badges.get("title", "")) + " " + str(raw_badges.get("text", ""))

                            state_reserved = bool(
                                it_val.get("isReserved") or
                                it_val.get("reserved") or
                                it_val.get("isClosed") or
                                it_val.get("closed") or
                                it_val.get("status") in ("closed", "reserved", "archived", "blocked", "inactive") or
                                any(w in badge_text.lower() for w in ["резерв", "бронь", "продан", "закрыт", "снят", "забронирован", "зарезервирован", "в резерве"])
                            )

                            comm_channels = it_val.get("communicationChannels") or it_val.get("contactMethods")
                            is_chat = True
                            if isinstance(comm_channels, list):
                                c_lower = [str(x).lower() for x in comm_channels]
                                if c_lower and "messages" not in c_lower and "chat" not in c_lower and "all" not in c_lower:
                                    is_chat = False
                            elif isinstance(comm_channels, str):
                                if comm_channels.lower() in ("calls", "phone") and "message" not in comm_channels.lower():
                                    is_chat = False
                            if it_val.get("isMessengerAvailable") is False or it_val.get("canWriteMessage") is False:
                                is_chat = False

                            # Точное извлечение рейтинга продавца
                            s_rating = None
                            s_r = seller_inf.get("rating") if isinstance(seller_inf, dict) else None
                            if isinstance(s_r, dict):
                                sc = s_r.get("scoreFloat") if s_r.get("scoreFloat") is not None else s_r.get("score")
                                if sc is None:
                                    sc = s_r.get("value")
                                rv = s_r.get("reviewCountText") or s_r.get("text") or s_r.get("reviewsCount") or s_r.get("reviews") or s_r.get("summary")
                                if sc is not None:
                                    try:
                                        sc_fl = float(sc)
                                        sc_str = f"{sc_fl:.1f}".replace(".", ",")
                                    except Exception:
                                        sc_str = str(sc)
                                    rv_str = str(rv).strip() if rv else ""
                                    if rv_str and not rv_str.startswith("("):
                                        rv_str = f"({rv_str})"
                                    s_rating = f"{sc_str} {rv_str}".strip()
                            elif isinstance(s_r, (str, int, float)):
                                s_rating = str(s_r)
                            elif seller_inf.get("score") is not None:
                                s_score = seller_inf.get("score")
                                s_reviews = seller_inf.get("reviewCountText") or seller_inf.get("reviewsCount") or seller_inf.get("summary")
                                s_rating = f"{s_score}" + (f" ({s_reviews})" if s_reviews else "")

                            state_items_map[str(it_id)] = {
                                "photo": chosen_url,
                                "photos": item_photos,
                                "is_reserved": state_reserved,
                                "is_delivery": bool(it_val.get("isDeliveryAvailable")),
                                "is_chat": is_chat,
                                "seller_name": s_name,
                                "seller_type": s_type,
                                "seller_rating": s_rating,
                                "address": s_addr,
                                "item_date": s_date,
                                "description": (it_val.get("description") or it_val.get("shortDescription") or it_val.get("snippet") or it_val.get("itemDescription") or "")
                            }
        except Exception as e:
            logger.debug(f"Не удалось извлечь state_items_map: {e}")

        soup = BeautifulSoup(html, "html.parser")
        items = soup.select('[data-marker="item"]')
        
        if not items:
            # Запасной селектор, если изменились атрибуты
            items = soup.select('article') or soup.select('[class*="item-"]')

        parsed_ads: List[AvitoAd] = []

        for it in items:
            try:
                # Ссылка на объявление
                link_el = it.select_one('a[data-marker="item/link"]') or it.select_one('a[href]')
                href = link_el.get("href", "") if link_el else ""
                if not href:
                    continue

                if href.startswith("/"):
                    full_url = f"https://www.avito.ru{href}"
                elif not href.startswith("http"):
                    full_url = f"https://www.avito.ru/{href}"
                else:
                    full_url = href.replace("https://m.avito.ru", "https://www.avito.ru")

                # ID объявления
                item_id = self._extract_id(it, full_url)
                if not item_id:
                    continue

                state_item = state_items_map.get(str(item_id), {})
                item_text = it.get_text(" ", strip=True).lower()

                # ТРЕБОВАНИЕ: проверка на актуальность (зарезервирован/снят ли товар на Авито)
                is_reserved = bool(
                    state_item.get("is_reserved") or
                    "зарезервирован" in item_text or
                    "забронирован" in item_text or
                    "в резерве" in item_text or
                    "снято с публикации" in item_text or
                    "объявление закрыто" in item_text or
                    "товар продан" in item_text or
                    it.select_one('[data-marker*="reserved"]') or
                    it.select_one('[class*="reserved"]') or
                    it.select_one('[class*="itemReserved"]') or
                    it.select_one('[data-marker*="closed"]') or
                    it.select_one('[data-marker*="item-reserved"]') or
                    it.select_one('[data-marker*="booked"]')
                )

                # Название
                title_el = (
                    it.select_one('[data-marker="titleLabelGrid"]') or
                    it.select_one('[data-marker="item-title"]') or
                    it.select_one('h3') or
                    it.select_one('[itemprop="name"]')
                )
                title = title_el.get_text(strip=True) if title_el else "Без названия"
                t_lower = title.lower()

                # Проверка ключевых слов брони/резерва в заголовке
                if not is_reserved:
                    if (
                        "зарезервирован" in t_lower or
                        "забронирован" in t_lower or
                        "в резерве" in t_lower or
                        t_lower.startswith("бронь") or
                        " бронь" in t_lower or
                        "(бронь)" in t_lower or
                        "[бронь]" in t_lower or
                        t_lower.startswith("резерв") or
                        " резерв" in t_lower or
                        "(резерв)" in t_lower or
                        "[резерв]" in t_lower
                    ):
                        is_reserved = True

                if is_reserved:
                    logger.info(f"Объявление #{item_id} помечено как зарезервированное/неактуальное на Авито.")

                # Цена
                price_el = (
                    it.select_one('[data-marker="priceLabelGrid"]') or
                    it.select_one('meta[itemprop="price"]') or
                    it.select_one('[data-marker="item-price"]')
                )
                if price_el:
                    if price_el.has_attr("content"):
                        price = f"{price_el['content']} ₽"
                    else:
                        price = price_el.get_text(strip=True)
                else:
                    price = "Цена не указана"

                # Фото / Превью видео
                photo = None
                
                # 1. Проверяем стандартные теги img
                img_el = (
                    it.select_one('img[itemprop="image"]') or
                    it.select_one('[data-marker="item-photo"] img') or
                    it.select_one('[data-marker*="photo"] img') or
                    it.select_one('img')
                )
                if img_el:
                    raw_photo = (
                        img_el.get("src") or
                        img_el.get("data-src") or
                        img_el.get("srcset")
                    )
                    if raw_photo:
                        if "," in raw_photo:
                            raw_photo = raw_photo.split(",")[-1].strip().split()[0]
                        if raw_photo.startswith("//"):
                            photo = f"https:{raw_photo}"
                        elif raw_photo.startswith("http"):
                            photo = raw_photo

                # 2. Если на первом месте видео или слайдер с ленивой загрузкой:
                # На Avito картинки и постеры видео лежат в data-marker="slider-image/image-URL"
                if not photo:
                    item_html = str(it)
                    slider_match = re.search(r'data-marker=[\"\']slider-image/(?:image|video)-([^\s\"\']+)[\"\']', item_html)
                    if slider_match:
                        raw = slider_match.group(1)
                        if raw.startswith("//"):
                            photo = f"https:{raw}"
                        elif raw.startswith("http"):
                            photo = raw

                # 3. Дополнительный поиск в атрибутах постера видео или теге video
                if not photo:
                    video_el = it.select_one('video')
                    if video_el:
                        poster = video_el.get("poster")
                        if poster:
                            photo = poster if poster.startswith("http") else f"https:{poster}"

                # 4. Fallback: любой avito.st URL картинки внутри карточки
                if not photo:
                    any_avito_img = re.search(r'https?://\d+\.img\.avito\.st/image/[^\s\"\'\<\>]+', str(it))
                    if any_avito_img:
                        photo = any_avito_img.group(0)

                # 5. Главный надёжный Fallback: извлечение фото из встроенного состояния Avito React (state_images_map)
                if not photo and item_id and item_id in state_images_map:
                    photo = state_images_map[item_id]

                # Извлекаем все доступные фото объявления (строго из state или слайдера текущей карточки)
                all_card_photos = []
                if state_item and state_item.get("photos"):
                    for sp in state_item["photos"]:
                        if sp and sp not in all_card_photos:
                            all_card_photos.append(sp)

                # Только если в state_item фото не было — извлекаем из разметки слайдера текущей карточки
                if not all_card_photos:
                    base_pref = "https://c60.img.avito.st/image/1/"
                    if photo:
                        m_pref = re.match(r'(https?://[a-zA-Z0-9\.\-]*img\.avito\.st/image/\d+/)', photo)
                        if m_pref:
                            base_pref = m_pref.group(1)

                    item_html_str = str(it)
                    for sm in re.findall(r'data-marker=[\"\']slider-image/(?:image|video)-([^\s\"\']+)[\"\']', item_html_str):
                        clean_sm = sm.strip().rstrip('\\/.,;\'\" ')
                        if clean_sm.startswith("http"):
                            u = clean_sm
                        elif clean_sm.startswith("//"):
                            u = f"https:{clean_sm}"
                        else:
                            u = f"{base_pref}{clean_sm}"
                        if u not in all_card_photos:
                            all_card_photos.append(u)

                    if not all_card_photos:
                        img_container = it.select_one('[data-marker="item/image"], [class*="photo-slider"], [class*="gallery"]') or it
                        for img_node in img_container.select('img'):
                            raw_s = img_node.get("src") or img_node.get("data-src") or img_node.get("srcset")
                            if raw_s:
                                if "," in raw_s:
                                    raw_s = raw_s.split(",")[-1].strip().split()[0]
                                clean_raw = raw_s.strip().rstrip('\\/.,;\'\" ').replace('\\/', '/')
                                full_s = f"https:{clean_raw}" if clean_raw.startswith("//") else (clean_raw if clean_raw.startswith("http") else "")
                                if full_s and "img.avito.st/image/" in full_s and not any(k in full_s for k in ["avatar", "badge", "icon", "logo"]):
                                    if full_s not in all_card_photos:
                                        all_card_photos.append(full_s)

                all_card_photos = deduplicate_avito_photos(all_card_photos)
                if photo and photo not in all_card_photos:
                    m_ph = re.search(r'img\.avito\.st/image/\d+/(?:[0-9]+x[0-9]+/)?(?:1\.)?([a-zA-Z0-9_\-]{6,8})', photo)
                    ph_h = m_ph.group(1)[:7].lower() if m_ph else None
                    if not ph_h or not any(ph_h in p.lower() for p in all_card_photos):
                        all_card_photos.insert(0, photo)
                elif not photo and all_card_photos:
                    photo = all_card_photos[0]

                # Продавец
                seller_el = it.select_one('[data-marker="sellerAndRatingSellerLabel"]')
                seller = seller_el.get_text(strip=True) if seller_el else None

                # Адрес/Город
                address_el = (
                    it.select_one('[data-marker="addressLabel"]') or
                    it.select_one('[data-marker*="address"]') or
                    it.select_one('[data-marker*="location"]') or
                    it.select_one('[data-marker*="geo"]') or
                    it.select_one('[class*="geo-"]') or
                    it.select_one('[class*="address-"]')
                )
                address = address_el.get_text(strip=True) if address_el else None

                # Fallback: если Avito не отрендерил город в мобильной карточке, извлекаем его из ссылки
                if not address and full_url:
                    parsed_path = urlparse(full_url).path.strip("/").split("/")
                    # Первый сегмент пути на Avito почти всегда транслитерированный город (moskva, sankt-peterburg, habarovsk)
                    if parsed_path and parsed_path[0] not in ("all", "rossiya", "items"):
                        raw_city = parsed_path[0].replace("-", " ").replace("_", " ")
                        # Переводим популярные или делаем красивый Capitalize
                        city_map = {
                            "moskva": "Москва",
                            "sankt peterburg": "Санкт-Петербург",
                            "novosibirsk": "Новосибирск",
                            "ekaterinburg": "Екатеринбург",
                            "kazan": "Казань",
                            "nizhniy novgorod": "Нижний Новгород",
                            "chelyabinsk": "Челябинск",
                            "samara": "Самара",
                            "omsk": "Омск",
                            "rostov na donu": "Ростов-на-Дону",
                            "ufa": "Уфа",
                            "krasnoyarsk": "Красноярск",
                            "voronezh": "Воронеж",
                            "perm": "Пермь",
                            "volgograd": "Волгоград",
                            "krasnodar": "Краснодар",
                            "saratov": "Саратов",
                            "tyumen": "Тюмень",
                            "tolyatti": "Тольятти",
                            "izhevsk": "Ижевск",
                            "barnaul": "Барнаул",
                            "ulyanovsk": "Ульяновск",
                            "irkutsk": "Иркутск",
                            "vladivostok": "Владивосток",
                            "yaroslavl": "Ярославль",
                            "habarovsk": "Хабаровск",
                            "mahachkala": "Махачкала",
                            "orenburg": "Оренбург",
                            "tomsk": "Томск",
                            "kemerovo": "Кемерово",
                            "novokuznetsk": "Новокузнецк",
                            "ryazan": "Рязань",
                            "astrahan": "Астрахань",
                            "penza": "Пенза",
                            "lipetsk": "Липецк",
                            "tula": "Тула",
                            "kirov": "Киров",
                            "cheboksary": "Чебоксары",
                            "kaliningrad": "Калининград",
                            "kursk": "Курск",
                            "ulan ude": "Улан-Удэ",
                            "stavropol": "Ставрополь",
                            "balashiha": "Балашиха",
                            "magnitogorsk": "Магнитогорск",
                            "tver": "Тверь",
                            "sevastopol": "Севастополь",
                            "ivanovo": "Иваново",
                            "bryansk": "Брянск",
                            "sochi": "Сочи",
                            "belgorod": "Белгород",
                            "surgut": "Сургут",
                            "vladimir": "Владимир",
                            "chita": "Чита",
                            "arhangelsk": "Архангельск",
                            "kaluga": "Калуга",
                            "smolensk": "Смоленск",
                            "volzhskiy": "Волжский",
                            "kurgan": "Курган",
                            "cherepovets": "Череповец",
                            "orel": "Орёл",
                            "saransk": "Саранск",
                            "vologda": "Вологда",
                            "yakutsk": "Якутск",
                            "vladikavkaz": "Владикавказ",
                            "podolsk": "Подольск",
                            "murmansk": "Мурманск",
                            "tambov": "Тамбов",
                            "petrozavodsk": "Петрозаводск",
                            "sterlitamak": "Стерлитамак",
                            "kostroma": "Кострома",
                            "novorossiysk": "Новороссийск",
                            "kurganinsk": "Курганинск",
                            "armavir": "Армавир",
                            "anapa": "Анапа",
                            "gelendzhik": "Геленджик",
                            "eysk": "Ейск",
                            "kropotkin": "Кропоткин",
                            "slavyansk na kubani": "Славянск-на-Кубани",
                            "tuapse": "Туапсе",
                            "labinsk": "Лабинск",
                            "tihoretsk": "Тихорецк",
                            "krymsk": "Крымск",
                            "timashevsk": "Тимашёвск",
                            "belorechensk": "Белореченск",
                            "ust labinsk": "Усть-Лабинск",
                            "apsheronsk": "Апшеронск",
                            "goryachiy klyuch": "Горячий Ключ",
                            "korenovsk": "Кореновск",
                            "temryuk": "Темрюк",
                            "gulkevichi": "Гулькевичи",
                            "novokubansk": "Новокубанск",
                            "abinsk": "Абинск",
                            "primorsko ahtarsk": "Приморско-Ахтарск",
                            "hadyzhensk": "Хадыженск"
                        }
                        address = city_map.get(raw_city, raw_city.title())

                # Авито Доставка
                if "is_delivery" in state_item:
                    has_delivery = bool(state_item["is_delivery"])
                else:
                    has_delivery = bool(
                        it.select_one('[data-marker*="delivery"]') or
                        "доставк" in item_text
                    )

                # Чат / сообщения
                if "is_chat" in state_item:
                    has_chat = bool(state_item["is_chat"])
                else:
                    has_chat = not ("только звонки" in item_text or "сообщения отключены" in item_text)

                # Тип продавца
                seller_type = state_item.get("seller_type")
                if not seller_type:
                    is_company = bool(
                        "компания" in item_text or
                        "магазин" in item_text or
                        "скупка" in item_text or
                        it.select_one('[data-marker*="company"]')
                    )
                    seller_type = "Компания" if is_company else "Частное лицо"
                else:
                    is_company = (seller_type == "Компания")

                if (not seller or seller == "Продавец") and state_item.get("seller_name"):
                    seller = state_item["seller_name"]

                if (not address or address == "Не указан") and state_item.get("address"):
                    address = state_item["address"]

                item_date = state_item.get("item_date")
                if not item_date:
                    date_el = (
                        it.select_one('[data-marker="sortTimeGrid"]') or
                        it.select_one('[data-marker*="sortTime"]') or
                        it.select_one('[data-marker*="sort-timestamp"]') or
                        it.select_one('[data-marker*="item-date"]') or
                        it.select_one('[data-marker*="date"]') or
                        it.select_one('[class*="sortTime"]') or
                        it.select_one('[class*="item-date"]') or
                        it.select_one('[class*="date"]')
                    )
                    if date_el:
                        raw_date = date_el.get_text(" ", strip=True)
                        if raw_date and not any(w in raw_date.lower() for w in ['доставка', '₽', 'купить', 'в избранное', 'отзыв']):
                            item_date = raw_date

                if not item_date:
                    card_text = it.get_text(" ", strip=True)
                    m_ru = re.search(r'(\d{1,2}\s+(?:январ[яе]|феврал[яе]|март[ае]|апрел[яе]|ма[яе]|июн[яе]|июл[яе]|август[ае]|сентябр[яе]|октябр[яе]|ноябр[яе]|декабр[яе])(?:\s+\d{4})?(?:\s+в\s+\d{1,2}:\d{2})?)', card_text, re.IGNORECASE)
                    if m_ru:
                        item_date = m_ru.group(1).strip()
                    else:
                        m_rel = re.search(r'((?:сегодня|вчера)(?:\s+в\s+\d{1,2}:\d{2})?|\d+\s*(?:мин[а-я]*|час[а-я]*|дн[а-я]*|недел[а-я]*)\s+назад|только что)', card_text, re.IGNORECASE)
                        if m_rel:
                            item_date = m_rel.group(1).strip()

                seller_rating = state_item.get("seller_rating")
                if not seller_rating:
                    rating_el = (
                        it.select_one('[data-marker*="sellerNameAndRatingSpreadContainer/rightChildren"]') or
                        it.select_one('[data-marker*="sellerNameAndRatingSpreadContainer"]') or
                        it.select_one('[data-marker="seller-rating/score"]') or
                        it.select_one('[data-marker*="seller-rating"]') or
                        it.select_one('[data-marker*="rating"]') or
                        it.select_one('[class*="rating-"]') or
                        it.select_one('[class*="seller-rating"]')
                    )
                    if rating_el:
                        sc_text = rating_el.get_text(strip=True)
                        rev_el = it.select_one('[data-marker="seller-rating/summary"]') or it.select_one('[data-marker*="reviews"]')
                        rev_text = rev_el.get_text(strip=True) if rev_el else ""
                        seller_rating = f"{sc_text} {rev_text}".strip()

                # Извлечение описания (сниппет карточки при наличии)
                desc_el = (
                    it.select_one('[data-marker="item-description"]') or
                    it.select_one('[class*="iva-item-description"]') or
                    it.select_one('[class*="description-"]') or
                    it.select_one('[itemprop="description"]')
                )
                card_description = desc_el.get_text(strip=True) if desc_el else (state_item.get("description") if state_item else None)

                parsed_ads.append(AvitoAd(
                    id=item_id,
                    title=title,
                    price=price,
                    url=full_url,
                    photo=photo,
                    seller=seller,
                    address=address,
                    has_delivery=has_delivery,
                    has_chat=has_chat,
                    is_company=is_company,
                    seller_type=seller_type,
                    is_reserved=is_reserved,
                    item_date=item_date,
                    photos=deduplicate_avito_photos(all_card_photos or state_item.get("photos") or ([photo] if photo else [])),
                    seller_rating=seller_rating,
                    description=card_description
                ))
            except Exception as e:
                logger.debug(f"Ошибка парсинга отдельного объявления: {e}")
                continue

        logger.info(f"Успешно распарсено {len(parsed_ads)} объявлений.")
        return parsed_ads
