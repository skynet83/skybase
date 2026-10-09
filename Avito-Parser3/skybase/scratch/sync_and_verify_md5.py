import hashlib, shutil, os

files = [
    'avito_api_helper.py',
    'avito_bot/bot.py',
    'avito_bot/parser.py',
    'server.py',
    'js/app.js'
]

dir1 = 'D:/ins/skybase/Avito-Parser3/skybase'
dir2 = 'D:/ins/skybase/skybotparser/app'

def md5(p):
    with open(p, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

for f in files:
    src = os.path.join(dir1, f)
    dst = os.path.join(dir2, f)
    shutil.copy2(src, dst)
    h1 = md5(src)
    h2 = md5(dst)
    match = (h1 == h2)
    print(f'{f}: match={match} ({h1})')
