import asyncio
import sys
import os
import json
import random

sys.path.insert(0, 'lib')
sys.path.insert(0, 'avito_bot')
from curl_cffi.requests import AsyncSession

RU_SOURCES = [
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/RU/data.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/BY/data.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/KZ/data.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=all&timeout=8000&country=ru&ssl=all&anonymity=all",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=all&timeout=8000&country=by,kz&ssl=all&anonymity=all",
]

MONOSANS_JSON = "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies.json"

async def test_gather():
    priority_candidates = set()
    general_candidates = set()

    async with AsyncSession() as s:
        # 1. Fetch Monosans JSON
        try:
            r = await s.get(MONOSANS_JSON, timeout=6)
            if r.status_code == 200:
                data = json.loads(r.text)
                for item in data:
                    proto = item.get("protocol", "http")
                    h = item.get("host")
                    p = item.get("port")
                    iso = item.get("geolocation", {}).get("country", {}).get("iso_code", "")
                    if h and p:
                        addr = f"{proto}://{h}:{p}"
                        if iso in ("RU", "BY", "KZ"):
                            priority_candidates.add(addr)
                        else:
                            general_candidates.add(addr)
                print(f"Monosans JSON: {len(priority_candidates)} RU/CIS, {len(general_candidates)} others")
        except Exception as e:
            print("Monosans error:", e)

        # 2. Fetch RU Sources
        for src in RU_SOURCES:
            try:
                r = await s.get(src, timeout=6)
                if r.status_code == 200:
                    lines = [l.strip() for l in r.text.splitlines() if ":" in l and l.strip()]
                    is_socks = "socks5" in src or "socks" in src
                    for l in lines:
                        if not l.startswith("http") and not l.startswith("socks"):
                            l = f"socks5://{l}" if is_socks else f"http://{l}"
                        priority_candidates.add(l)
                    print(f"Source {src[:50]}... added {len(lines)}")
            except Exception as e:
                print(f"Source {src[:50]} error: {e}")

    print(f"Total Priority Candidates: {len(priority_candidates)}")

    # Stage 1: TCP Ping
    async def tcp_ping(host: str, port: int, timeout: float = 1.5) -> bool:
        try:
            conn = asyncio.open_connection(host, port)
            reader, writer = await asyncio.wait_for(conn, timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return True
        except Exception:
            return False

    tcp_sem = asyncio.Semaphore(120)
    alive_tcp = []

    async def _tcp_worker(p: str):
        clean_p = p.split("://", 1)[1] if "://" in p else p
        try:
            host, port_str = clean_p.split(":", 1)
            port = int(port_str)
        except Exception:
            return
        async with tcp_sem:
            if await tcp_ping(host, port, timeout=1.5):
                alive_tcp.append(p)

    cand_list = list(priority_candidates)
    random.shuffle(cand_list)
    await asyncio.gather(*[_tcp_worker(p) for p in cand_list])
    print(f"Stage 1 TCP ping: {len(alive_tcp)} alive out of {len(cand_list)}")

    # Stage 2: Avito verification
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    avito_sem = asyncio.Semaphore(40)
    working = []

    async def _check_avito(p: str):
        async with avito_sem:
            try:
                async with AsyncSession(impersonate="safari15_5", proxy=p) as s:
                    resp = await s.get("https://m.avito.ru", headers=headers, timeout=6)
                    code = resp.status_code
                    if code in (200, 301, 302, 403, 429):
                        if code == 200:
                            lower_t = resp.text.lower()
                            if "доступ ограничен" in lower_t or "firewall" in lower_t:
                                return
                        working.append((p, code))
                        print(f"  [+] WORKING PROXY: {p} (HTTP {code})")
            except Exception:
                pass

    await asyncio.gather(*[_check_avito(p) for p in alive_tcp])
    print(f"\n==========================================")
    print(f"STAGE 2 AVITO RESULT: {len(working)} WORKING PROXIES FOUND!")
    print(f"==========================================")

asyncio.run(test_gather())
