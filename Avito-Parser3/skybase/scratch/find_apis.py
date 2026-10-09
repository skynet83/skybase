import re

server_ps1 = r"C:\ins\Avito-Parser2\skybase\server.ps1"
with open(server_ps1, "r", encoding="utf-8") as f:
    lines = f.readlines()

routes = []
for i, line in enumerate(lines):
    if "$localPath" in line and ("-eq" in line or "-like" in line or "-match" in line or "StartsWith" in line):
        routes.append((i + 1, line.strip()))

print(f"Total matching lines: {len(routes)}")
for line_no, r in routes:
    print(f"L{line_no:04d}: {r}")
