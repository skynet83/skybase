import json
import re

html = open("avito_item_8356331734.html", encoding="utf-8").read()

m_init = re.search(r'window\.__initialData__\s*=\s*(".*?"|{.*?});', html, re.DOTALL)
raw_json = m_init.group(1)

# Proper decoding:
if raw_json.startswith('"'):
    decoded = json.loads(raw_json)
    try:
        data = json.loads(decoded)
    except Exception:
        import urllib.parse
        data = json.loads(urllib.parse.unquote(decoded))
else:
    data = json.loads(raw_json)

def _find_gallery_rec(obj, depth=0):
    if depth > 10: return []
    if isinstance(obj, dict):
        for k in ["gallery", "galleryItems", "images", "photos"]:
            val = obj.get(k)
            if isinstance(val, list) and val:
                return val
        for v in obj.values():
            res = _find_gallery_rec(v, depth + 1)
            if res: return res
    elif isinstance(obj, list):
        for it in obj:
            res = _find_gallery_rec(it, depth + 1)
            if res: return res
    return []

gal_items = _find_gallery_rec(data)
print("Found gal_items:", len(gal_items))
photos = []
for g in gal_items:
    if isinstance(g, dict):
        u = g.get("1280x960") or g.get("1024x768") or g.get("864x648") or g.get("678x678") or g.get("url") or g.get("src") or next((v for v in g.values() if isinstance(v, str) and v.startswith("http")), None)
        if u: photos.append(u)
    elif isinstance(g, str):
        photos.append(g)

print("Extracted photos count:", len(photos))
for idx, p in enumerate(photos):
    print(f"  [{idx+1}] {p}")
