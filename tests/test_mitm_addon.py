from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.mitm_addon import (  # noqa: E402
    _enough,
    _merge_from_cookie,
    _merge_from_url,
    _url_carries_enough,
)


def test_merge_url_and_enough():
    cred: dict[str, str] = {}
    url = (
        "https://mp.weixin.qq.com/s?__biz=Mzg3NTg3ODA5MA==&uin=123&key=abcdef"
        "&pass_ticket=pt"
    )
    assert _merge_from_url(url, cred)
    assert _enough(cred)
    assert _url_carries_enough(url)
    assert cred["__biz"] == "Mzg3NTg3ODA5MA=="


def test_merge_cookie():
    cred: dict[str, str] = {"__biz": "B"}
    assert _merge_from_cookie("uin=9; key=kk; pass_ticket=p", cred)
    assert cred["uin"] == "9"
    assert cred["key"] == "kk"
    assert _enough(cred)


def test_ignore_other_hosts():
    cred: dict[str, str] = {}
    assert not _merge_from_url("https://example.com/?__biz=B&uin=1&key=k", cred)
    assert not cred
