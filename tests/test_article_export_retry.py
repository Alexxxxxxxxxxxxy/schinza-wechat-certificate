"""Batch export resilience: transient network errors are retried, not lost."""

from __future__ import annotations

import requests

from app.article_reader import (
    article_to_csv_row,
    batch_export_articles,
    fetch_article_html,
    write_article_export,
)


class _Session:
    def __init__(self, resp=None, exc=None, fail_first: int = 0) -> None:
        self._resp = resp
        self._exc = exc
        self._fail_first = fail_first
        self.calls = 0

    @property
    def trust_env(self) -> bool:
        return False

    @trust_env.setter
    def trust_env(self, value: bool) -> None:
        pass

    def get(self, *args, **kwargs):
        self.calls += 1
        if self._exc is not None and self.calls <= self._fail_first:
            raise self._exc
        return self._resp


class _Resp:
    def __init__(self, text: str = "<html>ok</html>", status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"{self.status_code} error")


def test_fetch_article_html_retries_timeout_then_succeeds() -> None:
    sess = _Session(resp=_Resp(), exc=requests.Timeout(), fail_first=1)
    html = fetch_article_html(
        "https://mp.weixin.qq.com/s/abc", session=sess, retries=2, retry_delay_s=0
    )
    assert html == "<html>ok</html>"
    assert sess.calls == 2


def test_fetch_article_html_gives_up_after_retries() -> None:
    sess = _Session(exc=requests.ConnectionError(), fail_first=999)
    try:
        fetch_article_html(
            "https://mp.weixin.qq.com/s/abc", session=sess, retries=2, retry_delay_s=0
        )
        raise AssertionError("should have raised")
    except requests.ConnectionError:
        pass
    assert sess.calls == 3


def test_fetch_article_html_retries_http_429() -> None:
    class _Flaky429(_Resp):
        def __init__(self) -> None:
            super().__init__(status_code=429)
            self.n = 0

        def raise_for_status(self) -> None:
            self.n += 1
            if self.n < 3:
                r = requests.Response()
                r.status_code = 429
                raise requests.exceptions.HTTPError("429 Too Many Requests", response=r)

    sess = _Session(resp=_Flaky429())
    fetch_article_html(
        "https://mp.weixin.qq.com/s/abc", session=sess, retries=2, retry_delay_s=0
    )
    assert sess.calls == 3  # 429 -> 429 -> 200


def test_batch_export_retries_transient_failure() -> None:
    calls = {"n": 0}

    def flaky_fetch(url, cred=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise requests.Timeout()
        return {"title": "标题A", "link": url, "content": "正文"}

    rows = [{"title": "标题A", "link": "https://mp.weixin.qq.com/s/a"}]
    result = batch_export_articles(
        rows, out_dir=".tmp_export_test", fmt="markdown", fetch_article=flaky_fetch, sleep_s=0
    )
    assert result["ok"] == 1
    assert result["failed"] == 0


def test_article_to_csv_row_columns() -> None:
    art = {
        "title": "标题T",
        "link": "https://mp.weixin.qq.com/s/x",
        "publish_at": "2026-08-13 19:55",
        "author": "作者A",
        "digest": "摘要D",
        "body_text": "正文内容B",
    }
    row = article_to_csv_row(art)
    assert row["标题"] == "标题T"
    assert row["链接"] == "https://mp.weixin.qq.com/s/x"
    assert row["发布时间"] == "2026-08-13 19:55"
    assert row["作者"] == "作者A"
    assert row["摘要"] == "摘要D"
    assert row["正文"] == "正文内容B"


def test_write_article_export_csv_utf8_bom(tmp_path) -> None:
    out = tmp_path / "a.csv"
    write_article_export(out, {"title": "标题T", "link": "L", "body_text": "正文B"}, "csv")
    raw = out.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")  # utf-8-sig BOM，Excel 中文不乱码
    text = out.read_text(encoding="utf-8-sig")
    assert "标题" in text and "正文" in text and "标题T" in text


def test_batch_export_csv_merges_all_articles_into_one_file(tmp_path) -> None:
    rows = [
        {"title": "文章A", "link": "https://mp.weixin.qq.com/s/a"},
        {"title": "文章B", "link": "https://mp.weixin.qq.com/s/b"},
    ]

    def fake_fetch(url, cred=None):
        title = "文章A" if url.endswith("/s/a") else "文章B"
        return {"title": title, "link": url, "body_text": "正文" + url}

    result = batch_export_articles(
        rows, out_dir=tmp_path, fmt="csv", fetch_article=fake_fetch, sleep_s=0
    )
    assert result["ok"] == 2
    csvs = list(tmp_path.glob("*.csv"))
    assert len(csvs) == 1  # 批量 = 合并成一个 csv
    text = csvs[0].read_text(encoding="utf-8-sig")
    assert "文章A" in text and "文章B" in text
    assert text.count("\n") == 3  # 表头 + 2 行数据


def test_csv_format_key_and_extension() -> None:
    from app.article_reader import (
        ARTICLE_EXPORT_LABELS,
        extension_for_article_format,
        format_key_for_article_label,
    )

    assert "CSV" in ARTICLE_EXPORT_LABELS
    assert format_key_for_article_label("CSV") == "csv"
    assert extension_for_article_format("csv") == "csv"
