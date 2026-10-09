import base64
import json
import re
from urllib.parse import urlparse, parse_qs

def decode_price_from_url(url: str):
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    
    pmin = None
    pmax = None
    
    # 1. Direct pmin / pmax
    if "pmin" in qs and qs["pmin"]:
        try:
            pmin = int(qs["pmin"][0])
        except Exception:
            pass
    if "pmax" in qs and qs["pmax"]:
        try:
            pmax = int(qs["pmax"][0])
        except Exception:
            pass

    # 2. Check f param
    if "f" in qs and qs["f"]:
        f_val = qs["f"][0]
        try:
            padded = f_val.replace('-', '+').replace('~', '/')
            padded += '=' * ((4 - len(padded) % 4) % 4)
            raw = base64.b64decode(padded)
            m = re.search(rb'\{[^{}]*(?:from|to)[^{}]*\}', raw)
            if m:
                data = json.loads(m.group(0).decode('utf-8', errors='ignore'))
                if "from" in data and pmin is None:
                    pmin = int(data["from"])
                if "to" in data and pmax is None:
                    pmax = int(data["to"])
        except Exception as e:
            print("Error decoding f:", e)
            
    return pmin, pmax

url1 = "https://www.avito.ru/all/tovary_dlya_kompyutera/komplektuyuschie/videokarty-ASgBAgICAkTGB~pm7gmmZw?context=H4sIAAAAAAAA_wEmANn_YToxOntzOjE6InkiO3M6MTY6ImdYaUtXMExWWkFPeUdZUzgiO338ueZdJgAAAA&f=ASgBAgECAkTGB~pm7gmmZwFFxpoMFnsiZnJvbSI6NTAwLCJ0byI6MjUwMH0&q=rx590&s=104"
url2 = "https://www.avito.ru/rossiya?s=104&q=RX590&pmin=500&pmax=2500"
url3 = "https://www.avito.ru/rossiya?q=RX590&pmax=3000"
url4 = "https://www.avito.ru/rossiya?q=RX590&pmin=1000"

print("url1:", decode_price_from_url(url1))
print("url2:", decode_price_from_url(url2))
print("url3:", decode_price_from_url(url3))
print("url4:", decode_price_from_url(url4))
