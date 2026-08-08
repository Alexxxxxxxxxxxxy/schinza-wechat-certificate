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
