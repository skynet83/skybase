import asyncio
import sys

sys.path.insert(0, 'D:/ins/skybase/Avito-Parser3/skybase/avito_bot')
from parser import AvitoParser

async def test():
    p = AvitoParser()
    url = "https://www.avito.ru/all/tovary_dlya_kompyutera/komplektuyuschie/videokarty-ASgBAgICAkTGB~pm7gmmZw?pmin=500&pmax=2000&q=rx+590&s=104"
    ads = await p.fetch_ads(url, allow_direct=True, max_pages=5)
    print(f"Total ads returned: {len(ads)}")
    for i, a in enumerate(ads[:5]):
        print(f"  {i+1}: {a.id} | {a.title} | {a.price}")

asyncio.run(test())
