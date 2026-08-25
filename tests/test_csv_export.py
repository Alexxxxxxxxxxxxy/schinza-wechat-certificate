import tempfile
import unittest
from pathlib import Path

from app.article_reader import (
    CSV_COLUMNS,
    article_to_csv_row,
    batch_export_articles,
    format_csv_video_columns,
    parse_wechat_article_html,
    resolve_csv_digest,
)


class ResolveDigestTests(unittest.TestCase):
    def test_prefers_history_digest(self):
        self.assertEqual(
            resolve_csv_digest(
                history_digest="列表摘要",
                og_description="页面描述",
                body_text="正文" * 40,
            ),
            "列表摘要",
        )

    def test_falls_back_to_og(self):
        self.assertEqual(
            resolve_csv_digest(
                history_digest="  ",
                og_description="页面描述",
                body_text="正文很多字",
            ),
            "页面描述",
        )

    def test_falls_back_to_body_80(self):
        body = "甲" * 100
        got = resolve_csv_digest(
            history_digest="", og_description="", body_text=body
        )
        self.assertEqual(got, "甲" * 80)


class CsvRowTests(unittest.TestCase):
    def test_columns_and_video_split(self):
        self.assertEqual(
            CSV_COLUMNS,
            (
                "标题", "链接", "发布时间", "作者", "摘要", "正文",
                "视频路径", "视频链接", "阅读量", "在看数", "评论数",
            ),
        )
        paths, urls = format_csv_video_columns(
            [
                {"local_path": r"D:\v\a.mp4", "url": "https://cdn/a.mp4"},
                {"url": "https://v.qq.com/x/page/x.html"},
            ]
        )
        self.assertEqual(paths, r"D:\v\a.mp4")
        self.assertEqual(urls, "https://v.qq.com/x/page/x.html")
        row = article_to_csv_row(
            {
                "title": "t",
                "digest": "d",
                "og_description": "og",
                "body_text": "正文",
                "videos": [
                    {"local_path": "C:/a.mp4", "url": "https://x/a.mp4"},
                    {"url": "https://v.qq.com/x"},
                ],
                "stats": {"read_num": 1, "like_num": 2, "comment_count": 3},
            }
        )
        self.assertEqual(row["摘要"], "d")
        self.assertEqual(row["视频路径"], "C:/a.mp4")
        self.assertEqual(row["视频链接"], "https://v.qq.com/x")
        self.assertNotIn("视频", row)

    def test_parse_sets_og_description(self):
        html = (
            '<html><meta property="og:description" content="OG摘要">'
            '<div id="js_content"><p>正文段落足够长用来当正文</p></div></html>'
        )
        parsed = parse_wechat_article_html(html)
        self.assertEqual(parsed.get("og_description"), "OG摘要")

    def test_parse_reads_meta_description_and_msg_desc(self):
        html = (
            "<html><head>"
            '<meta name="description" content="页面摘要字段">'
            "</head><body>"
            "<script>var msg_desc = htmlDecode(\"脚本里的摘要\");</script>"
            '<div id="js_content"><p>正文段落足够长用来当正文</p></div>'
            "</body></html>"
        )
        parsed = parse_wechat_article_html(html)
        self.assertEqual(parsed.get("og_description"), "页面摘要字段")

    def test_parse_error_page_does_not_dump_chrome(self):
        html = (
            "<html><body>"
            "<h1>请开启JavaScript</h1>"
            "<p>此内容因违规无法查看</p>"
            "<nav>首页 搜索 登录</nav>"
            "</body></html>"
        )
        parsed = parse_wechat_article_html(html)
        self.assertFalse(parsed.get("content_ok"))
        self.assertNotIn("请开启JavaScript", parsed.get("body_text") or "")
        self.assertNotIn("首页 搜索", parsed.get("body_text") or "")
        self.assertEqual((parsed.get("body_text") or "").strip(), "")

    def test_parse_extracts_author_byline(self):
        html = (
            "<html><body>"
            '<a id="js_name">半导体行业观察</a>'
            '<span id="js_author_name">张三</span>'
            '<div id="js_content"><p>正文段落足够长用来当正文</p></div>'
            "</body></html>"
        )
        parsed = parse_wechat_article_html(html)
        self.assertEqual(parsed.get("author"), "张三")

    def test_parse_author_falls_back_to_account_name(self):
        html = (
            "<html><body>"
            '<a id="js_name">半导体行业观察</a>'
            '<div id="js_content"><p>正文段落足够长用来当正文</p></div>'
            "</body></html>"
        )
        parsed = parse_wechat_article_html(html)
        self.assertEqual(parsed.get("author"), "半导体行业观察")

    def test_parse_joins_split_disclaimer_chars(self):
        html = (
            "<html><body><div id='js_content'>"
            "<p>正常段落足够长。</p>"
            "<p>文章内</p><p>容系</p><p>其个人观</p>"
            "<p>点，我方转载仅为</p>"
            "<p>分享与讨论，不代表我方赞成或认同。</p>"
            "</div></body></html>"
        )
        parsed = parse_wechat_article_html(html)
        text = parsed.get("body_text") or ""
        self.assertIn("文章内容系其个人观点", text)
        self.assertNotIn("文章内\n容系", text)

    def test_csv_row_uses_description_when_digest_empty(self):
        row = article_to_csv_row(
            {
                "title": "t",
                "digest": "",
                "og_description": "从页面来的摘要",
                "body_text": "",
            }
        )
        self.assertEqual(row["摘要"], "从页面来的摘要")
        self.assertEqual(row["正文"], "")

    def test_junk_platform_digest_falls_back(self):
        self.assertEqual(
            resolve_csv_digest(
                history_digest="微信公众平台",
                og_description="",
                body_text="真正的正文内容写在这里足够长",
            ),
            "真正的正文内容写在这里足够长"[:80],
        )

    def test_digest_skips_star_follow_promo(self):
        body = (
            "公众号记得加星标⭐️，第一时间推送不会错过。\n"
            "与其在单一赛道做“孤勇者”，不如做系统级解决方案的“平台玩家”。\n"
            "刚刚，君正股份在港交所敲钟上市，开盘价每股100港元。"
        )
        got = resolve_csv_digest(
            history_digest="", og_description="", body_text=body
        )
        self.assertTrue(got.startswith("与其在单一赛道"))
        self.assertNotIn("加星标", got)

    def test_user_sample_csv_row_fills_digest(self):
        row = article_to_csv_row(
            {
                "title": "三条芯片赛道在手，君正股份A+H上市",
                "digest": "",
                "og_description": "",
                "author": "",
                "body_text": (
                    "公众号记得加星标⭐️，第一时间推送不会错过。\n"
                    "与其在单一赛道做“孤勇者”，不如做系统级解决方案的“平台玩家”。"
                ),
            }
        )
        self.assertTrue(row["摘要"])
        self.assertNotIn("加星标", row["摘要"])
        self.assertIn("孤勇者", row["摘要"])


class BatchCsvMergeTests(unittest.TestCase):
    def test_one_file_uses_history_digest(self):
        def fake_fetch(url, cred=None):
            return {
                "title": "t",
                "link": url,
                "body_text": "x" * 10,
                "og_description": "",
                "videos": [],
            }

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            csv_path = out / "all.csv"
            result = batch_export_articles(
                [
                    {
                        "title": "t",
                        "link": "https://mp.weixin.qq.com/s/a",
                        "digest": "历史摘要",
                        "author": "张三",
                    }
                ],
                out_dir=out,
                fmt="csv",
                fetch_article=fake_fetch,
                csv_path=csv_path,
                download_videos=False,
                sleep_s=0,
            )
            self.assertTrue(csv_path.is_file())
            self.assertEqual(len(result.get("written") or []), 1)
            text = csv_path.read_text(encoding="utf-8-sig")
            self.assertIn("历史摘要", text)
            self.assertIn("张三", text)
            self.assertIn("视频路径", text)
            self.assertIn("视频链接", text)

    def test_error_page_keeps_history_digest_not_chrome(self):
        def fake_fetch(url, cred=None):
            return parse_wechat_article_html(
                "<html><body><h1>请开启JavaScript</h1><p>环境异常</p></body></html>",
                source_url=url,
            )

        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            csv_path = out / "all.csv"
            batch_export_articles(
                [
                    {
                        "title": "真标题",
                        "link": "https://mp.weixin.qq.com/s/a",
                        "digest": "列表里的摘要",
                    }
                ],
                out_dir=out,
                fmt="csv",
                fetch_article=fake_fetch,
                csv_path=csv_path,
                download_videos=False,
                sleep_s=0,
            )
            text = csv_path.read_text(encoding="utf-8-sig")
            self.assertIn("列表里的摘要", text)
            self.assertIn("真标题", text)
            self.assertNotIn("请开启JavaScript", text)
            self.assertNotIn("环境异常", text)


if __name__ == "__main__":
    unittest.main()
