import urllib.request
import urllib.error
import time

urls = [
    "http://127.0.0.1/",
    "http://127.0.0.1/index.html",
    "http://127.0.0.1/js/app.js",
    "http://127.0.0.1:8080/",
    "http://127.0.0.1:8081/",
    "http://127.0.0.1/api/auth/status",
    "http://127.0.0.1:8081/api/auth/status",
    "http://127.0.0.1/api/avito/items",
    "http://127.0.0.1:8081/api/avito/items",
]

for u in urls:
    t0 = time.perf_counter()
    try:
        req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = resp.read()
            elapsed = round((time.perf_counter() - t0) * 1000)
            print(f"[OK] {u} -> code={resp.status}, size={len(data)} bytes, time={elapsed}ms")
    except urllib.error.HTTPError as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        print(f"[HTTP ERR] {u} -> code={e.code}, time={elapsed}ms")
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        print(f"[FAIL] {u} -> {type(e).__name__}: {e}, time={elapsed}ms")
