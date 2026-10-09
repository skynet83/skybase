import os, sys, sqlite3
sys.stdout.reconfigure(encoding='utf-8')

for root, dirs, files in os.walk(r'D:\ins\skybase'):
    if any(k in root for k in ['__pycache__', '.git', 'node_modules', '1', 'test_build', 'app']):
        continue
    for f in files:
        if f.endswith('.db'):
            p = os.path.join(root, f)
            try:
                con = sqlite3.connect(p)
                cur = con.cursor()
                cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
                for t in cur.fetchall():
                    tbl = t[0]
                    try:
                        cur.execute(f"SELECT * FROM [{tbl}] WHERE item_id LIKE ?", ('%8344621788%',))
                        rows = cur.fetchall()
                        if rows:
                            print(f'Found in DB {p}, table {tbl}: {len(rows)} rows')
                            for r in rows:
                                print(' ', r)
                    except Exception:
                        pass
                con.close()
            except Exception:
                pass
