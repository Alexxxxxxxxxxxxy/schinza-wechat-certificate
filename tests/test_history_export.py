from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.history_export import (  # noqa: E402
    default_export_filename,
    render_export,
)

SAMPLE = [
    {
        "title": "标题A",
        "link": "https://mp.weixin.qq.com/s/a",
        "publish_at": "2026-08-01 12:00",
        "publish_ts": 1,
        "digest": "摘要",
        "author": "",
        "cover": "",
    },
    {
        "title": "标题B",
        "link": "https://mp.weixin.qq.com/s/b",
        "publish_at": "2026-08-02 12:00",
        "publish_ts": 2,
        "digest": "",
        "author": "",
        "cover": "",
    },
]


def test_json_csv_md_links():
    js = render_export(SAMPLE, fmt="json", account_name="测", days=7)
    assert '"title": "标题A"' in js
    csv_text = render_export(SAMPLE, fmt="csv", account_name="测", days=7)
    assert "标题A" in csv_text and "https://mp.weixin.qq.com/s/a" in csv_text
    md = render_export(SAMPLE, fmt="markdown", account_name="测", days=7)
    assert "[标题A](https://mp.weixin.qq.com/s/a)" in md
    links = render_export(SAMPLE, fmt="links")
    assert links.strip().splitlines() == [
        "https://mp.weixin.qq.com/s/a",
        "https://mp.weixin.qq.com/s/b",
    ]
    tl = render_export(SAMPLE, fmt="title_links")
    assert "标题A" in tl and "https://mp.weixin.qq.com/s/a" in tl


def test_render_export_all_days():
    """「全部」模式导出：标题与 JSON 使用全部语义，文件名用 all。"""
    md = render_export(SAMPLE, fmt="markdown", account_name="测", days=None)
    assert "全部历史文章" in md
    js = render_export(SAMPLE, fmt="json", account_name="测", days=None)
    assert '"days": null' in js
    fn = default_export_filename(account_name="测", days=None, ext="md")
    assert "_all_" in fn
