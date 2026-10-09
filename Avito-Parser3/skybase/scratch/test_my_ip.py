import urllib.request

for u in ["https://api.ipify.org", "https://icanhazip.com", "https://ifconfig.me/ip"]:
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "curl/7.68.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            print(u, resp.read().decode('utf-8').strip())
            break
    except Exception as e:
        print(u, 'error:', e)
