import sys
sys.stdout.reconfigure(encoding='utf-8')
from avito_api_helper import fetch_avito_item_details_live, get_db_connection

with get_db_connection() as con:
    cur = con.cursor()
    cur.execute("SELECT item_id, url FROM seen_items WHERE item_id = '8350392677'")
    row = cur.fetchone()

print("Item to test:", dict(row))
res = fetch_avito_item_details_live(row['item_id'], row['url'])
print("Result photos count:", len(res.get('photos', [])))
print("Result desc length:", len(res.get('description', '')))
print("Result desc:", repr(res.get('description', '')[:120]))
