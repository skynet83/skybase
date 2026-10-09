import sys
from curl_cffi.requests import Session
from bs4 import BeautifulSoup
import re
import json

sys.stdout.reconfigure(encoding='utf-8')

p = 'http://31.133.32.102:3128'
headers = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
}
url = 'https://m.avito.ru/kanevskaya/tovary_dlya_kompyutera/msi_rx_570_8447829543'

with Session(impersonate='safari15_5', proxy=p, timeout=8, verify=False) as s:
    r = s.get(url, headers=headers)
    print('status:', r.status_code, 'len:', len(r.text))
    if 'доступ ограничен' in r.text.lower():
        print('WAF block!')
    else:
        soup = BeautifulSoup(r.text, 'html.parser')
        print('Title:', soup.title.string if soup.title else '')
        desc_el = soup.select_one('[data-marker="item-view/item-description"], [data-marker="item-description/text"], [itemprop="description"], [class*="description-text"], [class*="style-item-description"]')
        print('desc_el:', desc_el.get_text(strip=True)[:100] if desc_el else 'None')
        meta = soup.select_one('meta[property="og:description"], meta[name="description"]')
        print('meta:', meta.get('content')[:100] if meta else 'None')
        
        # Check __initialData__
        m = re.search(r'window\.__initialData__\s*=\s*(".*?"|{.*?});', r.text, re.DOTALL)
        print('initialData found:', bool(m))
