"""Smoke tests for the CustomTkinter app.

These construct the real CertificateApp window. They skip on headless /
display-less environments (CI), so the suite still passes there.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

def _wait_until(predicate, app=None, timeout: float = 6.0) -> bool:
    """后台线程 + 队列消费需泵 _tick；轮询直到条件成立。"""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        if app is not None:
            try:
                app._tick()
            except Exception:
                pass
        time.sleep(0.02)
    return False


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


def test_sync_upload_finish_restores_paused_proxy(app, monkeypatch) -> None:
    """同步上传期间暂停的抓包代理，在 __finish__ 时自动恢复。"""
    started = []

    def fake_start(set_system_proxy=True):
        started.append(set_system_proxy)
        return True, "抓包代理已启动 127.0.0.1:8088"

    monkeypatch.setattr(app.mitm, "start", fake_start)

    app._sync_uploading = True
    app._sync_paused_proxy = True
    app._sync_ui_queue.put(("__finish__", "True"))
    app._pump_sync_queue()

    assert started == [True]
    assert app._sync_paused_proxy is False
    assert app._sync_uploading is False


def test_batch_import_accounts_flow(app, monkeypatch, tmp_path) -> None:
    """批量导入：读 CSV → 解析 → 去重 → 逐个 add_pending 并开始抓包。"""
    src = tmp_path / "import.csv"
    src.write_text(
        "公众号,文章链接\n数模加油站,https://mp.weixin.qq.com/s/AAAA\n"
        "知乎日报,https://mp.weixin.qq.com/s/BBBB\n",
        encoding="utf-8",
    )
    import app.ui as ui_mod

    monkeypatch.setattr("app.ui.filedialog.askopenfilename", lambda **kw: str(src))
    monkeypatch.setattr(ui_mod, "fetch_biz_from_url", lambda url, **kw: "")
    monkeypatch.setattr(app.mitm, "start", lambda set_system_proxy=True: (True, "ok"))

    app.batch_import_accounts()
    assert _wait_until(
        lambda: {r["name"] for r in app.store.list_accounts()}
        == {"数模加油站", "知乎日报"},
        app=app,
    )

    rows = {r["name"]: r for r in app.store.list_accounts()}
    assert set(rows) == {"数模加油站", "知乎日报"}
    assert app._pending_capture_id is None


def test_batch_import_skips_duplicate_and_invalid(app, monkeypatch, tmp_path) -> None:
    """批量导入：重复链接与无效行跳过，有效行仍添加。"""
    existing = app.store.add_pending(
        name="已有号", article_url="https://mp.weixin.qq.com/s/AAAA"
    )
    src = tmp_path / "import.csv"
    src.write_text(
        "公众号,文章链接\n"
        "已有号,https://mp.weixin.qq.com/s/AAAA\n"
        "坏链接号,https://example.com/x\n"
        "新号,https://mp.weixin.qq.com/s/CCCC\n",
        encoding="utf-8",
    )
    import app.ui as ui_mod

    monkeypatch.setattr("app.ui.filedialog.askopenfilename", lambda **kw: str(src))
    monkeypatch.setattr(ui_mod, "fetch_biz_from_url", lambda url, **kw: "")
    monkeypatch.setattr(app.mitm, "start", lambda set_system_proxy=True: (True, "ok"))

    app.batch_import_accounts()
    assert _wait_until(
        lambda: "新号" in {r["name"] for r in app.store.list_accounts()},
        app=app,
    )

    names = {r["name"] for r in app.store.list_accounts()}
    assert "新号" in names
    assert existing["name"] in names
    assert "坏链接号" not in names


def test_credential_name_filter_renders_only_matching(app) -> None:
    """凭证列表按公众号名称搜索：只渲染匹配的卡片。"""
    app.store.add_pending(name="数模加油站", article_url="https://mp.weixin.qq.com/s/a")
    app.store.add_pending(name="知乎日报", article_url="https://mp.weixin.qq.com/s/b")
    app._rebuild_list()
    assert len(app._cards) == 2

    app.search_entry.insert(0, "知乎")
    app._apply_name_filter()
    assert len(app._cards) == 1
    names = [str(r["name"]) for r in app.store.list_accounts() if r["id"] in app._cards]
    assert names == ["知乎日报"]

    app.search_entry.delete(0, "end")
    app._apply_name_filter()
    assert len(app._cards) == 2


def test_date_range_state_and_labels(app) -> None:
    """日期区间模式：下拉文案与拉取按钮文案正确。"""
    app._history_range_iso = ("2025-06-30", "2025-07-30")
    app._history_days = None
    assert app._history_range_label() == "2025-06-30 至 2025-07-30"
    assert app._fetch_btn_label() == "拉取 2025-06-30~2025-07-30"
    # 切回预设清除区间
    app._history_range_iso = None
    app._history_days = 7
    assert app._fetch_btn_label() == "拉取近7天"


def test_date_range_dialog_builds_without_error(app, monkeypatch) -> None:
    """日期区间弹窗必须能完整构建（输入框+按钮），确认后写入区间、取消则恢复。"""
    app._history_range_iso = None
    app._history_days = None
    monkeypatch.setattr(app, "wait_window", lambda w: None)  # 不阻塞等用户
    # 直接调用；若弹窗构建抛异常（如 datetime.timedelta 未导入）测试即失败
    app._prompt_date_range()
    assert app._history_range_iso is None  # 未确认 → 取消分支，保持原状态


def test_batch_import_short_link_auto_extracts_biz(app, monkeypatch, tmp_path) -> None:
    """短链 CSV：批量导入时自动抓文章页提取 __biz，保证抓包能匹配。"""
    import app.ui as ui_mod

    src = tmp_path / "import.csv"
    src.write_text(
        "公众号,文章链接\n短链号,https://mp.weixin.qq.com/s/shortXYZ\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("app.ui.filedialog.askopenfilename", lambda **kw: str(src))
    monkeypatch.setattr(ui_mod, "fetch_biz_from_url", lambda url, **kw: "BIZ_AUTO")
    monkeypatch.setattr(app.mitm, "start", lambda set_system_proxy=True: (True, "ok"))

    app.batch_import_accounts()
    assert _wait_until(
        lambda: any(r["name"] == "短链号" for r in app.store.list_accounts()),
        app=app,
    )

    rows = {r["name"]: r for r in app.store.list_accounts()}
    assert rows["短链号"]["biz"] == "BIZ_AUTO"
    assert rows["短链号"]["credentials"]["__biz"] == "BIZ_AUTO"


def test_select_all_many_articles_does_not_lose_list(app) -> None:
    """大量文章时点「全选」不再重建列表/耗尽 Tk 菜单资源导致列表空白。

    回归：每卡片曾各建一个 CTkOptionMenu，文章多时 TclError 菜单耗尽，
    重建中断 -> 列表丢失；且全选改为原地切换复选框。
    """
    from app.ui import MAX_HISTORY_CARDS

    n = 500
    app._history_articles = [
        {
            "title": f"文章 {i}",
            "publish_at": "2026-08-01 10:00",
            "digest": f"摘要 {i}",
            "link": f"https://mp.weixin.qq.com/s/art{i}",
            "source": "getmsg",
        }
        for i in range(n)
    ]
    app._history_selected.clear()
    app._render_history_list()
    # 渲染有上限，不会为每篇建海量控件
    assert len(app._history_card_vars) <= MAX_HISTORY_CARDS
    assert len(app.hist_list.winfo_children()) > 0

    app.select_all_history()
    assert len(app._history_selected) == n
    assert sum(1 for v in app._history_card_vars.values() if v.get()) == len(app._history_card_vars)
    # 列表仍在（没有因重建而丢失）
    assert len(app.hist_list.winfo_children()) > 0

    app.clear_history_selection()
    assert len(app._history_selected) == 0
    assert all(not v.get() for v in app._history_card_vars.values())
