import unittest

from app.history_batch_ui import (
    default_selected_ids,
    format_batch_progress,
    format_batch_summary,
    group_status_color_key,
    group_status_label,
)


class BatchUiHelperTests(unittest.TestCase):
    def test_default_selected_only_active_complete(self):
        rows = [
            {
                "id": "a",
                "active": True,
                "credentials": {"__biz": "1", "uin": "1", "key": "k"},
            },
            {"id": "b", "active": False, "credentials": {"__biz": "1", "uin": "1", "key": "k"}},
            {"id": "c", "active": True, "credentials": {}},
        ]
        self.assertEqual(default_selected_ids(rows), ["a"])

    def test_labels_and_colors(self):
        self.assertEqual(group_status_label("completed", 3), "完成")
        self.assertEqual(
            group_status_label("rate_limited", 5), "被风控跳过，已保留 5 篇"
        )
        self.assertEqual(group_status_label("expired", 0), "凭证过期，请续约")
        self.assertEqual(group_status_label("cancelled", 0), "已取消")
        self.assertEqual(group_status_label("failed", 0, "SSL 错误"), "失败：SSL 错误")
        self.assertEqual(group_status_color_key("rate_limited"), "warn")
        self.assertEqual(group_status_color_key("expired"), "muted")
        self.assertEqual(group_status_color_key("failed"), "danger")
        self.assertEqual(group_status_color_key("completed"), "ok")

    def test_progress_and_summary(self):
        self.assertEqual(
            format_batch_progress(3, 12, "校园号", "第 2 页"),
            "3/12 「校园号」第 2 页",
        )
        self.assertEqual(
            format_batch_summary(
                {
                    "completed": 8,
                    "rate_limited": 3,
                    "expired": 1,
                    "failed": 0,
                    "cancelled": 0,
                    "articles": 142,
                }
            ),
            "完成 8 · 风控跳过 3 · 过期 1 · 共 142 篇",
        )


if __name__ == "__main__":
    unittest.main()
