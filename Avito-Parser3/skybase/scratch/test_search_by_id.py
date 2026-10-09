from curl_cffi import requests
from bs4 import BeautifulSoup
import re, json

item_ids = ["8511297408", "1931251647", "7745078670"]
for i_id in item_ids:
    url = f"https://www.avito.ru/rossiya?q={i_id}"
    try:
        r = requests.get(url, impersonate="chrome124", timeout=10)
        print(f"\nSearch for ID {i_id} -> Status: {r.status_code}, Len: {len(r.text)}")
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            cards = soup.select('[data-marker="item"]')
            print(f"  Found {len(cards)} cards")
            m = re.search(r'__initialData__\s*=\s*"((?:\\.|[^"\\])*)"', r.text)
            if m:
                unquoted = json.loads('"' + m.group(1) + '"')
                data = json.loads(unquoted)
                all_items = data.get('search', {}).get('allItems') or {}
                print(f"  allItems count: {len(all_items)}")
                for k, v in all_items.items():
                    val = v.get('value', {})
                    gi = val.get('galleryItems') or []
                    print(f"    Item {k}: {val.get('title')} -> {len(gi)} photos!")
    except Exception as e:
        print(f"  Error for {i_id}: {e}")
