import re, sys
sys.stdout.reconfigure(encoding='utf-8')

files = [
    'D:/ins/skybase/Avito-Parser3/skybase/avito_api_helper.py',
    'D:/ins/skybase/Avito-Parser3/skybase/avito_sniper.py',
    'D:/ins/skybase/Avito-Parser3/skybase/avito_bot/parser.py',
    'D:/ins/skybase/Avito-Parser3/skybase/avito_bot/bot.py',
    'D:/ins/skybase/Avito-Parser3/skybase/server.py',
    'D:/ins/skybase/Avito-Parser3/skybase/gateway.py'
]

for f in files:
    print('=== ' + f + ' ===')
    with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
        lines = fp.readlines()
    for i, line in enumerate(lines, 1):
        line_str = line.strip()
        lower = line_str.lower()
        if any(kw in lower for kw in ['avito.ru', 'avito.st', 'fetch_ads', 'asyncsession', 'requests.get', 'requests.post', 'aiohttp.clientsession']):
            if any(term in lower for term in ['http', 'get', 'post', 'fetch', 'proxy', 'session', 'url', 'client']):
                print(f'{i}: {line_str[:130]}')
