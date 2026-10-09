import sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

with open(r'D:\ins\skybase\Avito-Parser3\skybase\scratch\search_page.html', 'r', encoding='utf-8') as f:
    soup = BeautifulSoup(f.read(), 'html.parser')

items = soup.select('[data-marker="item"]')
print("Total items found:", len(items))
if items:
    card = items[0]
    print("Markers:")
    for el in card.find_all(attrs={"data-marker": True}):
        print(" ", el.get("data-marker"), "->", repr(el.get_text(strip=True)[:60]))
    print("\nDesc/iva classes:")
    for el in card.find_all(attrs={"class": True}):
        cls = " ".join(el.get("class"))
        if "desc" in cls.lower() or "iva-item" in cls.lower() or "text" in cls.lower():
            print(" ", cls, "->", repr(el.get_text(strip=True)[:60]))
