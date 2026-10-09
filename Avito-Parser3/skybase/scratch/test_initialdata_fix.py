import re, json
from bs4 import BeautifulSoup

with open(r'E:\ins\skybase\Avito-Parser3\skybase\scratch\search_page.html', 'r', encoding='utf-8', errors='ignore') as f:
    html = f.read()

state_items_map = {}
init_idx = html.find("__initialData__")
if init_idx != -1:
    eq_idx = html.find("=", init_idx)
    start_pos = -1
    for pos in range(eq_idx + 1, min(eq_idx + 50, len(html))):
        if not html[pos].isspace():
            start_pos = pos
            break
    if start_pos != -1:
        try:
            decoder = json.JSONDecoder()
            decoded_obj, _ = decoder.raw_decode(html[start_pos:])
            if isinstance(decoded_obj, str):
                data = json.loads(decoded_obj)
            else:
                data = decoded_obj
            all_items = {}
            s_items = data.get("search", {}).get("allItems")
            if isinstance(s_items, dict):
                all_items.update(s_items)
            cat_items = data.get("catalog", {}).get("items") or data.get("items")
            if isinstance(cat_items, list):
                for ci in cat_items:
                    if isinstance(ci, dict) and ci.get("id"):
                        all_items[str(ci["id"])] = {"value": ci}
            elif isinstance(cat_items, dict):
                all_items.update(cat_items)
            
            for it_id, it_info in all_items.items():
                it_val = it_info.get("value", {}) if isinstance(it_info, dict) else {}
                gallery = it_val.get("galleryItems") or it_val.get("gallery") or it_val.get("images") or it_val.get("photos") or []
                item_photos = []
                for g in gallery:
                    g_val = g.get("value", {}) if isinstance(g, dict) else (g if isinstance(g, dict) else {})
                    if isinstance(g_val, dict) and g_val:
                        u = (
                            g_val.get("1280x960") or g_val.get("1024x768") or g_val.get("864x648") or
                            g_val.get("678x678") or g_val.get("558x558") or g_val.get("507x507") or
                            g_val.get("372x372") or g_val.get("url") or g_val.get("src") or
                            next((v for v in g_val.values() if isinstance(v, str) and v.startswith("http")), None)
                        )
                        if u and u not in item_photos:
                            item_photos.append(u)
                    elif isinstance(g, str) and "img.avito.st/image/" in g:
                        if g not in item_photos:
                            item_photos.append(g)
                state_items_map[str(it_id)] = {
                    "title": it_val.get("title"),
                    "photos": item_photos
                }
            print(f"SUCCESS! Extracted {len(state_items_map)} items from __initialData__!")
            for it_id, info in list(state_items_map.items())[:5]:
                print(f"  {it_id}: {info['title']} -> {len(info['photos'])} photos")
        except Exception as e:
            print("Error parsing:", e)
