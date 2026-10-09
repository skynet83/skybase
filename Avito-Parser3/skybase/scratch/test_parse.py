from bs4 import BeautifulSoup

with open(r'E:\ins\skybase\Avito-Parser3\skybase\scratch\search_page.html', 'r', encoding='utf-8', errors='ignore') as f:
    html = f.read()

soup = BeautifulSoup(html, 'html.parser')

cards = soup.select('[data-marker="item"]')
for i, c in enumerate(cards[:5]):
    texts = [t.strip() for t in c.stripped_strings if len(t.strip()) > 3]
    print(f"\n--- Card {i} texts ---")
    for t in texts:
        print("  ", t)
