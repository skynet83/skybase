# -*- mode: python ; coding: utf-8 -*-
import os

base_dir = SPECPATH if 'SPECPATH' in locals() else os.path.dirname(os.path.abspath(__file__))

a = Analysis(
    [os.path.join(base_dir, 'app_launcher.py')],
    pathex=[base_dir],
    binaries=[],
    datas=[
        (os.path.join(base_dir, 'img', 'skybase.ico'), 'img'),
        (os.path.join(base_dir, 'img', 'skybase_icon_256.png'), 'img'),
        (os.path.join(base_dir, 'img', 'skybase_header_logo.png'), 'img'),
    ],
    hiddenimports=['devices_db', 'hwid_security', 'gateway', 'avito_api_helper', 'PIL', 'PIL.Image', 'PIL.ImageTk', 'tools', 'tools.updater'],
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
    name='SkyBase',
    icon=os.path.join(base_dir, 'img', 'skybase.ico'),
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
