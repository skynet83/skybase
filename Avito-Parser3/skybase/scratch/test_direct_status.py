from curl_cffi.requests import Session

try:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    with Session(impersonate="safari15_5", timeout=5) as s:
        resp = s.get("https://m.avito.ru", headers=headers)
        print("Status code:", resp.status_code)
        print("Headers:", resp.headers)
        print("Body preview:", resp.text[:300])
except Exception as e:
    print("Direct connection error:", e)
