import re

server_ps1 = r"C:\ins\Avito-Parser2\skybase\server.ps1"
with open(server_ps1, "r", encoding="utf-8") as f:
    lines = f.readlines()

endpoints = []
for i, line in enumerate(lines):
    # Match $localPath -eq "..." or $localPath -like "..."
    for m in re.finditer(r'\$localPath\s+(-eq|-like|-match)\s+[\'\"]([^\'\"]+)[\'\"]', line):
        endpoints.append((i + 1, m.group(1), m.group(2)))
    # Match $localPath.StartsWith("...")
    for m in re.finditer(r'\$localPath\.StartsWith\([\'\"]([^\'\"]+)[\'\"]\)', line):
        endpoints.append((i + 1, "StartsWith", m.group(1)))

print(f"Total route matches found: {len(endpoints)}")
unique_eps = sorted(set(ep for _, _, ep in endpoints))
print(f"Unique endpoints: {len(unique_eps)}")
for ep in unique_eps:
    print("  ", ep)
