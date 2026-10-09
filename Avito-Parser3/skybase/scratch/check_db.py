import sqlite3
import glob

for db in glob.glob(r'C:\ins\**\*.db', recursive=True):
    if 'profile' in db or 'browsers' in db:
        continue
    try:
        con = sqlite3.connect(db)
        cur = con.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='seen_items'")
        if cur.fetchone():
            cur.execute('SELECT COUNT(*) FROM seen_items')
            cnt = cur.fetchone()[0]
            print(f'{db}: {cnt} seen_items')
            cur.execute('SELECT search_name, title, price, url FROM seen_items WHERE title LIKE ? OR search_name LIKE ?', ('%590%', '%590%'))
            for r in cur.fetchall():
                print('   Item:', r)
            cur.execute('SELECT id, name, url, is_active FROM tracked_urls')
            for t in cur.fetchall():
                print('   Tracked:', t)
    except Exception as e:
        print(db, e)
