import sqlite3

con = sqlite3.connect("avito_bot/avito_bot.db")
cur = con.cursor()
cur.execute("SELECT id, user_id, url, name, is_active FROM tracked_urls")
for row in cur.fetchall():
    print("tracked_url:", row)
con.close()
