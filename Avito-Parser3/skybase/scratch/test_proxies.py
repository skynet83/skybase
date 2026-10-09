import sys
import time
from curl_cffi.requests import Session

sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\ins\skybase\Avito-Parser3\skybase\avito_bot\proxies.txt', 'r', encoding='utf-8-sig') as f:
    lines = [l.strip() for l in f if l.strip() and not l.startswith('#')]

headers = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
}

print(f"Testing {len(lines)} proxies...")
working = []
for p in lines:
    t0 = time.perf_counter()
    try:
        with Session(impersonate="safari15_5", proxy=p, timeout=4, verify=False) as s:
            r = s.get("https://m.avito.ru", headers=headers)
            elapsed = round((time.perf_counter() - t0) * 1000)
            if r.status_code == 200 and "доступ ограничен" not in r.text.lower():
                print(f"[OK] {p} ({elapsed}ms)")
                working.append(p)
            else:
                print(f"[FAIL] {p} status={r.status_code}")
    except Exception as e:
        print(f"[ERR] {p}: {type(e).__name__}")

print(f"\nTotal working: {len(working)} / {len(lines)}")
