import sqlite3, sys
sys.stdout.reconfigure(encoding='utf-8')

for db in ['D:/ins/skybase/Avito-Parser3/skybase/avito_bot/avito_bot.db', 'D:/ins/skybase/Avito-Parser3/skybase/data/avito.db']:
    try:
        con = sqlite3.connect(db)
        cur = con.cursor()
        print('=== ' + db + ' ===')
        for tbl in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            t = tbl[0]
            cnt = cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f'{t}: {cnt} rows')
            if 'proxy' in t.lower():
                rows = cur.execute(f"SELECT * FROM {t} LIMIT 10").fetchall()
                print('  data:', rows)
        con.close()
    except Exception as e:
        print('err:', e)
