from curl_cffi import requests

headers = {
    "User-Agent": "Avito/101.0 (iPhone; iOS 16.5; Scale/3.00)",
    "X-Device-Type": "ios",
    "Accept": "application/json"
}

endpoints = [
    "https://m.avito.ru/api/11/items/8511297408",
    "https://m.avito.ru/api/9/items/8511297408",
    "https://api.avito.ru/core/item/8511297408",
    "https://m.avito.ru/items/8511297408",
    "https://www.avito.ru/web/1/item/8511297408",
    "https://www.avito.ru/items/8511297408"
]

for ep in endpoints:
    try:
        r = requests.get(ep, headers=headers, impersonate="chrome124", timeout=6)
        print(f"{ep} -> {r.status_code}, len: {len(r.text)}, type: {r.headers.get('content-type', '')[:30]}")
        if r.status_code == 200:
            print("  Response start:", r.text[:200])
    except Exception as e:
        print(f"{ep} -> Err {e}")
