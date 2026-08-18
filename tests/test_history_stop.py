import inspect
import unittest

from app.history_client import (
    DEFAULT_PAGE_COUNT,
    classify_stopped_reason,
    fetch_history_days,
    is_rate_limit_error,
    build_getmsg_cookies,
    build_getmsg_headers,
)


class ClassifyStopTests(unittest.TestCase):
    def test_rate_limited_unknownerror(self):
        self.assertTrue(is_rate_limit_error("微信风控拒绝（unknownerror）"))
        self.assertEqual(
            classify_stopped_reason("unknownerror"), "rate_limited"
        )

    def test_rate_limited_freq(self):
        self.assertEqual(classify_stopped_reason("操作频繁 freq"), "rate_limited")

    def test_expired(self):
        self.assertEqual(classify_stopped_reason("凭证已失效：过期"), "expired")
        self.assertEqual(classify_stopped_reason("缺少字段: key"), "expired")

    def test_network(self):
        self.assertEqual(
            classify_stopped_reason("Timeout: 连接微信超时"), "network"
        )

    def test_cancelled_and_completed(self):
        self.assertEqual(
            classify_stopped_reason("已取消", cancelled=True), "cancelled"
        )
        self.assertEqual(classify_stopped_reason("", ok=True), "completed")


class FingerprintRequestTests(unittest.TestCase):
    def test_headers_use_captured_ua(self):
        headers = build_getmsg_headers(
            {"user_agent": "Captured-UA"}, biz="MzA="
        )
        self.assertEqual(headers["User-Agent"], "Captured-UA")

    def test_headers_fallback_default_ua(self):
        headers = build_getmsg_headers({}, biz="MzA=")
        self.assertIn("MicroMessenger", headers["User-Agent"])

    def test_cookies_include_optional_tickets(self):
        cookies = build_getmsg_cookies(
            {
                "uin": "123",
                "pass_ticket": "pt",
                "slave_sid": "sid",
                "data_ticket": "dt",
            }
        )
        self.assertEqual(cookies["wxuin"], "123")
        self.assertEqual(cookies["pass_ticket"], "pt")
        self.assertEqual(cookies["slave_sid"], "sid")
        self.assertEqual(cookies["data_ticket"], "dt")


class HistoryDefaultsTests(unittest.TestCase):
    def test_page_count_is_eight(self):
        self.assertEqual(DEFAULT_PAGE_COUNT, 8)

    def test_fetch_history_days_default_pacing(self):
        params = inspect.signature(fetch_history_days).parameters
        self.assertEqual(params["sleep_s"].default, 3.4)
        self.assertEqual(params["sleep_jitter"].default, 0.32)
        self.assertEqual(params["cooldown_every"].default, 4)
        self.assertEqual(params["cooldown_extra_s"].default, 10.0)
        self.assertEqual(params["count"].default, 8)


if __name__ == "__main__":
    unittest.main()
