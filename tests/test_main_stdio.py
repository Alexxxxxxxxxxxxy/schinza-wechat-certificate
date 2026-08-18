"""main.py stdio guard: windowed exes must not crash on None stdout/stderr."""

from __future__ import annotations

import sys
from pathlib import Path

import main


def test_ensure_stdio_redirects_none_stdout_stderr(monkeypatch, tmp_path: Path) -> None:
    """stdout/stderr == None (PyInstaller --windowed) 时重定向到 data/app.log。"""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    main._ensure_stdio(tmp_path)
    assert sys.stdout is not None
    assert sys.stderr is not None
    # writing must not raise
    sys.stdout.write("out-test\n")
    sys.stderr.write("err-test\n")
    log = tmp_path / "data" / "app.log"
    assert log.is_file()
    content = log.read_text(encoding="utf-8")
    assert "out-test" in content
    assert "err-test" in content


def test_ensure_stdio_keeps_existing_streams(monkeypatch, tmp_path: Path) -> None:
    """正常(控制台)运行时不应替换已有的 stdout/stderr。"""
    old_out, old_err = sys.stdout, sys.stderr
    main._ensure_stdio(tmp_path)
    assert sys.stdout is old_out
    assert sys.stderr is old_err


def test_root_dir_macos_frozen_uses_application_support(monkeypatch, tmp_path: Path) -> None:
    """macOS 打包后数据目录放到 ~/Library/Application Support/Schinza（.app 包内不可写/找不到）。"""
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path), raising=False)
    root = main._root_dir()
    assert root == tmp_path / "Library" / "Application Support" / "Schinza"
    assert root.is_dir()
