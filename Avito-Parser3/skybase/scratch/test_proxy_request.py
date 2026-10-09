from curl_cffi.requests import Session
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('D:/ins/skybase/Avito-Parser3/skybase/avito_bot/proxies.txt', 'r', encoding='utf-8') as f:
    proxies = [l.strip() for l in f if l.strip() and not l.startswith('#')]

print("Proxies to test:", proxies)
for px in proxies:
    try:
        with Session(impersonate="safari15_5", proxy=px, timeout=6) as s:
            r = s.get("https://m.avito.ru/all?q=rx580")
            print(f"Proxy {px} -> status: {r.status_code}, len: {len(r.text)}")
            lower = r.text.lower()
            if "доступ ограничен" in lower or "firewall" in lower:
                print("  BLOCKED ON PROXY")
            else:
                print("  SUCCESS!")
    except Exception as e:
        print(f"Proxy {px} -> failed: {e}")
