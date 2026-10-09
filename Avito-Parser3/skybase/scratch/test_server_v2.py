import sys
import os
import time
import json
import urllib.request
import urllib.error
import subprocess

PORT = 8999
BASE_URL = f"http://127.0.0.1:{PORT}"
SKYBASE_DIR = r"C:\ins\Avito-Parser2\skybase"
SERVER_PY = os.path.join(SKYBASE_DIR, "server.py")

print(f"[*] Starting test server on port {PORT}...")
proc = subprocess.Popen(
    [sys.executable, SERVER_PY, "--port", str(PORT), "--no-browser"],
    cwd=SKYBASE_DIR,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE
)

def cleanup():
    print("[*] Terminating test server...")
    proc.terminate()
    try:
        proc.wait(timeout=3)
    except Exception:
        proc.kill()

# Wait for server to be ready
ready = False
for _ in range(30):
    time.sleep(0.2)
    try:
        req = urllib.request.urlopen(f"{BASE_URL}/api/server/power-state", timeout=1)
        if req.status == 200:
            ready = True
            break
    except Exception:
        pass

if not ready:
    print("[FAIL] Server failed to start!")
    out, err = proc.communicate(timeout=2)
    print("STDOUT:", out.decode("utf-8", errors="replace"))
    print("STDERR:", err.decode("utf-8", errors="replace"))
    cleanup()
    sys.exit(1)

print("[OK] Server is running and responding to HTTP requests!")

results = []

def test_endpoint(name, url, method="GET", data=None, headers=None, expected_status=200, check_fn=None):
    full_url = f"{BASE_URL}{url}"
    req_headers = headers or {}
    body_bytes = None
    if data is not None:
        body_bytes = json.dumps(data).encode("utf-8")
        req_headers["Content-Type"] = "application/json; charset=utf-8"

    req = urllib.request.Request(full_url, data=body_bytes, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            status = resp.status
            body = resp.read()
            passed = (status == expected_status)
            detail = ""
            if passed and check_fn:
                try:
                    passed, detail = check_fn(resp, body)
                except Exception as ex:
                    passed = False
                    detail = f"check_fn error: {ex}"
            results.append((name, passed, f"Status: {status} {detail}"))
    except urllib.error.HTTPError as e:
        passed = (e.code == expected_status)
        body = e.read()
        detail = f"HTTPError {e.code}"
        if passed and check_fn:
            try:
                passed, detail = check_fn(e, body)
            except Exception as ex:
                passed = False
                detail = f"check_fn error: {ex}"
        results.append((name, passed, detail))
    except Exception as e:
        results.append((name, False, f"Exception: {e}"))

# 1. Static Files
def check_index(resp, body):
    txt = body.decode("utf-8", errors="replace")
    has_title = "<title>" in txt or "<html" in txt
    return has_title, f"Length: {len(body)}"

test_endpoint("Static: / (index.html)", "/", check_fn=check_index)

def check_js(resp, body):
    ctype = resp.headers.get("Content-Type", "")
    return "javascript" in ctype, f"Content-Type: {ctype}, Len: {len(body)}"

test_endpoint("Static: /js/app.js", "/js/app.js", check_fn=check_js)

def check_manifest(resp, body):
    txt = body.decode("utf-8", errors="replace")
    return "name" in txt or "short_name" in txt, f"Len: {len(body)}"

test_endpoint("Static: /manifest.json", "/manifest.json", check_fn=check_manifest)

# 2. Server API
def check_json_success(resp, body):
    j = json.loads(body.decode("utf-8"))
    return j.get("success") is True, f"Keys: {list(j.keys())}"

test_endpoint("API: /api/server/power-state", "/api/server/power-state", check_fn=check_json_success)
test_endpoint("API: /api/server/network-info", "/api/server/network-info", check_fn=check_json_success)
test_endpoint("API: /api/me", "/api/me?username=skynet83", check_fn=check_json_success)
test_endpoint("API: /api/users", "/api/users", check_fn=check_json_success)

# 3. Chat API
test_endpoint("API: /api/chat/messages", "/api/chat/messages?username=skynet83", check_fn=check_json_success)
test_endpoint("API: /api/chat/send", "/api/chat/send", method="POST", data={
    "sender": "skynet83",
    "recipient": "admin",
    "text": "Unit Test Message from test_server_v2"
}, check_fn=check_json_success)
test_endpoint("API: /api/chat/read", "/api/chat/read", method="POST", data={
    "username": "skynet83"
}, check_fn=check_json_success)

# 4. Avito API
test_endpoint("API: /api/avito/stats", "/api/avito/stats?username=skynet83", check_fn=check_json_success)
test_endpoint("API: /api/avito/searches", "/api/avito/searches?username=skynet83", check_fn=check_json_success)
test_endpoint("API: /api/avito/interval", "/api/avito/interval?username=skynet83", check_fn=check_json_success)
test_endpoint("API: /api/avito/proxies", "/api/avito/proxies", check_fn=check_json_success)

# 5. License API
test_endpoint("API: /api/license/status", "/api/license/status?username=skynet83", check_fn=check_json_success)
test_endpoint("API: /api/license/client_id", "/api/license/client_id", check_fn=check_json_success)

# 6. Sniper API
test_endpoint("API: /api/avito/sniper/status", "/api/avito/sniper/status", check_fn=check_json_success)
test_endpoint("API: /api/avito/sniper/config", "/api/avito/sniper/config", check_fn=check_json_success)

# Cleanup
cleanup()

# Summary
print("\n" + "=" * 65)
print("             SKYBASE SERVER V2 VERIFICATION RESULTS")
print("=" * 65)
all_pass = True
for name, passed, detail in results:
    status_str = "[ PASS ]" if passed else "[ FAIL ]"
    if not passed:
        all_pass = False
    print(f"{status_str} {name:35s} | {detail}")

print("=" * 65)
if all_pass:
    print(f"[*] ALL {len(results)} TESTS PASSED PERFECTLY!")
else:
    print("[!] SOME TESTS FAILED.")
print("=" * 65)

sys.exit(0 if all_pass else 1)
