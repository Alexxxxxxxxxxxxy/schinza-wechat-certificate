# -*- mode: python ; coding: utf-8 -*-
# macOS PyInstaller spec — produces a double-clickable dist/Schinza.app
import os
import sys
import sysconfig

from PyInstaller.utils.hooks import collect_all

datas = [
    ("mitmproxy-ca.pem", "."),
    ("mitmproxy-ca-cert.p12", "."),
    ("mitmproxy-ca.p12", "."),
    ("mitmproxy-ca-cert.cer", "."),
    ("app/mitm_addon.py", "app"),
    ("assets/logo.png", "assets"),
    ("assets/logo-128.png", "assets"),
    ("assets/logo-256.png", "assets"),
    ("assets/schinza.icns", "assets"),
]
binaries = []

# Non-standard python installs (e.g. managed toolchains) need libpython bundled manually
_lib_name = sysconfig.get_config_var("LDLIBRARY") or "libpython3.13.dylib"
_candidates = [
    os.path.join(sysconfig.get_config_var("LIBDIR") or "", _lib_name),
    os.path.join(sys.base_prefix, "lib", _lib_name),
    os.path.join(sys.base_prefix, "lib64", _lib_name),
    os.path.join(sys.base_prefix, "Python.framework", "Versions", "Current", "lib", _lib_name),
]
_lib_python = next((p for p in _candidates if p and os.path.exists(p)), "")
if _lib_python:
    binaries.append((_lib_python, "."))
    print(f"[spec] bundling libpython: {_lib_python}")
hiddenimports = [
    "ssl",
    "_ssl",
    "pyperclip",
    "requests",
    "app.mitm_addon",
    "app.mitm_capture",
    "app.ca_setup",
    "app.history_client",
    "app.history_export",
    "app.article_reader",
    "app.sightings",
    "app.history_ranges",
    "app.history_account_select",
    "app.capture_target",
    "app.updater",
    "app.sync_server",
    "app.batch_import",
    "app.clipboard_watch",
    "app.credentials",
    "app.store",
    "app.errors",
    "bs4",
    "lxml",
    "docx",
    "PIL._tkinter_finder",
]
for pkg in ("customtkinter", "mitmproxy", "cryptography", "aioquic"):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
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
    [],
    exclude_binaries=True,
    name="Schinza",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["assets/schinza.icns"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Schinza",
)

app = BUNDLE(
    coll,
    name="Schinza.app",
    icon="assets/schinza.icns",
    bundle_identifier="com.schinza.desktop",
    info_plist={
        "CFBundleName": "Schinza",
        "CFBundleDisplayName": "Schinza 凭证助手",
        "CFBundleShortVersionString": "1.9.10",
        "CFBundleVersion": "1.9.10",
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "11.0",
        "NSPrincipalClass": "NSApplication",
    },
)
