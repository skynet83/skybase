import os
from curl_cffi import requests

url = "https://www.avito.ru/rostov-na-donu/tovary_dlya_kompyutera/rx_570_8gb_8511297408"
proxies_file = r"E:\ins\skybase\Avito-Parser3\skybase\avito_bot\proxies.txt"

with open(proxies_file, "r", encoding="utf-8", errors="ignore") as f:
    proxies = [l.strip() for l in f if l.strip() and not l.startswith("#")]

print(f"Testing {len(proxies)} proxies against {url}...")
for px in proxies:
    px_dict = {"http": px, "https": px}
    try:
        r = requests.get(
            url,
            proxies=px_dict,
            impersonate="chrome124",
            timeout=8,
            headers={"Accept-Language": "ru-RU,ru;q=0.9"}
        )
        print(f"Proxy {px} -> Status {r.status_code}, Len {len(r.text)}")
        if r.status_code == 200:
            print("  SUCCESS 200!")
            with open(r"E:\ins\skybase\Avito-Parser3\skybase\scratch\proxy_item_200.html", "w", encoding="utf-8") as out:
                out.write(r.text)
            break
    except Exception as e:
        print(f"Proxy {px} -> Error {e}")
