#!/usr/bin/env python3
"""Schinza 凭证助手 — Windows desktop entrypoint."""

from __future__ import annotations

import multiprocessing
import os
import sys
from pathlib import Path


def _root_dir() -> Path:
    if getattr(sys, "frozen", False):
        if sys.platform == "darwin":
            # macOS: 数据放用户目录，避免写在 .app 包内（只读/找不到）
            base = Path.home() / "Library" / "Application Support" / "Schinza"
            try:
                base.mkdir(parents=True, exist_ok=True)
            except Exception:
                base = Path(sys.executable).resolve().parent
            return base
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
    prefix = os.pathsep.join(str(d) for d in dirs)
    os.environ["PATH"] = prefix + os.pathsep + os.environ.get("PATH", "")


def _ensure_stdio(root: Path) -> None:
    """Windowed (--windowed) exes run with sys.stdout/sys.stderr == None.

    Any dependency that calls print() / sys.stderr.write() at import then dies
    with ``'NoneType' object has no attribute 'write'`` (reported on Windows
    VMs). Redirect both to ``data/app.log`` so imports are safe and future
    startup errors are visible.
    """
    log_dir = root / "data"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        log_dir = root
    try:
        fh = open(log_dir / "app.log", "a", encoding="utf-8", buffering=1)
    except Exception:
        fh = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = fh
    if sys.stderr is None:
        sys.stderr = fh


def _show_fatal(title: str, exc: BaseException) -> None:
    import traceback

    body = f"{title}\n\n{exc}\n\n{traceback.format_exc()}"
    if sys.platform == "darwin":
        try:
            import subprocess

            safe = (
                body.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " return ")
            )
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    f'display alert "Schinza 凭证助手" message "{safe}" as critical',
                ],
                check=False,
                timeout=5,
            )
            return
        except Exception:
            pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(  # type: ignore[attr-defined]
            0,
            body,
            "Schinza 凭证助手",
            0x10,
        )
    except Exception:
        print(body, file=sys.stderr)


def main() -> int:
    root = _root_dir()
    res = _resource_dir()
    _ensure_stdio(root)
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

    try:
        from app.ui import run_app
    except Exception as exc:  # noqa: BLE001 - show the real startup error
        _show_fatal("程序启动失败（导入界面模块出错）", exc)
        return 3
    try:
        run_app(root)
    except Exception as exc:  # noqa: BLE001 - keep windowed errors visible
        _show_fatal("程序运行出错", exc)
        return 4
    return 0


if __name__ == "__main__":
    multiprocessing.freeze_support()
    raise SystemExit(main())
