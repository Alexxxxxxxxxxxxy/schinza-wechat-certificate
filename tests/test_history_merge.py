from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.history_client import merge_articles_with_sightings  # noqa: E402


def test_merge_adds_missing_same_day_article():
    base = [
        {
            "title": "早间",
            "link": "https://mp.weixin.qq.com/s?__biz=B&mid=1&idx=1&sn=a",
            "publish_ts": 1785750000,
            "publish_at": "2026-08-03 15:58",
            "identity": "mid:1|idx:1|sn:a",
        }
    ]
    sightings = [
        {
            "title": "晚间",
            "link": "https://mp.weixin.qq.com/s?__biz=B&mid=2&idx=1&sn=b",
            "publish_ts": 1785751249,
            "publish_at": "2026-08-03 18:00",
            "__biz": "B",
            "source": "mitm",
        }
    ]
    merged = merge_articles_with_sightings(base, sightings, cutoff_ts=1785686400)
    titles = {a["title"] for a in merged}
    assert titles == {"早间", "晚间"}


def test_merge_skips_duplicates_and_old():
    base = [
        {
            "title": "早间",
            "link": "https://mp.weixin.qq.com/s?__biz=B&mid=1&idx=1&sn=a",
            "publish_ts": 1785750000,
            "identity": "mid:1|idx:1|sn:a",
        }
    ]
    sightings = [
        {
            "title": "早间重复",
            "link": "https://mp.weixin.qq.com/s?__biz=B&mid=1&idx=1&sn=a&scene=27",
            "publish_ts": 1785750000,
        },
        {
            "title": "太旧",
            "link": "https://mp.weixin.qq.com/s?__biz=B&mid=9&idx=1&sn=z",
            "publish_ts": 100,
        },
    ]
    merged = merge_articles_with_sightings(base, sightings, cutoff_ts=1785686400)
    assert len(merged) == 1
    assert merged[0]["title"] == "早间"
