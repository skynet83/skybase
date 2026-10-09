import sqlite3, glob, os, json

print("Searching for 8145502581...")
for db_path in glob.glob("**/*.db", recursive=True):
    try:
        con = sqlite3.connect(db_path)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [r[0] for r in cur.fetchall()]
        for t in tables:
            try:
                cur.execute(f"SELECT * FROM {t}")
                col_names = [d[0] for d in cur.description]
                for row in cur.fetchall():
                    row_str = " ".join(str(x) for x in row)
                    if "8145502581" in row_str or "видеочип" in row_str.lower():
                        print(f"Found in {db_path} table {t}:")
                        for c, v in zip(col_names, row):
                            print(f"  {c}: {v}")
            except Exception:
                pass
        con.close()
    except Exception as e:
        pass
