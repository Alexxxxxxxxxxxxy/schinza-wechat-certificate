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
    extract_article_sighting,
    is_article_url,
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


def test_extract_article_sighting_short_and_query():
    assert is_article_url("https://mp.weixin.qq.com/s/e2QPPpQdnz48bWM0Uk9NyA")
    s = extract_article_sighting("https://mp.weixin.qq.com/s/e2QPPpQdnz48bWM0Uk9NyA")
    assert s is not None
    assert s["identity"] == "s:e2QPPpQdnz48bWM0Uk9NyA"
    s2 = extract_article_sighting(
        "https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=b#rd"
    )
    assert s2 is not None
    assert s2["identity"] == "mid:2|idx:1|sn:b"
    assert s2["__biz"] == "B"
    assert extract_article_sighting("https://mp.weixin.qq.com/mp/profile_ext?action=home") is None
