import re

with open(r'c:\ins\Avito-Parser2\skybase\server.py', 'r', encoding='utf-8') as f:
    text = f.read()

endpoints = sorted(set(re.findall(r'url_path\s*==\s*["\']([^"\']+)["\']', text)))
print("=== All Server Endpoints ===")
for ep in endpoints:
    print(ep)

print("\n=== License checks on endpoints ===")
# Check where is_activated or license check is performed
for line in text.splitlines():
    if any(k in line.lower() for k in ['license', 'hwid', 'activate', 'trial', 'forbidden', '403']):
        if not line.strip().startswith('#'):
            print(line.strip()[:100])
