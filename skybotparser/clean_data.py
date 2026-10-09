import os
import sqlite3

base = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "Avito-Parser3", "skybase"))

# 1. users.json
with open(os.path.join(base, "data", "users.json"), "w", encoding="utf-8") as f:
    f.write("[]\n")
print("[+] users.json => []")

# 2. devices.json
with open(os.path.join(base, "data", "devices.json"), "w", encoding="utf-8") as f:
    f.write("{}\n")
print("[+] devices.json => {}")

# 3. chat_messages.json
with open(os.path.join(base, "data", "chat_messages.json"), "w", encoding="utf-8") as f:
    f.write("[]\n")
print("[+] chat_messages.json => []")

# 4. sqlite database
db_path = os.path.join(base, "avito_bot", "avito_bot.db")
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [t[0] for t in cur.fetchall() if not t[0].startswith("sqlite_")]
    for tbl in tables:
        cur.execute(f"DELETE FROM [{tbl}]")
        print(f"  [+] Cleared {tbl}")
    conn.commit()
    cur.execute("VACUUM")
    conn.close()
    print("[+] avito_bot.db cleared and vacuumed")

# 5. Clean log and pid files
for root, dirs, files in os.walk(base):
    for f in files:
        if f.endswith((".log", ".pid", ".tmp")):
            try:
                os.remove(os.path.join(root, f))
                print(f"  [+] Removed {f}")
            except Exception as e:
                print(f"  [!] Skip {f}: {e}")

print("\n[SUCCESS] All data reset to pristine clean state!")
