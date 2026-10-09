from curl_cffi.requests import Session
import sys
sys.stdout.reconfigure(encoding='utf-8')

with Session(impersonate="safari15_5", timeout=5) as s:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 16_5 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.5 Mobile/15E148 Safari/604.1"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    resp = s.get("https://m.avito.ru/all?q=rx580", headers=headers)
    lower = resp.text.lower()
    for kw in ["firewall", "qrator", "доступ ограничен", "проверка пользователя"]:
        print(f"'{kw}' in text:", kw in lower)
    import re
    title = re.search(r'<title>(.*?)</title>', resp.text, re.DOTALL)
    if title:
        print("Title:", title.group(1))
    else:
        title2 = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.DOTALL)
        if title2:
            print("Title2:", title2.group(1))
