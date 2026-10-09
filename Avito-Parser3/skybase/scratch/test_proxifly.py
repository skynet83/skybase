import asyncio
import sys
import urllib.request

sys.path.insert(0, 'lib')
from curl_cffi.requests import AsyncSession

u = 'https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/countries/RU/data.txt'
req = urllib.request.Request(u, headers={'User-Agent': 'Mozilla/5.0'})
raw = urllib.request.urlopen(req, timeout=5).read().decode('utf-8', errors='ignore')
lines = [l.strip() for l in raw.splitlines() if ':' in l and l.strip()]

headers = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}

async def check(p):
    clean = p
    if not clean.startswith('http') and not clean.startswith('socks'):
        clean = f'http://{clean}'
    try:
        async with AsyncSession(impersonate='safari15_5', proxy=clean) as s:
            r = await s.get('https://m.avito.ru', headers=headers, timeout=6)
            if r.status_code in (200, 301, 302, 403, 429):
                print(f'[OK] {clean} -> HTTP {r.status_code}')
                return clean
    except Exception:
        pass
    return None

async def main():
    print(f'Testing 100 RU proxies from proxifly against Avito...')
    tasks = [check(p) for p in lines[:100]]
    results = await asyncio.gather(*tasks)
    alive = [p for p in results if p]
    print(f'Done! Found {len(alive)} working proxies for Avito out of 100.')

asyncio.run(main())
