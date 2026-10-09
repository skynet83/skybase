import os
import sys
import time
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_DIR = os.path.join(os.path.dirname(BASE_DIR), "Avito-Parser3", "skybase")
PYD_DIR = os.path.join(BASE_DIR, "test_pyd")

os.makedirs(PYD_DIR, exist_ok=True)

TARGETS = [
    os.path.join(SRC_DIR, "hwid_security.py"),
    os.path.join(SRC_DIR, "devices_db.py"),
    os.path.join(SRC_DIR, "gateway.py"),
    os.path.join(SRC_DIR, "server.py"),
    os.path.join(SRC_DIR, "avito_api_helper.py"),
    os.path.join(SRC_DIR, "avito_sniper.py"),
    os.path.join(SRC_DIR, "app_launcher.py"),
    os.path.join(SRC_DIR, "avito_bot", "filters.py"),
    os.path.join(SRC_DIR, "avito_bot", "proxy_worker.py"),
    os.path.join(SRC_DIR, "avito_bot", "database.py"),
    os.path.join(SRC_DIR, "avito_bot", "parser.py"),
    os.path.join(SRC_DIR, "avito_bot", "bot.py"),
]

print(f"[*] Starting Nuitka compilation of {len(TARGETS)} modules...")
print(f"[*] Python: {sys.executable}")
print(f"[*] Source dir: {SRC_DIR}")
print(f"[*] Output dir: {PYD_DIR}")

failures = []

for idx, src in enumerate(TARGETS, 1):
    base_name = os.path.splitext(os.path.basename(src))[0]
    pyd_name = f"{base_name}.cp311-win_amd64.pyd"
    dst_pyd = os.path.join(PYD_DIR, pyd_name)
    
    print(f"\n[{idx}/{len(TARGETS)}] Compiling {base_name} ({src})...")
    start_t = time.time()
    
    cmd = [
        sys.executable, "-m", "nuitka",
        "--mode=module",
        "--assume-yes-for-downloads",
        "--no-pyi-file",
        f"--output-dir={PYD_DIR}",
        src
    ]
    
    res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)
    elapsed = time.time() - start_t
    
    if res.returncode == 0 and os.path.exists(dst_pyd):
        sz_kb = os.path.getsize(dst_pyd) / 1024
        print(f"  [+] SUCCESS in {elapsed:.1f}s -> {pyd_name} ({sz_kb:.1f} KB)")
    else:
        print(f"  [-] FAILED in {elapsed:.1f}s!")
        print("STDOUT:", res.stdout[-1000:] if res.stdout else "")
        print("STDERR:", res.stderr[-1000:] if res.stderr else "")
        failures.append(base_name)

print("\n" + "="*50)
if failures:
    print(f"[!] Compilation finished with failures: {failures}")
    sys.exit(1)
else:
    print("[SUCCESS] All modules compiled successfully!")
    sys.exit(0)
