import os
import sys
import time
import subprocess

BASE_DIR = r"D:\ins\skybase\skybotparser"
SRC_DIR = r"D:\ins\skybase\Avito-Parser3\skybase"
PYD_DIR = os.path.join(BASE_DIR, "test_pyd")

targets = [
    os.path.join(SRC_DIR, "avito_api_helper.py"),
    os.path.join(SRC_DIR, "avito_bot", "parser.py"),
    os.path.join(SRC_DIR, "avito_bot", "database.py"),
]

python_exe = r"C:\Users\Admin\AppData\Local\Programs\Python\Python311\python.exe"

for idx, src in enumerate(targets, 1):
    base_name = os.path.splitext(os.path.basename(src))[0]
    pyd_name = f"{base_name}.cp311-win_amd64.pyd"
    dst_pyd = os.path.join(PYD_DIR, pyd_name)
    
    print(f"[{idx}/{len(targets)}] Compiling {base_name}...", flush=True)
    t0 = time.time()
    
    cmd = [
        python_exe, "-m", "nuitka",
        "--mode=module",
        "--assume-yes-for-downloads",
        "--no-pyi-file",
        f"--output-dir={PYD_DIR}",
        src
    ]
    
    res = subprocess.run(cmd, cwd=BASE_DIR, capture_output=True, text=True)
    elapsed = time.time() - t0
    
    if res.returncode == 0 and os.path.exists(dst_pyd):
        sz_kb = os.path.getsize(dst_pyd) / 1024
        print(f"  [+] SUCCESS in {elapsed:.1f}s -> {pyd_name} ({sz_kb:.1f} KB)", flush=True)
    else:
        print(f"  [-] FAILED in {elapsed:.1f}s!", flush=True)
        if res.stdout:
            print("STDOUT:", res.stdout[-600:], flush=True)
        if res.stderr:
            print("STDERR:", res.stderr[-600:], flush=True)
        sys.exit(1)

print(f"[ALL DONE] {len(targets)} modules compiled successfully!", flush=True)
