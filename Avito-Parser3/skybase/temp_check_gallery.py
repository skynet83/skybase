import json
import re
import urllib.parse
from curl_cffi.requests import Session
from avito_api_helper import get_live_proxies_list

proxies = get_live_proxies_list(5)
for px in proxies:
    try:
        clean_px = "socks5h://" + px[9:] if px.startswith("socks5://") else px
        with Session(impersonate="safari15_5", proxy=clean_px, timeout=6, verify=False) as s:
            r = s.get("https://m.avito.ru/novoaltaysk/tovary_dlya_kompyutera/videokarta_rx580_4gb_sapphire_nitro_8356331734", headers={
                "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1",
                "Accept-Language": "ru-RU,ru;q=0.9"
            })
            if r.status_code != 200:
                continue
            m = re.search(r'window\.__initialData__\s*=\s*(".*?"|{.*?});', r.text, re.DOTALL)
            if not m:
                continue
            raw = m.group(1)
            decoded = json.loads(raw)
            data = json.loads(urllib.parse.unquote(decoded) if "%" in decoded else decoded) if raw.startswith('"') else json.loads(raw)
            
            # Print keys that contain gallery/images/photos
            def walk(obj, p=""):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k in ["gallery", "galleryItems", "images", "photos"]:
                            print(f"KEY: {p}.{k} -> {type(v)} (len {len(v) if isinstance(v, list) else 0})")
                            if isinstance(v, list):
                                for idx, it in enumerate(v):
                                    print(f"  item[{idx}] = {it}")
                        walk(v, f"{p}.{k}")
                elif isinstance(obj, list):
                    for i, it in enumerate(obj):
                        walk(it, f"{p}[{i}]")
            walk(data)
            break
    except Exception as e:
        print("err:", e)
