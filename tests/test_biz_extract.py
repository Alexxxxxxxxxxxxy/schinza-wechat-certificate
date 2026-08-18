"""Extract __biz from WeChat article HTML (short links have no __biz in URL)."""

from __future__ import annotations

import requests

from app.article_reader import extract_biz_from_html, fetch_biz_from_url


def test_extract_biz_from_og_url() -> None:
    html = (
        '<meta property="og:url" content="https://mp.weixin.qq.com/s?__biz='
        'Mzg3NTg3ODA5MA%3D%3D&amp;mid=1&amp;idx=1&amp;sn=abc" />'
    )
    assert extract_biz_from_html(html) == "Mzg3NTg3ODA5MA=="


def test_extract_biz_from_var_biz_script() -> None:
    html = '<script>var biz = "Mzg3NTg3ODA5MA==";</script>'
    assert extract_biz_from_html(html) == "Mzg3NTg3ODA5MA=="


def test_extract_biz_empty() -> None:
    assert extract_biz_from_html("<html>no biz</html>") == ""
    assert extract_biz_from_html("") == ""


class _Resp:
    def __init__(self, text: str) -> None:
        self.text = text
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"
        self.status_code = 200

    def raise_for_status(self) -> None:
        pass


class _Session:
    def __init__(self, html: str) -> None:
        self._html = html
        self.calls = 0

    @property
    def trust_env(self) -> bool:
        return False

    @trust_env.setter
    def trust_env(self, value: bool) -> None:
        pass

    def get(self, *args, **kwargs):
        self.calls += 1
        return _Resp(self._html)


def test_fetch_biz_from_url_extracts_from_page() -> None:
    html = (
        '<meta property="og:url" content="https://mp.weixin.qq.com/s?__biz='
        'Mzg3NTg3ODA5MA%3D%3D&amp;mid=1&amp;idx=1&amp;sn=abc" />'
    )
    sess = _Session(html)
    biz = fetch_biz_from_url("https://mp.weixin.qq.com/s/short", session=sess)
    assert biz == "Mzg3NTg3ODA5MA=="
    assert sess.calls == 1


def test_fetch_biz_from_url_returns_empty_on_error() -> None:
    class _BadSession:
        @property
        def trust_env(self) -> bool:
            return False

        @trust_env.setter
        def trust_env(self, value: bool) -> None:
            pass

        def get(self, *args, **kwargs):
            raise requests.ConnectionError()

    assert fetch_biz_from_url("https://mp.weixin.qq.com/s/x", session=_BadSession()) == ""
