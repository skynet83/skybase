import re

server_ps1 = r"C:\ins\Avito-Parser2\skybase\server.ps1"
with open(server_ps1, "r", encoding="utf-8") as f:
    text = f.read()

# Find occurrences of & $global:pythonCmd ... $pyScript <args>
matches = re.findall(r'(\$pyScript\s+([^\n\r]+))', text)
print(f"Total $pyScript calls: {len(matches)}")
commands = set()
for full, args in matches:
    # clean up quotes and arguments
    sub = args.strip().split()[0].strip('"\'')
    commands.add(sub)

print(f"Unique subcommands called on pyScript ({len(commands)}):")
for cmd in sorted(commands):
    print("  ", cmd)
