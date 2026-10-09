import asyncio
import sys
import urllib.request
import json

sys.path.insert(0, 'lib')
from curl_cffi.requests import AsyncSession

data = json.loads(urllib.request.urlopen('https://raw.githubusercontent.com/monosans/proxy-list/main/proxies.json').read())
ru = [f"{x['protocol']}://{x['host']}:{x['port']}" for x in data if x.get('geolocation',{}).get('country',{}).get('iso_code')=='RU']

async def check(p):
    try:
        async with AsyncSession(impersonate='chrome120', proxy=p) as s:
            r = await s.get('https://m.avito.ru', timeout=7)
            print(f'SUCCESS! {p} -> {r.status_code}, len={len(r.text)}')
            return p
    except Exception as e:
        return None

async def main():
    print(f'Testing {len(ru)} RU proxies against Avito...')
    tasks = [check(p) for p in ru]
    results = await asyncio.gather(*tasks)
    alive = [p for p in results if p]
    print(f'Total alive with Avito: {len(alive)}')

asyncio.run(main())
