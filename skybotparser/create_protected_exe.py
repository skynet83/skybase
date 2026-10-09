import os
import subprocess

SEVEN_ZIP = r"C:\Program Files\7-Zip\7z.exe"
SFX_MODULE = r"C:\Program Files\7-Zip\7z.sfx"
SOURCE_DIR = r"C:\G\ins\skybotparser\app\*"
OUTPUT_EXE = r"C:\G\ins\skybotparser\SkyBotParser_Setup.exe"
TEST_PASSWORD = "skybot_secret_2026"

print(f"[*] Packaging protected SFX executable...")
print(f"[*] Source: {SOURCE_DIR}")
print(f"[*] Target: {OUTPUT_EXE}")
print(f"[*] Password protection: AES-256 (Headers encrypted)")

if os.path.exists(OUTPUT_EXE):
    os.remove(OUTPUT_EXE)

# Команда 7-Zip для сборки самораспаковывающегося EXE с паролем и шифрованием заголовков:
cmd = [
    SEVEN_ZIP,
    "a",
    f"-sfx{SFX_MODULE}",
    f"-p{TEST_PASSWORD}",
    "-mhe=on",       # Защита имен файлов (заголовков)
    "-mx=7",         # Высокая степень сжатия
    OUTPUT_EXE,
    SOURCE_DIR
]

res = subprocess.run(cmd, capture_output=True, text=True)
print(res.stdout)
if res.returncode == 0 and os.path.exists(OUTPUT_EXE):
    size_mb = os.path.getsize(OUTPUT_EXE) / (1024 * 1024)
    print(f"\n[SUCCESS] Создан защищенный исполняемый файл: {OUTPUT_EXE}")
    print(f"Размер: {size_mb:.2f} МБ")
    print(f"Пароль для распаковки: {TEST_PASSWORD}")
else:
    print(f"[ERROR] Ошибка сборки: {res.stderr}")
