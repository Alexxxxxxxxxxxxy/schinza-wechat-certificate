from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.history_client import (  # noqa: E402
    _dedupe,
    article_identity,
    fetch_history_days,
    parse_general_msg_list,
    parse_getmsg_response,
)


def test_parse_general_msg_list():
    now = int(time.time())
    raw = {
        "list": [
            {
                "comm_msg_info": {"datetime": now, "type": 49, "id": 100},
                "app_msg_ext_info": {
                    "title": "主文",
                    "content_url": "https://mp.weixin.qq.com/s/abc",
                    "digest": "d",
                    "multi_app_msg_item_list": [
                        {
                            "title": "副文",
                            "content_url": "https://mp.weixin.qq.com/s/def",
                        },
                        {
                            "title": "",
                            "content_url": (
                                "https://mp.weixin.qq.com/s?__biz=B&mid=1&idx=3&sn=xyz"
                            ),
                        },
                    ],
                },
            }
        ]
    }
    rows = parse_general_msg_list(raw)
    assert len(rows) == 3
    assert rows[0]["title"] == "主文"
    assert rows[1]["title"] == "副文"
    assert rows[2]["title"] == "(无标题)"


def test_same_day_multi_app_keeps_both():
    """同一天一条多图文：头条 + 第二篇都必须保留。"""
    now = int(time.time())
    raw = {
        "list": [
            {
                "comm_msg_info": {"datetime": now, "type": 49, "id": 200},
                "app_msg_ext_info": {
                    "title": "今天第一篇",
                    "content_url": (
                        "http://mp.weixin.qq.com/s?__biz=MzA5&mid=2652767427"
                        "&idx=1&sn=aaa111&scene=4#wechat_redirect"
                    ),
                    "is_multi": 1,
                    "multi_app_msg_item_list": [
                        {
                            "title": "今天第二篇",
                            "content_url": (
                                "http://mp.weixin.qq.com/s?__biz=MzA5&mid=2652767427"
                                "&idx=2&sn=bbb222&scene=4#wechat_redirect"
                            ),
                        }
                    ],
                },
            }
        ]
    }
    rows = parse_general_msg_list(raw)
    rows = _dedupe(rows)
    titles = [r["title"] for r in rows]
    assert titles == ["今天第一篇", "今天第二篇"]
    assert rows[0]["idx"] == "1"
    assert rows[1]["idx"] == "2"


def test_head_without_link_still_kept_with_multi():
    """头条缺 link 时也不能丢掉标题，且第二篇仍在。"""
    now = int(time.time())
    raw = {
        "list": [
            {
                "comm_msg_info": {"datetime": now, "type": 49, "id": 201},
                "app_msg_ext_info": {
                    "title": "只有标题的头条",
                    "content_url": "",
                    "is_multi": 1,
                    "multi_app_msg_item_list": [
                        {
                            "title": "有链接的第二篇",
                            "content_url": (
                                "https://mp.weixin.qq.com/s?__biz=B&mid=9&idx=2&sn=zz"
                            ),
                        }
                    ],
                },
            }
        ]
    }
    rows = _dedupe(parse_general_msg_list(raw))
    assert len(rows) == 2
    assert rows[0]["title"] == "只有标题的头条"
    assert rows[1]["title"] == "有链接的第二篇"


def test_two_separate_pushes_same_day():
    now = int(time.time())
    raw = {
        "list": [
            {
                "comm_msg_info": {"datetime": now, "type": 49, "id": 301},
                "app_msg_ext_info": {
                    "title": "晚间推送",
                    "content_url": "https://mp.weixin.qq.com/s?__biz=B&mid=20&idx=1&sn=s1",
                    "multi_app_msg_item_list": [],
                },
            },
            {
                "comm_msg_info": {"datetime": now - 3600, "type": 49, "id": 300},
                "app_msg_ext_info": {
                    "title": "早间推送",
                    "content_url": "https://mp.weixin.qq.com/s?__biz=B&mid=19&idx=1&sn=s0",
                    "multi_app_msg_item_list": [],
                },
            },
        ]
    }
    rows = _dedupe(parse_general_msg_list(raw))
    assert {r["title"] for r in rows} == {"晚间推送", "早间推送"}


def test_article_identity_dedupes_tracking_params():
    a = (
        "https://mp.weixin.qq.com/s?__biz=B&mid=111&idx=1&sn=abc"
        "&chksm=xxx&scene=27#rd"
    )
    b = "https://mp.weixin.qq.com/s?__biz=B&mid=111&idx=1&sn=abc"
    c = "https://mp.weixin.qq.com/s?__biz=B&mid=111&idx=2&sn=def"
    assert article_identity(a) == article_identity(b)
    assert article_identity(a) != article_identity(c)


def test_parse_getmsg_ok_string_list():
    now = int(time.time())
    gml = json.dumps(
        {
            "list": [
                {
                    "comm_msg_info": {"datetime": now, "type": 49},
                    "app_msg_ext_info": {
                        "title": "T",
                        "content_url": "https://mp.weixin.qq.com/s/x",
                    },
                }
            ]
        },
        ensure_ascii=False,
    )
    page = parse_getmsg_response(
        {"ret": 0, "errmsg": "ok", "general_msg_list": gml, "can_msg_continue": 0}
    )
    assert page["ok"]
    assert len(page["articles"]) == 1


def _fake_page(articles, can_continue=True, next_offset=None, raw=None):
    return {
        "ok": True,
        "error": "",
        "articles": articles,
        "can_continue": can_continue,
        "next_offset": next_offset,
        "raw": raw or {},
    }


def test_fetch_all_keeps_old_articles(monkeypatch):
    """「全部」模式：不按日期过滤，翻页保留所有文章。"""
    now = int(time.time())
    old = {
        "title": "旧文",
        "link": "https://mp.weixin.qq.com/s/old",
        "publish_ts": now - 90 * 86400,
        "mid": "1", "idx": "1", "sn": "old",
    }
    new = {
        "title": "新文",
        "link": "https://mp.weixin.qq.com/s/new",
        "publish_ts": now - 1 * 86400,
        "mid": "2", "idx": "1", "sn": "new",
    }

    calls = {"n": 0}

    def fake_fetch(cred, offset=0, count=10, session=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_page([new, old], can_continue=True, next_offset=10)
        return _fake_page([], can_continue=False, next_offset=None)

    monkeypatch.setattr("app.history_client.fetch_getmsg_page", fake_fetch)
    cred = {"__biz": "B", "uin": "1", "key": "k"}
    result = fetch_history_days(cred, days=None, max_pages=5, sleep_s=0)
    assert result["ok"]
    assert result["days"] is None
    assert result["cutoff_ts"] is None
    assert {a["title"] for a in result["articles"]} == {"新文", "旧文"}


def test_fetch_days_filters_old_articles(monkeypatch):
    """按天模式：超过天数的文章被过滤。"""
    now = int(time.time())
    old = {
        "title": "旧文",
        "link": "https://mp.weixin.qq.com/s/old",
        "publish_ts": now - 90 * 86400,
        "mid": "1", "idx": "1", "sn": "old",
    }
    new = {
        "title": "新文",
        "link": "https://mp.weixin.qq.com/s/new",
        "publish_ts": now - 1 * 86400,
        "mid": "2", "idx": "1", "sn": "new",
    }

    calls = {"n": 0}

    def fake_fetch(cred, offset=0, count=10, session=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_page([new, old], can_continue=True, next_offset=10)
        return _fake_page([], can_continue=False, next_offset=None)

    monkeypatch.setattr("app.history_client.fetch_getmsg_page", fake_fetch)
    cred = {"__biz": "B", "uin": "1", "key": "k"}
    result = fetch_history_days(cred, days=7, max_pages=5, sleep_s=0)
    assert result["ok"]
    assert {a["title"] for a in result["articles"]} == {"新文"}


def test_fetch_all_cancel_returns_partial(monkeypatch):
    """「全部」拉取可取消：返回已收录的部分结果，不再空转。"""
    now = int(time.time())
    art = {
        "title": "A",
        "link": "https://mp.weixin.qq.com/s/a",
        "publish_ts": now,
        "mid": "1", "idx": "1", "sn": "a",
    }
    calls = {"n": 0}

    def fake_fetch(cred, offset=0, count=10, session=None, **kwargs):
        calls["n"] += 1
        return _fake_page([art], can_continue=True, next_offset=10)

    monkeypatch.setattr("app.history_client.fetch_getmsg_page", fake_fetch)
    cred = {"__biz": "B", "uin": "1", "key": "k"}
    cancels = {"n": 0}

    def should_cancel():
        cancels["n"] += 1
        return cancels["n"] >= 2

    result = fetch_history_days(
        cred, days=None, max_pages=10, sleep_s=0, should_cancel=should_cancel
    )
    assert result.get("cancelled") is True
    assert result["ok"] is False
    assert {a["title"] for a in result["articles"]} == {"A"}
    assert calls["n"] == 1  # 第二页没发出去


def test_fetch_passes_timeout_to_page(monkeypatch):
    seen = {}

    def fake_fetch(cred, offset=0, count=10, session=None, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        return _fake_page([], can_continue=False, next_offset=None)

    monkeypatch.setattr("app.history_client.fetch_getmsg_page", fake_fetch)
    cred = {"__biz": "B", "uin": "1", "key": "k"}
    fetch_history_days(cred, days=7, max_pages=2, sleep_s=0, timeout=17.0)
    assert seen["timeout"] == 17.0


def test_fetch_range_keeps_only_between_dates(monkeypatch):
    """日期区间：只保留 [start_ts, end_ts] 内的文章，翻页在早于 start 时停止。"""
    base = int(time.time())
    day = 86400
    art = lambda t, mid: {
        "title": f"t{mid}", "link": f"https://mp.weixin.qq.com/s/{mid}",
        "publish_ts": base - t * day, "mid": str(mid), "idx": "1", "sn": str(mid),
    }
    calls = {"n": 0}

    def fake_fetch(cred, offset=0, count=10, session=None, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return _fake_page([art(2, 1), art(10, 2), art(20, 3)], can_continue=True, next_offset=10)
        return _fake_page([art(40, 4)], can_continue=False, next_offset=None)

    monkeypatch.setattr("app.history_client.fetch_getmsg_page", fake_fetch)
    cred = {"__biz": "B", "uin": "1", "key": "k"}
    start_ts = base - 15 * day
    end_ts = base - 5 * day
    result = fetch_history_days(
        cred, days=None, max_pages=10, sleep_s=0, start_ts=start_ts, end_ts=end_ts
    )
    titles = sorted(a["title"] for a in result["articles"])
    # title 来自 mid：t1=2 天前（比 end 新，排除）；t2=10 天前（区间内，保留）；
    # t3=20 天前（比 start 老，排除）；t4=40 天前（整页更老，直接停）
    assert titles == ["t2"]
    assert result["start_ts"] == start_ts
    assert result["end_ts"] == end_ts


def test_fetch_range_stops_when_page_older_than_start(monkeypatch):
    """整页都早于 start_ts 时应提前停止翻页。"""
    base = int(time.time())
    day = 86400
    art = lambda t, mid: {
        "title": f"t{mid}", "link": f"https://mp.weixin.qq.com/s/{mid}",
        "publish_ts": base - t * day, "mid": str(mid), "idx": "1", "sn": str(mid),
    }
    calls = {"n": 0}

    def fake_fetch(cred, offset=0, count=10, session=None, **kwargs):
        calls["n"] += 1
        return _fake_page([art(30, 9)], can_continue=True, next_offset=10)

    monkeypatch.setattr("app.history_client.fetch_getmsg_page", fake_fetch)
    cred = {"__biz": "B", "uin": "1", "key": "k"}
    start_ts = base - 10 * day
    end_ts = base - 5 * day
    result = fetch_history_days(
        cred, days=None, max_pages=10, sleep_s=0, start_ts=start_ts, end_ts=end_ts
    )
    assert result["articles"] == []
    assert calls["n"] == 1  # 第一页就全老于 start，直接停


def test_parse_keeps_root_level_multi_without_app_msg_ext_info():
    """app_msg_ext_info 缺失但 multi_app_msg_item_list 在消息根级：不能整条丢弃。"""
    now = int(time.time())
    raw = {
        "list": [
            {
                "comm_msg_info": {"datetime": now, "type": 49, "id": 500},
                "multi_app_msg_item_list": [
                    {
                        "title": "根级副文1",
                        "content_url": (
                            "https://mp.weixin.qq.com/s?__biz=B&mid=5&idx=2&sn=aa"
                        ),
                    },
                    {
                        "title": "根级副文2",
                        "content_url": (
                            "https://mp.weixin.qq.com/s?__biz=B&mid=5&idx=3&sn=bb"
                        ),
                    },
                ],
            }
        ]
    }
    rows = parse_general_msg_list(raw)
    assert len(rows) == 2
    assert {r["title"] for r in rows} == {"根级副文1", "根级副文2"}
    assert all(r["idx"] in ("2", "3") for r in rows)


def test_parse_keeps_head_when_root_multi_also_present():
    """头条 + 根级 multi 同时存在时都保留（不丢非连在一起的文章）。"""
    now = int(time.time())
    raw = {
        "list": [
            {
                "comm_msg_info": {"datetime": now, "type": 49, "id": 501},
                "app_msg_ext_info": {
                    "title": "头条",
                    "content_url": "https://mp.weixin.qq.com/s?__biz=B&mid=6&idx=1&sn=h",
                },
                "multi_app_msg_item_list": [
                    {
                        "title": "根级副文",
                        "content_url": (
                            "https://mp.weixin.qq.com/s?__biz=B&mid=6&idx=2&sn=s"
                        ),
                    }
                ],
            }
        ]
    }
    rows = parse_general_msg_list(raw)
    titles = {r["title"] for r in rows}
    assert titles == {"头条", "根级副文"}


def test_fetch_history_days_applies_jitter_and_cooldown(monkeypatch):
    """防风控：翻页延迟带随机抖动，每 N 页加一次更长冷却。"""
    import app.history_client as hc

    sleeps: list[float] = []
    monkeypatch.setattr(hc.time, "sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(hc.random, "uniform", lambda a, b: 1.0)  # 抖动固定为 1.0
    now = int(time.time())
    art = {
        "title": "A",
        "link": "https://mp.weixin.qq.com/s/a",
        "publish_ts": now,
        "mid": "1", "idx": "1", "sn": "a",
    }

    def fake_fetch(cred, offset=0, count=10, session=None, **kwargs):
        return _fake_page([art], can_continue=True, next_offset=offset + 10)

    monkeypatch.setattr("app.history_client.fetch_getmsg_page", fake_fetch)
    cred = {"__biz": "B", "uin": "1", "key": "k"}
    fetch_history_days(
        cred, days=None, max_pages=6, sleep_s=1.0,
        sleep_jitter=0.6, cooldown_every=5, cooldown_extra_s=4.0,
    )
    # 第 1-4 页各 1.0s；第 5 页 1.0+4.0；第 6 页（最后）不睡
    assert sleeps == [1.0, 1.0, 1.0, 1.0, 5.0]


def test_rate_limit_hint() -> None:
    from app.history_client import _rate_limit_hint

    assert _rate_limit_hint("操作频繁") != ""
    assert _rate_limit_hint("freq control") != ""
    assert _rate_limit_hint("unknownerror") != ""
    assert _rate_limit_hint("网络错误") == ""
