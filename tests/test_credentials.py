from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.credentials import credentials_enough, try_parse_credentials


def test_parse_url():
    url = (
        "https://mp.weixin.qq.com/s?__biz=Mzg3NTg3ODA5MA==&uin=123&key=abcdef"
        "&pass_ticket=pt%2Fxx&appmsg_token=tok"
    )
    cred = try_parse_credentials(url)
    assert cred is not None
    assert credentials_enough(cred)
    assert cred["__biz"] == "Mzg3NTg3ODA5MA=="
    assert cred["uin"] == "123"
    assert cred["key"] == "abcdef"


def test_parse_json():
    raw = '{"__biz":"B","uin":"1","key":"k","pass_ticket":"p"}'
    cred = try_parse_credentials(raw)
    assert cred is not None
    assert cred["__biz"] == "B"


def test_reject_incomplete():
    assert try_parse_credentials("https://mp.weixin.qq.com/s?__biz=X") is None
