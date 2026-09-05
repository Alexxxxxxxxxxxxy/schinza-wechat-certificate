import json
import unittest
from unittest.mock import patch

from app.history_client import (
    fetch_history_days,
    merge_resumed_articles,
    resolve_history_start_offset,
)
from app.history_export import articles_for_list_export, render_export


def _page(offset: int, count: int = 8, *, more: bool = True) -> dict:
    return {
        "ok": True,
        "articles": [
            {
                "title": f"p{offset}",
                "link": f"https://mp.weixin.qq.com/s/{offset}",
                "publish_ts": 1_700_000_000 - offset,
                "mid": str(offset),
                "idx": "1",
                "sn": "s",
            }
        ],
        "can_continue": more,
        "next_offset": offset + count,
        "raw": {"general_msg_list": json.dumps({"list": [{}]})},
    }


class ResolveResumeOffsetTests(unittest.TestCase):
    def test_no_resume_starts_at_zero(self):
        self.assertEqual(
            resolve_history_start_offset(biz="A"),
            0,
        )

    def test_all_history_resumes_same_account(self):
        self.assertEqual(
            resolve_history_start_offset(
                biz="A",
                resume_biz="A",
                resume_offset=800,
                days=None,
            ),
            800,
        )

    def test_other_account_does_not_resume(self):
        self.assertEqual(
            resolve_history_start_offset(
                biz="B",
                resume_biz="A",
                resume_offset=800,
                days=None,
            ),
            0,
        )

    def test_older_date_range_resumes(self):
        self.assertEqual(
            resolve_history_start_offset(
                biz="A",
                resume_biz="A",
                resume_offset=800,
                resume_oldest_ts=1_700_000_000,
                start_ts=1_600_000_000,
                end_ts=1_650_000_000,
            ),
            800,
        )

    def test_newer_date_range_restarts(self):
        self.assertEqual(
            resolve_history_start_offset(
                biz="A",
                resume_biz="A",
                resume_offset=800,
                resume_oldest_ts=1_600_000_000,
                start_ts=1_700_000_000,
                end_ts=1_800_000_000,
            ),
            0,
        )


class FetchResumeTests(unittest.TestCase):
    @patch("app.history_client.fetch_getmsg_page")
    def test_uses_start_offset_and_returns_next(self, mock_fetch):
        seen: list[int] = []

        def fake(cred, offset=0, count=8, **kwargs):
            seen.append(offset)
            return _page(offset, count, more=True)

        mock_fetch.side_effect = fake
        result = fetch_history_days(
            {"__biz": "x", "uin": "1", "key": "k"},
            days=None,
            max_pages=1,
            count=8,
            start_offset=80,
            sleep_s=0,
            cooldown_every=0,
        )
        self.assertEqual(seen, [80])
        self.assertTrue(result.get("hit_page_cap"))
        self.assertEqual(result.get("next_offset"), 88)
        self.assertEqual(result.get("start_offset"), 80)

    def test_merge_keeps_older_pages(self):
        merged = merge_resumed_articles(
            [{"title": "new", "mid": "1", "idx": "1", "sn": "a"}],
            [{"title": "old", "mid": "2", "idx": "1", "sn": "b"}],
        )
        titles = {a["title"] for a in merged}
        self.assertEqual(titles, {"new", "old"})


class ListExportSelectionTests(unittest.TestCase):
    def test_export_only_checked_articles(self):
        articles = [
            {"title": "a", "link": "https://a", "identity": "a"},
            {"title": "b", "link": "https://b", "identity": "b"},
            {"title": "c", "link": "https://c", "identity": "c"},
        ]
        picked = articles_for_list_export(articles, {"b"})
        self.assertEqual([a["title"] for a in picked], ["b"])
        text = render_export(picked, fmt="links")
        self.assertIn("https://b", text)
        self.assertNotIn("https://a", text)
        self.assertNotIn("https://c", text)

    def test_export_empty_when_nothing_checked(self):
        articles = [{"title": "a", "link": "https://a", "identity": "a"}]
        self.assertEqual(articles_for_list_export(articles, set()), [])


if __name__ == "__main__":
    unittest.main()
