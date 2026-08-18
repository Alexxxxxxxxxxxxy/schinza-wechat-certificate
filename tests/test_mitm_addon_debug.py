"""Capture debug log: shows whether WeChat traffic reaches the proxy and if creds are complete."""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.mitm_addon import CredentialCapture  # noqa: E402


class _Headers:
    def __init__(self, cookie: str = "", referer: str = "") -> None:
        self._cookie = cookie
        self._referer = referer

    def get(self, key: str, default: str = "") -> str:
        low = key.lower()
        if low == "cookie":
            return self._cookie
        if low == "referer":
            return self._referer
        return default


class _Req:
    def __init__(self, url: str, cookie: str = "", referer: str = "") -> None:
        self.pretty_url = url
        self._cookie = cookie
        self._referer = referer

    @property
    def headers(self) -> _Headers:
        return _Headers(self._cookie, self._referer)


class _Flow:
    def __init__(self, url: str, cookie: str = "", referer: str = "") -> None:
        self.request = _Req(url, cookie, referer)


def _capture(monkeypatch, tmp_path: Path) -> Path:
    inbox = tmp_path / "capture_inbox.json"
    sights = tmp_path / "article_sightings.json"
    monkeypatch.setenv("SCHINZA_CAPTURE_INBOX", str(inbox))
    monkeypatch.setenv("SCHINZA_SIGHTINGS", str(sights))
    return inbox


def test_debug_log_records_complete_capture(monkeypatch, tmp_path) -> None:
    inbox = _capture(monkeypatch, tmp_path)
    url = "https://mp.weixin.qq.com/s?__biz=B&uin=1&key=k&pass_ticket=pt&appmsg_token=t"
    CredentialCapture().request(_Flow(url))
    assert inbox.is_file()
    log = tmp_path / "capture_debug.log"
    assert log.is_file()
    text = log.read_text(encoding="utf-8")
    assert "凭证已保存" in text
    assert "完整" in text


def test_debug_log_records_incomplete_without_save(monkeypatch, tmp_path) -> None:
    inbox = _capture(monkeypatch, tmp_path)
    url = "https://mp.weixin.qq.com/s?__biz=B"
    CredentialCapture().request(_Flow(url))
    assert not inbox.is_file()
    log = tmp_path / "capture_debug.log"
    assert log.is_file()
    text = log.read_text(encoding="utf-8")
    assert "不完整" in text


def test_addon_resets_stale_creds_when_biz_changes(monkeypatch, tmp_path) -> None:
    """Bulk renew: switching accounts must not mix account A's key into account B."""
    _capture(monkeypatch, tmp_path)
    cap = CredentialCapture()
    # fully capture account A
    cap.request(
        _Flow("https://mp.weixin.qq.com/s?__biz=A&uin=1&key=KA&pass_ticket=PA&appmsg_token=TA")
    )
    assert cap.creds["A"]["key"] == "KA"
    # article-page request for account B carries __biz but no key
    cap.request(_Flow("https://mp.weixin.qq.com/s?__biz=B"))
    assert cap.creds["B"]["__biz"] == "B"
    assert "key" not in cap.creds["B"]
    assert "uin" not in cap.creds["B"]
    # account A's bucket keeps its own key
    assert cap.creds["A"]["key"] == "KA"


def test_multiwindow_interleaved_requests_do_not_mix(monkeypatch, tmp_path) -> None:
    """Multiple windows: A's sub-request (referer) must never land in B's bucket."""
    inbox = _capture(monkeypatch, tmp_path)
    cap = CredentialCapture()
    # window A: article html (biz via URL), then sub-request (biz via Referer)
    cap.request(_Flow("https://mp.weixin.qq.com/s?__biz=A&mid=1&idx=1&sn=a"))
    # window B: article html
    cap.request(_Flow("https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=b"))
    # A's credential sub-request arrives AFTER B's html (interleaved)
    cap.request(
        _Flow(
            "https://mp.weixin.qq.com/mp/getappmsgext?f=json&uin=1&key=KA&pass_ticket=PA&appmsg_token=TA",
            referer="https://mp.weixin.qq.com/s?__biz=A&mid=1&idx=1&sn=a",
        )
    )
    # B's credential sub-request
    cap.request(
        _Flow(
            "https://mp.weixin.qq.com/mp/getappmsgext?f=json&uin=2&key=KB&pass_ticket=PB&appmsg_token=TB",
            referer="https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=b",
        )
    )
    assert cap.creds["A"]["key"] == "KA"
    assert cap.creds["A"]["uin"] == "1"
    assert cap.creds["B"]["key"] == "KB"
    assert cap.creds["B"]["uin"] == "2"
    # both were saved to the JSONL inbox
    lines = [ln for ln in inbox.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2
    import json
    saved = [json.loads(ln) for ln in lines]
    by_biz = {s["__biz"]: s for s in saved}
    assert by_biz["A"]["key"] == "KA"
    assert by_biz["B"]["key"] == "KB"


def test_short_link_article_records_sighting_without_biz(monkeypatch, tmp_path) -> None:
    """短链（/s/xxx 无 __biz）：即使无法归因也必须记录 sighting，否则 getmsg 漏的补不上。"""
    inbox = _capture(monkeypatch, tmp_path)
    cap = CredentialCapture()
    cap.request(_Flow("https://mp.weixin.qq.com/s/shortABC"))
    import json

    sights = tmp_path / "article_sightings.json"
    assert sights.is_file()
    data = json.loads(sights.read_text(encoding="utf-8"))
    rows = data.get("sightings") or []
    assert any(r.get("identity") == "s:shortABC" for r in rows)
