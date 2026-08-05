from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.article_reader import (  # noqa: E402
    ARTICLE_EXPORT_FORMATS,
    article_to_html_document,
    article_to_json,
    article_to_markdown,
    article_to_txt,
    normalize_wechat_html,
    parse_wechat_article_html,
    render_article_export,
)

RAW = """
<html><body class="zh_CN">
<div id="js_article">
  <h1 id="activity-name">导出测试标题</h1>
  <div id="js_top_ad_area">广告</div>
  <div id="js_content" style="visibility:hidden;opacity:0">
    <p>第一段。</p>
    <p><img data-src="https://example.com/a.jpg" /></p>
    <p>第二段<strong>加粗</strong>。</p>
  </div>
  <div id="js_pc_qr_code">二维码</div>
  <script>var ct = "1785751249";</script>
</div>
</body></html>
"""


def test_normalize_wechat_html_removes_noise_and_unhides_content():
    doc = normalize_wechat_html(RAW)
    assert "<!DOCTYPE html>" in doc
    assert "导出测试标题" in doc
    assert "js_top_ad_area" not in doc
    assert "js_pc_qr_code" not in doc
    assert "visibility:hidden" not in doc
    assert 'src="https://example.com/a.jpg"' in doc
    assert "第一段" in doc


def test_article_txt_json_and_render_dispatch():
    art = parse_wechat_article_html(RAW, source_url="https://mp.weixin.qq.com/s/abc")
    txt = article_to_txt(art)
    assert "导出测试标题" in txt
    assert "第一段" in txt
    assert "https://mp.weixin.qq.com/s/abc" in txt

    payload = json.loads(article_to_json(art))
    assert payload["title"] == "导出测试标题"
    assert "第一段" in payload["body_text"]
    assert payload["link"].endswith("/s/abc")

    assert "html" in ARTICLE_EXPORT_FORMATS
    assert "markdown" in ARTICLE_EXPORT_FORMATS
    assert "txt" in ARTICLE_EXPORT_FORMATS
    assert "json" in ARTICLE_EXPORT_FORMATS

    html_doc = render_article_export(art, "html")
    assert "<!DOCTYPE html>" in html_doc
    md = render_article_export(art, "markdown")
    assert md.startswith("# ")
    assert render_article_export(art, "txt") == txt
    assert json.loads(render_article_export(art, "json"))["title"] == "导出测试标题"


def test_html_document_prefers_normalized_when_present():
    art = parse_wechat_article_html(RAW, source_url="https://mp.weixin.qq.com/s/abc")
    assert art.get("normalized_html")
    doc = article_to_html_document(art)
    assert "js_top_ad_area" not in doc
    assert "第一段" in doc
    assert article_to_markdown(art).startswith("# 导出测试标题")
