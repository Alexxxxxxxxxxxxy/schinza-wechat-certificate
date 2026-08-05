"""Ensure conda/openssl SSL DLLs are collected for frozen builds."""

from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs

hiddenimports = ["ssl", "_ssl"]
binaries = collect_dynamic_libs("ssl")

# Conda layouts keep OpenSSL next to the env, which PyInstaller often misses.
try:
    import sys

    base = Path(sys.base_prefix)
    candidates = [
        base / "Library" / "bin",
        base / "DLLs",
        base / "bin",
    ]
    patterns = (
        "libssl*.dll",
        "libcrypto*.dll",
        "_ssl*.pyd",
        "_ssl*.dll",
        "libssl*.so*",
        "libcrypto*.so*",
    )
    for folder in candidates:
        if not folder.is_dir():
            continue
        for pat in patterns:
            for hit in folder.glob(pat):
                # (src, dest_dir_in_bundle)
                binaries.append((str(hit), "."))
except Exception:
    pass
