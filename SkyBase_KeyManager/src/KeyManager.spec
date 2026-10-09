# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None
current_dir = SPECPATH if 'SPECPATH' in locals() else os.path.dirname(os.path.abspath(__file__))

a = Analysis(
    [os.path.join(current_dir, 'key_manager.py')],
    pathex=[current_dir],
    binaries=[],
    datas=[
        (os.path.join(current_dir, 'img', 'skybase.ico'), 'img'),
        (os.path.join(current_dir, 'img', 'skybase_icon_256.png'), 'img'),
        (os.path.join(current_dir, 'img', 'skybase_header_logo.png'), 'img'),
    ],
    hiddenimports=['devices_db', 'hwid_security', 'PIL', 'PIL.Image', 'PIL.ImageTk'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='KeyManager',
    icon=os.path.join(current_dir, 'img', 'skybase.ico'),
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
