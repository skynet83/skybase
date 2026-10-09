import re
import json
from curl_cffi.requests import Session

proxies = [
    "http://85.8.47.207:7080",
    "http://13.209.65.136:39209",
    "socks5://83.147.217.103:1080",
    "socks5://37.18.73.60:5566",
    "socks5://45.74.31.40:8104"
]

url = "https://www.avito.ru/nizhniy_novgorod/tovary_dlya_kompyutera/msi_rx570_gaming_x_4g_-_defektnaya_7949955563"

for px in proxies:
    print(f"Trying {px}...")
    try:
        s = Session(impersonate="safari15_5", proxy=px)
        r = s.get(url, timeout=12)
        print(f"  Status: {r.status_code}, len: {len(r.text)}")
        if r.status_code == 200:
            if "доступ ограничен" in r.text.lower():
                print("  Blocked by captcha/429")
                continue
            print("  SUCCESS!")
            # Extract description
            m_desc = re.search(r'<div[^>]*itemprop=[\"\']description[\"\'][^>]*>(.*?)</div>', r.text, re.DOTALL)
            if not m_desc:
                m_desc = re.search(r'data-marker=[\"\']item-view/item-description[\"\'][^>]*>(.*?)</div>', r.text, re.DOTALL)
            if m_desc:
                # strip html tags
                clean_text = re.sub(r'<[^>]+>', ' ', m_desc.group(1)).strip()
                print("  Found Description:", clean_text[:200])
            
            # Check photos in __initialData__
            m_init = re.search(r'window\.__initialData__\s*=\s*(\{.*?\});\s*</script>', r.text)
            if m_init:
                print("  Found __initialData__!")
                try:
                    data = json.loads(m_init.group(1))
                    # search for item
                    for k, v in data.items():
                        if isinstance(v, dict) and "gallery" in v:
                            print("  Found gallery in key:", k)
                            print("  Gallery:", v["gallery"])
                except Exception as ex:
                    print("  JSON parse error:", ex)
            break
    except Exception as e:
        print(f"  Error: {e}")
