import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

con = sqlite3.connect("avito_bot/avito_bot.db")
cur = con.cursor()
cur.execute("SELECT * FROM seen_items WHERE item_id = 8145502581")
cols = [d[0] for d in cur.description]
for r in cur.fetchall():
    for c, v in zip(cols, r):
        print(f"{c}: {v}")
con.close()
