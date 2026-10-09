import sys
import os
import asyncio
sys.path.insert(0, r"C:\ins\Avito-Parser\skybase\lib")
sys.path.insert(0, r"C:\ins\Avito-Parser\skybase\avito_bot")
from parser import AvitoParser
from filters import is_relevant_ad

async def main():
    p = AvitoParser()
    url = 'https://www.avito.ru/rossiya?s=104&q=RX590'
    name = 'RX590'
    print("Fetching RX590 search...")
    ads = await p.fetch_ads(url)
    print("Parsed ads:", len(ads))
    for ad in ads:
        rel = is_relevant_ad(ad.title, url, name, ad.price)
        print(f"[{'OK' if rel else 'DROP'}] {ad.title} | {ad.price}")

asyncio.run(main())
