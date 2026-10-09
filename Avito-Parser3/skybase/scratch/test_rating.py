from bs4 import BeautifulSoup
import json
import re

with open(r'C:\ins\Avito-Parser2\skybase\scratch\search_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

# 1. Check window.__initialData__
init_idx = html.find("window.__initialData__")
if init_idx != -1:
    eq_idx = html.find("=", init_idx)
    start_pos = -1
    for pos in range(eq_idx + 1, min(eq_idx + 50, len(html))):
        if not html[pos].isspace():
            start_pos = pos
            break
    if start_pos != -1:
        decoder = json.JSONDecoder()
        decoded_obj, _ = decoder.raw_decode(html[start_pos:])
        data = json.loads(decoded_obj) if isinstance(decoded_obj, str) else decoded_obj
        all_items = data.get("search", {}).get("allItems", {})
        print(f"Total items in initialData: {len(all_items)}")
        for it_id, it_info in list(all_items.items())[:5]:
            it_val = it_info.get("value", {}) if isinstance(it_info, dict) else {}
            print(f"\n--- Item {it_id} in JSON ---")
            print("sellerInfo keys:", list(it_val.get("sellerInfo", {}).keys()) if isinstance(it_val.get("sellerInfo"), dict) else it_val.get("sellerInfo"))
            if isinstance(it_val.get("sellerInfo"), dict):
                print("sellerInfo:", it_val.get("sellerInfo"))
            # search any key with rating in it_val
            for k, v in it_val.items():
                if "rating" in k.lower() or "score" in k.lower() or "seller" in k.lower():
                    print(f"  key {k}: {v}")

soup = BeautifulSoup(html, 'html.parser')
items = soup.select('[data-marker="item"]')
print(f"\nTotal items in HTML: {len(items)}")
for idx, it in enumerate(items[:5]):
    item_id = it.get('data-item-id')
    print(f"\n--- Item {item_id} in HTML ---")
    rt = it.select('[data-marker*="rating"], [data-marker*="score"], [class*="rating"], [class*="score"]')
    for t in rt:
        print("  Tag:", t.name, t.get("data-marker"), t.get("class"), "Text:", t.get_text(strip=True))
