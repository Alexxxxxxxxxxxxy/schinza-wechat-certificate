from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.article_reader import (  # noqa: E402
    ARTICLE_EXPORT_FORMATS,
    article_to_docx,
    parse_wechat_article_html,
    render_article_export,
    write_article_export,
)

SAMPLE = """
<html><body>
<div id="js_article">
  <h1 id="activity-name">Word导出测试</h1>
  <div id="js_content"><p>段落一。</p><p>段落二。</p></div>
</div>
</body></html>
"""


def test_word_in_export_formats():
    assert "word" in ARTICLE_EXPORT_FORMATS
    assert ARTICLE_EXPORT_FORMATS["word"] in ("Word", "Word (.docx)")


def test_article_to_docx_is_zip_container():
    art = parse_wechat_article_html(SAMPLE, source_url="https://mp.weixin.qq.com/s/abc")
    data = article_to_docx(art)
    assert isinstance(data, (bytes, bytearray))
    assert data[:2] == b"PK"


def test_write_article_export_docx(tmp_path: Path | None = None):
    base = tmp_path if tmp_path is not None else Path(__file__).resolve().parents[1] / "data" / "_test_exports"
    base.mkdir(parents=True, exist_ok=True)
    art = parse_wechat_article_html(SAMPLE, source_url="https://mp.weixin.qq.com/s/abc")
    out = base / "word_test.docx"
    if out.exists():
        out.unlink()
    path = write_article_export(out, art, "word")
    assert path.is_file()
    assert path.read_bytes()[:2] == b"PK"
    # text formats still via render
    md = render_article_export(art, "markdown")
    assert md.startswith("# ")
