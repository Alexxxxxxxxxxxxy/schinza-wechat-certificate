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


if __name__ == "__main__":
    unittest.main()
