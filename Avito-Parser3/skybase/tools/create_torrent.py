"""
Генератор торрент-файла и Magnet-ссылки для раздачи проекта SkyBase (Сайт и Сервер).
Исключает временные файлы, логи, pid-файлы и кэш, обеспечивая стабильную 100% раздачу без сбоев хеша.
"""
import os
import sys
import time
import hashlib
import urllib.parse

def bencode(obj):
    if isinstance(obj, int):
        return f'i{obj}e'.encode('ascii')
    elif isinstance(obj, (bytes, bytearray)):
        return f'{len(obj)}:'.encode('ascii') + obj
    elif isinstance(obj, str):
        b = obj.encode('utf-8')
        return f'{len(b)}:'.encode('ascii') + b
    elif isinstance(obj, list):
        return b'l' + b''.join(bencode(x) for x in obj) + b'e'
    elif isinstance(obj, dict):
        items = []
        for k in sorted(obj.keys(), key=lambda x: x.encode('utf-8') if isinstance(x, str) else x):
            items.append(bencode(k))
            items.append(bencode(obj[k]))
        return b'd' + b''.join(items) + b'e'
    raise ValueError(f'Unsupported type: {type(obj)}')

def create_torrent(root_dir=None, piece_length=2097152):
    if root_dir is None:
        root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"=== [TORRENT] Генерация торрент-файла для '{root_dir}' ===")
    
    EXCLUDE_DIRS = {
        '.git', '.idea', '.vscode', '__pycache__',
        'scratch', 'temp_chrome_profile', 'profile', 'key_manager', 'build', 'dist',
        'skybase', 'backups', 'avito_browser_profile'
    }

    EXCLUDE_EXTS = {
        '.torrent', '.pid', '.log', '.tmp', '.pyc', '.pyo',
        '.db', '.sqlite', '.sqlite3', '.bak'
    }

    EXCLUDE_FILES = {
        'skybase_project_magnet.txt', 'skybase_magnet.txt',
        'screen_modal_test.png', 'screen_test.png',
        'proxies.txt', 'monitor_state.json', 'proxy_status.json',
        'activation_lock.json', 'activation_locks.json', 'activated_devices.json',
        'activation_codes.json', 'activation_history.json', 'wan_config.json',
        'chat_messages.json', 'devices.json', 'ngrok_state.json', 'users.json',
        'sniper_auth.json', 'license.json', 'license_keys.json', 'dispensed_keys.json'
    }

    files_list = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in EXCLUDE_EXTS or f in EXCLUDE_FILES or f.endswith(('-journal', '-wal', '-shm', '.pma', '.lock')):
                continue
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, root_dir)
            files_list.append((rel_path.replace('\\', '/'), full_path))

    files_list.sort(key=lambda x: x[0])
    print(f"[OK] Отобрано файлов: {len(files_list)}")

    t0 = time.time()
    info_files = []
    pieces = []
    current_piece = bytearray()

    for rel_path, full_path in files_list:
        size = os.path.getsize(full_path)
        parts = rel_path.split('/')
        info_files.append({'length': size, 'path': parts})
        
        with open(full_path, 'rb') as fp:
            while True:
                chunk = fp.read(piece_length - len(current_piece))
                if not chunk:
                    break
                current_piece.extend(chunk)
                if len(current_piece) == piece_length:
                    pieces.append(hashlib.sha1(current_piece).digest())
                    current_piece = bytearray()

    if len(current_piece) > 0:
        pieces.append(hashlib.sha1(current_piece).digest())

    pieces_bytes = b''.join(pieces)
    total_size = sum(f['length'] for f in info_files)
    elapsed = time.time() - t0
    print(f"[OK] Хеширование завершено за {elapsed:.2f} сек. Частей: {len(pieces)}, размер: {total_size / 1024 / 1024:.2f} МБ")

    info = {
        'name': 'skybase',
        'piece length': piece_length,
        'pieces': pieces_bytes,
        'files': info_files
    }

    trackers = [
        'udp://tracker.opentrackr.org:1337/announce',
        'udp://open.stealth.si:80/announce',
        'udp://tracker.torrent.eu.org:451/announce',
        'udp://tracker.openbittorrent.com:6969/announce',
        'udp://explodie.org:6969/announce',
        'udp://9.rarbg.to:2710/announce',
        'udp://tracker.coppersurfer.tk:6969/announce',
        'udp://tracker.moeking.me:6969/announce',
        'http://tracker.openbittorrent.com:80/announce'
    ]

    torrent_dict = {
        'announce': trackers[0],
        'announce-list': [[tr] for tr in trackers],
        'comment': 'SkyBase - Радиодетали, База и Сервер',
        'created by': 'SkyBase Antigravity',
        'creation date': int(time.time()),
        'info': info
    }

    encoded_torrent = bencode(torrent_dict)
    encoded_info = bencode(info)
    info_hash = hashlib.sha1(encoded_info).hexdigest()

    # Проверка целостности хешей (Self-verification)
    print("[VERIFY] Запуск контрольной сверки созданных хешей с файлами на диске...")
    ver_piece = bytearray()
    ver_idx = 0
    passed = 0
    failed = 0
    for rel_path, full_path in files_list:
        with open(full_path, 'rb') as fp:
            while True:
                chunk = fp.read(piece_length - len(ver_piece))
                if not chunk:
                    break
                ver_piece.extend(chunk)
                if len(ver_piece) == piece_length:
                    if hashlib.sha1(ver_piece).digest() == pieces[ver_idx]:
                        passed += 1
                    else:
                        failed += 1
                        print(f"[FAIL] Часть {ver_idx} не совпала: {rel_path}")
                    ver_idx += 1
                    ver_piece = bytearray()
    if len(ver_piece) > 0:
        if hashlib.sha1(ver_piece).digest() == pieces[ver_idx]:
            passed += 1
        else:
            failed += 1
            print(f"[FAIL] Часть {ver_idx} не совпала!")
        ver_idx += 1

    pct = (passed / len(pieces)) * 100
    print(f"[VERIFY] Результат верификации: {passed}/{len(pieces)} частей ({pct:.2f}% СОВПАДЕНИЕ)")

    # Сохраняем skybase_project.torrent и skybase.torrent
    t_proj_path = os.path.join(root_dir, 'skybase_project.torrent')
    t_site_path = os.path.join(root_dir, 'skybase.torrent')

    with open(t_proj_path, 'wb') as f:
        f.write(encoded_torrent)
    with open(t_site_path, 'wb') as f:
        f.write(encoded_torrent)

    # Дополнительно копируем в Загрузки и на Рабочий стол для удобства пользователя
    user_home = os.path.expanduser('~')
    downloads_dir = os.path.join(user_home, 'Downloads')
    desktop_dir = os.path.join(user_home, 'Desktop')
    for extra_dir in (downloads_dir, desktop_dir):
        if os.path.exists(extra_dir):
            try:
                dest = os.path.join(extra_dir, 'skybase.torrent')
                with open(dest, 'wb') as f:
                    f.write(encoded_torrent)
                print(f"[OK] Копия сохранена: {dest}")
            except Exception:
                pass

    print(f"[OK] Торрент сохранен: {t_proj_path} ({len(encoded_torrent)} байт)")
    print(f"[OK] Торрент сохранен: {t_site_path} ({len(encoded_torrent)} байт)")

    # Формируем Magnet-ссылку
    tr_params = '&'.join(f'tr={urllib.parse.quote(tr, safe="")}' for tr in trackers)
    magnet_uri = f"magnet:?xt=urn:btih:{info_hash}&dn=skybase&xl={total_size}&{tr_params}"

    m_proj_path = os.path.join(root_dir, 'skybase_project_magnet.txt')
    m_site_path = os.path.join(root_dir, 'skybase_magnet.txt')

    with open(m_proj_path, 'w', encoding='utf-8') as f:
        f.write(magnet_uri + '\n')
    with open(m_site_path, 'w', encoding='utf-8') as f:
        f.write(magnet_uri + '\n')

    print(f"[OK] Magnet-ссылка сохранена в {m_proj_path}")
    print(f"[SUCCESS] Info Hash: {info_hash}")
    return info_hash, magnet_uri, total_size

if __name__ == '__main__':
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    create_torrent(root)
