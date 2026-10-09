import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('D:/ins/skybase/Avito-Parser3/skybase/avito_bot/bot.log', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()
for l in lines[-25:]:
    print(l.strip())
