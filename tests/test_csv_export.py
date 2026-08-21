import unittest
from app.article_reader import (
    CSV_COLUMNS,
    article_to_csv_row,
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


if __name__ == "__main__":
    unittest.main()
