from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.article_reader import batch_export_articles  # noqa: E402


def test_batch_export_writes_files(tmp_path: Path | None = None):
    out = tmp_path if tmp_path is not None else ROOT / "data" / "_test_batch"
    out.mkdir(parents=True, exist_ok=True)
    for p in out.glob("*"):
        if p.is_file():
            p.unlink()

    articles = [
        {"title": "第一篇", "link": "https://mp.weixin.qq.com/s/a1"},
        {"title": "第二篇", "link": "https://mp.weixin.qq.com/s/a2"},
    ]

    def fake_fetch(url: str, cred=None):
        return {
            "title": "标题-" + url[-2:],
            "link": url,
            "body_text": "正文内容",
            "body_html": "<p>正文内容</p>",
            "publish_at": "2026-08-05 10:00",
            "publish_ts": 1785750000,
        }

    result = batch_export_articles(
        articles,
        out_dir=out,
        fmt="txt",
        fetch_article=fake_fetch,
        cred=None,
    )
    assert result["ok"] == 2
    assert result["failed"] == 0
    files = list(out.glob("*.txt"))
    assert len(files) == 2
