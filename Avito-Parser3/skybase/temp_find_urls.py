import re
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
            if r.status_code == 200:
                urls = re.findall(r'https?://[a-zA-Z0-9_\-\.]*img\.avito\.st/image/[^\s"\'<>\)]+', r.text)
                print(f"Found {len(urls)} img URLs:")
                for u in sorted(set(urls)):
                    print("  ", u)
                with open("avito_item_8356331734.html", "w", encoding="utf-8") as f:
                    f.write(r.text)
                break
    except Exception as e:
        print("err:", e)
