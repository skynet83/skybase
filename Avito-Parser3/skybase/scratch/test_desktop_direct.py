from curl_cffi.requests import Session
import sys
sys.stdout.reconfigure(encoding='utf-8')

with Session(impersonate="chrome124", timeout=5) as s:
    resp = s.get("https://www.avito.ru/all?q=rx580")
    print("Desktop status code:", resp.status_code)
    lower = resp.text.lower()
    for kw in ["firewall", "qrator", "доступ ограничен", "проверка пользователя"]:
        print(f"'{kw}' in text:", kw in lower)
    import re
    title2 = re.search(r'<title[^>]*>(.*?)</title>', resp.text, re.DOTALL)
    if title2:
        print("Title2:", title2.group(1))
