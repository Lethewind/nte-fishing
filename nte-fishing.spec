# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


asset_dir = Path('assets')
asset_data = [(str(path), 'assets') for path in asset_dir.glob('click_bank_*.png')]
asset_data += [
    ('assets/marker_template.png', 'assets'),
    ('assets/hook.png', 'assets'),
]

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=asset_data,
    hiddenimports=[
        'pywintypes',
        'win32api',
        'win32con',
        'win32gui',
        'win32process',
        'win32ui',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', '_tkinter'],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='nte-fishing',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,   # 无控制台窗口（托盘应用）
    uac_admin=True,  # 请求管理员权限（WH_KEYBOARD_LL 钩子 + PostMessage 需要）
    icon='assets/icon.ico',
)
