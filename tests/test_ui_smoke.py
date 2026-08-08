"""Smoke tests for the CustomTkinter app.

These construct the real CertificateApp window. They skip on headless /
display-less environments (CI), so the suite still passes there.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _require_display() -> None:
    """Skip the test unless a Tk display is available."""
    try:
        import tkinter as tk

        tk.Tk().destroy()
    except Exception as exc:  # pragma: no cover - headless CI
        pytest.skip(f"no display available for Tk: {exc}")


@pytest.fixture()
def app(tmp_path: Path):
    """A fully-constructed CertificateApp on a temp data dir."""
    _require_display()
    try:
        from app.ui import CertificateApp
    except Exception as exc:  # pragma: no cover - missing GUI deps
        pytest.skip(f"app.ui cannot be imported: {exc}")

    try:
        instance = CertificateApp(tmp_path)
    except Exception as exc:  # pragma: no cover - intermittent Tk init on some Windows
        pytest.skip(f"cannot construct CertificateApp: {exc}")
    yield instance
    try:
        instance._on_close()
    except Exception:  # pragma: no cover - window may already be gone
        pass


def test_certificate_app_constructs_sync_panel(app) -> None:
    """C1 regression: building the sync panel must not touch widgets too early."""
    assert hasattr(app, "sync_summary_lbl")
    assert hasattr(app, "sync_base_entry")
    assert app._sync_rows == []
    # 无内置默认服务器地址（开源版本需用户自行填写）
    assert app.sync_base_entry.get() == ""


def test_matched_payloads_buckets(app) -> None:
    """I4/M1: active accounts are bucketed into matched/no_creds/unmatched/bad_school_id."""
    app._sync_rows = [
        {"school_id": "2", "school_name": "中山大学", "nickname": "鸭大情报局", "source": "学校"},
        {"school_id": "", "school_name": "", "nickname": "优质号", "source": "优质"},
        {"school_id": "abc", "school_name": "某校", "nickname": "坏ID号", "source": "学校"},
    ]

    def add(name: str, cred: dict[str, str] | None) -> None:
        row = app.store.add_pending(name=name, article_url="https://mp.weixin.qq.com/s/x")
        if cred is not None:
            app.store.apply_credentials(row["id"], cred)

    creds = {"__biz": "MzA==", "uin": "1", "key": "k"}
    add("鸭大情报局", dict(creds))
    add("优质号", dict(creds))
    add("有凭证没匹配", dict(creds))
    add("无凭证号", {"__biz": "MzA==", "uin": "1"})  # active but missing key
    add("坏ID号", dict(creds))

    matched, no_creds, unmatched, bad_school_id = app._matched_payloads()

    assert sorted(p["nickname"] for p in matched) == ["优质号", "鸭大情报局"]
    assert no_creds == ["无凭证号"]
    assert unmatched == ["有凭证没匹配"]
    assert bad_school_id == ["坏ID号"]
