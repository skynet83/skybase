from bs4 import BeautifulSoup
import json

with open(r'C:\ins\Avito-Parser2\skybase\scratch\search_page.html', 'r', encoding='utf-8') as f:
    html = f.read()

init_idx = html.find('window.__initialData__')
eq_idx = html.find('=', init_idx)
start_pos = -1
for pos in range(eq_idx + 1, min(eq_idx + 50, len(html))):
    if not html[pos].isspace():
        start_pos = pos
        break
decoder = json.JSONDecoder()
decoded_obj, _ = decoder.raw_decode(html[start_pos:])
data = json.loads(decoded_obj) if isinstance(decoded_obj, str) else decoded_obj
all_items = data.get('search', {}).get('allItems', {})

if '7963365695' in all_items:
    print('Found 7963365695 in all_items!')
    val = all_items['7963365695'].get('value', {})
    print('sellerInfo:', json.dumps(val.get('sellerInfo'), ensure_ascii=False, indent=2))
else:
    print('7963365695 NOT in all_items. Searching all_items keys:')
    print(list(all_items.keys())[:10])

soup = BeautifulSoup(html, 'html.parser')
wrapper = soup.select_one('[data-marker*="7963365695"]')
if wrapper:
    print('\nFound wrapper in HTML!')
    for tag in wrapper.find_all(True):
        dm = tag.get('data-marker', '')
        cls = ' '.join(tag.get('class', []))
        txt = tag.get_text(strip=True)
        if any(w in dm.lower() or w in cls.lower() or w in txt.lower() for w in ['rating', 'score', 'отзыв', 'звезд', 'продавец', 'пользователь']):
            print(f'  HTML element: tag={tag.name} data-marker={dm} class={cls} text={txt[:80]}')
