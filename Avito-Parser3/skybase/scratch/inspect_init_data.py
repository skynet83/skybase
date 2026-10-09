import re
import json
import urllib.parse

with open(r'D:\ins\skybase\Avito-Parser3\skybase\scratch\search_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

m = re.search(r'window\.__initialData__\s*=\s*(".*?"|{.*?});', html, re.DOTALL)
if not m:
    print("No initialData found")
else:
    raw = m.group(1)
    if raw.startswith('"'):
        decoded = json.loads(raw)
        data = json.loads(urllib.parse.unquote(decoded) if "%" in decoded else decoded)
    else:
        data = json.loads(raw)
    print("initialData keys:", list(data.keys())[:10])
    
    # Search for an item in data
    def search_items(obj, depth=0):
        if depth > 8: return None
        if isinstance(obj, dict):
            if "items" in obj and isinstance(obj["items"], list) and len(obj["items"]) > 0:
                first = obj["items"][0]
                if isinstance(first, dict) and ("id" in first or "title" in first):
                    return obj["items"]
            for v in obj.values():
                res = search_items(v, depth + 1)
                if res: return res
        elif isinstance(obj, list):
            for it in obj:
                res = search_items(it, depth + 1)
                if res: return res
        return None

    items = search_items(data)
    if items:
        print(f"Found {len(items)} items in initialData!")
        print("Sample item keys:", list(items[0].keys()))
        for k in ["description", "shortDescription", "snippet", "body", "title", "id"]:
            if k in items[0]:
                print(f"  {k}:", repr(items[0][k])[:80])
    else:
        print("Items list not found in initialData")
