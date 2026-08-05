#!/usr/bin/env python3
"""Schinza 凭证助手 — Windows desktop entrypoint."""

from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path


def _root_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _resource_dir() -> Path:
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return _root_dir()


def _prepare_dll_search(root: Path, res: Path) -> None:
    """Make conda OpenSSL DLLs discoverable before importing _ssl."""
    dirs: list[Path] = []
    for p in (root, res, root / "_internal"):
        if p.is_dir() and p not in dirs:
            dirs.append(p)
    for d in dirs:
        if hasattr(os, "add_dll_directory"):
            try:
                os.add_dll_directory(str(d))
            except (OSError, FileNotFoundError):
                pass
    prefix = ";".join(str(d) for d in dirs)
    os.environ["PATH"] = prefix + ";" + os.environ.get("PATH", "")


def main() -> int:
    root = _root_dir()
    res = _resource_dir()
    _prepare_dll_search(root, res)
    for p in (root, res):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))

    # Force-load SSL early so missing OpenSSL DLLs fail before UI.
    try:
        import ssl  # noqa: F401
        import _ssl  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
                0,
                (
                    "SSL 模块加载失败，无法抓包。\n"
                    "请运行整个 dist\\SchinzaCertificate 目录"
                    "（需含 libssl-3-x64.dll / libcrypto-3-x64.dll），"
                    "不要只拷贝单个 exe。\n\n"
                    f"{exc}"
                ),
                "Schinza 凭证助手",
                0x10,
            )
        except Exception:
            print("SSL load failed:", exc, file=sys.stderr)
        return 2

    from app.ui import run_app

    run_app(root)
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
