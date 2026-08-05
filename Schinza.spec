# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = [('mitmproxy-ca.pem', '.'), ('app\\mitm_addon.py', 'app'), ('assets\\schinza.ico', 'assets'), ('assets\\logo.png', 'assets'), ('assets\\logo-128.png', 'assets'), ('assets\\logo-256.png', 'assets'), ('mitmproxy-ca-cert.p12', '.'), ('mitmproxy-ca.p12', '.'), ('mitmproxy-ca-cert.cer', '.')]
binaries = [('C:\\Users\\MR\\.conda\\envs\\schinza\\Library\\bin\\libssl-3-x64.dll', '.'), ('C:\\Users\\MR\\.conda\\envs\\schinza\\Library\\bin\\libcrypto-3-x64.dll', '.')]
hiddenimports = ['ssl', '_ssl', 'pyperclip', 'requests', 'app.mitm_addon', 'app.history_client', 'app.history_export', 'app.article_reader', 'app.sightings', 'app.history_ranges', 'bs4', 'lxml']
tmp_ret = collect_all('customtkinter')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('mitmproxy')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('cryptography')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('aioquic')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=['hooks'],
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
    [],
    exclude_binaries=True,
    name='Schinza',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['assets\\schinza.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Schinza',
)
