"""Article video extraction + download, adapted to all export formats."""

from __future__ import annotations

from pathlib import Path

from app.article_reader import (
    article_to_csv_row,
    download_article_videos,
    extract_videos_from_html,
    parse_wechat_article_html,
)

HTML = """<html><body><div id="js_content">
<p>正文</p>
<video controls src="http://mpvideo.qpic.cn/abc123.mp4"></video>
<iframe class="video_iframe" data-src="https://v.qq.com/iframe/preview.html?vid=xyz123&amp;width=640&amp;height=360"></iframe>
<mpvideo src="https://mpvideo.qpic.cn/other.mp4"></mpvideo>
</div></body></html>"""


def test_extract_videos_from_html() -> None:
    videos = extract_videos_from_html(HTML)
    kinds = [v["kind"] for v in videos]
    assert "mp4" in kinds and "qq_video" in kinds
    mp4_urls = [v["url"] for v in videos if v["kind"] == "mp4"]
    assert any("abc123.mp4" in u for u in mp4_urls)
    qq = [v for v in videos if v["kind"] == "qq_video"][0]
    assert qq["vid"] == "xyz123"


def test_extract_videos_empty() -> None:
    assert extract_videos_from_html("<p>no video</p>") == []
    assert extract_videos_from_html("") == []


def test_parse_article_keeps_videos() -> None:
    art = parse_wechat_article_html(HTML, source_url="https://mp.weixin.qq.com/s/x")
    assert art.get("videos")
    assert any(v["kind"] == "mp4" for v in art["videos"])


def test_csv_row_has_video_column() -> None:
    row = article_to_csv_row(
        {
            "title": "T",
            "videos": [{"kind": "mp4", "url": "http://mpvideo.qpic.cn/a.mp4"}],
        }
    )
    assert "视频" in row
    assert "a.mp4" in row["视频"]


class _Resp:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def raise_for_status(self) -> None:
        pass

    def iter_content(self, chunk_size: int = 65536):
        yield self._data


class _Session:
    def __init__(self, data: bytes) -> None:
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


def test_download_videos_mp4(tmp_path: Path, monkeypatch) -> None:
    import app.article_reader as ar

    sess = _Session(b"MP4DATA")
    monkeypatch.setattr(ar.requests, "Session", lambda: sess)
    art = {
        "title": "标题A",
        "videos": [
            {"kind": "mp4", "url": "http://mpvideo.qpic.cn/a.mp4"},
            {"kind": "qq_video", "url": "https://v.qq.com/x/page/x.html"},
        ],
    }
    out = download_article_videos(art, tmp_path)
    dl_dir = tmp_path / "视频"
    files = list(dl_dir.glob("*.mp4"))
    assert len(files) == 1  # 只下载 mp4 直链，v.qq.com 不下载
    assert files[0].read_bytes() == b"MP4DATA"
    mp4 = [v for v in out if v["kind"] == "mp4"][0]
    assert mp4.get("local_path", "").endswith(".mp4")
    qq = [v for v in out if v["kind"] == "qq_video"][0]
    assert "local_path" not in qq


def test_extract_videos_regex_script_embedded() -> None:
    """真实微信文章常把视频 URL 藏在 script 里：正则兜底也要能抓到。"""
    html = (
        "<html><body><div id=js_content>"
        "<script>var videoUrl='https://mpvideo.qpic.cn/abc123.m4v?x=1';</script>"
        "<script>var qq='https://v.qq.com/x/page/xyz123.html';</script>"
        "</div></body></html>"
    )
    videos = extract_videos_from_html(html)
    kinds = [v["kind"] for v in videos]
    assert "mp4" in kinds and "qq_video" in kinds
    mp4s = [v["url"] for v in videos if v["kind"] == "mp4"]
    assert any("mpvideo.qpic.cn" in u for u in mp4s)
    qqs = [v["url"] for v in videos if v["kind"] == "qq_video"]
    assert any("v.qq.com" in u for u in qqs)


def test_download_videos_uses_article_referer(tmp_path, monkeypatch) -> None:
    import app.article_reader as ar

    seen = {}

    class _Rec:
        @property
        def trust_env(self) -> bool:
            return False

        @trust_env.setter
        def trust_env(self, value: bool) -> None:
            pass

        def get(self, url, **kwargs):
            seen["referer"] = kwargs.get("headers", {}).get("Referer")
            return _Resp(b"DATA")

    monkeypatch.setattr(ar.requests, "Session", lambda: _Rec())
    art = {
        "title": "T",
        "link": "https://mp.weixin.qq.com/s/art123",
        "videos": [{"kind": "mp4", "url": "https://mpvideo.qpic.cn/a.mp4"}],
    }
    download_article_videos(art, tmp_path)
    assert seen.get("referer") == "https://mp.weixin.qq.com/s/art123"


def test_extract_videos_finder_stodownload() -> None:
    """服务号/视频号视频：data-url 里的 findermp stodownload 链接要记录进导出。"""
    html = (
        '<div class="videosnap_video_iframe" data-url="https://findermp.video.qq.com/'
        '251/20304/stodownload?encfilekey=abc123&amp;b=1"></div>'
    )
    videos = extract_videos_from_html(html)
    finders = [v for v in videos if v["kind"] == "finder"]
    assert finders
    assert "findermp.video.qq.com" in finders[0]["url"]
    assert "encfilekey=abc123" in finders[0]["url"]


def test_download_videos_skips_finder(tmp_path: Path) -> None:
    """finder 视频链接只记录不下载（直链需专用接口签名）。"""
    art = {
        "title": "T",
        "videos": [
            {"kind": "finder", "url": "https://findermp.video.qq.com/x/stodownload?encfilekey=k"}
        ],
    }
    out = download_article_videos(art, tmp_path)
    assert "local_path" not in out[0]
    dl = tmp_path / "视频"
    assert not dl.exists() or list(dl.iterdir()) == []


def test_extract_js_escaped_mp4_url() -> None:
    """文章里 mp4 URL 的 & 是 \x26amp; 转义：必须解码成完整直链。"""
    html = (
        '<script>var u="http://mpvideo.qpic.cn/abc.f10004.mp4'
        '?dis_k=k1\\x26amp;dis_t=t1\\x26amp;play_scene=10120"</script>'
    )
    videos = extract_videos_from_html(html)
    mp4s = [v for v in videos if v["kind"] == "mp4"]
    assert mp4s
    u = mp4s[0]["url"]
    assert "&dis_t=t1" in u and "&play_scene=10120" in u


def test_extract_mp4_dedupes_highest_quality() -> None:
    """同一视频多个清晰度（f10002/f10104）只保留最高清。"""
    html = (
        "<script>"
        'var a="http://mpvideo.qpic.cn/v.f10002.mp4?dis_k=a\\x26amp;dis_t=1";'
        'var b="http://mpvideo.qpic.cn/v.f10104.mp4?dis_k=b\\x26amp;dis_t=1";'
        "</script>"
    )
    videos = extract_videos_from_html(html)
    mp4s = [v for v in videos if v["kind"] == "mp4"]
    assert len(mp4s) == 1
    assert ".f10104.mp4" in mp4s[0]["url"]


def test_parse_article_extracts_videos_outside_js_content() -> None:
    """主 bug：视频在 #js_content 之外（如 <script>/页面级），parse 也必须抓到。"""
    html = (
        "<html><head><title>x</title></head><body>"
        "<div id=js_content><p>正文</p></div>"
        '<script>var v="http://mpvideo.qpic.cn/out.f10104.mp4?dis_k=k\x26amp;dis_t=t";</script>'
        '<mp-common-videosnap data-url="https://findermp.video.qq.com/1/2/stodownload?'
        'encfilekey=fk1\x26amp;token=t1" data-nickname="频道A"></mp-common-videosnap>'
        "</body></html>"
    )
    art = parse_wechat_article_html(html, source_url="https://mp.weixin.qq.com/s/x")
    vids = art.get("videos") or []
    assert any(v["kind"] == "mp4" and "out.f10104.mp4" in v["url"] for v in vids)
    assert any(v["kind"] == "finder" for v in vids)


def test_extract_finder_card_nickname() -> None:
    """视频号卡片：记录频道昵称，导出时能识别。"""
    html = (
        '<mp-common-videosnap data-url="https://findermp.video.qq.com/1/2/stodownload?'
        'encfilekey=fk1&amp;token=t1" data-nickname="鸭我宣你"></mp-common-videosnap>'
    )
    vids = extract_videos_from_html(html)
    f = [v for v in vids if v["kind"] == "finder"]
    assert f and f[0].get("title") == "鸭我宣你"


def test_extract_finder_dedupes_by_encfilekey() -> None:
    """同一视频号视频在 HTML 有多个 token 变体：按 encfilekey 去重只留 1 个。"""
    html = (
        "<script>"
        'var a="https://findermp.video.qq.com/1/2/stodownload?encfilekey=KEY1&amp;token=AAA";'
        'var b="https://findermp.video.qq.com/1/2/stodownload?encfilekey=KEY1&amp;token=BBB";'
        'var c="https://findermp.video.qq.com/1/2/stodownload?encfilekey=KEY2&amp;token=CCC";'
        "</script>"
    )
    vids = extract_videos_from_html(html)
    f = [v for v in vids if v["kind"] == "finder"]
    assert len(f) == 2


class _FakeRespEncoding:
    def __init__(self, content: bytes, header_enc: str | None, apparent: str = "utf-8"):
        self.content = content
        self._enc = header_enc
        self._apparent = apparent

    @property
    def encoding(self) -> str | None:
        return self._enc

    @property
    def apparent_encoding(self) -> str:
        return self._apparent

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")


def test_detect_response_encoding_prefers_server_charset() -> None:
    from app.article_reader import _detect_response_encoding

    # 服务器声明 UTF-8，探测误判 cp775：必须用 UTF-8
    resp = _FakeRespEncoding("中文".encode("utf-8"), "UTF-8", apparent="cp775")
    assert _detect_response_encoding(resp).lower() == "utf-8"


def test_detect_response_encoding_meta_fallback() -> None:
    from app.article_reader import _detect_response_encoding

    # 无 charset 头 + ISO-8859-1 默认值：读 <meta charset>
    resp = _FakeRespEncoding(
        b"<html><head><meta charset=\"gb2312\"></head></html>",
        "ISO-8859-1",
        apparent="ascii",
    )
    assert _detect_response_encoding(resp).lower() == "gb2312"


def test_looks_mojibake() -> None:
    from app.article_reader import _looks_mojibake

    good = _FakeRespEncoding("正常中文内容".encode("utf-8"), "UTF-8")
    assert not _looks_mojibake(good.text, good)

    # UTF-8 中文被当成 ascii 解码 → 大量 U+FFFD，应判定乱码
    raw = "正常中文内容正常中文内容正常中文内容".encode("utf-8")
    bad = _FakeRespEncoding(raw, "ascii")
    bad_text = raw.decode("ascii", errors="replace")
    assert bad_text.count("\ufffd") > 4
    assert _looks_mojibake(bad_text, bad)
