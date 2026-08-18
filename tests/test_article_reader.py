from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.article_reader import (  # noqa: E402
    article_to_html_document,
    article_to_markdown,
    parse_wechat_article_html,
)

SAMPLE_HTML = """
<html><head>
<meta property="og:title" content="测试标题">
<meta property="og:description" content="摘要一段">
</head><body>
<h1 class="rich_media_title" id="activity-name">测试标题</h1>
<div id="js_content" class="rich_media_content">
<p>第一段内容。</p>
<p>第二段<strong>加粗</strong>。</p>
</div>
<script>var ct = "1785751249";</script>
</body></html>
"""


def test_parse_wechat_article_html():
    art = parse_wechat_article_html(SAMPLE_HTML, source_url="https://mp.weixin.qq.com/s/abc")
    assert art["title"] == "测试标题"
    assert "第一段内容" in art["body_text"]
    assert "js_content" in art["body_html"] or "第一段" in art["body_html"]
    assert art["link"] == "https://mp.weixin.qq.com/s/abc"


def test_article_to_markdown_and_html():
    art = parse_wechat_article_html(SAMPLE_HTML, source_url="https://mp.weixin.qq.com/s/abc")
    md = article_to_markdown(art)
    assert md.startswith("# 测试标题")
    assert "https://mp.weixin.qq.com/s/abc" in md
    assert "第一段内容" in md
    doc = article_to_html_document(art)
    assert "<!DOCTYPE html>" in doc
    assert "测试标题" in doc
    assert "第一段内容" in doc
