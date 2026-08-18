"""Fetch read/like/comment stats via getappmsgext (optional, default off)."""

from __future__ import annotations

import requests

from app.article_reader import (
    article_to_csv_row,
    batch_export_articles,
    fetch_article_stats,
)

LINK = "https://mp.weixin.qq.com/s?__biz=B&mid=1&idx=1&sn=s"
CRED = {"__biz": "B", "uin": "1", "key": "k", "pass_ticket": "pt", "appmsg_token": "at"}


class _Resp:
    def __init__(self, data) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def json(self):
        return self._data


class _Session:
    def __init__(self, data) -> None:
        self._data = data
        self.calls = 0

    @property
    def trust_env(self) -> bool:
        return False

    @trust_env.setter
    def trust_env(self, value: bool) -> None:
        pass

    def get(self, url, **kwargs):
        self.calls += 1
        return _Resp(self._data)


def test_fetch_article_stats_parses(monkeypatch) -> None:
    import app.article_reader as ar

    payload = {
        "appmsgstat": {"read_num": 456, "like_num": 123, "old_like_num": 0, "show_like_num": 1},
        "comment": {"elected_comment_total_count": 7},
    }
    sess = _Session(payload)
    monkeypatch.setattr(ar.requests, "Session", lambda: sess)
    stats = fetch_article_stats(LINK, CRED, session=sess)
    assert stats["read_num"] == 456
    assert stats["like_num"] == 123
    assert stats["comment_count"] == 7
    assert sess.calls == 1


def test_fetch_article_stats_requires_cred() -> None:
    assert fetch_article_stats(LINK, {}) == {}


def test_fetch_article_stats_empty_on_error(monkeypatch) -> None:
    import app.article_reader as ar

    class _Bad:
        @property
        def trust_env(self) -> bool:
            return False

        @trust_env.setter
        def trust_env(self, value: bool) -> None:
            pass

        def get(self, url, **kwargs):
            raise requests.ConnectionError()

    monkeypatch.setattr(ar.requests, "Session", lambda: _Bad())
    assert fetch_article_stats(LINK, CRED) == {}


def test_csv_row_stats_columns() -> None:
    row = article_to_csv_row(
        {"title": "T", "stats": {"read_num": 456, "like_num": 123, "comment_count": 7}}
    )
    assert row["阅读量"] == "456"
    assert row["在看数"] == "123"
    assert row["评论数"] == "7"


def test_batch_fetch_stats_attaches(monkeypatch) -> None:
    import app.article_reader as ar

    monkeypatch.setattr(
        ar, "fetch_article_stats", lambda link, cred=None, **kw: {"like_num": 9, "read_num": 8}
    )

    def fake_fetch(url, cred=None):
        return {"title": "文章A", "link": url, "body_text": "正文"}

    result = batch_export_articles(
        [{"title": "文章A", "link": LINK}],
        out_dir=".tmp_stats_test",
        fmt="markdown",
        fetch_article=fake_fetch,
        sleep_s=0,
        fetch_stats=True,
    )
    assert result["ok"] == 1
