from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.history_client import parse_general_msg_list, parse_getmsg_response  # noqa: E402


def test_parse_general_msg_list():
    now = int(time.time())
    raw = {
        "list": [
            {
                "comm_msg_info": {"datetime": now},
                "app_msg_ext_info": {
                    "title": "主文",
                    "content_url": "https://mp.weixin.qq.com/s/abc",
                    "digest": "d",
                    "multi_app_msg_item_list": [
                        {
                            "title": "副文",
                            "content_url": "https://mp.weixin.qq.com/s/def",
                        }
                    ],
                },
            }
        ]
    }
    rows = parse_general_msg_list(raw)
    assert len(rows) == 2
    assert rows[0]["title"] == "主文"
    assert rows[1]["title"] == "副文"


def test_parse_getmsg_ok_string_list():
    now = int(time.time())
    gml = json.dumps(
        {
            "list": [
                {
                    "comm_msg_info": {"datetime": now},
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
