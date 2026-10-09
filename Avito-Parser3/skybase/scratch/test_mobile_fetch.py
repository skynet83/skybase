from curl_cffi import requests

url = "https://m.avito.ru/rostov-na-donu/tovary_dlya_kompyutera/rx_570_8gb_8511297408"
headers = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Dest": "document"
}

try:
    r = requests.get(url, headers=headers, impersonate="safari15_5", timeout=10)
    print("Safari Impersonate Status:", r.status_code, "Len:", len(r.text))
    if r.status_code == 200:
        print("Title:", r.text[:500])
except Exception as e:
    print("Err:", e)
