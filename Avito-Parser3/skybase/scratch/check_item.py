import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\ins\skybase\Avito-Parser3\skybase\scratch\item_page_result.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

print("Title:", repr(soup.title.string if soup.title else ''))
desc_el = soup.select_one('[data-marker="item-view/item-description"], [data-marker="item-description/text"], [itemprop="description"], [class*="description-text"], [class*="style-item-description"]')
print("desc_el found:", bool(desc_el))
if desc_el:
    print("desc text:", repr(desc_el.get_text(strip=True)[:100]))

meta = soup.select_one('meta[property="og:description"], meta[name="description"]')
print("meta found:", bool(meta))
if meta:
    print("meta content:", repr(meta.get("content", "")[:100]))
